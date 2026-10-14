"""Caller-owned source-only Ø12×30 cylinder setup; no connection or acceptance.

CreateCircleByRadius and the 23 FeatureExtrusion3 arguments follow session.py.
The admitted original Y-normal plane gives a model-Y cylinder, radius .006 m
and height .030 m. Boss extrusion defaults along the sketch/plane normal;
Dir=True reverses it, so a negative native Y normal requires Dir=True:
https://help.solidworks.com/2017/english/api/sldworksapi/SOLIDWORKS.Interop.sldworks~SOLIDWORKS.Interop.sldworks.IFeatureManager~FeatureExtrusion3.html
Every call uses the shared paired durable ledger, original STA/process guard
and externally retained receipt. Unknown outcomes stay held, without retry or
cleanup. No installed wheel, B1 sketch or complete B3 manifest is accepted here.
"""
from dataclasses import dataclass
import math
from pathlib import Path

from verifier_b3_part_fixture import (
    FixtureAnchor, PartFixtureReceipt, _Builder, require)


ROLE = 'Цилиндр'
BOUNDS_M = (-.006, .006, 0., .030, -.006, .006)


@dataclass(frozen=True)
class CylinderEmptyBaseline:
    """Complete original empty tree and independently proven original plane.

transform is native IRefPlane.Transform.ArrayData: tangent basis [0:6],
normal [6:9], origin [9:12], scale [12], unused slots [13:16].
"""
    model_canonical: object
    features: tuple
    plane: FixtureAnchor
    transform: tuple
    plane_proven: bool


def validated_plane_transform(values):
    """Validate a complete origin-centered, proper unit native Y-normal frame."""
    require(isinstance(values, (tuple, list)) and len(values) == 16
            and all(type(x) in (int, float) and math.isfinite(x) for x in values),
            'Complete finite original plane native transform required.')
    data = tuple(float(x) for x in values)
    axes = [data[i:i + 3] for i in (0, 3, 6)]
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    cross = (axes[0][1]*axes[1][2] - axes[0][2]*axes[1][1],
             axes[0][2]*axes[1][0] - axes[0][0]*axes[1][2],
             axes[0][0]*axes[1][1] - axes[0][1]*axes[1][0])
    require(all(abs(dot(a, a) - 1.) <= 1e-9 for a in axes)
            and all(abs(dot(axes[i], axes[j])) <= 1e-9 for i, j in ((0, 1), (0, 2), (1, 2)))
            and all(abs(x - y) <= 1e-9 for x, y in zip(cross, axes[2]))
            and all(abs(x) <= 1e-9 for x in data[9:12]) and abs(data[12] - 1.) <= 1e-9
            and abs(data[6]) <= 1e-9 and abs(data[8]) <= 1e-9 and abs(abs(data[7]) - 1.) <= 1e-9,
            'Original Y-normal plane requires origin0/proper unit native basis.')
    return data


