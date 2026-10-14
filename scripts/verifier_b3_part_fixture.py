"""Bounded, caller-owned B3 part setup; no connection, cleanup or acceptance.

The original STA owner supplies application admission, an explicit configured
part template, empty-template/XY-plane proof and a durable recorder. Every raw
normal return stays in the externally held receipt BEFORE the returned record.
An exception, recorder loss or failed postcondition latches the receipt; no
retry, Undo, close, save or further native call is permitted here.

Extrusion arguments follow session.py/cad_rectangle_construction.py. Sheet API:
https://help.solidworks.com/2023/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModeler~CreatePlanarSurface2.html
https://help.solidworks.com/2024/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IModeler~CreateSheetFromSurface.html
https://help.solidworks.com/2020/english/api/sldworksapi/SolidWorks.Interop.sldworks~SolidWorks.Interop.sldworks.IPartDoc~CreateSurfaceFeatureFromBody.html
CreateSurfaceFeatureFromBody returns an actual feature ARRAY; exactly one
returned feature is required. No InsertPlanarRefSurface/name-difference path.
"""
from dataclasses import dataclass, field
import math
from pathlib import Path
from threading import get_ident


def require(condition, message):
    if not condition:
        raise ValueError(message)


@dataclass(frozen=True)
class FixtureAnchor:
    role: str
    kind: str
    handle: object
    canonical: object


@dataclass(frozen=True)
class EmptyPartBaseline:
    """Parent's complete empty-template proof, including actual model-XY plane.

xy_plane is admitted through its native transform, not tree position or name.
features are original complete template feature handles/canonical anchors.
"""
    model_canonical: object
    features: tuple
    xy_plane: FixtureAnchor
    xy_plane_proven: bool


@dataclass
class PartFixtureReceipt:
    request_id: str
    thread_id: int = field(default_factory=get_ident)
    attempted: bool = False
    halted: bool = False
    pending_step: str | None = None
    journal_lost: bool = False
    native_returns: list = field(default_factory=list)
    anchors: list = field(default_factory=list)
    baselines: dict = field(default_factory=dict)
    documents: dict = field(default_factory=dict)
    configurations: dict = field(default_factory=dict)
    features: dict = field(default_factory=dict)
    sketches: dict = field(default_factory=dict)
    bodies: dict = field(default_factory=dict)
    setup_complete: bool = False
    accepted: bool = False
    native_acceptance: bool = False
    cleanup_authorized: bool = False
    # This bounded setup does not replace the remaining full manifest fixtures.
    remaining_profile: tuple = ('separate_cylinder_12x30', 'same_wheel_B1_sketch')


