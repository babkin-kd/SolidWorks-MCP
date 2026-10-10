"""Durable explicit selected-edge fillet with complete source and result proof."""

from copy import deepcopy
from dataclasses import asdict
import hashlib
import math

from .documents import rejected
from .geometry import GeometryCatalog
from .jobs import _json
from .mutations import PreparedMutation
from .part_cut import PartCutCatalog
from .part_fillet_definition import SelectedEdgeFillet, SCOPE, cuboid_edge, cuboid_body_matches, fillet_body_matches
from .sketches import rectangle_parameters, persistent_sketch_members


class PartFilletCatalog:
    def __init__(self,sketches):
        self.sketches,self.dimensions=sketches,sketches.dimensions
        self.adapter=self.dimensions.adapter
        self.geometry=GeometryCatalog(self.dimensions.documents)

    def _capture(self,document_id,configuration,definition):
        base=self.sketches._capture(document_id,configuration,definition.object_id)
        entry,identity,_,semantic,_=base.dimensions.state
        parameters=rectangle_parameters(base.snapshot,semantic,configuration)
        if not cuboid_body_matches(semantic['geometry'],parameters):
            raise rejected('unsupported_fillet_base','Every base vertex, edge and planar face must match the explicit cuboid.')
        if any(row['name'].casefold()==definition.feature_name.casefold() for row in semantic['tree']['features']):
            raise rejected('fillet_name_conflict','Requested Russian tree name already exists.')
        edge,ref=self.geometry._resolve(entry,definition.edge_id,configuration,identity,'edge')
        bodies=self.adapter.bodies(entry.model,'all')
        if ref.body_id is None or len(bodies)!=1 or self.adapter.identity(self.adapter.owner_body(edge,'edge'))!=self.adapter.identity(bodies[0]):
            raise rejected('fillet_edge_body_mismatch','Explicit edge must belong to the exact single supported base body.')
        points=self.adapter.pattern_edge_points(edge)
        axis,corner=cuboid_edge(points,parameters)
        expected=definition.expected_geometry(parameters,axis,corner)
        controls=self.adapter.part_creation_controls(entry.model)
        if controls['dimension_input']:
            raise rejected('fillet_interactive_dimension_input','Interactive dimension entry must be disabled.')
        self.dimensions._close_native_proof(entry,base.dimensions.event_sequence)
        return base,edge,ref,points,controls,expected

    def _prepare(self,document_id,configuration,**arguments):
        definition=SelectedEdgeFillet.validate(**arguments)
        first,second=(self._capture(document_id,configuration,definition) for _ in range(2))
        a,b=first[0],second[0]
        same=(self.dimensions._same_capture(a.dimensions,b.dimensions) and a.revision==b.revision
            and a.snapshot==b.snapshot and persistent_sketch_members(a.members)==persistent_sketch_members(b.members)
            and self.adapter.identity(first[1])==self.adapter.identity(second[1])
            and first[2].persistent_id==second[2].persistent_id and first[3:]==second[3:])
        self.dimensions._close_native_proof(b.dimensions.state[0],b.dimensions.event_sequence)
        if not same:raise rejected('fillet_changed_during_read','Complete source/edge/control/shape proof changed during preparation.')
        payload=dict(scope=SCOPE,document_id=document_id,configuration=configuration,source_revision=b.revision,
            definition=asdict(definition),edge_pid_hex=second[2].persistent_id.hex(),points=second[3],controls=second[4],expected_geometry=second[5])
        return dict(document_id=document_id,configuration=configuration,revision_scope=SCOPE,
            revision='rev_'+hashlib.sha256(_json(payload).encode('utf8')).hexdigest(),
            definition=asdict(definition),expected_geometry=second[5],native_creation_available=True),second

    def prepare_edge_fillet(self,document_id,configuration,**arguments):
        return self._prepare(document_id,configuration,**arguments)[0]

    def _inspect(self,document_id,configuration,definition,receipt):
        entry,_=self.dimensions.documents.resolve(document_id,configuration)
        evidence=self.adapter.edge_fillet_evidence(entry.model,receipt)
        a,b=(self.sketches._capture(document_id,configuration,definition.object_id) for _ in range(2))
        same=(self.dimensions._same_capture(a.dimensions,b.dimensions) and a.revision==b.revision
            and a.snapshot==b.snapshot and persistent_sketch_members(a.members)==persistent_sketch_members(b.members))
        parameters=self.adapter.edge_fillet_parameters(entry.model,receipt)
        wanted={k:v for k,v in evidence.get('parameters',{}).items() if k!='edge_matches'}
        same=same and (parameters==wanted if wanted else parameters is None)
        self.dimensions._close_native_proof(b.dimensions.state[0],b.dimensions.event_sequence)
        if not same:raise rejected('fillet_changed_during_inspection','Complete final source/body/native definition changed across inspection.')
        return dict(semantic=b.dimensions.state[3],base_sketch=b.snapshot,created=evidence)

    _baseline_unchanged=staticmethod(PartCutCatalog._baseline_unchanged)

    @staticmethod
    def _owned_features(before,after,definition):
        old={row['native_id'] for row in before['semantic']['tree']['features']}
        added=[row for row in after['semantic']['tree']['features'] if row['native_id'] not in old]
        native_id=after['created'].get('fillet_native_id')
        if native_id is None:return not added
        if (len(added)!=1 or added[0]['native_id']!=native_id or added[0]['feature_type']!='Fillet'
                or added[0]['name']!=definition.feature_name or added[0]['error_code'] or added[0]['suppressed']):return False
        old_names={row['full_name'] for row in before['semantic']['dimensions']}
        extra=[row for row in after['semantic']['dimensions'] if row['full_name'] not in old_names]
        return len(extra)==1 and extra[0]['owner'] and extra[0]['owner']['native_id']==native_id

    @staticmethod
    def _native_parameters(after,definition):
        p=after['created'].get('parameters',{})
        # FilletItemsCount describes multiple-radius items, not selected edges.
        # The documented constant-radius sentinel is -1; GetEdgeCount proves 1.
        return (p.get('type')==0 and p.get('edge_count')==1 and p.get('items_count')==-1
            and p.get('feature_count')==0 and p.get('loop_count')==0 and p.get('hold_line_count')==0
            and p.get('edge_matches') is True and p.get('multiple_radius') is False
            and p.get('propagate') is False and p.get('partial') is False and p.get('asymmetric') is False
            and p.get('curvature_continuous') is False and p.get('conic_type')==0
            and math.isclose(p.get('radius_m',-1.),definition.radius_mm/1000.,rel_tol=0.,abs_tol=1e-12))

    def create_edge_fillet(self,operation_id,document_id,configuration,expected_revision,**arguments):
        definition=SelectedEdgeFillet.validate(**arguments)
        if self.dimensions.mutation_guard is None:raise rejected('mutation_guard_unavailable','An owning-STA guard is required.')
        target={}
        def prepare():
            public,current=self._prepare(document_id,configuration,**asdict(definition))
            base,edge,_,_,controls,expected=current;entry=base.dimensions.state[0]
            features=self.adapter.features(entry.model)
            if tuple(self.adapter.identity(f) for f in features)!=base.dimensions.feature_identities:
                raise rejected('fillet_target_changed','Exact feature membership changed before receipt construction.')
            receipt=self.adapter.new_edge_fillet_receipt(entry.model,features,controls,edge)
            self.dimensions._close_native_proof(entry,base.dimensions.event_sequence)
            target.update(entry=entry,receipt=receipt)
            return PreparedMutation(public['revision'],dict(scope=SCOPE,definition=asdict(definition),
                semantic=base.dimensions.state[3],base_sketch=base.snapshot,controls=controls,
                body_name=receipt.baseline_body_name,expected_geometry=expected))
        def validate(prepared):
            public,current=self._prepare(document_id,configuration,**asdict(definition))
            same=(public['revision']==prepared.revision and current[0].dimensions.state[0] is target['entry']
                and self.adapter.identity(current[1])==self.adapter.identity(target['receipt'].edge))
            self.dimensions._close_native_proof(target['entry'],current[0].dimensions.event_sequence)
            return same
        def apply(prepared):
            entry=target['entry'];entry.features['mutation_sequence']=entry.features.get('mutation_sequence',0)+1
            self.adapter.create_edge_fillet(entry.model,definition,target['receipt'])
            return dict(feature_name=definition.feature_name,radius_mm=definition.radius_mm)
        def inspect(prepared):return self._inspect(document_id,configuration,definition,target['receipt'])
        def verify(before,after,value):
            evidence=after['created']
            return (evidence.get('complete') is True and evidence.get('controls')==before['controls']
                and evidence.get('body_name')==before['body_name'] and self._baseline_unchanged(before,after)
                and self._owned_features(before,after,definition) and self._native_parameters(after,definition)
                and fillet_body_matches(after['semantic']['geometry'],before['expected_geometry'])
                and all(math.isclose(evidence.get(k,-1.),before['expected_geometry'][k],rel_tol=1e-10,abs_tol=1e-8)
                    for k in ('volume_mm3','surface_area_mm2')))
        def restore(before,prepared):
            current=inspect(prepared)
            if (not self._baseline_unchanged(before,current) or not self._owned_features(before,current,definition)
                    or current['created'].get('controls')!=before['controls']):
                raise rejected('fillet_restore_unsafe','Foreign baseline/metadata/controls prevent own-feature restoration.')
            if current['created'].get('fillet_native_id') is not None:
                if not self._native_parameters(current,definition) or not fillet_body_matches(current['semantic']['geometry'],before['expected_geometry']):
                    raise rejected('fillet_restore_unsafe','Unattributable definition/body prevents own-feature deletion.')
            elif current['semantic']['geometry']!=before['semantic']['geometry']:
                raise rejected('fillet_restore_unsafe','Unconfirmed body effects prevent restoration.')
            self.adapter.restore_edge_fillet(target['entry'].model,target['receipt'])
        def verify_restored(before,after):
            return (self.dimensions._comparable(before['semantic'])==self.dimensions._comparable(after['semantic'])
                and before['base_sketch']==after['base_sketch'] and after['created'].get('restored') is True)
        return self.dimensions.coordinator.execute(operation_id,document_id=document_id,configuration=configuration,
            expected_revision=expected_revision,prepare=prepare,validate=validate,apply=apply,inspect=inspect,
            verify=verify,restore=restore,verify_restored=verify_restored,
            guard=lambda prepared:self.dimensions.mutation_guard(target['entry'].model))
