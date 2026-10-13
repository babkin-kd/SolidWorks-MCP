"""API-shaped artificial cylinder handles. No CAD, connection or COM calls."""
from dataclasses import replace
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b3_cylinder_fixture import (
        BOUNDS_M, CylinderEmptyBaseline, create_cylinder_fixture, validated_plane_transform)
    from verifier_b3_part_fixture import FixtureAnchor, PartFixtureReceipt
    from verifier_b3_empty_template import EmptyTemplateReceipt,capture_empty_template
    from verifier_b3_application_admission import ApplicationAdmissionReceipt,capture_empty_application,admit_fixture_application
    from verify_export_operations import PREFS
finally:
    sys.path.remove(scripts)


POSITIVE_FRAME = (1., 0., 0., 0., 0., -1., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0.)
NEGATIVE_FRAME = (1., 0., 0., 0., 0., 1., 0., -1., 0., 0., 0., 0., 1., 0., 0., 0.)


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

    def GetTypeName2(self):
        return self.kind

    def GetSpecificFeature2(self):
        return self.specific

    def Select2(self, append, mark):
        assert append is False and mark == 0
        self.model.selected = self.model.features[0] if self.world.wrong_selection else self
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
            return [Face(self.world, Body(self.world)) for _ in range(3)]
        if self.world.duplicate_faces:
            return [self.body.faces[0]] * 3
        return self.body.faces


class Face(Native):
    def __init__(self, world, body):
        super().__init__(world)
        self.body = body

    def GetBody(self):
        return self.body


class Body(Native):
    def __init__(self, world):
        super().__init__(world)
        self.faces = [Face(world, self) for _ in range(3)]
        self.bounds = BOUNDS_M

    def GetType(self):
        return self.world.body_type

    def IsMeshBody(self):
        return self.world.mesh

    def GetFaces(self):
        return [Face(self.world, self)] * 3 if self.world.foreign_body_faces else self.faces

    def GetFaceCount(self):
        return len(self.faces)

    def GetExtremePoint(self, x, y, z):
        return (not self.world.extrema_failed,) + tuple(
            self.bounds[2*i + (sign > 0)] + (0.001 if self.world.wrong_size else 0.)
            for i, sign in enumerate((x, y, z)))


class Sketch(Native):
    def __init__(self, world):
        super().__init__(world)
        self.segments = []

    def GetSketchSegments(self):
        return self.segments


class Manager:
    def __init__(self, world, model):
        self.world, self.model = world, model
        self.ActiveSketch, self.AddToDB = None, False

    def InsertSketch(self, update):
        assert update is True
        if self.ActiveSketch is None:
            sketch = Sketch(self.world)
            self.ActiveSketch = sketch
            self.model.features.append(Feature(self.world, self.model, 'ProfileFeature', sketch))
            if self.world.ambiguous_sketch:
                self.model.features.append(Feature(self.world, self.model, 'ProfileFeature', sketch))
        elif not self.world.close_failure:
            self.ActiveSketch = None

    def CreateCircleByRadius(self, x, y, z, radius):
        assert self.AddToDB is True and (x, y, z, radius) == (0., 0., 0., .006)
        self.world.circles += 1
        circle = Native(self.world)
        self.ActiveSketch.segments.append(circle)
        return None if self.world.null_circle else circle


class Model(Native):
    def __init__(self, world):
        super().__init__(world)
        self.features = [Feature(world, self, 'RefPlane') for _ in range(3)]
        self.cfg = Native(world)
        self.cfgs = [self.cfg]
        self.SketchManager = Manager(world, self)
        self.FeatureManager = NS(FeatureExtrusion3=self.extrude)
        self.SelectionManager = NS(GetSelectedObjectCount2=lambda mark: int(self.selected is not None),
            GetSelectedObject6=lambda index, mark: self.selected, GetSelectedObjectMark=lambda index: 0)
        self.bodies, self.selected, self.title = [], None, 'Деталь'

    def GetType(self):
        return 1

    def FirstFeature(self):
        return self.features[0]

    def GetBodies2(self, kind, visible_only):
        assert kind == -1 and visible_only is False
        return self.bodies + ([Body(self.world)] if self.world.extra_body and self.bodies else [])

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
        assert all is True
        self.selected = None

    def extrude(self, *args):
        self.world.extrusions.append(args)
        assert len(args) == 23 and args[2] == (self.world.transform[7] < 0)
        assert args[5] == .030 and args[17:20] == (False, True, True)
        assert self.SketchManager.ActiveSketch is None and self.selected.kind == 'ProfileFeature'
        body = Body(self.world)
        self.bodies.append(body)
        feature = Feature(self.world, self, 'Boss', body=body)
        self.features.append(feature)
        self.world.returned_feature = feature
        if self.world.old_return:
            return self.features[0] if self.world.old_return == 'template' else self.selected
        return None if self.world.null_extrusion else feature

    def ForceRebuild3(self, top_only):
        return True

    def GetSaveFlag(self):
        return True

    def GetPathName(self):
        return ''


