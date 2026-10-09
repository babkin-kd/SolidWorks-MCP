"""Artificial dimension cases with actual SQLite mutation protocol; no CAD calls."""

from concurrent.futures import Future
from contextlib import contextmanager
from copy import deepcopy
import math
from types import SimpleNamespace

import pytest

from solidworks_mcp.dimensions import DimensionCatalog, SCOPE, system_value
from solidworks_mcp.documents import DocumentCatalog, rejected
from solidworks_mcp.jobs import ExecutionFailure, JobRunner, JobStore
from test_document_catalog_v2 import model
from test_feature_domain_v2 import Adapter as FeatureAdapter, feature


def dimension(number, *, kind=0, value=.01):
    return SimpleNamespace(identity=object(), pid=('dimension:' + str(number)).encode(), state={
        'full_name': f'D{number}@Выдавливание', 'name': f'D{number}', 'parameter_type': kind,
        'unit': {0: 'mm', 1: 'deg'}.get(kind),
        'values_si': {'Основная': value, 'Вариант': value + .001},
        'driven_state': 2, 'read_only': False, 'reference': False, 'design_table': False,
        'linked': False, 'owner_update_stamp': 1,
        'owner': {'native_id': 1, 'name': 'Выдавливание', 'feature_type': 'Boss'},
        'tolerance': {'type': 0, 'values_si': [0, 0]}, 'write_blockers': []})


class Adapter(FeatureAdapter):
    def __init__(self):
        super().__init__()
        self.context = {'active_document': True, 'read_only': False, 'editing_sketch': False,
                        'configuration_geometry_complete': True,
                        'configuration_needs_rebuild': {'Основная': False, 'Вариант': False},
                        'external_reference_count': 0, 'design_table': False, 'equation_count': 0,
                        'equations_linked': False, 'unsafe_feature_types': []}
        self.dimension_writes = []
        self.dimension_fault = None
        self.rebuild_fault = None
        self.guard_hook = None
        self.guard_entries = 0
        self.snapshot_hook = None
    def dimensions(self, wrapper, features):
        return self.original(wrapper).dimensions[:]
    def dimension_object(self, record):
        return record
    def dimension_summary(self, record, configurations):
        state = deepcopy(record.state)
        state['values_si'] = {key: state['values_si'][key] for key in configurations}
        state['values'] = {key: (v * 1000 if state['unit'] == 'mm' else math.degrees(v))
                           for key, v in state['values_si'].items()}
        return state
    def resolve_dimension_id(self, wrapper, persistent):
        for obj in self.original(wrapper).dimensions:
            if obj.pid == persistent:
                return obj
        raise rejected('object_deleted', 'Persistent dimension was deleted.')
    def dimension_context(self, wrapper):
        return deepcopy(self.context)
    def dimension_geometry_snapshot(self, wrapper):
        original = self.original(wrapper)
        if self.snapshot_hook:
            hook, self.snapshot_hook = self.snapshot_hook, None
            hook()
        return {'representation': 'fake_exact_geometry', 'values': [
            row.state['values_si']['Основная'] for row in original.dimensions],
            'extra': original.state.get('unrelated_geometry', None)}
    @contextmanager
    def guard(self, wrapper):
        self.guard_entries += 1
        if self.guard_hook:
            self.guard_hook()
        yield
    def set_dimension_value(self, record, value_si, configuration):
        self.dimension_writes.append((record.pid, value_si, configuration))
        fault, self.dimension_fault = self.dimension_fault, None
        if fault == 'silent':
            return 0
        record.state['values_si'][configuration] = value_si
        self.context['configuration_needs_rebuild'][configuration] = True
        for original in self.models:
            if any(row is record for row in original.dimensions):
                original.state['update_stamp'] += 1
                original.state['pending'] = True
                self.watches[id(original.identity)].sequence += 1
        if callable(fault):
            return fault(record)
        if fault == 'exception':
            raise RuntimeError('Native write raised after changing the value.')
        if fault == 'status':
            return 1
        if fault == 'bool':
            return False
        return 0
    def rebuild_dimension_document(self, wrapper):
        original = self.original(wrapper)
        original.state['pending'] = False
        self.context['configuration_needs_rebuild']['Основная'] = False
        original.state['update_stamp'] += 1
        fault, self.rebuild_fault = self.rebuild_fault, None
        if callable(fault):
            return fault(original)
        return fault != 'fail'


