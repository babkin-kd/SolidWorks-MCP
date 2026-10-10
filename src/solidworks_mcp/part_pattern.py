"""Bounded engineering pattern with full source/BREP proof and durable writes."""

from copy import deepcopy
from dataclasses import asdict
import hashlib
import math

from .documents import rejected
from .geometry import GeometryCatalog
from .jobs import _json
from .mutations import PreparedMutation
from .part_hole import hole_body_matches
from .part_hole_edit import PartHoleEditCatalog
from .part_pattern_definition import LinearHolePattern, SCOPE
from .sketches import persistent_sketch_members


def pattern_axis(points, base):
    """Require a real cuboid edge, positive local X/Y, with explicit flip."""
    frame = base['plane_transform']
    axes = (frame[:3], frame[3:6], frame[6:9])
    extents = tuple(base[key] for key in ('width_m', 'height_m', 'depth_m'))
    local = [tuple(math.fsum((p[i]-frame[9+i])*a[i] for i in range(3)) for a in axes) for p in points]
    if len(local)!=2 or any(len(p)!=3 or not all(math.isfinite(v) for v in p) for p in local):
        raise rejected('unsupported_pattern_axis', 'Two finite straight-edge endpoints are required.')
    bits = []
    for p in local:
        row = []
        for value,extent in zip(p,extents):
            matches = [end for end in (0,1) if abs(value-end*extent)<=1e-12]
            if len(matches)!=1:
                raise rejected('unsupported_pattern_axis', 'Direction must be an exact outer cuboid edge.')
            row.append(matches[0])
        bits.append(row)
    changed = [axis for axis in range(3) if bits[0][axis]!=bits[1][axis]]
    if len(changed)!=1 or changed[0]==2:
        raise rejected('unsupported_pattern_axis', 'Direction must follow local base X or Y; thickness edges are excluded.')
    return changed[0], bits[1][changed[0]] < bits[0][changed[0]]


