"""Nonstructural native rows and closed scoped context; no CAD acceptance."""

import asyncio
from concurrent.futures import Future
from copy import deepcopy
from types import SimpleNamespace

import pytest

from solidworks_mcp import cad_deletion_context as native
from solidworks_mcp.feature_deletion_context import SCOPE, context_semantics
from solidworks_mcp.jobs import ExecutionFailure, JobError
from solidworks_mcp.runtime_v2 import Runtime
from test_feature_domain_v2 import setup
from test_feature_dependency_graph_v2 import install


def capture():
    return {'scope': native.SCOPE,
        'equations': {'enumerated_count': 1, 'disabled_count': 1, 'disabled_definitions_captured': False, 'properties': {
            'linked_to_file': True, 'file_path': 'private/equations.txt', 'automatic_rebuild': False,
            'automatic_solve_order': True, 'angular_equation_units': 0}, 'rows': [
            {'row_index': 0, 'expression': '"Высота" = 9', 'disabled': False, 'global_variable': True, 'configuration_option': 1}]},
        'external_references': {'count': 1, 'rows': [{'row_index': 0,
            **dict(zip(native.EXTERNAL_FIELDS, ('private/Основа.SLDPRT', '', 'Базовая деталь', 'Тело', 5, 'Тело@Основа', '', 3, 'Основная')))}]},
        'auxiliary_references': {'count': 1, 'rows': [{'row_index': 0, 'feature_name': 'Макроэлемент', 'file_path': 'private/script.dll'}]}}


class Manager:
    def __init__(self, data):
        self.data = data
        for field, key in [('LinkToFile', 'linked_to_file'), ('FilePath', 'file_path'),
                           ('AutomaticRebuild', 'automatic_rebuild'), ('AutomaticSolveOrder', 'automatic_solve_order'),
                           ('AngularEquationUnits', 'angular_equation_units')]:
            setattr(self, field, data['properties'][key])
    def GetCount(self): return self.data['enumerated_count']
    def GetDisabledEquationCount(self): return self.data['disabled_count']
    def Equation(self, index): return self.data['rows'][index]['expression']
    def Disabled(self, index): return self.data['rows'][index]['disabled']
    def GlobalVariable(self, index): return self.data['rows'][index]['global_variable']
    def GetConfigurationOption(self, index): return self.data['rows'][index]['configuration_option']


class Driver(native.CadDeletionContextMixin):
    def __init__(self, value):
        self.value = value
        self.manager = Manager(value['equations'])
        self._module = SimpleNamespace(IEquationMgr=object)
    def _wrap_equation_manager(self, raw): return raw
    def _extension(self, model): return self
    def GetEquationMgr(self): return self.manager
    def ListExternalFileReferencesCount(self): return self.value['external_references']['count']
    def ListExternalFileReferences2(self):
        rows = self.value['external_references']['rows']
        return tuple([row[field] for row in rows] or None for field in native.EXTERNAL_FIELDS)
    def ListAuxiliaryExternalFileReferencesCount(self): return self.value['auxiliary_references']['count']
    def ListAuxiliaryExternalFileReferences(self):
        rows = self.value['auxiliary_references']['rows']
        return tuple([row[field] for row in rows] or None for field in ('feature_name', 'file_path'))


@pytest.fixture
def driver():
    return Driver(capture())


def test_native_collector_keeps_enabled_rows_disabled_counter_and_both_reference_categories(driver):
    actual = driver.feature_deletion_context(driver)
    assert actual == capture()
    assert context_semantics(actual) == actual


def test_native_zero_counts_and_null_parallel_arrays_are_explicit_empty_inventory(driver):
    value = driver.value
    for key in ('external_references', 'auxiliary_references'):
        value[key].update(count=0, rows=[])
    value['equations'].update(enumerated_count=0, rows=[], disabled_count=0, disabled_definitions_captured=True)
    result = driver.feature_deletion_context(driver)
    assert all(result[key]['rows'] == [] for key in ('equations', 'external_references', 'auxiliary_references'))


@pytest.mark.parametrize('value', [True, -1, 5001, 1.])
def test_native_bad_count_rejected_before_equation_traversal(driver, value):
    driver.manager.GetCount = lambda: value
    driver.manager.Equation = lambda index: pytest.fail('Bad count must not traverse.')
    with pytest.raises(ExecutionFailure): driver.feature_deletion_context(driver)