@pytest.fixture
def setup(tmp_path):
    adapter = Adapter()
    first, second = model(title='Первая'), model(title='Вторая')
    first.features, second.features = [feature(1)], [feature(1, 'Другой элемент')]
    first.dimensions, second.dimensions = [dimension(1), dimension(2)], [dimension(1)]
    adapter.models = [first, second]
    store = JobStore(tmp_path / 'dimensions.sqlite')
    documents = DocumentCatalog(adapter)
    ids = [item['document_id'] for item in documents.list()['documents']]
    catalog = DimensionCatalog(documents, store, 'connection_1', mutation_guard=adapter.guard)
    yield adapter, catalog, store, ids
    documents.close()
    store.close()


def set_value(setup, *, request='dimension-set', document=None, object_id=None,
              revision=None, configuration='Основная', value=25., unit='mm'):
    adapter, catalog, store, ids = setup
    document = document or ids[0]
    if object_id is None or revision is None:
        page = catalog.list(document, configuration)
        object_id = object_id or page['items'][0]['object_id']
        revision = revision or page['revision']
    args = {'document_id': document, 'configuration': configuration, 'object_id': object_id,
            'expected_revision': revision, 'value': value, 'unit': unit}
    class Worker:
        def submit(self, function):
            future = Future()
            try:
                future.set_result(function())
            except BaseException as exc:
                future.set_exception(exc)
            return future
    runner = JobRunner(store, Worker())
    return runner.submit(request, 'dimension.set_value', args,
        lambda job_id: catalog.set_value(job_id, **args),
        context={k: args[k] for k in ('document_id', 'configuration', 'expected_revision')},
        mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)


def test_target_value_other_configuration_other_dimensions_other_document_and_idempotency(setup):
    adapter, catalog, _, ids = setup
    page = catalog.list(ids[0], 'Основная')
    target = page['items'][0]['object_id']
    assert target.startswith('dim_') and page['revision_scope'] == SCOPE
    args = {'object_id': target, 'revision': page['revision']}
    result = set_value(setup, **args)
    assert result['status'] == 'succeeded' and result['mutation']['phase'] == 'committed'
    assert catalog.get(ids[0], 'Основная', target)['dimension']['values']['Основная'] == 25.
    assert adapter.models[0].dimensions[0].state['values_si']['Вариант'] == .011
    assert adapter.models[0].dimensions[1].state['values_si']['Основная'] == .01
    assert adapter.models[1].dimensions[0].state['values_si']['Основная'] == .01
    retry = set_value(setup, **args)
    assert retry['operation_id'] == result['operation_id']
    assert len(adapter.dimension_writes) == 1
    assert catalog.list(ids[0], 'Основная')['revision'] != page['revision']


def test_angular_units_use_radians_without_wrapping_or_abs(setup):
    adapter, _, _, _ = setup
    adapter.models[0].dimensions[0] = dimension(1, kind=1, value=math.pi / 4)
    result = set_value(setup, value=90, unit='deg')
    assert result['status'] == 'succeeded'
    assert adapter.dimension_writes[0][1] == math.pi / 2


def test_existing_negative_target_is_not_reinterpreted_as_a_positive_size(setup):
    adapter, _, _, _ = setup
    adapter.models[0].dimensions[0].state['values_si']['Основная'] = -.01
    assert set_value(setup)['error']['code'] == 'unsupported_signed_dimension'
    assert adapter.dimension_writes == []


@pytest.mark.parametrize('value,unit', [(True, 'mm'), (float('nan'), 'mm'), (float('inf'), 'deg'),
    (0, 'mm'), (-1, 'mm'), (-30, 'deg'), (360, 'deg'), (10, 'm'), ('12', 'mm')])
