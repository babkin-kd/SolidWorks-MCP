"""Actual parent publication gate and atomic writer; artificial owned process only."""
from copy import deepcopy
import json
import os
from pathlib import Path

import pytest

from test_b4_installed_child import FakeProcess, harness, helper, ready, false_native


@pytest.fixture
def live_child(harness, tmp_path):
    _, process, launches, candidate = harness
    child = helper.InstalledMetadataChild(
        tmp_path / 'own-live-inspection', wheel_path='pure-wheel', expected_version='pure',
        expected_git_sha='b' * 40, expected_wheel_sha256='a' * 64,
        profile='dimension_commands_live')
    ready(child)
    child.sdk_live = True
    return child, process, launches, candidate


def request(child):
    return dict(scope='b4_dimension_control_command_v1', sequence=1, nonce=child.identity['nonce'],
                lineage=helper.control_lineage(child.identity, child.path), command='inspect', arguments={})


def snapshot_files(child):
    return {path.name: path.read_bytes() for path in child.path.iterdir() if path.is_file()}


def assert_no_process_action(child, process, launches, launch_count):
    assert child._original_process is process
    assert len(launches) == launch_count
    assert process.waits == [] and process.stdin.getvalue() == b''
    assert process.stdin.closed is False
    assert child.eof_sent is False


def test_original_live_inspection_exact_atomic_request_and_no_second_publication(live_child):
    child, process, launches, _ = live_child
    original_identity, original_spec = deepcopy(child._launch_identity), deepcopy(child._launch_spec)
    before = snapshot_files(child)
    expected = request(child)
    path = child.publish_live_inspection()
    assert path == child.path / 'dimension-command-0001.json'
    raw = json.dumps(expected, ensure_ascii=False, allow_nan=False, sort_keys=True).encode('utf8')
    assert path.read_bytes() == raw
    assert helper.owned._read(path) == expected
    assert not path.with_name(path.name + '.publishing').exists()
    assert not (child.path / 'dimension-command-ack-0001.json').exists()
    assert child._inspection_publication_attempted is True
    assert child.process is process and child._original_process is process
    assert child._launch_identity == original_identity and child._launch_spec == original_spec
    assert child.sdk_live is True and child.sdk_closed is False
    for proof_name in ('parent-launch.json', 'child-ready.json'):
        proof = helper.owned._read(child.path / proof_name)
        false_native(proof)
        for name, expected_flag in helper.flags().items():
            assert proof[name] == expected_flag and type(proof[name]) is type(expected_flag)
    after = snapshot_files(child)
    assert after.pop(path.name) == raw and after == before
    with pytest.raises(helper.InstalledChildError, match='one-shot; no retry'):
        child.publish_live_inspection()
    assert snapshot_files(child) == {**before, path.name: raw}
    assert_no_process_action(child, process, launches, 2)


@pytest.mark.parametrize('change', ['no_ready', 'no_sdk', 'sdk_closed', 'eof', 'exit', 'wrong_profile', 'launch_failed'])
def test_missing_original_ready_open_sdk_live_process_or_profile_consumes_attempt_without_publish(live_child, change):
    child, process, launches, _ = live_child
    if change == 'no_ready':
        child.ready = None
    elif change == 'no_sdk':
        child.sdk_live = False
    elif change == 'sdk_closed':
        child.sdk_closed = True
    elif change == 'eof':
        child.eof_sent = True
    elif change == 'exit':
        process.code = 0
    elif change == 'wrong_profile':
        child._profile = 'dimension_commands'
    else:
        child.launch_failed = 'Original launch proof unavailable'
    before = snapshot_files(child)
    with pytest.raises(helper.InstalledChildError, match='ready/live|open SDK') as caught:
        child.publish_live_inspection()
    assert caught.value.retained_owner is child
    assert child._inspection_publication_attempted is True
    assert snapshot_files(child) == before
    assert child.process is child._original_process is process
    assert len(launches) == 2 and process.waits == [] and process.stdin.getvalue() == b''
    with pytest.raises(helper.InstalledChildError, match='one-shot; no retry'):
        child.publish_live_inspection()
    assert snapshot_files(child) == before