class World:
    def __init__(self):
        self.next_token, self.circles = 1, 0
        self.models, self.events, self.extrusions = [], [], []
        self.receipt = PartFixtureReceipt('explicit-cylinder-request')
        self.template = Path('C:/controlled-template/controlled.prtdot')
        self.application = NS(NewDocument=self.new_document)
        self.transform = POSITIVE_FRAME
        self.safe = self.admitted = self.empty_admitted = True
        self.body_type = 0
        self.failure = self.old_return = None
        self.null_circle = self.null_extrusion = self.mesh = self.wrong_size = self.extrema_failed = False
        self.foreign_feature_body = self.foreign_body_faces = self.extra_body = self.duplicate_faces = False
        self.close_failure = self.wrong_selection = self.ambiguous_sketch = False

    def new_document(self, template, paper, width, height):
        assert template == str(self.template) and (paper, width, height) == (0, 0., 0.)
        model = Model(self)
        self.models.append(model)
        return model

    def recorder(self, label, phase, data):
        json.dumps(data)
        self.events.append((label, phase, dict(data)))
        if self.failure == (label, phase):
            raise RuntimeError('durable recorder failed')

    def baseline(self, document, receipt, role):
        features = tuple(FixtureAnchor(role + '_плоскость_' + str(i), 'feature', f, f.canonical)
                         for i, f in enumerate(document.handle.features))
        # Admission explicitly returns the original plane, even though it is
        # neither a chosen native name nor the first/last feature in the tree.
        return CylinderEmptyBaseline(document.canonical, features, features[1], self.transform, self.empty_admitted)

    def run(self, **overrides):
        args = dict(receipt=self.receipt, application=self.application, template=str(self.template),
                    title_suffix='source_test', wrap=lambda raw, interface: raw,
                    identity=lambda obj: obj.canonical, assert_safe=lambda receipt: self.safe,
                    recorder=self.recorder, admit_application=lambda *args: self.admitted,
                    admit_empty_part=self.baseline)
        args.update(overrides)
        return create_cylinder_fixture(**args)


@pytest.fixture
def world(monkeypatch):
    result = World()
    monkeypatch.setattr(Path, 'is_file', lambda path: path == result.template)
    return result


@pytest.mark.parametrize('frame', [POSITIVE_FRAME, NEGATIVE_FRAME])
def test_complete_original_y_cylinder_success_has_no_native_or_cleanup_acceptance(world, frame):
    world.transform = frame
    r = world.run()
    assert r.setup_complete and not r.accepted and not r.native_acceptance and not r.cleanup_authorized
    assert r.remaining_profile == ('same_wheel_B1_sketch', 'whole_session_original_baseline', '13_named_B3_groups')
    assert len(world.models) == 1 and len(world.extrusions) == world.circles == 1
    assert list(r.documents) == list(r.bodies) == list(r.features) == list(r.sketches) == ['Цилиндр']
    assert r.bodies['Цилиндр'].handle.bounds == BOUNDS_M
    assert r.features['Цилиндр'].handle is world.returned_feature
    model = world.models[0]
    assert model.GetConfigurationNames() == ('Основная',) and model.selected is None
    assert model.GetPathName() == '' and model.GetSaveFlag() is True
    assert model.SketchManager.AddToDB is False and model.SketchManager.ActiveSketch is None
    assert len(r.native_returns) * 2 == len(world.events)
    for pending, returned in zip(world.events[::2], world.events[1::2]):
        assert pending[0] == returned[0] and (pending[1], returned[1]) == ('pending', 'returned')
        assert not pending[2]['native_call_returned'] and returned[2]['native_call_returned']


def test_normally_returned_none_is_allowed_only_for_empty_body_baseline(world, monkeypatch):
    original=Model.GetBodies2
    monkeypatch.setattr(Model,'GetBodies2',lambda model,*args:
        None if not model.bodies else original(model,*args))
    assert world.run().setup_complete is True