@pytest.mark.parametrize('fault', ['count_changed', 'disabled_changed', 'columns_short', 'array_length', 'status_bool', 'configuration_bool', 'string_object', 'expression_budget', 'aggregate_budget'])
def test_native_incomplete_or_unsafe_rows_fail_closed(driver, fault):
    if fault == 'count_changed':
        counts = iter([1, 2]); driver.manager.GetCount = lambda: next(counts)
    elif fault == 'disabled_changed':
        counts = iter([1, 0]); driver.manager.GetDisabledEquationCount = lambda: next(counts)
    elif fault == 'columns_short':
        driver.ListExternalFileReferences2 = lambda: ([],)
    elif fault == 'array_length':
        driver.value['external_references']['count'] = 2
    elif fault == 'status_bool':
        driver.value['external_references']['rows'][0]['status'] = True
    elif fault == 'configuration_bool':
        driver.value['external_references']['rows'][0]['configuration_option'] = False
    elif fault == 'string_object':
        class Native:
            def __str__(self): pytest.fail('Do not format native objects.')
            def __eq__(self, other): pytest.fail('Do not compare native objects.')
        driver.value['external_references']['rows'][0]['feature_name'] = Native()
    elif fault == 'expression_budget':
        driver.value['equations']['rows'][0]['expression'] = 'x' * (native.MAX_TEXT + 1)
    else:
        rows = [{**driver.value['equations']['rows'][0], 'row_index': i, 'expression': 'x'*native.MAX_TEXT} for i in range(130)]
        driver.value['equations'].update(enumerated_count=len(rows), disabled_count=0, rows=rows, disabled_definitions_captured=True)
    with pytest.raises(ExecutionFailure): driver.feature_deletion_context(driver)


@pytest.mark.parametrize('fault', ['scope', 'extra', 'count', 'disabled', 'row_index', 'missing_column', 'integer_type', 'file_type'])
def test_domain_schema_never_accepts_incomplete_or_forged_capture(fault):
    value = capture()
    if fault == 'scope': value['scope'] = None
    elif fault == 'extra': value['unverified'] = True
    elif fault == 'count': value['equations']['enumerated_count'] = True
    elif fault == 'disabled': value['equations']['disabled_definitions_captured'] = True
    elif fault == 'row_index': value['equations']['rows'][0]['row_index'] = False
    elif fault == 'missing_column': value['external_references']['rows'][0].pop('model_path')
    elif fault == 'integer_type': value['external_references']['rows'][0]['status'] = True
    else: value['auxiliary_references']['rows'][0]['file_path'] = None
    with pytest.raises(ExecutionFailure): context_semantics(value)


def feature_capture(native, rows):
    return {'scope': 'native_feature_external_references_v1', 'feature_count': len(native),
            'total_reference_rows': len(rows), 'features': [
                {'native_id': item.state['native_id'], 'count': len(rows) if index == 0 else 0,
                 'rows': deepcopy(rows) if index == 0 else []} for index, item in enumerate(native)]}


def install_context(adapter, change=None):
    calls = []
    shared = capture()
    def read(model):
        calls.append('context')
        if change: change(len(calls), shared)
        return shared
    adapter.feature_deletion_context = read
    adapter.feature_external_references = lambda native: feature_capture(native, shared['external_references']['rows'])
    return calls


def test_context_binds_two_native_inventories_to_stable_graph_and_revision_without_writes(setup):
    adapter, documents, catalog, store, ids = setup
    install(adapter, owner=True)
    calls = install_context(adapter)
    first = catalog.deletion_context(ids[0], 'Основная')
    second = catalog.deletion_context(ids[0], 'Основная')
    assert first == second and calls == ['context'] * 4
    assert first['revision_scope'] == SCOPE and first['native_context'] == capture()
    assert first['native_inventory_capture_closed'] is True
    assert first['row_indices_and_names_are_writable_anchors'] is False
    assert first['deletion_impact_complete'] is first['deletion_authorized'] is False
    assert adapter.writes == [] and store.list()['items'] == []
    assert any(row['code'] == 'disabled_equation_definitions_unavailable' for row in first['blockers'])
    assert 'incoming_external_document_references' in {row.get('scope') for row in first['blockers']}


