"""Verifier-only observation tests; AST extraction never imports CAD modules."""

import ast
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'verify_internal_exports.py'


class FakeParentAdapter:
    def __init__(self, documents_adapter):
        self.documents_adapter = documents_adapter

    def export_part_to_file(self, model, path, options, before):
        extension = self._extension(model)
        self.documents_adapter.events.append('full-profile-gate')
        if not self.documents_adapter.profile_matches:
            raise RuntimeError('Profile gate rejected before SaveAs3')
        return extension.SaveAs3(path, 0, 3, None, None, 0, 0)


@pytest.fixture
def definitions():
    tree = ast.parse(SCRIPT.read_text(encoding='utf8'), filename=str(SCRIPT))
    names = {'ObservedExtension', 'ObservedExportsAdapter', 'compact_job_failure'}
    nodes = [node for node in tree.body
             if isinstance(node, (ast.ClassDef, ast.FunctionDef)) and node.name in names]
    assert {node.name for node in nodes} == names
    namespace = {'CadExportsAdapter': FakeParentAdapter}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SCRIPT), 'exec'), namespace)
    return namespace


class Extension:
    def __init__(self, events, *, result=None, exception=None):
        self.events, self.result, self.exception = events, result, exception
        self.calls = []
        self.marker = object()
        self.at_entry = lambda: None

    def SaveAs3(self, *args, **kwargs):
        self.events.append('SaveAs3')
        self.at_entry()
        self.calls.append((args, kwargs))
        if self.exception is not None:
            raise self.exception
        return self.result

    def GetUserPreferenceString(self, *args):
        self.events.append(('GetUserPreferenceString', args))
        return self.marker

    def __getattr__(self, name):
        raise AssertionError('Unexpected native attribute/getter: ' + name)


def observed_adapter(definitions, *, result=(True, 0, 0), exception=None, profile_matches=True):
    events = []
    extension = Extension(events, result=result, exception=exception)
    model = SimpleNamespace(GetBlockingState=lambda: 2)
    extension_models = []

    def native_extension(target):
        assert target is model
        extension_models.append(target)
        return extension

    documents = SimpleNamespace(_extension=native_extension, events=events, profile_matches=profile_matches)
    checkpoint = {'phase': 'prepared', 'before_state': {'_mutation_effect_scope': 'application'}}
    audit = []

    def get(operation):
        assert operation == 'owned-operation'
        audit.append(('checkpoint', operation))
        return {'mutation': checkpoint}

    def blockers(epoch, document):
        audit.append(('blockers', epoch, document))
        return [{'operation_id': 'owned-operation'}]

    store = SimpleNamespace(get=get, mutation_blockers=blockers)
    adapter = definitions['ObservedExportsAdapter'](documents, store, 'owned-epoch')
    adapter.expected_operation = 'owned-operation'
    return adapter, extension, model, events, extension_models, audit, checkpoint


@pytest.mark.parametrize('result', [(True, 0, 0), (False, 4, 8), None, object()])
def test_proxy_preserves_exact_arguments_return_and_call_boundary_without_getters(definitions, result):
    events, attempts = [], []
    extension = Extension(events, result=result)
    proxy = definitions['ObservedExtension'](extension, lambda: attempts.append('attempt'))
    args = (object(), 0, 3, None, object(), 0, 0)
    kwargs = {'native_keyword': object()}
    extension.at_entry = lambda: assert_attempt(attempts)
    assert proxy.SaveAs3(*args, **kwargs) is result
    assert extension.calls == [(args, kwargs)]
    assert events == ['SaveAs3'] and attempts == ['attempt']


def assert_attempt(attempts):
    assert attempts == ['attempt']


def test_proxy_propagates_original_exception_and_counts_attempt(definitions):
    events, attempts = [], []
    error = RuntimeError('native-shaped failure')
    extension = Extension(events, exception=error)
    proxy = definitions['ObservedExtension'](extension, lambda: attempts.append('attempt'))
    with pytest.raises(RuntimeError) as raised:
        proxy.SaveAs3('owned.x_t', 0, 3, None, None, 0, 0)
    assert raised.value is error
    assert attempts == ['attempt'] and events == ['SaveAs3']
    assert len(extension.calls) == 1


def test_other_extension_methods_and_properties_delegate_to_original_object(definitions):
    events = []
    extension = Extension(events)
    attempts = []
    proxy = definitions['ObservedExtension'](extension, lambda: attempts.append('attempt'))
    assert proxy.GetUserPreferenceString(16, 0) is extension.marker
    assert proxy.marker is extension.marker
    assert events == [('GetUserPreferenceString', (16, 0))]
    assert attempts == [] and extension.calls == []