def test_replacement_popen_with_same_pid_start_and_candidate_cannot_be_adopted(live_child):
    child, original, launches, _ = live_child
    replacement = FakeProcess()
    assert replacement.pid == original.pid
    child.process = replacement
    before = snapshot_files(child)
    with pytest.raises(helper.InstalledChildError, match='Original ready/live'):
        child.publish_live_inspection()
    assert child._inspection_publication_attempted is True
    assert child._original_process is original and child.process is replacement
    assert child._launch_identity['pid'] == original.pid
    assert snapshot_files(child) == before
    assert original.waits == replacement.waits == [] and len(launches) == 2
    assert original.stdin.getvalue() == replacement.stdin.getvalue() == b''


@pytest.mark.parametrize('change', ['pid', 'cached_start', 'current_start'])
def test_original_pid_and_start_incarnation_drift_refuses_without_publication(live_child, monkeypatch, change):
    child, process, launches, _ = live_child
    if change == 'pid':
        process.pid += 1
    elif change == 'cached_start':
        child.start['ticks'] += 1
    else:
        monkeypatch.setattr(helper.owned, '_process_start', lambda *args: {'kind': 'pure_fake', 'ticks': 124})
    before = snapshot_files(child)
    with pytest.raises(helper.InstalledChildError, match='binding changed|process start changed'):
        child.publish_live_inspection()
    assert child._inspection_publication_attempted is True
    assert snapshot_files(child) == before
    assert_no_process_action(child, process, launches, 2)


@pytest.mark.parametrize('change', [
    'identity_nonce', 'identity_pid', 'identity_candidate', 'identity_helpers', 'ready_identity',
    'nonce', 'candidate_wheel', 'candidate_package', 'candidate_sdk', 'helpers_mapping',
    'spec_nonce', 'spec_profile', 'spec_root', 'spec_parent',
    'specfile_nonce', 'specfile_extra', 'specfile_json',
])
def test_original_identity_candidate_spec_and_actual_specfile_are_immutable(live_child, change):
    child, process, launches, _ = live_child
    if change == 'identity_nonce':
        child.identity['nonce'] = 'f' * 64
    elif change == 'identity_pid':
        child.identity['pid'] += 1
    elif change == 'identity_candidate':
        child.identity['candidate']['wheel']['source_digest'] = 'f' * 64
    elif change == 'identity_helpers':
        child.identity['helpers']['verifier_b4_dimension_command_host.py'] = 'f' * 64
    elif change == 'ready_identity':
        child.ready['identity']['nonce'] = 'f' * 64
    elif change == 'nonce':
        child.nonce = 'f' * 64
    elif change == 'candidate_wheel':
        child.candidate['wheel']['wheel_sha256'] = 'f' * 64
    elif change == 'candidate_package':
        child.candidate['package_root'] = 'source/src'
    elif change == 'candidate_sdk':
        child.candidate['sdk_version'] = 'foreign-sdk'
    elif change == 'helpers_mapping':
        child.helpers.pop('verifier_b4_dimension_command_host.py')
    elif change == 'spec_nonce':
        child.spec['nonce'] = 'f' * 64
    elif change == 'spec_profile':
        child.spec['profile'] = 'metadata'
    elif change == 'spec_root':
        child.spec['state_dir'] = str(child.path.parent)
    elif change == 'spec_parent':
        child.spec['parent_pid'] += 1
    else:
        path = child.path / 'launch-spec.json'
        if change == 'specfile_json':
            path.write_bytes(b'{')
        else:
            data = helper.owned._read(path)
            if change == 'specfile_nonce':
                data['nonce'] = 'f' * 64
            else:
                data['extra'] = True
            path.write_text(json.dumps(data), encoding='utf8')
    before = snapshot_files(child)
    with pytest.raises(helper.InstalledChildError) as caught:
        child.publish_live_inspection()
    assert caught.value.retained_owner is child
    if change == 'specfile_json':
        assert isinstance(caught.value.__cause__, json.JSONDecodeError)
    assert child._inspection_publication_attempted is True
    assert snapshot_files(child) == before
    assert child.process is process
    assert_no_process_action(child, process, launches, 2)
    with pytest.raises(helper.InstalledChildError, match='one-shot; no retry'):
        child.publish_live_inspection()