def test_invalid_values_fail_before_native_write(setup, value, unit):
    # Non-finite JSON is rejected at JobRunner's input gate; direct conversion
    # covers the domain gate without pretending the invalid request was queued.
    with pytest.raises(ExecutionFailure):
        system_value(value, unit)
    assert setup[0].dimension_writes == []


def test_wrong_unit_foreign_ref_missing_guard_inactive_document_fail_without_writes(setup):
    adapter, catalog, _, ids = setup
    page = catalog.list(ids[0], 'Основная')
    target = page['items'][0]['object_id']
    assert set_value(setup, unit='deg')['error']['code'] == 'dimension_unit_mismatch'
    assert set_value(setup, request='foreign', document=ids[1], object_id=target)['error']['code'] == 'object_reference_not_found'
    adapter.context['active_document'] = False
    assert set_value(setup, request='inactive')['error']['code'] == 'document_not_active'
    catalog.mutation_guard = None
    assert set_value(setup, request='guard')['error']['code'] == 'mutation_guard_unavailable'
    assert adapter.dimension_writes == []


@pytest.mark.parametrize('field,value', [('read_only', True), ('editing_sketch', True),
    ('external_reference_count', 1), ('design_table', True), ('equation_count', 1),
    ('equations_linked', True), ('unsafe_feature_types', ['MacroFeature'])])
def test_unsupported_controls_fail_before_write(setup, field, value):
    adapter, _, _, _ = setup
    adapter.context[field] = value
    assert set_value(setup)['error']['code'] == 'unsupported_dimension_context'
    assert adapter.dimension_writes == []


def test_driven_readonly_signed_coordinate_unknown_type_and_existing_errors_rejected(setup):
    adapter, _, _, _ = setup
    row = adapter.models[0].dimensions[0]
    row.state['write_blockers'] = ['read_only']
    assert set_value(setup)['error']['code'] == 'dimension_not_writable'
    row.state['write_blockers'] = []
    adapter.models[0].dimensions[1].state['driven_state'] = 1
    assert set_value(setup, request='driven')['error']['code'] == 'unsupported_dimension_dependencies'
    adapter.models[0].dimensions[1].state['driven_state'] = 2
    adapter.models[0].features[0].state['error_code'] = 42
    assert set_value(setup, request='errors')['error']['code'] == 'document_has_feature_errors'
    assert adapter.dimension_writes == []


def test_stale_revision_covers_other_dimension_other_configuration_and_tolerance(setup):
    adapter, catalog, _, ids = setup
    page = catalog.list(ids[0], 'Основная')
    adapter.models[0].dimensions[1].state['values_si']['Вариант'] += .002
    assert set_value(setup, revision=page['revision'])['error']['code'] == 'stale_revision'
    page = catalog.list(ids[0], 'Основная')
    adapter.models[0].dimensions[1].state['tolerance']['type'] = 2
    assert set_value(setup, request='tolerance', revision=page['revision'])['error']['code'] == 'stale_revision'
    assert adapter.dimension_writes == []


def test_same_looking_replaced_other_dimension_invalidates_revision_without_notification(setup):
    adapter, catalog, _, ids = setup
    page = catalog.list(ids[0], 'Основная')
    adapter.models[0].dimensions[1] = dimension(3)
    adapter.models[0].dimensions[1].state['full_name'] = 'D2@Выдавливание'
    adapter.models[0].dimensions[1].state['name'] = 'D2'
    assert set_value(setup, revision=page['revision'])['error']['code'] == 'stale_revision'
    assert adapter.dimension_writes == []


def test_guard_entry_edit_and_disk_checkpoint_edit_are_rechecked_before_write(setup, monkeypatch):
    adapter, catalog, store, ids = setup
    page = catalog.list(ids[0], 'Основная')
    adapter.guard_hook = lambda: adapter.models[0].dimensions[1].state['values_si'].__setitem__('Основная', .02)
    assert set_value(setup, revision=page['revision'])['error']['code'] == 'stale_revision'
    adapter.guard_hook = None
    page = catalog.list(ids[0], 'Основная')
    original = store.prepare_mutation
    def checkpoint(*args, **kwargs):
        result = original(*args, **kwargs)
        adapter.models[0].dimensions[1].state['values_si']['Основная'] += .001
        return result
    monkeypatch.setattr(store, 'prepare_mutation', checkpoint)
    result = set_value(setup, request='disk-edit', revision=page['revision'])
    assert result['status'] == 'failed' and result['mutation']['phase'] == 'not_started'
    assert adapter.dimension_writes == []