def test_none_current_body_census_cannot_hide_the_created_cylinder(world, monkeypatch):
    monkeypatch.setattr(Model,'GetBodies2',lambda *args:None)
    with pytest.raises(ValueError,match='body membership census'):world.run()
    assert world.receipt.halted and world.receipt.setup_complete is False


@pytest.mark.parametrize('frame',[POSITIVE_FRAME,NEGATIVE_FRAME])
def test_native_shaped_empty_admission_feeds_actual_cylinder_builder_under_its_pending_ledger(world,frame):
    world.transform=frame
    admission=EmptyTemplateReceipt()
    xy=(1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.,1.,0.,0.,0.)
    normal_x=(0.,1.,0.,0.,0.,1.,1.,0.,0.,0.,0.,0.,1.,0.,0.,0.)
    adapter=NS(_sw=NS(CommandInProgress=True),identity=lambda obj:obj.canonical,
        native_close_windows=lambda:[(world.models[0],dict(hwnd=101))],
        snapshot=lambda model:dict(path=model.GetPathName(),document_type='part',needs_save=bool(model.bodies),
            configurations=list(model.GetConfigurationNames()),active_configuration=model.cfg.Name),
        native_close_model_context=lambda model:dict(dependencies=[],mode=dict(editing_sketch=False,
            editing_component=False,view_only=False,read_only_state=0,blocking_state=0)),
        features=lambda model:tuple(model.features),
        reference_plane_transform=lambda feature:(xy,frame,normal_x)[feature.model.features.index(feature)])
    def admit(document,fixture,role):
        assert fixture.pending_step=='cylinder:empty_admission'
        captured=capture_empty_template(receipt=admission,fixture=fixture,document=document,
            original_documents=(document,),adapter=adapter,wrap=lambda raw,interface:raw,
            assert_safe=lambda current:current is fixture,watch_poll=lambda:0)
        return captured.cylinder_baseline()
    completed=world.run(admit_empty_part=admit)
    assert completed.setup_complete and admission.complete
    assert completed.baselines['Цилиндр'].plane is admission.features[1]
    assert completed.baselines['Цилиндр'].transform==frame
    assert completed.accepted is admission.accepted is False


def test_original_application_baseline_and_startup_admission_feed_the_cylinder_owner(world):
    app=world.application
    app.canonical=object();app.CommandInProgress=False;app.ActiveDoc=None
    native_new=app.NewDocument
    def new_document(*args):
        model=native_new(*args);app.ActiveDoc=model;return model
    app.NewDocument=new_document
    context=dict(user_control=True,visible=True,current_directory='private_test',search_folders='')
    values={'String':'','Toggle':False,'Integer':0,'Double':0.}
    prefs={name:values[kind] for name,(kind,_) in PREFS.items()}
    adapter=NS(_sw=app,identity=lambda obj:obj.canonical,documents=lambda:list(world.models),
        native_close_windows=lambda:[(model,dict(hwnd=101+i)) for i,model in enumerate(world.models)],
        native_close_application_context=lambda:dict(context))
    before=ApplicationAdmissionReceipt();startup=ApplicationAdmissionReceipt()
    baseline=capture_empty_application(receipt=before,adapter=adapter,preference_reader=lambda:dict(prefs),
        assert_safe=lambda:world.safe,watch_poll=lambda:0)
    app.CommandInProgress=True # Caller-owned guard acquisition; helpers contain no setter.
    def admit(application,fixture):
        assert application is app and fixture.pending_step=='application:admission'
        return admit_fixture_application(receipt=startup,baseline=baseline,baseline_receipt=before,
            fixture=fixture,prior_fixtures=(),adapter=adapter,preference_reader=lambda:dict(prefs),
            assert_safe=lambda:world.safe,watch_poll=lambda:0)
    completed=world.run(admit_application=admit)
    assert before.complete and startup.complete and completed.setup_complete
    assert len(world.models)==1 and app.ActiveDoc is completed.documents['Цилиндр'].handle
    assert before.accepted is startup.accepted is completed.accepted is False
    assert startup.preference_evidence['baseline']['scope_exactly_equal'] is True


@pytest.mark.parametrize('phase', ['pending', 'returned'])
@pytest.mark.parametrize('label', ['cylinder:new_document', 'cylinder:open_sketch',
                                  'cylinder:circle', 'cylinder:extrude'])