class _Builder:
    def __init__(self, receipt, application, wrap, identity, assert_safe, recorder):
        self.r, self.app = receipt, application
        self.wrap, self.identity = wrap, identity
        self.assert_safe, self.recorder = assert_safe, recorder
        self.index = 0

    def ready(self):
        require(get_ident() == self.r.thread_id, 'Original caller-owned STA required.')
        require(not self.r.halted and self.r.pending_step is None and not self.r.journal_lost,
                'Unconfirmed fixture owner remains held; further native calls forbidden.')
        require(self.assert_safe(self.r) is True, 'Original application/STA guard admission required.')

    def call(self, label, function, *args):
        self.ready()
        self.index += 1
        self.r.pending_step = label
        data = dict(request_id=self.r.request_id, step_index=self.index,
                    native_call_returned=False)
        self.r.journal_lost = True
        self.recorder(label, 'pending', data)
        self.r.journal_lost = False
        value = function(*args)
        # Keep the actual raw return even if wrapping or the durable ack fails.
        self.r.native_returns.append((self.index, label, value))
        self.r.journal_lost = True
        self.recorder(label, 'returned', dict(data, native_call_returned=True))
        self.r.journal_lost = False
        self.r.pending_step = None
        return value

    def anchor(self, role, kind, raw, interface):
        require(raw is not None, 'No normally returned ' + kind + ' anchor for ' + role + '.')
        obj = self.call(role + ':wrap', self.wrap, raw, interface)
        require(obj is not None, 'Missing typed fixture anchor.')
        token = self.call(role + ':identity', self.identity, obj)
        require(token is not None, 'Original canonical anchor required.')
        anchor = FixtureAnchor(role, kind, obj, token)
        self.r.anchors.append(anchor)
        return anchor

    def name(self, anchor, name, attribute='Name'):
        self.call(anchor.role + ':name', setattr, anchor.handle, attribute, name)
        require(self.call(anchor.role + ':name_readback', getattr, anchor.handle, attribute) == name,
                'Russian fixture name readback differs.')

    def current(self, anchor):
        require(self.call(anchor.role + ':current_identity', self.identity, anchor.handle) == anchor.canonical,
                'Retained original fixture anchor changed.')

    def tree(self, model):
        """Bounded canonical traversal; never select a feature by tail/name/ID."""
        seen, links, result = [], [], []
        first = self.call('tree:first', model.FirstFeature)
        stack = [(first, False)]
        while stack:
            raw, sub = stack.pop()
            if raw is None:
                continue
            feature = self.call('tree:wrap', self.wrap, raw, 'IFeature')
            token = self.call('tree:identity', self.identity, feature)
            # The same absorbed sketch may occur in both main and subfeature
            # walks. Follow each link mode once, publish each canonical once.
            if any(token == previous and sub == mode for previous, mode in links):
                continue
            require(len(links) < 200, 'Finite fixture traversal-link budget exceeded.')
            links.append((token, sub))
            sibling = self.call('tree:next', feature.GetNextSubFeature if sub else feature.GetNextFeature)
            stack.append((sibling, sub))
            if any(token == previous for previous in seen):
                continue
            require(len(result) < 100, 'Finite fixture feature budget exceeded.')
            seen.append(token)
            result.append(feature)
            child = self.call('tree:child', feature.GetFirstSubFeature)
            stack.append((child, True))
        return result

    def require_new_feature(self, feature, operation):
        # anchor() already retained the raw return/current anchor for custody.
        # All earlier template, exact-sketch and created-feature anchors count.
        require(not any(a is not feature and a.kind == 'feature'
                        and a.canonical == feature.canonical for a in self.r.anchors),
                operation + ' returned an earlier original feature; no naming allowed.')

    def exact_sketch_feature(self, model, sketch):
        matches = []
        for feature in self.tree(model):
            kind = self.call('sketch_feature:type', feature.GetTypeName2)
            if kind not in ('ProfileFeature', '3DProfileFeature'):
                continue
            specific = self.call('sketch_feature:specific', feature.GetSpecificFeature2)
            if specific is not None:
                specific = self.call('sketch_feature:wrap', self.wrap, specific, 'ISketch')
                if self.call('sketch_feature:identity', self.identity, specific) == sketch.canonical:
                    matches.append(feature)
        require(len(matches) == 1, 'Returned active sketch lacks unique canonical feature roundtrip.')
        return self.anchor(sketch.role + '_feature', 'feature', matches[0], 'IFeature')

    def body_from_feature(self, feature, role, kind, expected_bounds, part):
        # Ownership derives ONLY from the returned feature's own faces.
        faces = self.call(role + ':feature_faces', feature.handle.GetFaces)
        require(isinstance(faces, (tuple, list)) and len(faces) == (6 if kind == 0 else 1),
                'Returned feature does not have the finite expected face scope.')
        bodies = []
        for raw in faces:
            face = self.call(role + ':face_wrap', self.wrap, raw, 'IFace2')
            body = self.anchor(role, 'body', self.call(role + ':face_body', face.GetBody), 'IBody2')
            bodies.append(body)
        first = bodies[0]
        require(all(body.canonical == first.canonical for body in bodies),
                'Returned feature faces have different body owners.')
        previous = [a for key, a in self.r.bodies.items() if (key == 'Сосед') == (role == 'Сосед')]
        require(not any(a.canonical == first.canonical for a in self.r.bodies.values()),
                'Returned feature reused an earlier original body; no naming allowed.')
        roster = self.call(role + ':body_membership', part.GetBodies2, -1, False) or ()
        require(isinstance(roster, (tuple, list)) and len(roster) == len(previous) + 1
                and len(roster) <= (1 if role == 'Сосед' else 3),
                'Full returned body membership census differs; no naming allowed.')
        tokens = [self.call(role + ':member_identity', self.identity, raw) for raw in roster]
        require(len(tokens) == len(previous) + 1
                and all(sum(x == a.canonical for x in tokens) == 1 for a in previous + [first]),
                'Full returned body membership census differs; no naming allowed.')
        actual_kind = self.call(role + ':body_type', first.handle.GetType)
        require(type(actual_kind) is int and actual_kind == kind,
                'Returned feature produced the wrong normal-body kind.')
        self.bounds(first, expected_bounds)
        self.r.bodies[role] = first
        self.name(first, 'Контрольное тело ' + role)
        return first

    def bounds(self, body, expected):
        actual = []
        for axis in range(3):
            for sign in (-1., 1.):
                direction = [0., 0., 0.]
                direction[axis] = sign
                point = self.call(body.role + ':extreme', body.handle.GetExtremePoint, *direction)
                require(isinstance(point, tuple) and len(point) in (3, 4)
                        and (len(point) == 3 or point[0] is True), 'Unconfirmed native extrema.')
                require(all(type(x) in (int, float) and math.isfinite(x) for x in point[-3:]),
                        'Finite native extrema required.')
                actual.append(point[-3:][axis])
        require(all(abs(x - y) <= 1e-8 for x, y in zip(actual, expected)),
                'Actual native extrema differ from the finite fixture profile.')

    def box(self, model, plane, role, x, width, height, depth):
        self.current(plane)
        manager = self.call(role + ':manager', self.wrap,
                            self.call(role + ':manager_raw', getattr, model, 'SketchManager'), 'ISketchManager')
        require(self.call(role + ':closed_baseline', getattr, manager, 'ActiveSketch') is None,
                'An existing open sketch cannot be borrowed.')
        original_add = self.call(role + ':add_to_db_baseline', getattr, manager, 'AddToDB')
        require(original_add is False, 'Parent must admit AddToDB=False baseline.')
        self.call(role + ':clear_selection', model.ClearSelection2, True)
        require(self.call(role + ':select_plane', plane.handle.Select2, False, 0) is True,
                'Exact admitted XY plane selection failed.')
        self.call(role + ':open_sketch', manager.InsertSketch, True)
        sketch = self.anchor(role, 'sketch', self.call(role + ':active_sketch', getattr, manager, 'ActiveSketch'), 'ISketch')
        self.r.sketches[role] = sketch
        sketch_feature = self.exact_sketch_feature(model, sketch)
        self.name(sketch_feature, 'Контрольный эскиз ' + role)
        self.call(role + ':add_to_db_on', setattr, manager, 'AddToDB', True)
        corners = ((x, 0.), (x + width, 0.), (x + width, height), (x, height))
        for index, (a, b) in enumerate(zip(corners, corners[1:] + corners[:1])):
            self.anchor(role + '_линия_' + str(index + 1), 'segment',
                        self.call(role + ':line', manager.CreateLine, *a, 0., *b, 0.), 'ISketchSegment')
        self.call(role + ':add_to_db_off', setattr, manager, 'AddToDB', False)
        require(self.call(role + ':add_to_db_readback', getattr, manager, 'AddToDB') is False,
                'Owned AddToDB transition was not confirmed.')
        self.current(sketch)
        require(self.call(role + ':active_identity', self.identity,
                         self.call(role + ':active_readback', getattr, manager, 'ActiveSketch')) == sketch.canonical,
                'Another active sketch replaced the retained original.')
        self.call(role + ':close_sketch', manager.InsertSketch, True)
        require(self.call(role + ':closed_readback', getattr, manager, 'ActiveSketch') is None,
                'Owned sketch close unconfirmed.')
        require(self.call(role + ':select_sketch', sketch_feature.handle.Select2, False, 0) is True,
                'Exact returned sketch feature selection failed.')
        factory = self.call(role + ':factory', self.wrap,
                            self.call(role + ':factory_raw', getattr, model, 'FeatureManager'), 'IFeatureManager')
        feature = self.anchor(role, 'feature', self.call(role + ':extrude', factory.FeatureExtrusion3,
            True, False, False, 0, 0, depth, 0., False, False, False, False, 0., 0.,
            False, False, False, False, False, True, True, 0, 0., False), 'IFeature')
        self.require_new_feature(feature, 'Extrusion')
        self.r.features[role] = feature
        self.name(feature, 'Контрольный блок ' + role)
        part = self.call(role + ':owned_part', self.wrap, model, 'IPartDoc')
        return self.body_from_feature(feature, role, 0, (x, x + width, 0., height, 0., depth), part)