@pytest.mark.parametrize('fault', ['silent', 'status', 'exception', 'bool'])
def test_native_failure_or_silent_mismatch_verifies_scoped_restoration(setup, fault):
    adapter, _, store, ids = setup
    adapter.dimension_fault = fault
    result = set_value(setup)
    assert result['status'] == 'failed' and result['mutation']['phase'] == 'rolled_back'
    assert adapter.models[0].dimensions[0].state['values_si']['Основная'] == .01
    assert not store.mutation_blockers('connection_1', ids[0])


def test_rebuild_failure_restores_input_and_rebuilds_before_confirming_rollback(setup):
    adapter, _, _, _ = setup
    adapter.rebuild_fault = 'fail'
    result = set_value(setup)
    assert result['error']['code'] == 'dimension_rebuild_failed'
    assert result['mutation']['phase'] == 'rolled_back'


def test_new_feature_error_restores_value_but_retains_unknown_hold(setup):
    adapter, _, store, ids = setup
    def new_error(original):
        original.features[0].state['error_code'] = 42
        return True
    adapter.rebuild_fault = new_error
    result = set_value(setup)
    assert result['status'] == 'unknown' and result['mutation']['phase'] == 'unresolved'
    assert adapter.models[0].dimensions[0].state['values_si']['Основная'] == .01
    assert store.mutation_blockers('connection_1', ids[0])


def test_unrelated_geometry_is_not_called_restored_from_value_alone(setup):
    adapter, _, store, ids = setup
    def concurrent_geometry(original):
        original.state['unrelated_geometry'] = 'foreign-shape'
        return False
    adapter.rebuild_fault = concurrent_geometry
    result = set_value(setup)
    assert result['status'] == 'unknown'
    assert result['error']['code'] == 'mutation_rollback_unconfirmed'
    assert adapter.models[0].dimensions[0].state['values_si']['Основная'] == .01
    assert adapter.models[0].state['unrelated_geometry'] == 'foreign-shape'
    assert store.mutation_blockers('connection_1', ids[0])


def test_concurrent_target_value_not_overwritten_on_rollback(setup):
    adapter, _, _, _ = setup
    def foreign_write(row):
        row.state['values_si']['Основная'] = .123
        raise RuntimeError('Another client changed the target.')
    adapter.dimension_fault = foreign_write
    result = set_value(setup)
    assert result['status'] == 'unknown'
    assert adapter.models[0].dimensions[0].state['values_si']['Основная'] == .123
    assert len(adapter.dimension_writes) == 1


def test_deleted_dimension_and_recreated_configuration_do_not_retarget_by_name(setup):
    adapter, catalog, _, ids = setup
    target = catalog.list(ids[0], 'Основная')['items'][0]['object_id']
    adapter.models[0].dimensions[0] = dimension(3)
    adapter.models[0].dimensions[0].state['full_name'] = 'D1@Выдавливание'
    assert set_value(setup, object_id=target)['error']['code'] == 'object_deleted'
    target = catalog.list(ids[0], 'Основная')['items'][0]['object_id']
    adapter.config_identity['Основная'] = object()
    assert set_value(setup, request='config', object_id=target)['error']['code'] == 'object_configuration_mismatch'
    assert adapter.dimension_writes == []


def test_pagination_reference_mismatch_and_read_race_fail_honestly(setup, monkeypatch):
    adapter, catalog, _, ids = setup
    first = catalog.list(ids[0], 'Основная', limit=1)
    second = catalog.list(ids[0], 'Основная', limit=1, cursor=first['next_cursor'])
    assert first['items'][0]['object_id'] != second['items'][0]['object_id']
    original = adapter.resolve_dimension_id
    one, two = adapter.models[0].dimensions
    monkeypatch.setattr(adapter, 'resolve_dimension_id', lambda m, p: two if p == one.pid else original(m, p))
    page = catalog.list(ids[0], 'Основная')
    assert page['items'][0]['object_id'] is None and page['items'][1]['object_id']
    adapter.snapshot_hook = lambda: one.state['values_si'].__setitem__('Основная', .022)
    with pytest.raises(ExecutionFailure) as error:
        catalog.list(ids[0], 'Основная')
    assert error.value.code == 'document_changed_during_read'