def test_current_frozen_helper_digest_drift_refuses_without_changing_source_helper(live_child, monkeypatch):
    child, process, launches, _ = live_child
    original_hash = helper.owned._file_sha
    changed = Path(helper.__file__).with_name('verifier_b4_dimension_command_host.py')
    source_digest = original_hash(changed)
    calls = []

    def hash_drift(path):
        calls.append(Path(path).name)
        return 'f' * 64 if Path(path) == changed else original_hash(path)

    monkeypatch.setattr(helper.owned, '_file_sha', hash_drift)
    before = snapshot_files(child)
    with pytest.raises(helper.InstalledChildError, match='helpers changed'):
        child.publish_live_inspection()
    assert changed.name in calls
    assert original_hash(changed) == source_digest
    assert child._inspection_publication_attempted is True
    assert snapshot_files(child) == before
    assert_no_process_action(child, process, launches, 2)


@pytest.mark.parametrize('failure', ['partial_write', 'fsync', 'rename', 'race'])
def test_atomic_publication_failure_retains_original_owner_attempt_and_partial(live_child, monkeypatch, failure):
    child, process, launches, _ = live_child
    final = child.path / 'dimension-command-0001.json'
    partial = child.path / (final.name + '.publishing')
    expected = json.dumps(request(child), ensure_ascii=False, allow_nan=False, sort_keys=True).encode('utf8')
    before = snapshot_files(child)
    original_identity, original_spec = deepcopy(child._launch_identity), deepcopy(child._launch_spec)
    if failure == 'partial_write':
        original_open = Path.open

        class FailedWrite:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def write(self, raw):
                self.stream.write(raw[:19])
                self.stream.flush()
                raise OSError('Own incomplete atomic request write')

            def __exit__(self, *args):
                self.stream.close()

        def failed_open(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            return FailedWrite(stream) if path == partial and args == ('xb',) else stream

        monkeypatch.setattr(Path, 'open', failed_open)
    elif failure == 'fsync':
        def fail_sync(fd):
            raise OSError('Own request fsync unknown')
        monkeypatch.setattr(os, 'fsync', fail_sync)
    else:
        primitive = 'rename' if os.name == 'nt' else 'link'
        original_publish = getattr(os, primitive)

        def fail_publish(source, destination):
            assert Path(source).read_bytes() == expected
            if failure == 'race':
                Path(destination).write_bytes(b'original-racing-request')
                return original_publish(source, destination)
            raise OSError('Own atomic publication failure')

        monkeypatch.setattr(os, primitive, fail_publish)
    with pytest.raises(helper.InstalledChildError) as caught:
        child.publish_live_inspection()
    assert caught.value.retained_owner is child
    assert isinstance(caught.value.__cause__, OSError)
    assert child._inspection_publication_attempted is True
    assert child.process is child._original_process is process
    assert child._launch_identity == original_identity and child._launch_spec == original_spec
    assert partial.read_bytes() == (expected[:19] if failure == 'partial_write' else expected)
    if failure == 'race':
        assert final.read_bytes() == b'original-racing-request'
    else:
        assert not final.exists()
    after = snapshot_files(child)
    assert {name: raw for name, raw in after.items() if name in before} == before
    assert_no_process_action(child, process, launches, 2)
    with pytest.raises(helper.InstalledChildError, match='one-shot; no retry'):
        child.publish_live_inspection()
    assert snapshot_files(child) == after
