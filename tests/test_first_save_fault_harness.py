"""Fault-harness/domain evidence with artificial CAD; not native acceptance."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_native_first_save import setup  # Reuse the real domain/JobStore fixture with artificial CAD/FS.


spec = importlib.util.spec_from_file_location('first_save_fault_harness',
    Path(__file__).resolve().parents[1] / 'scripts/verifier_first_save_faults.py')
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


@pytest.mark.parametrize('fault', harness.COPY_FAULTS)
def test_after_copy_response_fault_keeps_original_effect_unknown_and_never_replays(setup, fault):
    x = setup
    adapter = harness.CopyResponseFault(x.a, fault)
    x.c.adapter = adapter
    job = x.run()
    assert job['status'] == 'unknown' and job['mutation']['phase'] == 'unresolved'
    assert adapter.injection_applied and adapter.original_receipt['success'] is True
    assert adapter.original_receipt['errors'] == adapter.original_receipt['warnings'] == 0
    assert Path(adapter.original_receipt['filename']).read_bytes() == b'artificial persisted complete part'
    assert x.run() == job and adapter.copy_calls == x.a.copy_calls == 1
    assert x.run('another-request')['error']['code'] == 'document_mutation_blocked'
    assert x.a.open_calls == x.a.calls == x.f.publications == x.f.cleanups == 0
    assert not x.source.retired and x.source in x.a.models


def test_failed_real_delegate_is_not_labelled_as_applied_injection(setup):
    x = setup
    x.a.copy_fault = 'false'
    adapter = harness.CopyResponseFault(x.a, 'warning_after_copy')
    x.c.adapter = adapter
    job = x.run()
    assert job['status'] != 'succeeded' and adapter.injection_applied is False
    assert adapter.original_receipt['success'] is False
    assert adapter.copy_calls == 1


def test_race_is_exclusive_records_original_file_and_cannot_repeat(tmp_path):
    target = tmp_path / 'Чужая деталь.SLDPRT'
    calls = []
    def publish(stage, lease):
        calls.append(target.read_bytes())
        return {'status': 'conflict'}
    race = harness.DestinationRace(SimpleNamespace(publish=publish), tmp_path)
    lease = SimpleNamespace(token={'destination': str(target)})
    assert race.publish(None, lease) == {'status': 'conflict'}
    assert len(calls) == 1 and race.preserved_foreign_file()
    with pytest.raises(AssertionError, match='never repeat'):
        race.publish(None, lease)
    assert len(calls) == 1 and race.preserved_foreign_file()
    target.write_bytes(b'changed')
    assert not race.preserved_foreign_file()


def test_race_never_overwrites_preexisting_destination(tmp_path):
    target = tmp_path / 'Чужая деталь.SLDPRT'
    target.write_bytes(b'original')
    race = harness.DestinationRace(SimpleNamespace(publish=lambda *_: pytest.fail('No delegate call')), tmp_path)
    with pytest.raises(FileExistsError):
        race.publish(None, SimpleNamespace(token={'destination': str(target)}))
    assert target.read_bytes() == b'original'


def test_race_cannot_write_outside_private_root(tmp_path):
    private = tmp_path / 'private'
    private.mkdir()
    target = tmp_path / 'Чужая деталь.SLDPRT'
    race = harness.DestinationRace(SimpleNamespace(publish=lambda *_: pytest.fail('No delegate call')), private)
    with pytest.raises(ValueError, match='private test root'):
        race.publish(None, SimpleNamespace(token={'destination': str(target)}))
    assert not target.exists() and race.publication_calls == 0