@pytest.mark.parametrize('field', ['expression', 'disabled', 'external', 'auxiliary', 'link', 'configuration_option'])
def test_nonstructural_change_without_tree_stamp_changes_revision(setup, field):
    adapter, documents, catalog, store, ids = setup
    install(adapter)
    value = capture()
    adapter.feature_deletion_context = lambda model: value
    adapter.feature_external_references = lambda native: feature_capture(native, value['external_references']['rows'])
    before = catalog.deletion_context(ids[0], 'Основная')
    if field == 'expression': value['equations']['rows'][0]['expression'] = '"Высота" = 12'
    elif field == 'disabled':
        value['equations']['disabled_count'] = 2
    elif field == 'external': value['external_references']['rows'][0]['status'] = 3
    elif field == 'auxiliary': value['auxiliary_references']['rows'][0]['file_path'] = 'private/changed.dll'
    elif field == 'link': value['equations']['properties']['file_path'] = 'private/changed.txt'
    else: value['equations']['rows'][0]['configuration_option'] = 2
    after = catalog.deletion_context(ids[0], 'Основная')
    assert before['dependency_graph'] == after['dependency_graph']
    assert before['revision'] != after['revision']
    assert before['native_context'] != after['native_context']
    assert adapter.writes == []


@pytest.mark.parametrize('fault', ['shared_mutated', 'late_notification', 'configuration', 'native_identity'])
def test_race_between_inventories_never_returns_success_even_with_reused_mutable_capture(setup, fault):
    adapter, documents, catalog, store, ids = setup
    install(adapter)
    def change(number, value):
        if number != 2: return
        if fault == 'shared_mutated': value['equations']['rows'][0]['expression'] = '"Высота" = 99'
        elif fault == 'late_notification': adapter.watches[id(adapter.models[0].identity)].sequence += 1
        elif fault == 'configuration': adapter.config_identity['Основная'] = object()
        else: adapter.models[0].features[0].identity = object()
    install_context(adapter, change)
    with pytest.raises(ExecutionFailure) as error: catalog.deletion_context(ids[0], 'Основная')
    assert error.value.code == 'document_changed_during_read' and adapter.writes == []


def test_runtime_context_read_is_durable_idempotent_and_cannot_be_dispatched_as_mutation(setup):
    adapter, documents, catalog, store, ids = setup
    install(adapter); calls = install_context(adapter)
    class Worker:
        def submit(self, function):
            future = Future()
            try: future.set_result(function())
            except BaseException as error: future.set_exception(error)
            return future
        def shutdown(self, timeout_s=5): return True
    runtime = Runtime(store, worker_factory=Worker, catalog_factory=lambda: documents)
    async def check():
        arguments = {'document_id': ids[0], 'configuration': 'Основная'}
        with pytest.raises(JobError): await runtime.mutate('write', 'feature.deletion_context', arguments)
        assert runtime._runner is None
        first = await runtime.read('read', 'feature.deletion_context', arguments)
        assert first['status'] == 'succeeded' and first['payload']['mutates'] is False
        assert first['result']['revision_scope'] == SCOPE
        second = await runtime.read('read', 'feature.deletion_context', arguments)
        assert second['operation_id'] == first['operation_id'] and calls == ['context'] * 2
        assert 'mutation' not in store.get(first['operation_id'])
    try: asyncio.run(check())
    finally: runtime.shutdown()



def test_domain_context_import_does_not_load_com_bindings():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, '-c', """
import importlib.abc, sys
class BlockNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in ('pythoncom', 'win32com', 'solidworks_mcp.binding'):
            raise AssertionError('Pure context import attempted native binding: ' + fullname)
sys.meta_path.insert(0, BlockNative())
from solidworks_mcp.feature_deletion_context import context_semantics
assert callable(context_semantics)
"""], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr



def test_disabled_only_inventory_retains_native_counter_and_blocked_missing_definitions(driver):
    driver.value['equations'].update(enumerated_count=0, rows=[], disabled_count=3, disabled_definitions_captured=False)
    actual = driver.feature_deletion_context(driver)
    assert actual['equations']['disabled_count'] == 3 and actual['equations']['rows'] == []
    assert actual['equations']['disabled_definitions_captured'] is False
    assert context_semantics(actual) == actual
