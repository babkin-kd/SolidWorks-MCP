"""Synthetic journal predicate tests: no actual CAD or NT publication."""
import ast
from copy import deepcopy
import importlib.util
from pathlib import Path

import pytest
from test_native_first_save import setup


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('race_shared_protocol', ROOT / 'scripts/verifier_native_first_save.py')
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)
tree = ast.parse((ROOT / 'scripts/verifier_first_save_race.py').read_text(encoding='utf-8'))
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'verified_race_rollback')
namespace = {'_json': shared._json, 'released_first_save_guard': shared.released_first_save_guard}
exec(compile(ast.Module(body=[function], type_ignores=[]), 'race_protocol', 'exec'), namespace)
verify = namespace['verified_race_rollback']


@pytest.fixture
def evidence(setup):
    x = setup
    x.f.fault = 'conflict'
    job = deepcopy(x.run())
    assert job['status'] == 'failed' and job['mutation']['phase'] == 'rolled_back'
    before = job['mutation']['before_state']
    # Native-shaped guard is manufactured for a predicate test, never CAD evidence.
    job['mutation']['verification']['evidence']['execution_guard'] = dict(
        scope='native_first_save_guard_v1', destination_lease_released=True,
        native_guard=dict(scope='application_document_close_guard_v1', original_command_in_progress=False,
            acquired=True, released=True, model_guards=[dict(original_state=0, locked_state=2, released_state=0)],
            selection_preserved=True, retiring_document_ids=[before['document_id']],
            retiring_targets_locked_during_close=False, activation_ui_release=dict(attempted=False, verified=False)))
    file = job['mutation']['verification']['evidence']['after']['destination_file']
    foreign = dict(identity=file['identity'], sha256=file['sha256'], size=file['bytes'])
    return job, foreign


def test_complete_synthetic_rollback_requires_receipts_not_only_rolled_back_flag(evidence):
    job, foreign = evidence
    assert verify(job, foreign)
    job['mutation']['verification']['native_steps'] = []
    assert not verify(job, foreign)


@pytest.mark.parametrize('fault', ['guard', 'hold', 'foreign', 'stage', 'snapshot', 'copy_error_type',
                                 'sequence', 'retirement', 'destination'])
def test_missing_changed_or_unconfirmed_race_evidence_rejected(evidence, fault):
    job, foreign = evidence
    verification = job['mutation']['verification']
    after = verification['evidence']['after']
    steps = verification['native_steps']
    if fault == 'guard':verification['evidence']['execution_guard']['destination_lease_released'] = False
    elif fault == 'hold':job['error']['requires_reconciliation'] = True
    elif fault == 'foreign':foreign['sha256'] = 'foreign'
    elif fault == 'stage':after['stage']['file'] = {'retained': True}
    elif fault == 'snapshot':after['snapshots'] = {}
    elif fault == 'copy_error_type':
        next(row for row in steps if row['name'] == 'first_save_copy_native' and row['phase'] == 'returned')['evidence']['errors'] = False
    elif fault == 'sequence':steps[0]['sequence'] = True
    elif fault == 'retirement':steps[2]['name'] = steps[3]['name'] = 'first_save_close_source_native'
    elif fault == 'destination':job['payload']['arguments']['filename'] = 'foreign'
    assert not verify(job, foreign)