class _CylinderBuilder(_Builder):
    def selection(self, model, expected=None):
        manager = self.call('selection:manager', self.wrap,
                            self.call('selection:raw', getattr, model, 'SelectionManager'),
                            'ISelectionMgr')
        count = self.call('selection:count', manager.GetSelectedObjectCount2, -1)
        require(type(count) is int and count == (0 if expected is None else 1),
                'Exact owned selection count differs.')
        if expected is not None:
            selected = self.call('selection:object', manager.GetSelectedObject6, 1, -1)
            mark = self.call('selection:mark', manager.GetSelectedObjectMark, 1)
            require(self.call('selection:identity', self.identity, selected) == expected.canonical
                    and type(mark) is int and mark == 0,
                    'Exact original owned selection/mark differs.')

    def census(self, part, body=None):
        roster = self.call('cylinder:body_membership', part.GetBodies2, -1, False)
        # GetBodies2 normally returns None for an empty newly created part.
        # Only the explicit empty baseline accepts it, never a live body scope.
        if body is None and roster is None:
            roster = ()
        require(isinstance(roster, (tuple, list)) and len(roster) == (0 if body is None else 1),
                'Full cylinder body membership census differs.')
        if body is not None:
            require(self.call('cylinder:member_identity', self.identity, roster[0]) == body.canonical,
                    'Full cylinder body membership census differs.')
            self.current(body)

    def body(self, feature, part):
        raw_faces = self.call('cylinder:feature_faces', feature.handle.GetFaces)
        require(isinstance(raw_faces, (tuple, list)) and len(raw_faces) == 3,
                'Exactly three original returned cylinder feature faces required.')
        faces = [self.anchor('Цилиндр_грань_' + str(i + 1), 'face', raw, 'IFace2')
                 for i, raw in enumerate(raw_faces)]
        require(all(sum(a.canonical == other.canonical for other in faces) == 1 for a in faces),
                'Returned feature face identities are duplicated.')
        owners = [self.anchor('Цилиндр_владелец_' + str(i + 1), 'body',
                             self.call('cylinder:face_body', face.handle.GetBody), 'IBody2')
                  for i, face in enumerate(faces)]
        body = owners[0]
        require(all(a.canonical == body.canonical for a in owners),
                'Returned cylinder feature faces have different body owners.')
        self.census(part, body)
        kind = self.call('cylinder:body_type', body.handle.GetType)
        require(type(kind) is int and kind == 0
                and self.call('cylinder:mesh', body.handle.IsMeshBody) is False,
                'Returned cylinder requires one normal solid BREP body.')
        members = self.call('cylinder:body_faces', body.handle.GetFaces)
        require(isinstance(members, (tuple, list)) and len(members) == 3,
                'Complete cylinder body face membership differs.')
        tokens = [self.call('cylinder:face_member_identity', self.identity, raw) for raw in members]
        require(all(sum(token == face.canonical for token in tokens) == 1 for face in faces),
                'Returned feature faces are not the complete original body membership.')
        count = self.call('cylinder:face_count', body.handle.GetFaceCount)
        require(type(count) is int and count == 3, 'Complete cylinder body face count differs.')
        self.bounds(body, BOUNDS_M)
        self.r.bodies[ROLE] = body
        self.name(body, 'Контрольное тело цилиндра')
        return body

    def closing_faces(self, feature, body):
        faces = [a for a in self.r.anchors if a.kind == 'face']
        require(len(faces) == 3, 'Complete original retained cylinder faces required.')
        for label, raw in (
            ('feature_faces', self.call('closing:feature_faces', feature.handle.GetFaces)),
            ('body_faces', self.call('closing:body_faces', body.handle.GetFaces))):
            require(isinstance(raw, (tuple, list)) and len(raw) == 3,
                    'Complete original closing cylinder face membership differs.')
            tokens = [self.call('closing:' + label + ':identity', self.identity, member) for member in raw]
            require(all(sum(token == face.canonical for token in tokens) == 1 for face in faces),
                    'Complete original closing cylinder face membership differs.')
        for face in faces:
            self.current(face)
            require(self.call('closing:face_owner_identity', self.identity,
                             self.call('closing:face_owner', face.handle.GetBody)) == body.canonical,
                    'Original closing cylinder face owner differs.')
        kind = self.call('closing:body_type', body.handle.GetType)
        require(type(kind) is int and kind == 0
                and self.call('closing:mesh', body.handle.IsMeshBody) is False,
                'Original closing cylinder must remain normal solid BREP.')

    def circle(self, model, plane, transform):
        self.current(plane)
        manager = self.call('cylinder:manager', self.wrap,
                            self.call('cylinder:manager_raw', getattr, model, 'SketchManager'),
                            'ISketchManager')
        require(self.call('cylinder:closed_baseline', getattr, manager, 'ActiveSketch') is None,
                'An existing open sketch cannot be borrowed.')
        require(self.call('cylinder:add_baseline', getattr, manager, 'AddToDB') is False,
                'Parent must admit AddToDB=False baseline.')
        self.selection(model)
        self.call('cylinder:clear_selection', model.ClearSelection2, True)
        self.selection(model)
        require(self.call('cylinder:select_plane', plane.handle.Select2, False, 0) is True,
                'Exact admitted Y-normal plane selection failed.')
        self.selection(model, plane)
        self.call('cylinder:open_sketch', manager.InsertSketch, True)
        sketch = self.anchor(ROLE, 'sketch',
                             self.call('cylinder:active_sketch', getattr, manager, 'ActiveSketch'), 'ISketch')
        self.r.sketches[ROLE] = sketch
        sketch_feature = self.exact_sketch_feature(model, sketch)
        self.require_new_feature(sketch_feature, 'Sketch creation')
        require(self.call('cylinder:sketch_feature_type', sketch_feature.handle.GetTypeName2) == 'ProfileFeature',
                'Original returned circle sketch must be a typed 2D profile.')
        segments_before = self.call('cylinder:empty_segments', sketch.handle.GetSketchSegments)
        require(segments_before is None or isinstance(segments_before, (tuple, list)) and not segments_before,
                'New original active circle sketch must start empty.')
        self.name(sketch_feature, 'Контрольный эскиз цилиндра')
        self.call('cylinder:add_on', setattr, manager, 'AddToDB', True)
        require(self.call('cylinder:add_on_readback', getattr, manager, 'AddToDB') is True,
                'Owned AddToDB enable unconfirmed.')
        segment = self.anchor('Цилиндр_окружность', 'segment', self.call('cylinder:circle',
            manager.CreateCircleByRadius, 0., 0., 0., .006), 'ISketchSegment')
        segments = self.call('cylinder:segments', sketch.handle.GetSketchSegments)
        require(isinstance(segments, (tuple, list)) and len(segments) == 1
                and self.call('cylinder:segment_identity', self.identity, segments[0]) == segment.canonical,
                'Returned circle is not the sole original active sketch member.')
        self.call('cylinder:add_off', setattr, manager, 'AddToDB', False)
        require(self.call('cylinder:add_readback', getattr, manager, 'AddToDB') is False,
                'Owned AddToDB restore unconfirmed.')
        self.current(sketch)
        require(self.call('cylinder:active_identity', self.identity,
                         self.call('cylinder:active_readback', getattr, manager, 'ActiveSketch')) == sketch.canonical,
                'Another active sketch replaced the retained original.')
        self.call('cylinder:close_sketch', manager.InsertSketch, True)
        require(self.call('cylinder:closed_readback', getattr, manager, 'ActiveSketch') is None,
                'Owned sketch close unconfirmed.')
        self.call('cylinder:clear_sketch_selection', model.ClearSelection2, True)
        self.selection(model)
        require(self.call('cylinder:select_sketch', sketch_feature.handle.Select2, False, 0) is True,
                'Exact returned sketch feature selection failed.')
        self.selection(model, sketch_feature)
        factory = self.call('cylinder:factory', self.wrap,
                           self.call('cylinder:factory_raw', getattr, model, 'FeatureManager'), 'IFeatureManager')
        feature = self.anchor(ROLE, 'feature', self.call('cylinder:extrude', factory.FeatureExtrusion3,
            True, False, transform[7] < 0., 0, 0, .030, 0., False, False, False, False, 0., 0.,
            False, False, False, False, False, True, True, 0, 0., False), 'IFeature')
        self.require_new_feature(feature, 'Extrusion')
        self.r.features[ROLE] = feature
        self.name(feature, 'Контрольный цилиндр')
        return feature, sketch_feature, manager