def test_unintended_second_configuration_change_retains_hold_after_target_restore(setup):
    adapter, _, store, ids = setup
    def across_configurations(row):
        row.state['values_si']['Вариант'] = .5
        return 0
    adapter.dimension_fault = across_configurations
    result = set_value(setup)
    assert result['status'] == 'unknown'
    assert adapter.models[0].dimensions[0].state['values_si']['Основная'] == .01
    assert adapter.models[0].dimensions[0].state['values_si']['Вариант'] == .5
    assert store.mutation_blockers('connection_1', ids[0])


def test_target_becoming_linked_during_failed_write_is_not_overwritten(setup):
    adapter, _, _, _ = setup
    def linked(row):
        row.state['write_blockers'] = ['linked']
        raise RuntimeError('Another client linked this dimension.')
    adapter.dimension_fault = linked
    result = set_value(setup)
    assert result['status'] == 'unknown' and len(adapter.dimension_writes) == 1
    assert adapter.models[0].dimensions[0].state['values_si']['Основная'] == .025


def test_inactive_configuration_and_pending_rebuild_are_not_implicitly_changed(setup):
    adapter, catalog, _, ids = setup
    with pytest.raises(ExecutionFailure) as error:
        catalog.list(ids[0], 'Вариант')
    assert error.value.code == 'configuration_not_active'
    adapter.models[0].state['pending'] = True
    assert set_value(setup)['error']['code'] == 'document_needs_rebuild'
    assert adapter.dimension_writes == []


def test_missing_inactive_configuration_geometry_scope_blocks_native_candidate_write(setup):
    adapter, _, _, _ = setup
    adapter.context['configuration_geometry_complete'] = False
    assert set_value(setup)['error']['code'] == 'configuration_geometry_scope_unavailable'
    assert adapter.dimension_writes == []


def test_adapter_parameter_enum_units_configuration_arguments_and_signed_semantics(monkeypatch):
    # Python fakes exercise wrapper contracts; no typelib instantiation or COM.
    from solidworks_mcp import cad_dimensions
    monkeypatch.setattr(cad_dimensions.binding, 'wrap', lambda obj, cls: obj)
    class Adapter(cad_dimensions.CadDimensionsMixin):
        _module = SimpleNamespace(IFeature=object)
        def feature_summary(self, owner):
            return {'native_id': 1, 'name': 'Выдавливание', 'feature_type': 'Boss',
                    'suppressed': False, 'error_code': 0, 'is_warning': False}
    owner = SimpleNamespace(IsFrozen=lambda: False, IsRolledBack=lambda: False, GetUpdateStamp=lambda: 3)
    calls = []
    dim = SimpleNamespace(FullName='D1@Выдавливание', Name='D1', DrivenState=2, ReadOnly=False,
        GetType=lambda: 1, IsReference=lambda: False, IsDesignTableDimension=lambda: False,
        GetSystemValue3=lambda option, names: calls.append((option, names)) or [math.pi / 2],
        GetToleranceType=lambda: 0, GetToleranceValues=lambda: [0., 0.],
        SetSystemValue3=lambda value, option, names: calls.append((value, option, names)) or 0)
    display = SimpleNamespace(GetType=lambda: 3, IsLinked=False, GetLinkedText=lambda: '')
    record = cad_dimensions.NativeDimension(dim, owner, [display])
    adapter = Adapter()
    row = adapter.dimension_summary(record, ['Основная', 'Вариант'])
    assert row['unit'] == 'deg' and row['values']['Основная'] == 90
    assert row['write_blockers'] == []
    assert calls == [(3, ['Основная']), (3, ['Вариант'])]
    assert adapter.set_dimension_value(record, math.pi, 'Основная') == 0
    assert calls[-1] == (math.pi, 3, ['Основная'])
    dim.GetType = lambda: 0
    display.GetType = lambda: 11
    assert 'unsupported_display_semantics' in adapter.dimension_summary(record, ['Основная'])['write_blockers']
    dim.ReadOnly = True
    dim.DrivenState = 0
    display.IsLinked = True
    row = adapter.dimension_summary(record, ['Основная'])
    assert {'read_only', 'driven_or_unknown_state', 'linked'} <= set(row['write_blockers'])