def test_recorder_loss_retains_raw_normal_return_before_ack_and_never_retries(world, label, phase):
    world.failure = label, phase
    with pytest.raises(RuntimeError, match='recorder'):
        world.run()
    r = world.receipt
    assert r.halted and r.journal_lost and r.pending_step == label and not r.setup_complete
    raw = [value for _, step, value in r.native_returns if step == label]
    assert bool(raw) == (phase == 'returned')
    if label == 'cylinder:new_document' and raw:
        assert raw[0] is world.models[0]
    if label == 'cylinder:extrude' and raw:
        assert raw[0] is world.returned_feature
    before = len(world.events), len(world.models), len(world.extrusions), world.circles
    with pytest.raises(ValueError, match='Fresh'):
        world.run()
    assert before == (len(world.events), len(world.models), len(world.extrusions), world.circles)


def test_native_unknown_outcome_remains_pending_without_return_or_followup(world):
    def fail(*args):
        raise RuntimeError('unknown native outcome')
    world.application.NewDocument = fail
    with pytest.raises(RuntimeError, match='unknown'):
        world.run()
    assert world.receipt.halted and world.receipt.pending_step == 'cylinder:new_document'
    assert not world.receipt.journal_lost and world.events[-1][1] == 'pending'


@pytest.mark.parametrize('state', ['pending', 'halted', 'journal_lost', 'thread', 'process'])
def test_original_owner_guard_blocks_dispatch(world, state):
    if state == 'thread':
        world.receipt.thread_id = -1
    elif state == 'process':
        world.safe = False
    elif state == 'pending':
        world.receipt.pending_step = 'unconfirmed-call'
    else:
        setattr(world.receipt, state, True)
    with pytest.raises(ValueError):
        world.run()
    assert not world.events and not world.models


def test_guard_loss_after_document_return_holds_raw_handle_and_stops(world):
    original = world.recorder
    def recorder(label, phase, data):
        original(label, phase, data)
        if (label, phase) == ('cylinder:new_document', 'returned'):
            world.safe = False
    with pytest.raises(ValueError, match='guard admission'):
        world.run(recorder=recorder)
    assert world.receipt.halted and len(world.models) == 1
    assert world.receipt.native_returns[-1][2] is world.models[0]


@pytest.mark.parametrize('flag,message', [
    ('null_circle', 'normally returned segment'), ('null_extrusion', 'normally returned feature'),
    ('foreign_feature_body', 'different body owners'), ('foreign_body_faces', 'complete original body membership'),
    ('duplicate_faces', 'duplicated'), ('extra_body', 'body membership census'),
    ('mesh', 'normal solid'), ('wrong_size', 'native extrema'), ('extrema_failed', 'Unconfirmed native extrema'),
    ('close_failure', 'sketch close'), ('wrong_selection', 'owned selection'),
    ('ambiguous_sketch', 'unique canonical feature'),
])
def test_invalid_original_postcondition_latches_without_native_cleanup(world, flag, message):
    setattr(world, flag, True)
    with pytest.raises(ValueError, match=message):
        world.run()
    assert world.receipt.halted and not world.receipt.setup_complete
    assert len(world.models) == 1 and len(world.extrusions) <= 1


@pytest.mark.parametrize('kind', [1, 2, True, 0.])
def test_only_normal_typed_solid_is_accepted_before_body_naming(world, kind):
    world.body_type = kind
    with pytest.raises(ValueError, match='normal solid'):
        world.run()
    assert world.models[0].bodies[0].Name == 'По умолчанию'


@pytest.mark.parametrize('old', ['template', 'sketch'])
def test_old_feature_return_rejected_before_any_feature_rename(world, old):
    world.old_return = old
    with pytest.raises(ValueError, match='earlier original feature'):
        world.run()
    expected = 'Контрольная плоскость 1' if old == 'template' else 'Контрольный эскиз цилиндра'
    actual = world.models[0].features[0] if old == 'template' else world.models[0].selected
    assert actual.Name == expected and not world.receipt.features


@pytest.mark.parametrize('invalid', ['foreign_model', 'missing_plane', 'partial_tree', 'unproven', 'duplicate_tree'])
def test_empty_admission_requires_original_complete_owner_and_plane(world, invalid):
    original = world.baseline
    def baseline(*args):
        b = original(*args)
        if invalid == 'foreign_model':
            return replace(b, model_canonical=-1)
        if invalid == 'missing_plane':
            return replace(b, plane=FixtureAnchor('foreign', 'feature', object(), -1))
        if invalid == 'partial_tree':
            return replace(b, features=b.features[:2])
        if invalid == 'unproven':
            return replace(b, plane_proven=False)
        return replace(b, features=b.features + (b.features[0],))
    with pytest.raises(ValueError, match='admission|census'):
        world.run(admit_empty_part=baseline)
    assert not world.extrusions and world.circles == 0 and world.models[0].title == 'Деталь'