def create_cylinder_fixture(*, receipt, application, template, title_suffix, wrap, identity,
                            assert_safe, recorder, admit_application, admit_empty_part):
    """Create exactly one separate unsaved caller-owned cylinder, once.

The caller retains PartFixtureReceipt before entry. Application admission must
reject any foreign/reused NewDocument return, and empty admission supplies the
complete original template census and native-transform proof of original Yplane.
assert_safe enforces the original process/STA owner before EVERY ledger call.
No reconnect, activation, save, close, Undo or exception cleanup is attempted.
"""
    require(isinstance(receipt, PartFixtureReceipt) and not receipt.attempted
            and not any((receipt.documents, receipt.configurations, receipt.features,
                         receipt.sketches, receipt.bodies, receipt.anchors, receipt.native_returns,
                         receipt.baselines)) and not receipt.setup_complete
            and receipt.accepted is False and receipt.native_acceptance is False
            and receipt.cleanup_authorized is False,
            'Fresh externally retained cylinder fixture receipt required.')
    require(type(receipt.request_id) is str and receipt.request_id.strip(), 'Explicit request_id required.')
    require(all(callable(x) for x in (wrap, identity, assert_safe, recorder, admit_application, admit_empty_part)),
            'Original owner guard, durable recorder and admission callbacks required.')
    path = Path(template)
    require(path.is_absolute() and path.is_file() and path.suffix.lower() == '.prtdot',
            'Explicit configured existing absolute part template required.')
    require(type(title_suffix) is str and title_suffix and len(title_suffix) <= 64
            and not any(char in title_suffix for char in '\r\n/\\'), 'Bounded explicit fixture title suffix required.')
    b = _CylinderBuilder(receipt, application, wrap, identity, assert_safe, recorder)
    b.ready()
    receipt.attempted = True
    receipt.remaining_profile = ('same_wheel_B1_sketch', 'whole_session_original_baseline', '13_named_B3_groups')
    try:
        require(b.call('application:admission', admit_application, application, receipt) is True,
                'Parent original application/owned admission required.')
        document = b.anchor(ROLE, 'document', b.call('cylinder:new_document',
            application.NewDocument, str(path), 0, 0., 0.), 'IModelDoc2')
        receipt.documents[ROLE] = document
        kind = b.call('cylinder:part_type', document.handle.GetType)
        require(type(kind) is int and kind == 1, 'Configured template must create a part.')
        baseline = b.call('cylinder:empty_admission', admit_empty_part, document, receipt, ROLE)
        require(isinstance(baseline, CylinderEmptyBaseline) and baseline.plane_proven is True
                and baseline.model_canonical == document.canonical and type(baseline.features) is tuple
                and 0 < len(baseline.features) <= 100
                and all(isinstance(a, FixtureAnchor) and a.kind == 'feature' for a in baseline.features)
                and isinstance(baseline.plane, FixtureAnchor) and baseline.plane.kind == 'feature'
                and sum(a.canonical == baseline.plane.canonical for a in baseline.features) == 1
                and all(sum(a.canonical == other.canonical for other in baseline.features) == 1
                        for a in baseline.features),
                'Complete original empty template/Y-normal plane admission required.')
        transform = validated_plane_transform(baseline.transform)
        receipt.baselines[ROLE] = baseline
        receipt.anchors.extend(baseline.features)
        model = document.handle
        original_tree = b.tree(model)
        tokens = [b.call('template:tree_identity', identity, raw) for raw in original_tree]
        require(len(tokens) == len(baseline.features)
                and all(sum(token == a.canonical for token in tokens) == 1 for a in baseline.features),
                'Complete original template feature census differs.')
        require(b.call('template:plane_type', baseline.plane.handle.GetTypeName2) == 'RefPlane',
                'Admitted original Y-normal plane must be a typed RefPlane.')
        part = b.call('cylinder:part_interface', wrap, model, 'IPartDoc')
        b.census(part)
        b.selection(model)
        require(b.call('cylinder:initial_path', model.GetPathName) == '', 'Owned template must be unsaved.')
        title = 'Проверка B3 Цилиндр ' + title_suffix
        require(b.call('cylinder:title', model.SetTitle2, title) is True
                and b.call('cylinder:title_readback', model.GetTitle) == title,
                'Russian owned document title readback differs.')
        cfg = b.anchor('Цилиндр_Основная', 'configuration',
                       b.call('cylinder:active_configuration', model.GetActiveConfiguration), 'IConfiguration')
        original_name = b.call('cylinder:original_configuration_name', getattr, cfg.handle, 'Name')
        names = b.call('cylinder:configuration_names', model.GetConfigurationNames)
        require(isinstance(names, (tuple, list)) and list(names) == [original_name],
                'Owned template must have exactly its one original configuration.')
        receipt.configurations['Цилиндр_Основная'] = cfg
        b.name(cfg, 'Основная')
        for i, anchor in enumerate(baseline.features):
            b.current(anchor)
            if b.call('template:feature_type', anchor.handle.GetTypeName2) == 'RefPlane':
                b.name(anchor, 'Контрольная плоскость ' + str(i + 1))
        feature, sketch_feature, manager = b.circle(model, baseline.plane, transform)
        body = b.body(feature, part)
        require(b.call('cylinder:rebuild', model.ForceRebuild3, False) is True, 'Owned cylinder rebuild failed.')
        b.call('cylinder:closing_clear_selection', model.ClearSelection2, True)
        b.selection(model)
        require(b.call('cylinder:closing_add', getattr, manager, 'AddToDB') is False
                and b.call('cylinder:closing_sketch', getattr, manager, 'ActiveSketch') is None,
                'Owned closing sketch/AddToDB flags differ.')
        require(b.call('cylinder:dirty', model.GetSaveFlag) is True
                and b.call('cylinder:path', model.GetPathName) == '', 'Owned cylinder must remain unsaved and dirty.')
        b.census(part, body)
        b.closing_faces(feature, body)
        b.bounds(body, BOUNDS_M)
        closing = b.tree(model)
        tokens = [b.call('cylinder:closing_feature_identity', identity, raw) for raw in closing]
        expected = baseline.features + (sketch_feature, feature)
        require(len(tokens) == len(expected)
                and all(sum(token == a.canonical for token in tokens) == 1 for a in expected),
                'Complete original closing feature census differs.')
        names = b.call('cylinder:closing_configuration_names', model.GetConfigurationNames)
        require(isinstance(names, (tuple, list)) and list(names) == ['Основная']
                and b.call('cylinder:closing_active_identity', identity,
                           b.call('cylinder:closing_active', model.GetActiveConfiguration)) == cfg.canonical,
                'Complete original closing configuration differs.')
        for anchor in receipt.anchors:
            b.current(anchor)
        receipt.setup_complete = True
        return receipt
    except BaseException:
        receipt.halted = True
        raise