def test_adapter_enumerates_both_chamfer_values_deduplicates_aliases_and_rejects_cycles(monkeypatch):
    from solidworks_mcp import cad_dimensions
    monkeypatch.setattr(cad_dimensions.binding, 'wrap', lambda obj, cls: obj)
    class Adapter(cad_dimensions.CadDimensionsMixin):
        _module = SimpleNamespace(IFeature=object, IDimension=object, IDisplayDimension=object)
        def identity(self, obj):
            return obj.identity
    first = SimpleNamespace(identity=object(), GetFeatureOwner=lambda: None)
    second = SimpleNamespace(identity=object(), GetFeatureOwner=lambda: None)
    indices = []
    display = SimpleNamespace(identity=object(), GetType=lambda: 10,
        GetDimension2=lambda index: indices.append(index) or (first, second)[index])
    feature = SimpleNamespace(GetFirstDisplayDimension=lambda: display,
                             GetNextDisplayDimension=lambda old: None)
    records = Adapter().dimensions(object(), [feature, feature])
    assert len(records) == 2 and indices == [0, 1, 0, 1]
    assert all(len(record.displays) == 1 for record in records)
    feature.GetNextDisplayDimension = lambda old: display
    with pytest.raises(ExecutionFailure) as error:
        Adapter().dimensions(object(), [feature])
    assert error.value.code == 'dimension_traversal_cycle'


def test_exact_native_stream_evidence_has_no_bounds_or_mass_fallback(monkeypatch):
    from io import BytesIO
    from solidworks_mcp import cad_dimensions
    class Stream:
        def __init__(self):
            self.buffer = BytesIO()
        def Seek(self, offset, mode):
            return self.buffer.seek(offset, mode)
        def Read(self, count):
            return self.buffer.read(count)
    monkeypatch.setattr(cad_dimensions.pythoncom, 'CreateStreamOnHGlobal', Stream)
    class Adapter(cad_dimensions.CadDimensionsMixin):
        _module = SimpleNamespace(IBody2=object)
        def bodies(self, model, kind):
            assert kind == 'all'
            return model
        def identity(self, obj):
            return obj.identity
    monkeypatch.setattr(cad_dimensions.binding, 'wrap', lambda obj, cls: obj)
    def copy(source):
        return SimpleNamespace(identity=object(), IsTemporaryBody=lambda: True,
                               Save=lambda stream: stream.buffer.write(source.raw), GetType=lambda: source.kind)
    def forbid_save(stream):
        raise AssertionError('Saving a source CAD body is forbidden.')
    first = SimpleNamespace(identity=object(), Save=forbid_save, raw=b'first exact body', kind=0)
    second = SimpleNamespace(identity=object(), Save=forbid_save, raw=b'second exact body', kind=1)
    first.Copy, second.Copy = lambda: copy(first), lambda: copy(second)
    adapter = Adapter()
    before = adapter.dimension_geometry_snapshot([first, second])
    assert before == adapter.dimension_geometry_snapshot([second, first])
    assert before['representation'] == 'native_body_stream_sha256_v1'
    first.raw = b'changed shape with same dimensions'
    assert before != adapter.dimension_geometry_snapshot([first, second])
    first.raw = b''
    with pytest.raises(ExecutionFailure) as error:
        adapter.dimension_geometry_snapshot([first])
    assert error.value.code == 'geometry_snapshot_unavailable'
    first.Copy = lambda: first
    first.IsTemporaryBody = lambda: True
    with pytest.raises(ExecutionFailure):
        adapter.dimension_geometry_snapshot([first])