def create_part_fixture(*, receipt, application, template, title_suffix, wrap, identity,
                        assert_safe, recorder, admit_application, admit_empty_part):
    """Create two owned unsaved parts on the original STA; return held receipt.

No CAD connection or STA initialization. Parent must retain receipt before entry
and keep its owner after ANY failure. Admission callbacks run under this ledger
and guard; they must supply independent application/empty-template proofs.
The template must be an explicit existing absolute .prtdot path. Nothing falls
back to NewPart or an ambient active document. Raw return receipt is private and
must never be JSON serialized or interpreted as cleanup/native acceptance.
"""
    require(isinstance(receipt, PartFixtureReceipt) and not receipt.attempted,
            'Fresh externally retained fixture receipt required.')
    require(type(receipt.request_id) is str and receipt.request_id.strip(), 'Explicit request_id required.')
    require(all(callable(x) for x in (wrap, identity, assert_safe, recorder, admit_application, admit_empty_part)),
            'Original owner guard, durable recorder and admission callbacks required.')
    path = Path(template)
    require(path.is_absolute() and path.is_file() and path.suffix.lower() == '.prtdot',
            'Explicit configured existing absolute part template required.')
    require(type(title_suffix) is str and title_suffix and len(title_suffix) <= 64
            and not any(char in title_suffix for char in '\r\n/\\'), 'Bounded explicit fixture title suffix required.')
    b = _Builder(receipt, application, wrap, identity, assert_safe, recorder)
    b.ready()
    receipt.attempted = True
    try:
        require(b.call('application:admission', admit_application, application, receipt) is True,
                'Parent original empty application/owned admission required.')
        for role in ('Основная деталь', 'Сосед'):
            document = b.anchor(role, 'document', b.call(role + ':new_document',
                application.NewDocument, str(path), 0, 0., 0.), 'IModelDoc2')
            require(not any(a.canonical == document.canonical for a in receipt.documents.values()),
                    'NewDocument returned an earlier original document; no naming allowed.')
            receipt.documents[role] = document
            require(b.call(role + ':part_type', document.handle.GetType) == 1, 'Configured template must create a part.')
            baseline = b.call(role + ':empty_admission', admit_empty_part, document, receipt, role)
            require(isinstance(baseline, EmptyPartBaseline) and baseline.xy_plane_proven is True
                    and baseline.model_canonical == document.canonical and type(baseline.features) is tuple
                    and baseline.features and all(isinstance(a, FixtureAnchor) for a in baseline.features)
                    and isinstance(baseline.xy_plane, FixtureAnchor)
                    and sum(a.canonical == baseline.xy_plane.canonical for a in baseline.features) == 1,
                    'Complete original empty template/actual XY-plane admission required.')
            receipt.baselines[role] = baseline
            receipt.anchors.extend(baseline.features)
            part = b.call(role + ':part_interface', wrap, document.handle, 'IPartDoc')
            require(not b.call(role + ':empty_bodies', part.GetBodies2, -1, False), 'Owned template must have no bodies.')
            require(b.call(role + ':title', document.handle.SetTitle2,
                           'Проверка B3 ' + role + ' ' + title_suffix) is True, 'Russian owned document title failed.')
            require(b.call(role + ':title_readback', document.handle.GetTitle) == 'Проверка B3 ' + role + ' ' + title_suffix,
                    'Russian owned document title readback differs.')
            cfg = b.anchor(role + '_Основная', 'configuration',
                           b.call(role + ':active_configuration', document.handle.GetActiveConfiguration), 'IConfiguration')
            original_name = b.call(role + ':original_configuration_name', getattr, cfg.handle, 'Name')
            initial_names = b.call(role + ':configuration_names', document.handle.GetConfigurationNames)
            require(isinstance(initial_names, (tuple, list)) and len(initial_names) == 1
                    and initial_names[0] == original_name,
                    'Owned template must have exactly its one original configuration.')
            receipt.configurations[role + '_Основная'] = cfg
            b.name(cfg, 'Основная')
            for i, anchor in enumerate(baseline.features):
                b.current(anchor)
                if b.call(role + ':template_feature_type', anchor.handle.GetTypeName2) == 'RefPlane':
                    b.name(anchor, 'Контрольная плоскость ' + str(i + 1))
            model = document.handle
            if role == 'Основная деталь':
                b.box(model, baseline.xy_plane, 'Первый', 0., .02, .01, .005)
                second = b.box(model, baseline.xy_plane, 'Второй', .04, .02, .01, .005)
                modeler = b.call('surface:modeler', wrap,
                    b.call('surface:modeler_raw', application.GetModeler), 'IModeler')
                surface = b.anchor('Поверхность', 'temporary_surface', b.call('surface:plane',
                    modeler.CreatePlanarSurface2, (.08, 0., 0.), (0., 0., 1.), (1., 0., 0.)), 'ISurface')
                sheet = b.anchor('Лист', 'temporary_body', b.call('surface:finite_sheet',
                    modeler.CreateSheetFromSurface, surface.handle, (0., .015, 0., .01)), 'IBody2')
                b.bounds(sheet, (.08, .095, 0., .01, 0., 0.))
                returned = b.call('surface:import', part.CreateSurfaceFeatureFromBody, sheet.handle, 0)
                require(isinstance(returned, (list, tuple)) and len(returned) == 1,
                        'Exactly one normally returned surface feature required; no fallback.')
                feature = b.anchor('Поверхность', 'feature', returned[0], 'IFeature')
                b.require_new_feature(feature, 'Surface import')
                receipt.features['Поверхность'] = feature
                b.name(feature, 'Контрольная поверхность')
                b.body_from_feature(feature, 'Поверхность', 1, (.08, .095, 0., .01, 0., 0.), part)
                variant = b.anchor('Вариант', 'configuration', b.call('configuration:add_variant',
                    model.AddConfiguration3, 'Вариант', '', '', 128), 'IConfiguration')
                receipt.configurations['Вариант'] = variant
                require(variant.canonical != cfg.canonical, 'Configuration creation returned the original main anchor.')
                require(b.call('configuration:variant_name', getattr, variant.handle, 'Name') == 'Вариант',
                        'Returned variant configuration name differs.')
                require(b.call('configuration:active_identity', identity,
                    b.call('configuration:active', model.GetActiveConfiguration)) == cfg.canonical,
                    'DontActivate configuration creation changed active configuration.')
                b.current(second)
                b.call('second:hide', second.handle.HideBody, True)
                require(b.call('second:hidden_readback', getattr, second.handle, 'Visible') is False,
                        'Exact second original body hide unconfirmed.')
            else:
                b.box(model, baseline.xy_plane, 'Сосед', 0., .005, .006, .007)
            require(b.call(role + ':rebuild', model.ForceRebuild3, False) is True, 'Owned fixture rebuild failed.')
            require(b.call(role + ':dirty', model.GetSaveFlag) is True, 'Owned unsaved fixture must remain dirty.')
            require(b.call(role + ':path', model.GetPathName) == '', 'Owned fixture unexpectedly acquired a saved file.')
            expected = [a for key, a in receipt.bodies.items() if (key == 'Сосед') == (role == 'Сосед')]
            roster = b.call(role + ':closing_body_census', part.GetBodies2, -1, False) or ()
            require(isinstance(roster, (tuple, list)) and len(roster) == len(expected)
                    and len(roster) <= (1 if role == 'Сосед' else 3),
                    'Full closing body census differs from original returned-feature owners.')
            current = [b.call(role + ':body_canonical', identity, raw) for raw in roster]
            require(len(current) == len(expected) and all(sum(x == a.canonical for x in current) == 1 for a in expected),
                    'Full closing body census differs from original returned-feature owners.')
            for anchor in expected:
                b.current(anchor)
            for inventory in (receipt.features, receipt.sketches):
                for key, anchor in inventory.items():
                    if (key == 'Сосед') == (role == 'Сосед'):
                        b.current(anchor)
            names = b.call(role + ':closing_configuration_names', model.GetConfigurationNames)
            require(isinstance(names, (tuple, list)) and len(names) == (2 if role == 'Основная деталь' else 1)
                    and set(names) == ({'Основная', 'Вариант'} if role == 'Основная деталь' else {'Основная'}),
                    'Complete closing configuration roster differs.')
            require(b.call(role + ':closing_active_identity', identity,
                           b.call(role + ':closing_active_configuration', model.GetActiveConfiguration)) == cfg.canonical,
                    'Original main active configuration changed.')
            b.current(document)
        receipt.setup_complete = True
        return receipt
    except BaseException:
        receipt.halted = True
        raise
