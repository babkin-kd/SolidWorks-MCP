"""Original native part anchors + actual child PID/HWND evidence -> I02 oracle.

No geometry/name/ordinal selects ownership. Static I02 uses exact originally
retained PIDs; rename aliases remain the separate I04 reference route.
"""
from dataclasses import dataclass
import re

from verifier_b3_part_geometry import _context
from verifier_b3_native_part_reference import RetainedPartReference,capture_native_part_reference


def require(condition,message):
    if not condition:raise ValueError(message)


@dataclass(frozen=True)
class OriginalPartObject:
    kind:str
    handle:object
    canonical:object
    persistent_id:bytes
    body_canonical:object


class PartReferenceBridge:
    def __init__(self,*,model,model_canonical,configuration_canonical,hwnd,
                 original_objects,adapter,watch,wrap,persistent_variant,ordinal,assert_safe):
        require(type(hwnd) is int and 0<hwnd<2**63 and type(original_objects) is tuple
            and 0<len(original_objects)<=5000
            and all(isinstance(obj,OriginalPartObject) and obj.kind in ('body','face','edge')
                    and type(obj.persistent_id) is bytes and obj.persistent_id for obj in original_objects),
            'Original acknowledged HWND/complete retained native part anchors required.')
        self.model,self.model_canonical,self.configuration_canonical=model,model_canonical,configuration_canonical
        self.hwnd,self.originals,self.adapter,self.watch=hwnd,original_objects,adapter,watch
        self.wrap,self.persistent_variant,self.ordinal,self.assert_safe=wrap,persistent_variant,ordinal,assert_safe

    def _windows(self,context,trace):
        self.assert_safe(context)
        a=self.adapter
        require(a.identity(self.model)==self.model_canonical,'Original root model incarnation changed.')
        native=a.native_close_windows()
        declared=trace['document_window_bindings']
        require(len(native)==len(declared) and len({info['hwnd'] for _,info in native})==len(native)
                and {info['hwnd'] for _,info in native}=={row['hwnd'] for row in declared},
                'Whole native window census differs from actual child observation.')
        root=[info for model,info in native if a.identity(model)==self.model_canonical]
        child=[row for row in declared if row['document_id']==context['document_id']]
        require(len(root)==len(child)==1 and root[0]['hwnd']==child[0]['hwnd']==self.hwnd,
                'Actual child document must map to the retained original root model/HWND.')

    def capture(self,context,item,child_evidence):
        context=_context(context)
        require(child_evidence.get('scope')=='b3_actual_child_trace_job_binding_v1'
                and child_evidence.get('accepted') is False,'Actual coherent child trace binding required.')
        trace=child_evidence['trace']
        self.assert_safe(context)
        event=self.watch.poll()
        self._windows(context,trace)
        documents=[row for row in trace['registered_references'] if row['document_id']==context['document_id']]
        require(len(documents)==1,'One actual child namespace for the explicit document required.')
        rows=documents[0]['rows']
        matches=[row for row in rows if row['family']=='part_geometry' and row['object_id']==item['object_id']]
        require(len(matches)==1,'One actual child PID registration for the exact opaque object required.')
        row=matches[0]
        require(row['kind']==item['kind'] and row['configuration']==context['configuration']
                and row['body_id']==item['body_id'],'Actual object kind/configuration/body context differs.')
        def original(registration):
            token=registration['persistent_id_hex']
            require(type(token) is str and re.fullmatch('[0-9a-f]+',token) and len(token)%2==0,
                    'Actual native PID hex required.')
            pid=bytes.fromhex(token)
            matches=[obj for obj in self.originals if obj.kind==registration['kind'] and obj.persistent_id==pid]
            require(len(matches)==1,'Child PID must bind one original retained native object, not shape/name matching.')
            return matches[0]
        obj=original(row)
        if obj.kind=='body':owner=obj;owner_row=row
        else:
            owner_rows=[value for value in rows if value['family']=='part_geometry'
                and value['object_id']==row['body_id'] and value['kind']=='body'
                and value['configuration']==context['configuration']]
            require(len(owner_rows)==1,'Exact actual namespace owner body registration required.')
            owner_row=owner_rows[0];owner=original(owner_row)
        require(obj.body_canonical==owner.canonical and owner.body_canonical==owner.canonical,
                'Original retained topology/body ownership differs from child association.')
        binding=RetainedPartReference(row['object_id'],obj.kind,obj.handle,obj.canonical,obj.persistent_id)
        body=RetainedPartReference(owner_row['object_id'],'body',owner.handle,owner.canonical,owner.persistent_id)
        proof=capture_native_part_reference(context=context,item=item,model=self.model,
            model_canonical=self.model_canonical,configuration_canonical=self.configuration_canonical,
            binding=binding,owner_body=body,wrap=self.wrap,identity=self.adapter.identity,
            persistent_variant=self.persistent_variant,original_body_census=[x.canonical for x in self.originals if x.kind=='body'],
            ordinal=self.ordinal,watch=self.watch,assert_safe=self.assert_safe)
        self._windows(context,trace)
        self.assert_safe(context)
        require(self.watch.poll()==event,'Part bridge changed inside native owner/window/PID observation envelope.')
        return proof
