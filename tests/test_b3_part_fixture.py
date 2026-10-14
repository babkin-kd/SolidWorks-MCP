"""API-shaped artificial fixture handles; no SolidWorks connection or COM."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b3_part_fixture import (
        EmptyPartBaseline, FixtureAnchor, PartFixtureReceipt, create_part_fixture)
finally:
    sys.path.remove(scripts)


class Native:
    def __init__(self, world):
        self.world = world
        self.canonical = world.next_token
        world.next_token += 1
        self.Name = 'По умолчанию'


class Feature(Native):
    def __init__(self, world, model, kind, specific=None, body=None):
        super().__init__(world)
        self.model, self.kind, self.specific, self.body = model, kind, specific, body
        self.children = []

    def GetTypeName2(self):
        return self.kind

    def GetSpecificFeature2(self):
        return self.specific

    def Select2(self, append, mark):
        assert append is False and mark == 0
        self.model.selected = self
        return True

    def GetNextFeature(self):
        roster = self.model.features
        index = roster.index(self)
        return roster[index + 1] if index + 1 < len(roster) else None

    def GetFirstSubFeature(self):
        return None

    def GetNextSubFeature(self):
        return None

    def GetFaces(self):
        if self.world.foreign_feature_body:
            return [NS(GetBody=lambda: Body(self.world, self.body.bounds, self.body.kind)) for _ in self.body.faces]
        return self.body.faces


class Body(Native):
    def __init__(self, world, bounds, kind):
        super().__init__(world)
        self.bounds, self.kind, self.Visible = bounds, kind, True
        self.faces = [NS(GetBody=lambda: self) for _ in range(6 if kind == 0 else 1)]

    def GetType(self):
        return self.kind

    def GetExtremePoint(self, x, y, z):
        directions = x, y, z
        return (True,) + tuple(self.bounds[2 * i + (directions[i] > 0)] for i in range(3))

    def HideBody(self, hide):
        self.world.hidden.append(self)
        if not self.world.hide_failure:
            self.Visible = not hide


class Manager(Native):
    def __init__(self, world, model):
        super().__init__(world)
        self.model, self.ActiveSketch, self.AddToDB = model, None, False
        self.lines = []

    def InsertSketch(self, update):
        assert update is True
        if self.ActiveSketch is None:
            self.ActiveSketch = Native(self.world)
            self.lines = []
            self.model.features.append(Feature(self.world, self.model, 'ProfileFeature', self.ActiveSketch))
        elif not self.world.close_failure:
            self.ActiveSketch = None

    def CreateLine(self, *points):
        assert self.AddToDB is True and len(points) == 6
        self.lines.append(points)
        return Native(self.world)


class Model(Native):
    def __init__(self, world):
        super().__init__(world)
        self.features = [Feature(world, self, 'RefPlane') for _ in range(3)]
        self.cfg = Native(world)
        self.cfg.Name = 'По умолчанию'
        self.cfgs = [self.cfg]
        self.SketchManager = Manager(world, self)
        self.FeatureManager = NS(FeatureExtrusion3=self.extrude)
        self.bodies, self.selected, self.title = [], None, 'Деталь'

    def GetType(self):
        return 1

    def FirstFeature(self):
        return self.features[0]

    def GetBodies2(self, kind, visible_only):
        assert kind == -1 and visible_only is False
        roster = list(reversed(self.bodies))
        if self.world.extra_body and self.bodies:
            roster.append(Body(self.world, (0., .001, 0., .001, 0., .001), 0))
        return roster

    def SetTitle2(self, title):
        self.title = title
        return True

    def GetTitle(self):
        return self.title

    def GetActiveConfiguration(self):
        return self.cfg

    def GetConfigurationNames(self):
        return tuple(cfg.Name for cfg in self.cfgs)

    def ClearSelection2(self, all):
        self.selected = None

    def extrude(self, *args):
        self.world.extrusions.append(args)
        assert len(args) == 23 and args[17:20] == (False, True, True)
        lines = self.SketchManager.lines
        points = [line[:3] for line in lines]
        bounds = (min(x[0] for x in points), max(x[0] for x in points),
                  min(x[1] for x in points), max(x[1] for x in points), 0., args[5])
        body = Body(self.world, bounds, 0)
        self.bodies.append(body)
        feature = Feature(self.world, self, 'Boss', body=body)
        self.features.append(feature)
        self.world.returned_features.append(feature)
        if self.world.null_extrusion:
            return None
        return feature

    def CreateSurfaceFeatureFromBody(self, sheet, options):
        assert options == 0 and sheet.kind == 1
        self.world.imports += 1
        body = Body(self.world, sheet.bounds, 1)
        feature = Feature(self.world, self, 'SurfaceBody', body=body)
        self.bodies.append(body)
        self.features.append(feature)
        self.world.returned_features.append(feature)
        return [feature] * self.world.surface_feature_count

    def AddConfiguration3(self, name, comment, alternate, options):
        assert options == 128 and name == 'Вариант'
        cfg = Native(self.world)
        cfg.Name = name
        self.cfgs.append(cfg)
        if self.world.activate_variant:
            self.cfg = cfg
        return cfg

    def ForceRebuild3(self, top_only):
        return not self.world.rebuild_failure

    def GetSaveFlag(self):
        return True

    def GetPathName(self):
        return ''


class World:
    def __init__(self):
        self.next_token = 1
        self.models, self.events, self.hidden, self.extrusions, self.returned_features = [], [], [], [], []
        self.imports = 0
        self.null_extrusion = self.foreign_feature_body = self.extra_body = False
        self.close_failure = self.hide_failure = self.activate_variant = self.rebuild_failure = False
        self.sheet_wrong_bounds = False
        self.surface_feature_count = 1
        self.admitted = self.empty_admitted = self.safe = True
        self.failure = None
        self.receipt = PartFixtureReceipt('explicit-request')
        self.template = Path('C:/controlled-template/controlled.prtdot')
        self.application = NS(NewDocument=self.new_document, GetModeler=lambda: self.modeler)
        self.modeler = NS(CreatePlanarSurface2=self.surface, CreateSheetFromSurface=self.sheet)

    def new_document(self, template, paper, width, height):
        assert template == str(self.template) and (paper, width, height) == (0, 0., 0.)
        model = Model(self)
        self.models.append(model)
        return model

    def surface(self, root, normal, ref):
        assert (root, normal, ref) == ((.08, 0., 0.), (0., 0., 1.), (1., 0., 0.))
        surface = Native(self)
        return surface

    def sheet(self, surface, uv):
        assert uv == (0., .015, 0., .01)
        return Body(self, (.08, .095, 0., .01, 0., .001 if self.sheet_wrong_bounds else 0.), 1)

    def recorder(self, label, phase, data):
        json.dumps(data)
        self.events.append((label, phase, dict(data)))
        if self.failure == (label, phase):
            raise RuntimeError('durable recorder failed')

    def baseline(self, document, receipt, role):
        model = document.handle
        anchors = tuple(FixtureAnchor(role + '_plane_' + str(i), 'feature', f, f.canonical)
                        for i, f in enumerate(model.features))
        return EmptyPartBaseline(document.canonical, anchors, anchors[0], self.empty_admitted)

    def run(self, **overrides):
        args = dict(receipt=self.receipt, application=self.application, template=str(self.template),
                    title_suffix='source_test', wrap=lambda raw, interface: raw,
                    identity=lambda obj: obj.canonical, assert_safe=lambda receipt: self.safe,
                    recorder=self.recorder, admit_application=lambda *args: self.admitted,
                    admit_empty_part=self.baseline)
        args.update(overrides)
        return create_part_fixture(**args)


@pytest.fixture
def world(monkeypatch):
    world = World()
    # Artificial configured file admission; no real template or CAD data is used.
    monkeypatch.setattr(Path, 'is_file', lambda path: path == world.template)
    return world


def test_finite_profile_uses_original_feature_body_owners_and_retains_handles(world):
    r = world.run()
    assert r.setup_complete and not r.accepted and not r.native_acceptance and not r.cleanup_authorized
    assert set(r.documents) == {'Основная деталь', 'Сосед'}
    assert len(world.models[0].bodies) == 3 and len(world.models[1].bodies) == 1
    assert r.bodies['Первый'].handle.bounds == (0., .02, 0., .01, 0., .005)
    assert r.bodies['Второй'].handle.bounds == (.04, .06, 0., .01, 0., .005)
    assert r.bodies['Поверхность'].handle.bounds == (.08, .095, 0., .01, 0., 0.)
    assert r.bodies['Сосед'].handle.bounds == (0., .005, 0., .006, 0., .007)
    assert world.hidden == [r.bodies['Второй'].handle]
    assert r.bodies['Второй'].handle.Visible is False
    assert r.configurations['Вариант'].handle.Name == 'Вариант'
    assert world.models[0].cfg is r.configurations['Основная деталь_Основная'].handle
    assert len(r.sketches) == 3 and len(world.extrusions) == 3
    assert all(a.canonical == a.handle.canonical for a in r.anchors)
    assert all(f.handle in world.returned_features for f in r.features.values())
    assert len(r.native_returns) * 2 == len(world.events)
    for pending, returned in zip(world.events[::2], world.events[1::2]):
        assert pending[0] == returned[0] and (pending[1], returned[1]) == ('pending', 'returned')
        assert pending[2]['native_call_returned'] is False and returned[2]['native_call_returned'] is True


@pytest.mark.parametrize('phase', ['pending', 'returned'])
@pytest.mark.parametrize('label', ['Основная деталь:new_document', 'Первый:open_sketch',
                                  'Первый:extrude', 'surface:import', 'second:hide'])
def test_recorder_loss_latches_and_retains_all_normal_returns_without_retry(world, phase, label):
    world.failure = label, phase
    with pytest.raises(RuntimeError, match='recorder'):
        world.run()
    r = world.receipt
    assert r.halted and r.journal_lost and r.pending_step == label and not r.setup_complete
    recorded = [entry for entry in r.native_returns if entry[1] == label]
    assert bool(recorded) == (phase == 'returned')
    if label == 'Основная деталь:new_document':
        assert len(world.models) == (phase == 'returned')
        if recorded:
            assert recorded[0][2] is world.models[0]
    if label == 'Первый:extrude' and recorded:
        assert recorded[0][2] is world.returned_features[0]
    before = len(world.events), len(world.models), len(world.extrusions), world.imports
    with pytest.raises(ValueError, match='Fresh'):
        world.run()
    assert before == (len(world.events), len(world.models), len(world.extrusions), world.imports)


def test_native_exception_stays_pending_and_never_acknowledges_return(world):
    def fail(*args):
        raise RuntimeError('native outcome unknown')
    world.application.NewDocument = fail
    with pytest.raises(RuntimeError, match='unknown'):
        world.run()
    assert world.receipt.pending_step == 'Основная деталь:new_document'
    assert world.receipt.halted and not world.receipt.journal_lost
    assert world.events[-1][1] == 'pending'
    assert not world.receipt.documents


@pytest.mark.parametrize('flag,message', [
    ('empty_admitted', 'template/actual XY'), ('admitted', 'application/owned')])
def test_parent_admission_rejection_does_not_borrow_or_guess_scope(world, flag, message):
    setattr(world, flag, False)
    with pytest.raises(ValueError, match=message):
        world.run()
    assert world.receipt.halted and not world.extrusions
    assert len(world.models) == (flag == 'empty_admitted')


@pytest.mark.parametrize('flag,message', [
    ('null_extrusion', 'normally returned feature'),
    ('foreign_feature_body', 'different body owners'),
    ('extra_body', 'body membership census'),
    ('close_failure', 'sketch close'),
    ('hide_failure', 'hide unconfirmed'),
    ('activate_variant', 'changed active configuration'),
    ('rebuild_failure', 'rebuild failed'),
    ('sheet_wrong_bounds', 'native extrema'),
])
def test_failed_native_postconditions_keep_owner_without_followup_mutations(world, flag, message):
    setattr(world, flag, True)
    with pytest.raises(ValueError, match=message):
        world.run()
    assert world.receipt.halted and not world.receipt.setup_complete
    assert len(world.models) == 1
    if flag == 'sheet_wrong_bounds':
        assert world.imports == 0


@pytest.mark.parametrize('count', [0, 2])
def test_import_array_must_provide_one_actual_returned_feature(world, count):
    world.surface_feature_count = count
    with pytest.raises(ValueError, match='Exactly one'):
        world.run()
    assert world.imports == 1 and world.receipt.halted
    assert not world.hidden and len(world.models) == 1
    assert any(label == 'surface:import' for _, label, _ in world.receipt.native_returns)


@pytest.mark.parametrize('invalid', ['missing', 'relative', 'wrong_extension'])
def test_template_preflight_never_falls_back_to_NewPart(world, invalid):
    template = {'missing': str(world.template.parent / 'missing.prtdot'), 'relative': 'relative.prtdot',
                'wrong_extension': str(world.template.with_suffix('.sldprt'))}[invalid]
    with pytest.raises(ValueError, match='template'):
        world.run(template=template)
    assert not world.models and not world.events and not world.receipt.attempted


def test_guard_rejection_before_any_call(world):
    world.safe = False
    with pytest.raises(ValueError, match='guard admission'):
        world.run()
    assert not world.events and not world.models


def test_same_thread_custody_is_required_before_native_dispatch(world):
    world.receipt.thread_id = -1
    with pytest.raises(ValueError, match='STA'):
        world.run()
    assert not world.events and not world.models


def test_guard_loss_after_raw_document_return_retains_owner_before_readback(world):
    original = world.recorder
    def recorder(label, phase, data):
        original(label, phase, data)
        if (label, phase) == ('Основная деталь:new_document', 'returned'):
            world.safe = False
    with pytest.raises(ValueError, match='guard admission'):
        world.run(recorder=recorder)
    assert world.receipt.halted and len(world.models) == 1
    assert world.receipt.native_returns[-1][2] is world.models[0]
    assert world.events[-1][:2] == ('Основная деталь:new_document', 'returned')


def test_same_name_replacement_plane_does_not_get_adopted(world):
    original = world.recorder
    def recorder(label, phase, data):
        original(label, phase, data)
        if (label, phase) == ('Основная деталь:template_feature_type', 'returned'):
            world.models[0].features[0].canonical += 10000
    with pytest.raises(ValueError, match='anchor changed'):
        world.run(recorder=recorder)
    assert not world.extrusions and world.receipt.halted


def test_reused_original_body_is_rejected_before_body_rename(world, monkeypatch):
    original = Model.extrude
    def extrude(model, *args):
        feature = original(model, *args)
        if len(model.bodies) == 2:
            feature.body = model.bodies[0]
        return feature
    monkeypatch.setattr(Model, 'extrude', extrude)
    with pytest.raises(ValueError, match='earlier original body'):
        world.run()
    assert world.models[0].bodies[0].Name == 'Контрольное тело Первый'
    assert set(world.receipt.bodies) == {'Первый'}
    assert not world.hidden


def test_reused_original_feature_is_rejected_before_feature_rename(world, monkeypatch):
    original = Model.extrude
    def extrude(model, *args):
        feature = original(model, *args)
        return world.returned_features[0] if len(model.bodies) == 2 else feature
    monkeypatch.setattr(Model, 'extrude', extrude)
    with pytest.raises(ValueError, match='earlier original feature'):
        world.run()
    assert world.returned_features[0].Name == 'Контрольный блок Первый'
    assert not world.hidden


def test_reused_original_document_is_rejected_before_new_title(world):
    original = world.new_document
    def new_document(*args):
        return world.models[0] if world.models else original(*args)
    world.application.NewDocument = new_document
    with pytest.raises(ValueError, match='earlier original document'):
        world.run()
    assert world.models[0].title == 'Проверка B3 Основная деталь source_test'
    assert len(world.receipt.documents) == 1 and world.receipt.halted


def test_template_with_extra_configuration_is_not_silently_reused(world):
    original = world.baseline
    def baseline(document, receipt, role):
        document.handle.cfgs.append(Native(world))
        return original(document, receipt, role)
    with pytest.raises(ValueError, match='one original configuration'):
        world.run(admit_empty_part=baseline)
    assert not world.extrusions and world.models[0].cfg.Name == 'По умолчанию'


def test_membership_failure_precedes_native_body_naming(world):
    world.extra_body = True
    with pytest.raises(ValueError, match='body membership census'):
        world.run()
    assert world.models[0].bodies[0].Name == 'По умолчанию'
    assert not world.receipt.bodies


@pytest.mark.parametrize('field,value', [('request_id', ''), ('recorder', None)])
def test_explicit_durable_contract_is_required_before_dispatch(world, field, value):
    overrides = {}
    if field == 'request_id':
        world.receipt.request_id = value
    else:
        overrides[field] = value
    with pytest.raises(ValueError):
        world.run(**overrides)
    assert not world.events and not world.models


def test_absorbed_sketch_repeated_in_main_and_sub_walk_has_one_canonical_result(world, monkeypatch):
    original = Feature.GetFirstSubFeature
    def child(feature):
        if feature.kind == 'Boss':
            index = feature.model.features.index(feature)
            return feature.model.features[index - 1]
        return original(feature)
    monkeypatch.setattr(Feature, 'GetFirstSubFeature', child)
    # First block's same exact profile occurs in main and absorbed walks while
    # second.box resolves its newly returned sketch. Canonical output is unique.
    assert world.run().setup_complete
    assert len(world.extrusions) == 3 and len(world.receipt.sketches) == 3


@pytest.mark.parametrize('operation', ['extrude', 'surface'])
@pytest.mark.parametrize('existing', ['template', 'sketch'])
def test_returned_existing_template_or_sketch_feature_cannot_be_renamed(world, monkeypatch, operation, existing):
    target = []
    def existing_feature(model):
        feature = model.features[0] if existing == 'template' else next(
            f for f in reversed(model.features) if f.kind == 'ProfileFeature')
        target.append((feature, feature.Name))
        return feature
    if operation == 'extrude':
        original = Model.extrude
        def extrude(model, *args):
            original(model, *args)
            return existing_feature(model)
        monkeypatch.setattr(Model, 'extrude', extrude)
    else:
        original = Model.CreateSurfaceFeatureFromBody
        def surface(model, *args):
            original(model, *args)
            return [existing_feature(model)]
        monkeypatch.setattr(Model, 'CreateSurfaceFeatureFromBody', surface)
    with pytest.raises(ValueError, match='earlier original feature'):
        world.run()
    feature, original_name = target[0]
    assert feature.Name == original_name and world.receipt.halted
    assert len(world.models) == 1 and not world.hidden


@pytest.mark.parametrize('phase', ['membership', 'closing'])
@pytest.mark.parametrize('role', ['Основная деталь', 'Сосед'])
def test_oversized_roster_is_rejected_before_any_member_identity_calls(world, monkeypatch, phase, role):
    class ForbiddenMember:
        @property
        def canonical(self):
            raise AssertionError('Huge unsupported roster member was inspected')
    bomb = ForbiddenMember()
    closing_models = []
    original_rebuild = Model.ForceRebuild3
    def rebuild(model, *args):
        result = original_rebuild(model, *args)
        closing_models.append(model)
        return result
    monkeypatch.setattr(Model, 'ForceRebuild3', rebuild)
    original_roster = Model.GetBodies2
    def roster(model, *args):
        result = original_roster(model, *args)
        model_role = 'Основная деталь' if model is world.models[0] else 'Сосед'
        if model_role == role and result and (phase == 'membership' or model in closing_models):
            return [bomb] * 10000
        return result
    monkeypatch.setattr(Model, 'GetBodies2', roster)
    with pytest.raises(ValueError, match='body membership census' if phase == 'membership' else 'closing body census'):
        world.run()
    assert world.receipt.halted and world.events[-1][1] == 'returned'
    assert world.events[-1][0].endswith(':body_membership' if phase == 'membership' else ':closing_body_census')
