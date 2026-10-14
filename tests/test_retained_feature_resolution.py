"""Artificial adapter proofs for an internal bridge, never native acceptance."""
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.retained_feature_resolution import resolve_retained_feature_pid


@pytest.fixture
def case():
    owner, foreign = object(), object()
    feature = NS(identity=owner, pid=b'\xaa', IsSuppressed2=lambda *args: [True])
    state = NS(feature=feature, raw=feature, status=2, members=[feature],
               generic_code='object_suppressed', native_reads=0)
    def generic(*args):
        if state.generic_code:
            raise ExecutionFailure(state.generic_code, 'Normally returned native resolver refusal.')
        return state.feature
    def lookup(pid):
        state.native_reads += 1
        return state.raw, state.status
    state.adapter = NS(resolve_persistent_id=generic, identity=lambda item: item.identity,
        persistent_id=lambda model, item: item.pid, features=lambda model: list(state.members),
        _persistent_variant=lambda pid: pid,
        _extension=lambda model: NS(GetObjectByPersistReference3=lookup))
    state.owner, state.foreign, state.model = owner, foreign, object()
    return state


@pytest.mark.parametrize('suppressed', [False, True])
def test_state0_preserves_normal_generic_resolution_without_extra_native_lookup(case, suppressed):
    case.generic_code = None
    case.feature.IsSuppressed2 = lambda *args: [suppressed]
    assert resolve_retained_feature_pid(case.adapter, case.model, b'\xaa', case.owner) is case.feature
    assert case.native_reads == 0


def test_state2_requires_returned_raw_feature_and_exact_retained_membership(case):
    assert resolve_retained_feature_pid(case.adapter, case.model, b'\xaa', case.owner) is case.feature
    assert case.native_reads == 1


@pytest.mark.parametrize('fault', ['raw_null', 'raw_alias', 'state0', 'state4', 'state6',
    'state_bool', 'no_member', 'duplicate', 'foreign_member', 'foreign_pid',
    'false_flag', 'numeric_flag', 'null_flag', 'multiple_flags'])
def test_state2_proof_refuses_alias_partial_and_untyped_native_data(case, fault):
    if fault == 'raw_null': case.raw = None
    elif fault == 'raw_alias': case.raw = NS(identity=case.foreign)
    elif fault.startswith('state'):
        case.status = {'state0': 0, 'state4': 4, 'state6': 6, 'state_bool': True}[fault]
    elif fault == 'no_member': case.members = []
    elif fault == 'duplicate': case.members *= 2
    elif fault == 'foreign_member': case.members = [NS(identity=case.foreign, pid=b'\xaa')]
    elif fault == 'foreign_pid': case.feature.pid = b'\xbb'
    else:
        flag = {'false_flag': [False], 'numeric_flag': [1], 'null_flag': None,
                'multiple_flags': [True, True]}[fault]
        case.feature.IsSuppressed2 = lambda *args: flag
    with pytest.raises(ExecutionFailure) as error:
        resolve_retained_feature_pid(case.adapter, case.model, b'\xaa', case.owner)
    assert error.value.code == 'retained_feature_resolution_unconfirmed'


@pytest.mark.parametrize('code', ['object_deleted', 'object_reference_invalid',
    'persistent_reference_mismatch', 'native_read_failed'])
def test_other_errors_propagate_without_secondary_lookup(case, code):
    case.generic_code = code
    with pytest.raises(ExecutionFailure) as error:
        resolve_retained_feature_pid(case.adapter, case.model, b'\xaa', case.owner)
    assert error.value.code == code and case.native_reads == 0


@pytest.mark.parametrize('fault', ['null', 'identity', 'pid'])
def test_state0_still_requires_exact_original_binding(case, fault):
    case.generic_code = None
    if fault == 'null': case.feature = None
    elif fault == 'identity': case.feature.identity = case.foreign
    else: case.feature.pid = b'\xbb'
    with pytest.raises(ExecutionFailure):
        resolve_retained_feature_pid(case.adapter, case.model, b'\xaa', case.owner)
    assert case.native_reads == 0


@pytest.mark.parametrize('pid,identity', [(b'', object()), ('aa', object()),
    (bytearray(b'\xaa'), object()), (b'\xaa', None)])
def test_missing_original_binding_refuses_before_native_reads(case, pid, identity):
    with pytest.raises(ExecutionFailure) as error:
        resolve_retained_feature_pid(case.adapter, case.model, pid, identity)
    assert error.value.code == 'retained_feature_binding_required' and case.native_reads == 0
