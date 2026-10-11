"""Persistent faces/edges owned by the exact assembly instance and normal body."""
from dataclasses import dataclass
import math
import uuid
from .components import ComponentCatalog
from .documents import rejected


@dataclass
class TopologyReference:
    object_id: str
    component_id: str
    body_id: str
    kind: str
    persistent_id: bytes
    native_identity: object


class ComponentTopologyCatalog(ComponentCatalog):
    TOPOLOGY_SCOPE='resolved_assembly_instance_topology_reads_v1'
    MAX_TOPOLOGY=100000

    @staticmethod
    def _topology_state(entry):
        return entry.geometry.setdefault('component_topology',{'refs':{},'index':{},'cursors':{}})

    def _resolve_body(self,entry,row,component_id,body_id,items):
        ref=self._state(entry)['bodies'].get(body_id)
        if ref is None:
            raise rejected('component_body_reference_not_found','Unknown instance body_id in this assembly.')
        if ref.component_id!=component_id:
            raise rejected('object_component_mismatch','Body belongs to another explicitly referenced instance.')
        body=self.adapter.resolve_persistent_id(entry.model,ref.persistent_id,'body')
        if self.adapter.identity(body)!=ref.native_identity:
            raise rejected('persistent_reference_mismatch','Body reference no longer identifies its original native body.')
        found=[item for item in items if item[0].native_identity==ref.native_identity]
        if len(found)!=1:
            raise rejected('object_not_in_current_component','Body is absent from the current instance/configuration.')
        return found[0]

    def _register_topology(self,entry,obj,component_id,body_id,kind):
        pid=self.adapter.persistent_id(entry.model,obj)
        if not pid:
            raise rejected('persistent_reference_unavailable','No instance-context topology reference; no index/name fallback.')
        native=self.adapter.identity(obj)
        resolved=self.adapter.resolve_persistent_id(entry.model,pid,kind)
        if self.adapter.identity(resolved)!=native:
            raise rejected('persistent_reference_mismatch','Topology reference resolved to another native object.')
        state=self._topology_state(entry)
        key=(component_id,body_id,kind,pid)
        ref=state['index'].get(key)
        if ref is not None and ref.native_identity==native and self.adapter.same_persistent_id(entry.model,ref.persistent_id,pid):
            return ref
        if len(state['refs'])>=self.MAX_TOPOLOGY:
            raise rejected('reference_budget_exceeded','Instance topology reference budget exceeded.')
        ref=TopologyReference('cmp_obj_'+uuid.uuid4().hex,component_id,body_id,kind,pid,native)
        state['refs'][ref.object_id]=ref
        state['index'][key]=ref
        return ref

    @staticmethod
    def _summary(summary,kind):
        def scalar(value):return type(value) in (int,float) and math.isfinite(value)
        if kind=='face':
            valid=scalar(summary.get('area_mm2')) and summary['area_mm2']>0.
        else:
            valid=scalar(summary.get('length_mm')) and summary['length_mm']>=0.
            for key in ('start_mm','end_mm'):
                value=summary.get(key)
                valid=valid and isinstance(value,(tuple,list)) and len(value)==3 and all(scalar(x) for x in value)
        if not valid:
            raise rejected('invalid_native_topology_summary','Native topology measurement must have finite local mm/mm2 values.')
        return summary

    def _topology_rows(self,entry,body,component_id,body_id,kind):
        objects=tuple(self.adapter.topology(body,kind))
        if len(objects)>self.MAX_TOPOLOGY:
            raise rejected('topology_budget_exceeded','Native instance topology count exceeds its budget.')
        native_body=self.adapter.identity(body)
        rows=[]
        for obj in objects:
            if self.adapter.identity(self.adapter.owner_body(obj,kind))!=native_body:
                raise rejected('object_body_mismatch','Topology is not owned by the requested native instance body.')
            ref=self._register_topology(entry,obj,component_id,body_id,kind)
            summary=self._summary(self.adapter.geometry_summary(obj,kind),kind)
            rows.append((ref,obj,summary))
        if len({row[0].object_id for row in rows})!=len(rows):
            raise rejected('topology_roster_invalid','Native topology enumeration contains duplicate objects.')
        # Enumeration order is not guaranteed by SolidWorks. Opaque IDs sort a
        # live snapshot for paging; the ordering never identifies an object.
        return tuple(sorted(rows,key=lambda row:row[0].object_id))

    @staticmethod
    def _topology_signature(rows):
        return tuple((row[0].native_identity,row[2]) for row in rows)

    def _topology_context(self,document_id,configuration,expected_observation_revision,component_id,body_id):
        entry,observed,identity=self._context(document_id,configuration,expected_observation_revision)
        components=self._snapshot(entry,configuration,identity)
        component=self._resolve(entry,configuration,identity,component_id,components)
        bodies=self._body_rows(entry,component,component_id)
        body_row=self._resolve_body(entry,component,component_id,body_id,bodies)
        return entry,observed,identity,components,component,bodies,body_row

    def _finish_topology(self,entry,observed,identity,configuration,components,component,component_id,bodies,body,body_id,kind,rows):
        self._confirm(entry,observed,configuration,identity)
        after=self._topology_rows(entry,body,component_id,body_id,kind)
        if self._topology_signature(rows)!=self._topology_signature(after):
            raise rejected('component_topology_changed_during_read','Instance topology membership/summary changed during read.')
        if self._body_signature(bodies)!=self._body_signature(self._body_rows(entry,component,component_id)):
            raise rejected('component_bodies_changed_during_read','Instance body membership/summary changed during topology read.')
        self._finish(entry,observed,configuration,identity,components)

    def _topology_result(self,entry,observed,configuration,component,component_id,body_id):
        return {**self._result(entry,observed,configuration),'topology_scope':self.TOPOLOGY_SCOPE,
                'component':self._item(component,component_id),'body_id':body_id,
                'object_coordinate_frame':'component_model','area_unit':'mm2'}

    @staticmethod
    def _topology_item(row,object_id=None):
        ref=row[0]
        return dict(object_id=object_id or ref.object_id,component_id=ref.component_id,body_id=ref.body_id,kind=ref.kind,**row[2])

    def list_topology(self,document_id,configuration,expected_observation_revision,component_id,body_id,*,kind,limit=100,cursor=''):
        if kind not in ('face','edge'):
            raise rejected('invalid_topology_kind','Only faces/edges have this topology contract.')
        if type(limit) is not int or not 1<=limit<=200:
            raise rejected('invalid_limit','Topology page limit must be between 1 and 200.')
        values=self._topology_context(document_id,configuration,expected_observation_revision,component_id,body_id)
        entry,observed,identity,components,component,bodies,body_row=values
        body=body_row[1]
        rows=self._topology_rows(entry,body,component_id,body_id,kind)
        state=self._topology_state(entry)
        for token,prior in list(state['cursors'].items()):
            if prior[0]!=observed['observation_revision']:
                del state['cursors'][token]
        query=(configuration,component_id,body_id,kind)
        signature=(self._signature(components),self._body_signature(bodies),self._topology_signature(rows))
        offset=0
        if cursor:
            prior=state['cursors'].get(cursor)
            if prior is None or prior[2]!=query:
                raise rejected('invalid_component_topology_cursor','Cursor belongs to another document/instance/body/kind or previous snapshot.')
            if prior[0]!=observed['observation_revision'] or prior[1]!=identity or prior[3]!=signature:
                raise rejected('stale_component_topology_cursor','Complete instance/body/topology snapshot changed between pages.')
            offset=prior[4]
        selected=rows[offset:offset+limit]
        self._finish_topology(entry,observed,identity,configuration,components,component,component_id,bodies,body,body_id,kind,rows)
        next_cursor=None
        if offset+len(selected)<len(rows):
            if len(state['cursors'])>=100:
                raise rejected('cursor_budget_exceeded','Too many retained topology snapshots.')
            cost=len(components)+len(bodies)+len(rows)
            if sum(sum(len(x) for x in prior[3]) for prior in state['cursors'].values())+cost>self.MAX_TOPOLOGY:
                raise rejected('topology_budget_exceeded','Retained instance/body/topology snapshot budget exceeded.')
            next_cursor='cmp_topo_page_'+uuid.uuid4().hex
            state['cursors'][next_cursor]=(observed['observation_revision'],identity,query,signature,offset+len(selected))
        return {**self._topology_result(entry,observed,configuration,component,component_id,body_id),
                'kind':kind,'items':[self._topology_item(row) for row in selected],
                'total_count':len(rows),'next_cursor':next_cursor}

    def get_topology(self,document_id,configuration,expected_observation_revision,component_id,body_id,object_id):
        values=self._topology_context(document_id,configuration,expected_observation_revision,component_id,body_id)
        entry,observed,identity,components,component,bodies,body_row=values
        ref=self._topology_state(entry)['refs'].get(object_id)
        if ref is None:
            raise rejected('component_topology_reference_not_found','Unknown topology ID in this open assembly.')
        if ref.component_id!=component_id:
            raise rejected('object_component_mismatch','Topology belongs to another original native instance.')
        if ref.body_id!=body_id:
            raise rejected('object_body_mismatch','Topology belongs to another original native body reference.')
        obj=self.adapter.resolve_persistent_id(entry.model,ref.persistent_id,ref.kind)
        if self.adapter.identity(obj)!=ref.native_identity:
            raise rejected('persistent_reference_mismatch','Topology reference no longer identifies its original native object.')
        body=body_row[1]
        if self.adapter.identity(self.adapter.owner_body(obj,ref.kind))!=self.adapter.identity(body):
            raise rejected('object_body_mismatch','Resolved topology no longer belongs to this native instance body.')
        rows=self._topology_rows(entry,body,component_id,body_id,ref.kind)
        found=[row for row in rows if row[0].native_identity==ref.native_identity]
        if len(found)!=1:
            raise rejected('object_not_in_current_body','Topology is absent from the current instance body.')
        self._finish_topology(entry,observed,identity,configuration,components,component,component_id,bodies,body,body_id,ref.kind,rows)
        return {**self._topology_result(entry,observed,configuration,component,component_id,body_id),
                'object':self._topology_item(found[0],object_id)}