class PartPatternCatalog:
    def __init__(self, sketches):
        self.sketches, self.dimensions = sketches, sketches.dimensions
        self.adapter = self.dimensions.adapter
        self.holes = PartHoleEditCatalog(sketches)
        self.geometry = GeometryCatalog(self.dimensions.documents)

    def _capture(self, document_id, configuration, definition):
        hole = self.holes._capture(document_id, configuration, definition.base_object_id, definition.object_id)
        captured = hole.circle.dimensions
        entry, identity, _, semantic, _ = captured.state
        features = self.adapter.features(entry.model)
        if tuple(self.adapter.identity(item) for item in features)!=captured.feature_identities:
            raise rejected('pattern_target_changed', 'Current feature membership changed.')
        seed, seed_ref = self.dimensions.features._resolve(entry, configuration, identity, features, definition.seed_object_id)
        circle_id = hole.circle.snapshot['feature_native_id']
        owner_ids = {row['owner']['owner_native_id'] for row in semantic['dimensions']
                     if row['owner'] and row['owner']['native_id']==circle_id}
        summary = self.adapter.feature_summary(seed)
        if owner_ids!={summary['native_id']} or summary['feature_type'] not in ('Cut','ICE') or summary['suppressed']:
            raise rejected('pattern_seed_mismatch', 'Explicit seed must be the exact owning cut of the circle sketch.')
        if any(row['name'].casefold()==definition.feature_name.casefold() for row in semantic['tree']['features']):
            raise rejected('pattern_name_conflict', 'Requested Russian pattern name already exists.')
        edge, edge_ref = self.geometry._resolve(entry, definition.direction_edge_id, configuration, identity, 'edge')
        bodies = self.adapter.bodies(entry.model, 'all')
        if (edge_ref.body_id is None or len(bodies)!=1
                or self.adapter.identity(self.adapter.owner_body(edge,'edge'))!=self.adapter.identity(bodies[0])):
            raise rejected('pattern_direction_body_mismatch', 'Direction must belong to the exact supported single body.')
        points = self.adapter.pattern_edge_points(edge)
        axis,reverse = pattern_axis(points, hole.base_parameters)
        expected = definition.expected_geometry(hole.base_parameters, hole.parameters, axis)
        self.dimensions._close_native_proof(entry, captured.event_sequence)
        return hole, seed, seed_ref, edge, edge_ref, points, axis, reverse, expected

    def _prepare(self, document_id, configuration, **arguments):
        definition = LinearHolePattern.validate(**arguments)
        first,second = (self._capture(document_id,configuration,definition) for _ in range(2))
        a,b = first[0],second[0]
        same = (self.dimensions._same_capture(a.circle.dimensions,b.circle.dimensions)
            and a.revision==b.revision and a.circle.snapshot==b.circle.snapshot and a.base.snapshot==b.base.snapshot
            and persistent_sketch_members(a.circle.members)==persistent_sketch_members(b.circle.members)
            and persistent_sketch_members(a.base.members)==persistent_sketch_members(b.base.members)
            and self.adapter.identity(first[1])==self.adapter.identity(second[1])
            and self.adapter.identity(first[3])==self.adapter.identity(second[3])
            and first[2].persistent_id==second[2].persistent_id and first[4].persistent_id==second[4].persistent_id
            and first[5:]==second[5:])
        self.dimensions._close_native_proof(b.circle.dimensions.state[0],b.circle.dimensions.event_sequence)
        if not same:
            raise rejected('pattern_changed_during_read', 'Complete source/edge/shape proof changed across preparation.')
        payload = dict(scope=SCOPE, source_revision=b.revision, definition=asdict(definition),
            seed_pid_hex=second[2].persistent_id.hex(), edge_pid_hex=second[4].persistent_id.hex(),
            direction_points=second[5], axis=second[6], reverse=second[7], expected_geometry=second[8])
        return dict(document_id=document_id, configuration=configuration, revision_scope=SCOPE,
            revision='rev_'+hashlib.sha256(_json(payload).encode('utf8')).hexdigest(),
            definition=asdict(definition), axis=('x','y')[second[6]],
            expected_geometry=second[8], native_creation_available=True), second

    def prepare_linear_hole_pattern(self, document_id, configuration, **arguments):
        return self._prepare(document_id,configuration,**arguments)[0]

    def _inspect(self, document_id, configuration, definition, receipt):
        entry,_ = self.dimensions.documents.resolve(document_id,configuration)
        evidence = self.adapter.linear_hole_pattern_evidence(entry.model,receipt)
        readings=[]
        for _ in range(2):
            # Read the full final body only after AccessSelections has released
            # native rollback; never compare an intermediate rollback body.
            circle = self.holes.circles._capture(document_id,configuration,definition.object_id)
            base = self.sketches._capture_from_dimensions(circle.dimensions,document_id,configuration,definition.base_object_id)
            readings.append((circle,base))
        a,b=readings
        same=(self.dimensions._same_capture(a[0].dimensions,b[0].dimensions)
            and a[0].snapshot==b[0].snapshot and a[1].snapshot==b[1].snapshot
            and persistent_sketch_members(a[0].members)==persistent_sketch_members(b[0].members)
            and persistent_sketch_members(a[1].members)==persistent_sketch_members(b[1].members))
        scalars=self.adapter.linear_hole_pattern_parameters(entry.model,receipt)
        wanted={key:value for key,value in evidence.get('parameters',{}).items()
                if key not in ('seed_matches','axis_matches')}
        same = same and (scalars==wanted if wanted else scalars is None)
        self.dimensions._close_native_proof(b[0].dimensions.state[0],b[0].dimensions.event_sequence)
        if not same:
            raise rejected('pattern_changed_during_inspection','Complete source/pattern proof changed across inspection.')
        return dict(semantic=b[0].dimensions.state[3],circle=b[0].snapshot,base=b[1].snapshot,created=evidence)

    def _baseline_unchanged(self,before,after):
        current=deepcopy(after['semantic'])
        ids={row['native_id'] for row in before['semantic']['tree']['features']}
        current['tree']['features']=[row for row in current['tree']['features'] if row['native_id'] in ids]
        names={row['full_name'] for row in before['semantic']['dimensions']}
        current['dimensions']=[row for row in current['dimensions'] if row['full_name'] in names]
        return (self.dimensions._comparable(before['semantic'],ignore_geometry=True)
            ==self.dimensions._comparable(current,ignore_geometry=True)
            and before['base']==after['base'] and before['circle']==after['circle'])

    @staticmethod
    def _owned_features(before,after,definition):
        old={row['native_id'] for row in before['semantic']['tree']['features']}
        added=[row for row in after['semantic']['tree']['features'] if row['native_id'] not in old]
        native_id=after['created'].get('pattern_native_id')
        if native_id is None:return not added
        if (len(added)!=1 or added[0]['native_id']!=native_id or added[0]['feature_type']!='LPattern'
                or added[0]['name']!=definition.feature_name or added[0]['error_code'] or added[0]['suppressed']):
            return False
        old_names={row['full_name'] for row in before['semantic']['dimensions']}
        extra=[row for row in after['semantic']['dimensions'] if row['full_name'] not in old_names]
        return len(extra)<=4 and all(row['owner'] and row['owner']['native_id']==native_id for row in extra)

    @staticmethod
    def _native_parameters(before,after,definition):
        p=after['created'].get('parameters',{})
        return (p.get('count')==definition.count and p.get('reverse') is before['reverse']
            and p.get('end_condition')==0 and p.get('geometry_pattern') is False
            and p.get('vary_sketch') is False and p.get('body_pattern') is False
            and p.get('direction_2') is False and p.get('skipped_count')==0
            and p.get('seed_count')==1 and p.get('seed_matches') is True and p.get('axis_matches') is True
            and math.isclose(p.get('spacing_m',-1.),definition.spacing_mm/1000.,rel_tol=0.,abs_tol=1e-12))

    def create_linear_hole_pattern(self, operation_id, document_id, configuration, expected_revision, **arguments):
        definition=LinearHolePattern.validate(**arguments)
        if self.dimensions.mutation_guard is None:
            raise rejected('mutation_guard_unavailable','An owning-STA guard is required.')
        target={}
        def prepare():
            public,captured=self._prepare(document_id,configuration,**asdict(definition))
            hole,seed,_,edge,_,_,_,reverse,expected=captured
            entry=hole.circle.dimensions.state[0]
            features=self.adapter.features(entry.model)
            if tuple(self.adapter.identity(item) for item in features)!=hole.circle.dimensions.feature_identities:
                raise rejected('pattern_target_changed','Feature membership changed before receipt construction.')
            controls=hole.controls['sketch_controls']
            receipt=self.adapter.new_linear_hole_pattern_receipt(entry.model,features,controls,seed,edge,reverse)
            self.dimensions._close_native_proof(entry,hole.circle.dimensions.event_sequence)
            target.update(entry=entry,receipt=receipt)
            return PreparedMutation(public['revision'],dict(scope=SCOPE,definition=asdict(definition),
                semantic=hole.circle.dimensions.state[3],circle=hole.circle.snapshot,base=hole.base.snapshot,
                controls=controls,body_name=hole.controls['body_name'],reverse=reverse,expected_geometry=expected))
        def validate(prepared):
            public,current=self._prepare(document_id,configuration,**asdict(definition))
            receipt=target['receipt']
            entry=current[0].circle.dimensions.state[0]
            same=(public['revision']==prepared.revision and entry is target['entry']
                and self.adapter.identity(current[1])==self.adapter.identity(receipt.seed)
                and self.adapter.identity(current[3])==self.adapter.identity(receipt.direction))
            self.dimensions._close_native_proof(entry,current[0].circle.dimensions.event_sequence)
            return same
        def apply(prepared):
            entry=target['entry']
            entry.features['mutation_sequence']=entry.features.get('mutation_sequence',0)+1
            self.adapter.create_linear_hole_pattern(entry.model,definition,target['receipt'])
            return {'feature_name':definition.feature_name,'count':definition.count}
        def inspect(prepared):
            return self._inspect(document_id,configuration,definition,target['receipt'])
        def verify(before,after,value):
            evidence=after['created']
            return (evidence.get('complete') is True and evidence.get('controls')==before['controls']
                and evidence.get('body_name')==before['body_name']
                and self._baseline_unchanged(before,after) and self._owned_features(before,after,definition)
                and self._native_parameters(before,after,definition)
                and hole_body_matches(after['semantic']['geometry'],before['expected_geometry'])
                and all(math.isclose(evidence.get(key,-1.),before['expected_geometry'][key],rel_tol=1e-10,abs_tol=1e-8)
                        for key in ('volume_mm3','surface_area_mm2')))
        def restore(before,prepared):
            current=inspect(prepared)
            if (not self._baseline_unchanged(before,current) or not self._owned_features(before,current,definition)
                    or current['created'].get('controls')!=before['controls']):
                raise rejected('pattern_restore_unsafe','Foreign source/metadata/controls prevent own-pattern restoration.')
            if current['created'].get('pattern_native_id') is not None:
                if (not self._native_parameters(before,current,definition)
                        or not hole_body_matches(current['semantic']['geometry'],before['expected_geometry'])):
                    raise rejected('pattern_restore_unsafe','Unattributable pattern definition/body prevents deletion.')
            elif current['semantic']['geometry']!=before['semantic']['geometry']:
                raise rejected('pattern_restore_unsafe','Unconfirmed body effects prevent restoration.')
            self.adapter.restore_linear_hole_pattern(target['entry'].model,target['receipt'])
        def verify_restored(before,after):
            return (self.dimensions._comparable(before['semantic'])==self.dimensions._comparable(after['semantic'])
                and before['base']==after['base'] and before['circle']==after['circle']
                and after['created'].get('restored') is True)
        return self.dimensions.coordinator.execute(operation_id,document_id=document_id,configuration=configuration,
            expected_revision=expected_revision,prepare=prepare,validate=validate,apply=apply,inspect=inspect,
            verify=verify,restore=restore,verify_restored=verify_restored,
            guard=lambda prepared:self.dimensions.mutation_guard(target['entry'].model))