@pytest.mark.parametrize('index,value', [(6, 1.), (7, 0.), (9, .001), (12, 2.), (0, -1.), (3, .1), (0, float('nan'))])
def test_plane_frame_must_be_origin_centered_right_handed_unit_y_normal(world, index, value):
    data = list(POSITIVE_FRAME)
    data[index] = value
    world.transform = tuple(data)
    with pytest.raises(ValueError, match='native transform|Y-normal'):
        world.run()
    assert world.circles == 0 and not world.extrusions


@pytest.mark.parametrize('values', [(), POSITIVE_FRAME[:15], POSITIVE_FRAME + (0.,), (True,) + POSITIVE_FRAME[1:]])
def test_complete_typed_plane_transform_required(values):
    with pytest.raises(ValueError, match='native transform'):
        validated_plane_transform(values)


@pytest.mark.parametrize('template', ['relative.prtdot', 'C:/controlled-template/missing.prtdot',
                                      'C:/controlled-template/controlled.sldprt'])
def test_explicit_existing_absolute_template_required_before_dispatch(world, template):
    with pytest.raises(ValueError, match='template'):
        world.run(template=template)
    assert not world.events and not world.receipt.attempted


def test_application_admission_rejection_before_new_document(world):
    world.admitted = False
    with pytest.raises(ValueError, match='application/owned'):
        world.run()
    assert not world.models and not world.extrusions


def test_complete_original_closing_body_census_is_required(world, monkeypatch):
    original = Model.ForceRebuild3
    def rebuild(model, *args):
        result = original(model, *args)
        world.extra_body = True
        return result
    monkeypatch.setattr(Model, 'ForceRebuild3', rebuild)
    with pytest.raises(ValueError, match='body membership census'):
        world.run()
    assert world.receipt.halted and not world.receipt.setup_complete


@pytest.mark.parametrize('change', ['replace_faces', 'foreign_owner', 'wrong_kind'])
def test_rebuild_does_not_allow_replacement_faces_owner_or_non_solid(world, monkeypatch, change):
    original = Model.ForceRebuild3
    def rebuild(model, *args):
        result = original(model, *args)
        if change == 'replace_faces':
            model.bodies[0].faces = [Face(world, model.bodies[0]) for _ in range(3)]
        elif change == 'foreign_owner':
            model.bodies[0].faces[0].body = Body(world)
        else:
            world.body_type = 1
        return result
    monkeypatch.setattr(Model, 'ForceRebuild3', rebuild)
    with pytest.raises(ValueError, match='closing cylinder'):
        world.run()
    assert world.receipt.halted and not world.receipt.setup_complete


def test_new_sketch_must_start_empty_before_circle_creation(world, monkeypatch):
    original = Manager.InsertSketch
    def insert(manager, *args):
        result = original(manager, *args)
        if manager.ActiveSketch is not None:
            manager.ActiveSketch.segments.append(Native(world))
        return result
    monkeypatch.setattr(Manager, 'InsertSketch', insert)
    with pytest.raises(ValueError, match='must start empty'):
        world.run()
    assert world.circles == 0 and not world.extrusions


def test_false_selection_mark_is_not_integer_zero(world, monkeypatch):
    original = Model.__init__
    def initialize(model, *args):
        original(model, *args)
        model.SelectionManager.GetSelectedObjectMark = lambda index: False
    monkeypatch.setattr(Model, '__init__', initialize)
    with pytest.raises(ValueError, match='selection/mark'):
        world.run()
    assert world.circles == 0 and not world.extrusions


def test_oversized_body_census_rejected_without_adopting_member(world, monkeypatch):
    original = Model.GetBodies2
    class Foreign:
        @property
        def canonical(self):
            raise AssertionError('An oversized foreign roster must never be inspected.')
    def bodies(model, *args):
        result = original(model, *args)
        return [Foreign()] * 10000 if result else result
    monkeypatch.setattr(Model, 'GetBodies2', bodies)
    with pytest.raises(ValueError, match='body membership census'):
        world.run()
    assert world.receipt.halted and world.models[0].bodies[0].Name == 'По умолчанию'


def test_source_module_does_not_connect_initialize_or_invoke_cad_on_import():
    source = (Path(scripts) / 'verifier_b3_cylinder_fixture.py').read_text(encoding='utf-8')
    assert 'import pythoncom' not in source and 'CoInitialize' not in source and 'Dispatch(' not in source