def test_adapter_observes_actual_attempt_after_profile_gate_and_preserves_checkpoint_audit(definitions):
    adapter, extension, model, events, extension_models, audit, _ = observed_adapter(definitions)
    def entered():
        assert adapter.saveas_attempts == ['owned-operation']
    extension.at_entry = entered
    result = adapter.export_part_to_file(model, 'owned.stl', object(), object())
    assert result is extension.result
    assert adapter.native_calls == ['owned-operation'] and adapter.saveas_attempt_count == 1
    assert extension_models == [model]
    assert events == ['full-profile-gate', 'SaveAs3']
    assert audit == [('checkpoint', 'owned-operation'),
                     ('blockers', 'owned-epoch', 'unrelated-verifier-document'),
                     ('blockers', 'unrelated-verifier-epoch', 'unrelated-verifier-document')]


def test_profile_rejection_records_adapter_entry_but_zero_actual_saveas_attempts(definitions):
    adapter, extension, model, events, _, _, _ = observed_adapter(definitions, profile_matches=False)
    with pytest.raises(RuntimeError, match='Profile gate rejected'):
        adapter.export_part_to_file(model, 'owned.stl', object(), object())
    assert adapter.native_calls == ['owned-operation']
    assert adapter.saveas_attempt_count == 0 and adapter.saveas_attempts == []
    assert extension.calls == [] and events == ['full-profile-gate']


def test_adapter_native_exception_is_not_converted_to_success(definitions):
    error = RuntimeError('native-shaped failure')
    adapter, extension, model, events, _, _, _ = observed_adapter(definitions, exception=error)
    with pytest.raises(RuntimeError) as raised:
        adapter.export_part_to_file(model, 'owned.stl', object(), object())
    assert raised.value is error
    assert adapter.saveas_attempt_count == 1 and len(extension.calls) == 1
    assert events == ['full-profile-gate', 'SaveAs3']


@pytest.mark.parametrize('invalid', ['ownership', 'checkpoint', 'application_scope', 'ui_guard'])
def test_failed_existing_audit_never_reaches_extension_or_saveas(definitions, invalid):
    adapter, extension, model, events, extension_models, _, checkpoint = observed_adapter(definitions)
    if invalid == 'ownership':
        adapter.expected_operation = None
    elif invalid == 'checkpoint':
        checkpoint['phase'] = 'committed'
    elif invalid == 'application_scope':
        checkpoint['before_state']['_mutation_effect_scope'] = 'document'
    else:
        model.GetBlockingState = lambda: 0
    with pytest.raises(AssertionError):
        adapter.export_part_to_file(model, 'owned.stl', object(), object())
    assert adapter.native_calls == [] and adapter.saveas_attempt_count == 0
    assert extension_models == [] and extension.calls == [] and events == []


@pytest.mark.parametrize('guard_location', ['result', 'verification', 'absent'])
def test_compact_failure_preserves_status_error_phase_guard_without_checkpoint(definitions, guard_location):
    guard = {'original_state': 0, 'locked_state': 2, 'released_state': 0}
    job = {'operation_id': 'owned-operation', 'status': 'unknown',
           'error': {'code': 'native_export_result_invalid', 'message': 'Inspect retained journal.'},
           'result': None, 'payload': {'arguments': {'private': 'large'}},
           'mutation': {'phase': 'prepared', 'before_state': {'full_brep': 'x' * 90000},
                        'verification': None}}
    if guard_location == 'result':
        job['result'] = {'execution_guard': guard, 'full_after': 'y' * 90000}
    elif guard_location == 'verification':
        job['mutation']['verification'] = {'evidence': {'execution_guard': guard, 'after': 'y' * 90000}}
    original = deepcopy(job)
    compact = definitions['compact_job_failure'](job)
    assert compact == {'operation_id': 'owned-operation', 'status': 'unknown', 'error': job['error'],
                       'mutation': {'phase': 'prepared'},
                       'execution_guard': guard if guard_location != 'absent' else None}
    assert len(json.dumps(compact)) < 500
    assert job == original


def test_missing_optional_checkpoint_still_has_compact_diagnostic(definitions):
    compact = definitions['compact_job_failure']({'operation_id': 'op', 'status': 'failed', 'error': None})
    assert compact == {'operation_id': 'op', 'status': 'failed', 'error': None,
                       'mutation': {'phase': None}, 'execution_guard': None}
