"""B3-I13: two exact original reads replayed without a second domain calculation."""
from copy import deepcopy

from verifier_b3_journal import bind_durable_job
from verifier_b3_part_geometry import _call, _canonical, _proof
from verifier_lifecycle import read_journal

SCOPE = 'bounded_b3_i13_read_replay_evidence_v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def dto(row):
    value = {key: deepcopy(item) for key, item in row.items() if key != 'digest'}
    if value.get('mutation') is None:
        value.pop('mutation', None)
    return value


async def replay_case(reader, *, passive_receipt, mass_receipt, capture_full, capture_activity):
    """Reuse actual original receipt records, never create a replacement request.

Each receipt contains tool, arguments and complete raw journal as produced by
the original B3 route. Selected passive tool is geometry_get or bounds. The
guarded mass must be a committed same-part/configuration job. capture_full
reads the complete original part/neighbor/session. capture_activity reads the
original owner's connection_epoch, domain_dispatch_count and
mass_calculation_count, instrumented at actual domain and mass solver entry.
These are selected-operation counters, not a claim of counting all COM calls.
Both callbacks must reject incomplete/replaced owner scope. No cleanup here.
"""
    require(callable(capture_full) and callable(capture_activity), 'Independent current scope/activity observers required.')
    selected = [deepcopy(passive_receipt), deepcopy(mass_receipt)]
    require(selected[0]['tool'] in ('geometry_get', 'measurement_get_bounds')
            and selected[1]['tool'] == 'measurement_get_mass', 'One passive geometry and one guarded mass receipt required.')
    before_journal = read_journal(reader.journal_path)
    index = {row['operation_id']: row for row in before_journal}
    for receipt in selected:
        row = receipt['journal']
        require(row['operation_id'] in index and _canonical(row) == _canonical(index[row['operation_id']]),
                'Actual full original durable row required before replay.')
        bind_durable_job(dto=dto(row), row=row, tool=receipt['tool'], arguments=receipt['arguments'])
    passive, mass = (receipt['journal'] for receipt in selected)
    require(passive['operation_id'] != mass['operation_id'] and passive['request_id'] != mass['request_id']
            and all(passive['payload']['arguments'][key] == mass['payload']['arguments'][key]
                    for key in ('document_id', 'configuration')), 'Same original part/configuration and distinct original jobs required.')
    epoch = mass['mutation']['connection_epoch']
    before = _proof(await _call(capture_full))
    activity = _proof(await _call(capture_activity))
    require(set(activity) == {'connection_epoch', 'domain_dispatch_count', 'mass_calculation_count'}
            and activity['connection_epoch'] == epoch
            and all(type(activity[key]) is int and activity[key] >= 1
                    for key in ('domain_dispatch_count', 'mass_calculation_count')),
            'Original live owner epoch and actual selected-operation counters required.')
    replays = []
    for receipt in selected:
        row = await reader.read(receipt['tool'], deepcopy(receipt['arguments']))
        require(_canonical(row) == _canonical(receipt['journal']), 'Replay changed operation/result/checkpoint/history.')
        current = _proof(await _call(capture_activity))
        require(_canonical(current) == _canonical(activity), 'Replay performed another domain dispatch or mass calculation.')
        replays.append(dict(tool=receipt['tool'], arguments=receipt['arguments'], journal=deepcopy(row)))
    after_journal = read_journal(reader.journal_path)
    require(_canonical(before_journal) == _canonical(after_journal), 'Replay changed whole durable journal.')
    after = _proof(await _call(capture_full))
    require(_canonical(before) == _canonical(after), 'Whole original part/neighbor/session changed during replay.')
    return dict(scope=SCOPE, originals=selected, rows=replays, before=before, after=after,
        before_journal=before_journal, after_journal=after_journal, activity=activity,
        accepted=False, native_acceptance=False, cleanup_authorized=False,
        open_gates=['actual_owner_native_scope_and_activity_producers', 'exact_installed_B3_driver',
                    'all_I01_I12_terminal_calls', 'terminal_owned_cleanup'])
