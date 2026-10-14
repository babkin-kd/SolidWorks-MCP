"""Pure filesystem scenarios with fake Windows leases; no CAD/Win32 acceptance."""

from contextlib import contextmanager
from copy import deepcopy
import ctypes
import os
from pathlib import Path
import threading
import sys
from types import SimpleNamespace

import pytest

from solidworks_mcp import native_first_save_files as files
from solidworks_mcp.jobs import ExecutionFailure


class FakeLocks:
    def __init__(self, *, directory_share=1):
        self.directory_share = directory_share
        self.paths = []
        self.closed = False
        self.retargeted = {}

    def acquire(self, path, *, directory, delete=False):
        self.paths.append((path, directory, delete))
        return path

    def check(self):
        assert not self.closed

    def close(self):
        self.closed = True

    def retarget(self, handle, path):
        self.retargeted[handle] = path
        self.paths = [(path if original == handle else original, directory, delete)
                      for original, directory, delete in self.paths]

    def directory_paths(self):
        return [path for path, directory, _ in self.paths if directory]

    def path_handle(self, path):
        assert [p for p, directory, _ in self.paths if directory and p == path] == [path]
        return path


def test_windows_directory_and_file_handles_do_not_share_write_delete(monkeypatch, tmp_path):
    calls = []
    class Function:
        def __init__(self, result=1): self.result = result
        def __call__(self, *args):
            calls.append((self, args))
            return self.result
    class Kernel:
        CreateFileW = Function(123)
        CloseHandle = Function()
        GetFinalPathNameByHandleW = Function()
        FlushFileBuffers = Function()
        GetFileInformationByHandle = Function()
    kernel = Kernel()
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *args, **kwargs: kernel, raising=False)
    monkeypatch.setattr(files._WindowsLocks, 'check', lambda self: None)
    locks = files._WindowsLocks()
    locks.acquire(tmp_path, directory=True)
    create = next(args for function, args in calls if function is kernel.CreateFileW)
    assert create[1] & 0x80000000 and create[1] & 1 and create[1] & 0x80
    assert create[2] == 1 and not create[2] & (2 | 4)
    assert create[5] & 0x200000 and create[5] & 0x2000000
    assert not create[5] & 0x40000000  # synchronous; no FILE_FLAG_OVERLAPPED
    locks.acquire(tmp_path / 'staged.SLDPRT', directory=False, delete=True)
    file_create = [args for function, args in calls if function is kernel.CreateFileW][-1]
    assert file_create[1] & 0xC0000000 == 0xC0000000 and file_create[1] & 0x10000
    assert file_create[2] == 1 and not file_create[2] & (2 | 4)
    assert not file_create[5] & 0x40000000
    publication = files._WindowsLocks(directory_share=3)
    publication.acquire(tmp_path, directory=True)
    publication.acquire(tmp_path / 'staged.SLDPRT', directory=False, delete=True)
    creates = [args for function, args in calls if function is kernel.CreateFileW]
    assert creates[-2][2] == 3 and not creates[-2][2] & 4
    assert creates[-1][2] == 1  # file sharing is never weakened
    publication.close()
    locks.close()


@pytest.fixture
def environment(monkeypatch, tmp_path):
    monkeypatch.setattr(files, '_require_local_ntfs', lambda path: None)
    monkeypatch.setattr(files, '_WindowsLocks', FakeLocks)
    monkeypatch.setattr(files, '_RETAINED_PUBLICATIONS', {})

    def fake_remove(path, expected):
        assert files.native_file_facts(str(path), 'part') == expected
        path.unlink()

    monkeypatch.setattr(files, '_remove_owned_file', fake_remove)
    def fake_move(locks, handle, destination, *, root_directory):
        # Effect simulation only, not an atomic-move/Win32 sharing proof.
        assert root_directory == destination.parent
        os.link(handle, destination, follow_symlinks=False)
        handle.unlink()
    monkeypatch.setattr(files, '_move_no_replace', fake_move)
    @contextmanager
    def fake_duplicate_reader(locks, handle):
        # No real Windows handle: filesystem-only simulation of a bound reader.
        with locks.retargeted.get(handle, handle).open('rb') as stream:
            yield stream
    monkeypatch.setattr(files, '_duplicate_reader', fake_duplicate_reader)
    parent = tmp_path / 'local'
    parent.mkdir()
    return parent / 'Контрольная деталь.SLDPRT'


@contextmanager
def staged(destination):
    token = files.prepare_destination(str(destination))
    with files.lease_destination(token) as lease:
        receipt = files.create_owned_stage(lease)
        receipt.filename.write_bytes(b'synthetic native part bytes; not CAD geometry')
        files.inspect_staged(receipt)
        yield receipt, lease


def test_prepare_read_only_and_exact_lease_ownership(environment):
    token = files.prepare_destination(str(environment))
    original = deepcopy(token)
    assert list(environment.parent.iterdir()) == []
    with files.lease_destination(token) as lease:
        receipt = files.create_owned_stage(lease)
        assert receipt.lease is lease and receipt in lease.stages
        assert receipt.directory.parent == environment.parent and receipt.filename.suffix == '.SLDPRT'
        assert list(receipt.directory.iterdir()) == []
        assert len(lease.locks.paths) == len(token['ancestry']) + 1
    assert token == original and not lease.active and lease.locks.closed


def test_stage_path_checkpoint_precedes_mkdir_and_confirmed_ownership(environment):
    checkpoints = []
    def record(value):
        checkpoints.append((value, Path(value['directory']).exists()))
    with files.lease_destination(files.prepare_destination(str(environment))) as lease:
        receipt = files.create_owned_stage(lease, on_owned_change=record)
        assert checkpoints[0][0]['pending_creation'] is True and checkpoints[0][1] is False
        assert checkpoints[0][0]['creation_attempted'] is False
        assert checkpoints[1][0]['pending_creation'] is False and checkpoints[1][1] is True
        assert checkpoints[1][0]['creation_returned'] is True and receipt.identity is not None


def test_lost_mkdir_ack_retains_planned_receipt_without_adoption_cleanup(environment, monkeypatch):
    original = Path.mkdir
    def lost_ack(path, *args, **kwargs):
        original(path, *args, **kwargs)
        if path.name.startswith('sw-first-save-'):
            raise OSError('lost mkdir acknowledgement')
    with files.lease_destination(files.prepare_destination(str(environment))) as lease:
        monkeypatch.setattr(Path, 'mkdir', lost_ack)
        with pytest.raises(files.StageCreationFailure) as error:
            files.create_owned_stage(lease)
        receipt = error.value.receipt
        assert receipt.directory.exists() and receipt.uncertain and receipt.pending_creation
        assert receipt.identity is None and receipt.creation_returned is False
        with pytest.raises(ExecutionFailure): files.inspect_staged(receipt)
        with pytest.raises(ExecutionFailure): files.cleanup_owned_stage(receipt, lease, verified_terminal=True)


def test_checkpoint_failure_before_mkdir_has_no_filesystem_effect(environment):
    def record(value):
        raise ValueError('durable checkpoint failed')
    with files.lease_destination(files.prepare_destination(str(environment))) as lease:
        with pytest.raises(ValueError): files.create_owned_stage(lease, on_owned_change=record)
        assert list(environment.parent.iterdir()) == []


def test_publish_same_volume_move_verified_and_cleanup_keeps_destination(environment):
    with staged(environment) as (receipt, lease):
        output = files.publish(receipt, lease)
        assert output['status'] == 'published', output
        assert output['publication_attempted'] is output['publication_returned'] is output['published'] is True
        assert output['pending_publication'] is output['uncertain'] is False
        assert not receipt.filename.exists() and environment.exists()
        assert output['destination_file']['sha256'] == receipt.facts['sha256']
        original = environment.read_bytes()
        cleanup = files.cleanup_owned_stage(receipt, lease, verified_terminal=True)
        assert cleanup['status'] == 'retained_empty_owned_directory'
        assert cleanup['file_moved'] is True
        assert cleanup['destination_removed'] is False and environment.read_bytes() == original
        assert receipt.directory.exists() and not list(receipt.directory.iterdir())


def test_existing_destination_refused_without_touching_file(environment):
    environment.write_bytes(b'foreign')
    with pytest.raises(ExecutionFailure, match='already exists'):
        files.prepare_destination(str(environment))
    assert environment.read_bytes() == b'foreign' and len(list(environment.parent.iterdir())) == 1


def test_raced_foreign_destination_is_known_conflict_and_owned_stage_can_be_cleaned(environment):
    with staged(environment) as (receipt, lease):
        environment.write_bytes(b'raced foreign bytes')
        result = files.publish(receipt, lease)
        assert result['status'] == 'conflict' and result['uncertain'] is False
        assert result['published'] is False
        assert result['directory_phase']['strict_restored'] is True
        assert result['directory_phase']['restore_returned'] is True
        files.cleanup_owned_stage(receipt, lease, verified_terminal=True)
        assert environment.read_bytes() == b'raced foreign bytes'


@pytest.mark.parametrize('exception', [OSError('lost ack'), FileExistsError('lost ack')])
def test_exception_after_simulated_move_is_unknown_never_retried_or_deleted(environment, monkeypatch, exception):
    original_move = files._move_no_replace
    calls = []

    def lost_ack(locks, handle, destination, *, root_directory):
        calls.append((handle, destination))
        original_move(locks, handle, destination, root_directory=root_directory)
        raise exception

    monkeypatch.setattr(files, '_move_no_replace', lost_ack)
    with staged(environment) as (receipt, lease):
        result = files.publish(receipt, lease)
        assert result['status'] == 'unknown' and result['uncertain'] is True
        assert result['directory_phase']['strict_restored'] is True
        assert result['file_lease_retained'] is False
        assert not receipt.filename.exists() and environment.exists()
        with pytest.raises(ExecutionFailure): files.publish(receipt, lease)
        with pytest.raises(ExecutionFailure): files.cleanup_owned_stage(receipt, lease, verified_terminal=True)
        assert len(calls) == 1 and not receipt.filename.exists() and environment.exists()


def test_throw_before_observed_effect_remains_unknown_without_oracle(environment, monkeypatch):
    def unsupported_move(*args, **kwargs):
        raise OSError('Filesystem acknowledgement unavailable')
    monkeypatch.setattr(files, '_move_no_replace', unsupported_move)
    with staged(environment) as (receipt, lease):
        assert files.publish(receipt, lease)['status'] == 'unknown'
        assert not environment.exists() and receipt.uncertain


@pytest.mark.parametrize('change', ['sidecar', 'changed_bytes', 'replacement', 'uninspected'])
def test_stage_inventory_or_identity_changes_prevent_publication(environment, change):
    with staged(environment) as (receipt, lease):
        if change == 'sidecar': (receipt.directory / 'unexpected.sldprt').write_bytes(b'foreign')
        if change == 'changed_bytes': receipt.filename.write_bytes(b'changed geometry bytes')
        if change == 'replacement':
            receipt.filename.rename(receipt.directory / 'retained-original')
            receipt.filename.write_bytes(b'replacement')
        if change == 'uninspected': receipt.facts = None
        with pytest.raises(ExecutionFailure): files.publish(receipt, lease)
        assert not environment.exists() and receipt.publication_attempted is False


def test_unknown_sidecar_never_removed_by_cleanup(environment):
    with staged(environment) as (receipt, lease):
        foreign = receipt.directory / 'sidecar'
        foreign.write_bytes(b'foreign')
        with pytest.raises(ExecutionFailure): files.cleanup_owned_stage(receipt, lease, verified_terminal=True)
        assert foreign.read_bytes() == b'foreign' and receipt.filename.exists()


def test_cleanup_requires_exact_bool_terminal_proof_and_unchanged_fingerprint(environment):
    with staged(environment) as (receipt, lease):
        for terminal in (False, 1, 'true'):
            with pytest.raises(ExecutionFailure): files.cleanup_owned_stage(receipt, lease, verified_terminal=terminal)
        receipt.filename.write_bytes(b'changed')
        with pytest.raises(ExecutionFailure): files.cleanup_owned_stage(receipt, lease, verified_terminal=True)
        assert receipt.filename.read_bytes() == b'changed'


def test_fabricated_stage_receipt_cannot_adopt_existing_directory(environment):
    token = files.prepare_destination(str(environment))
    with files.lease_destination(token) as lease:
        directory = environment.parent / 'preexisting'
        directory.mkdir()
        path = directory / 'Первая запись.SLDPRT'
        path.write_bytes(b'not owned')
        forged = files.OwnedStage(lease, directory, files._plain(directory, True), path)
        with pytest.raises(ExecutionFailure): files.inspect_staged(forged)
        assert path.read_bytes() == b'not owned'


def test_parent_identity_change_rejected_before_lease_or_stage(environment):
    token = files.prepare_destination(str(environment))
    token['ancestry'][-1]['identity'][1] += 1
    with pytest.raises(ExecutionFailure):
        with files.lease_destination(token): pytest.fail('Stale parent accepted')
    assert list(environment.parent.iterdir()) == []


def test_thread_or_expired_lease_cannot_inspect_or_publish(environment):
    with staged(environment) as (receipt, lease):
        lease.thread = threading.get_ident() + 1
        with pytest.raises(ExecutionFailure): files.inspect_staged(receipt)
        lease.thread = threading.get_ident()
    with pytest.raises(ExecutionFailure): files.publish(receipt, lease)
    assert not environment.exists()


def test_parent_or_stage_reparse_rejected_without_effect(environment, monkeypatch):
    with staged(environment) as (receipt, lease):
        plain = files._plain
        def redirected(path, directory):
            if path == receipt.directory:
                raise ExecutionFailure('redirect', 'reparse denied', uncertain=False)
            return plain(path, directory)
        monkeypatch.setattr(files, '_plain', redirected)
        with pytest.raises(ExecutionFailure): files.publish(receipt, lease)
        assert not environment.exists() and not receipt.publication_attempted


@pytest.mark.parametrize('name', ['CON.SLDPRT', 'wrong.SLDASM', '.hidden.SLDPRT', 'bad?.SLDPRT'])
def test_invalid_native_filenames_refused(environment, name):
    with pytest.raises(ExecutionFailure): files.prepare_destination(str(environment.with_name(name)))
    assert list(environment.parent.iterdir()) == []


def test_nonwindows_or_remote_contract_fails_closed_before_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(files.os, 'name', 'posix')
    with pytest.raises(ExecutionFailure, match='Windows NTFS'):
        files._require_local_ntfs(tmp_path)


def test_prepare_ancestry_token_detached_and_lease_rejects_extra_fields(environment):
    token = files.prepare_destination(str(environment))
    token['extra'] = True
    with pytest.raises(ExecutionFailure):
        with files.lease_destination(token): pytest.fail('Extra token field accepted')


def test_move_return_followed_by_bad_disk_readback_is_unknown(environment, monkeypatch):
    original = files._locked_file_facts
    def corrupted(locks, handle, path):
        value = original(locks, handle, path)
        if Path(path) == environment:
            value['sha256'] = '0' * 64
        return value
    monkeypatch.setattr(files, '_locked_file_facts', corrupted)
    with staged(environment) as (receipt, lease):
        result = files.publish(receipt, lease)
        assert result['status'] == 'unknown' and result['publication_returned'] is True
        assert environment.exists() and not receipt.filename.exists()


def test_lost_owned_cleanup_ack_is_unknown_and_not_repeated(environment, monkeypatch):
    calls = []
    def lost_ack(path, facts):
        calls.append(path)
        path.unlink()
        raise OSError('lost cleanup acknowledgement')
    monkeypatch.setattr(files, '_remove_owned_file', lost_ack)
    with staged(environment) as (receipt, lease):
        with pytest.raises(ExecutionFailure) as error:
            files.cleanup_owned_stage(receipt, lease, verified_terminal=True)
        assert error.value.uncertain is True and receipt.uncertain and receipt.pending_cleanup
        with pytest.raises(ExecutionFailure): files.cleanup_owned_stage(receipt, lease, verified_terminal=True)
        assert len(calls) == 1 and not environment.exists()


def test_passive_observer_handles_owned_empty_file_and_cleaned_stage_without_adoption(environment):
    with files.lease_destination(files.prepare_destination(str(environment))) as lease:
        receipt = files.create_owned_stage(lease)
        empty = files.observe_owned_stage(receipt, lease)
        assert empty['empty'] is True and empty['file'] is None and receipt.facts is None
        receipt.filename.write_bytes(b'synthetic part')
        observed = files.observe_owned_stage(receipt, lease)
        assert observed['empty'] is False and observed['file']['bytes'] > 0 and receipt.facts is None
        files.inspect_staged(receipt)
        files.cleanup_owned_stage(receipt, lease, verified_terminal=True)
        clean = files.observe_owned_stage(receipt, lease)
        assert clean['empty'] is True and clean['checkpoint']['cleaned'] is True


def test_passive_destination_observation_absent_published_and_changed_ancestry(environment):
    token = files.prepare_destination(str(environment))
    assert files.observe_destination(token) is None
    with staged(environment) as (receipt, lease):
        assert files.publish(receipt, lease)['status'] == 'published'
        files.cleanup_owned_stage(receipt, lease, verified_terminal=True)
        final = files.observe_destination(token)
        assert final['identity'] == receipt.facts['identity'] and final['sha256'] == receipt.facts['sha256']
    token['ancestry'][-1]['identity'][1] += 1
    with pytest.raises(ExecutionFailure): files.observe_destination(token)


def test_passive_owned_observer_rejects_unknown_sidecar_without_removal(environment):
    with staged(environment) as (receipt, lease):
        sidecar = receipt.directory / 'extra'
        sidecar.write_bytes(b'foreign')
        with pytest.raises(ExecutionFailure): files.observe_owned_stage(receipt, lease)
        assert sidecar.read_bytes() == b'foreign' and receipt.filename.exists()


def test_handle_rename_structure_fixed_width_full_utf16_path_no_replace(tmp_path):
    destination = tmp_path / 'Контрольная😀.SLDPRT'
    buffer = files._rename_buffer(destination)
    header = files._FileRenameInfo.from_buffer(buffer)
    encoded = str(destination).encode('utf-16-le')
    offset = files._FileRenameInfo.name.offset
    assert offset == (20 if ctypes.sizeof(ctypes.c_void_p) == 8 else 12)
    assert header.replace_or_flags == 0 and header.root_directory is None
    assert header.name_length == len(encoded)
    assert buffer.raw[offset:offset + len(encoded)] == encoded
    assert buffer.raw[offset + len(encoded):offset + len(encoded) + 2] == b'\0\0'


def test_nt_move_uses_held_file_and_parent_handles_basename_class_ten(tmp_path, monkeypatch):
    calls = []
    class Function:
        def __call__(self, handle, iosb, pointer, size, info_class):
            calls.append((handle, info_class, ctypes.string_at(pointer, size)))
            ctypes.cast(iosb, ctypes.POINTER(files._IoStatusBlock)).contents.state.status = 0
            return 0
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **kw: SimpleNamespace(NtSetInformationFile=Function()), raising=False)
    files._move_no_replace(None, 987, tmp_path / 'Публикация😀.SLDPRT', root_directory=654)
    assert len(calls) == 1 and calls[0][:2] == (987, 10)
    header = files._FileRenameInfo.from_buffer_copy(calls[0][2])
    assert header.replace_or_flags == 0 and header.root_directory == 654
    offset = files._FileRenameInfo.name.offset
    assert calls[0][2][offset:offset + header.name_length].decode('utf-16-le') == 'Публикация😀.SLDPRT'


def test_moved_stage_cleanup_rejects_changed_final_without_removing_destination(environment):
    with staged(environment) as (receipt, lease):
        assert files.publish(receipt, lease)['status'] == 'published'
        assert files.observe_owned_stage(receipt, lease)['empty'] is True
        environment.write_bytes(b'foreign final change')
        with pytest.raises(ExecutionFailure): files.cleanup_owned_stage(receipt, lease, verified_terminal=True)
        assert environment.read_bytes() == b'foreign final change'


def test_locked_fingerprint_bound_to_path_identity_not_different_handle(environment, monkeypatch):
    alternate = environment.parent / 'different.SLDPRT'
    alternate.write_bytes(b'different file')
    @contextmanager
    def wrong_reader(locks, handle):
        with alternate.open('rb') as stream:
            yield stream
    monkeypatch.setattr(files, '_duplicate_reader', wrong_reader)
    with staged(environment) as (receipt, lease):
        with pytest.raises(ExecutionFailure): files.publish(receipt, lease)
        assert not receipt.publication_attempted and not environment.exists()


def test_locked_fingerprint_size_budget_before_possible_move(environment, monkeypatch):
    monkeypatch.setattr(files, 'MAX_FILE_BYTES', 4)
    with staged(environment) as (receipt, lease):
        with pytest.raises(ExecutionFailure): files.publish(receipt, lease)
        assert not receipt.publication_attempted and not environment.exists()


def test_duplicate_reader_transfers_only_own_duplicate_never_original_handle(tmp_path, monkeypatch):
    from ctypes import wintypes
    path = tmp_path / 'reader'
    path.write_bytes(b'bounded fixture bytes')
    class Function:
        def __init__(self, action): self.action = action
        def __call__(self, *args): return self.action(*args)
    duplicated = []
    def duplicate(process, handle, target, pointer, access, inherit, options):
        assert options == 2 and access == 0 and inherit is False
        descriptor = os.dup(handle)
        duplicated.append(descriptor)
        ctypes.cast(pointer, ctypes.POINTER(wintypes.HANDLE))[0] = descriptor
        return 1
    kernel = SimpleNamespace(GetCurrentProcess=Function(lambda: 123), DuplicateHandle=Function(duplicate),
                             CloseHandle=Function(lambda handle: os.close(handle.value)))
    locks = SimpleNamespace(kernel=kernel, ctypes=ctypes, wintypes=wintypes)
    monkeypatch.setitem(sys.modules, 'msvcrt', SimpleNamespace(open_osfhandle=lambda handle, flags: handle))
    monkeypatch.setattr(os, 'O_BINARY', 0, raising=False)
    with path.open('rb') as original:
        with files._duplicate_reader(locks, original.fileno()) as stream:
            assert stream.read() == b'bounded fixture bytes'
        original.seek(0)
        assert original.read() == b'bounded fixture bytes'
        with pytest.raises(OSError): os.fstat(duplicated[0])


def changed_ctime(info):
    values = {name: getattr(info, name) for name in
              ('st_dev', 'st_ino', 'st_size', 'st_mode', 'st_mtime_ns', 'st_ctime_ns')}
    values['st_ctime_ns'] += 100
    values['st_file_attributes'] = getattr(info, 'st_file_attributes', 0)
    return SimpleNamespace(**values)


def test_locked_reader_never_ignores_raw_handle_ctime_changes(environment, monkeypatch):
    original = os.fstat
    calls = []
    def drift(descriptor):
        value = original(descriptor)
        calls.append(descriptor)
        return changed_ctime(value) if len(calls) == 2 else value
    with staged(environment) as (receipt, lease):
        monkeypatch.setattr(files.os, 'fstat', drift)
        with pytest.raises(ExecutionFailure): files.publish(receipt, lease)
        assert not receipt.publication_attempted and not environment.exists()


def test_locked_reader_never_ignores_raw_path_ctime_changes(environment, monkeypatch):
    original = Path.lstat
    calls = []
    with staged(environment) as (receipt, lease):
        def drift(path):
            value = original(path)
            if path == receipt.filename:
                calls.append(path)
                # _plain, path-before, path-after within the locked reader.
                return changed_ctime(value) if len(calls) == 3 else value
            return value
        monkeypatch.setattr(Path, 'lstat', drift)
        with pytest.raises(ExecutionFailure): files.publish(receipt, lease)
        assert not receipt.publication_attempted and not environment.exists()


@pytest.mark.parametrize('returned,iosb_status,information,exception', [
    (0xC0000035, 0x103, 0, FileExistsError),
    (0xC0000043, 0x103, 0, OSError),
    (0x103, 0, 0, files.PendingNativeRename),
    (0, 0x103, 0, OSError),
    (0, 0, 1, OSError),
])
def test_nt_status_controls_pending_not_unchanged_iosb(tmp_path, monkeypatch, returned, iosb_status, information, exception):
    calls = []
    class Function:
        def __call__(self, handle, iosb, pointer, size, info_class):
            calls.append((handle, info_class))
            value = ctypes.cast(iosb, ctypes.POINTER(files._IoStatusBlock)).contents
            value.state.status, value.information = iosb_status, information
            return returned
    monkeypatch.setattr(ctypes, 'WinDLL', lambda *a, **kw: SimpleNamespace(NtSetInformationFile=Function()), raising=False)
    with pytest.raises(exception) as error:
        files._move_no_replace(None, 12, tmp_path / 'Результат.SLDPRT', root_directory=34)
    assert calls == [(12, 10)]
    if returned == 0x103:
        resources = error.value.resources
        assert resources[1].state.status == iosb_status and resources[-2:] == (12, 34)
    else:
        assert not isinstance(error.value, files.PendingNativeRename)


def test_strict_cad_phase_weak_publication_only_and_file_held_until_restore(environment, monkeypatch):
    instances, events = [], []
    class TrackedLocks(FakeLocks):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.number = len(instances)
            instances.append(self)
        def acquire(self, path, *, directory, delete=False):
            events.append(('acquire', self.number, self.directory_share, directory))
            if self.directory_share == 3:
                assert not instances[0].closed
            return super().acquire(path, directory=directory, delete=delete)
        def close(self):
            events.append(('close', self.number))
            super().close()
    monkeypatch.setattr(files, '_WindowsLocks', TrackedLocks)
    original_move = files._move_no_replace
    with staged(environment) as (receipt, lease):
        # Native copy/readback belongs to the caller and sees strict leases.
        assert lease.mode == 'strict' and instances[0].directory_share == 1
        def move(locks, handle, destination, *, root_directory):
            assert lease.mode == 'publication' and lease.locks.directory_share == 3
            assert instances[0].closed and not locks.closed
            assert all(not delete for _, directory, delete in lease.locks.paths if directory)
            events.append(('move', locks.number))
            return original_move(locks, handle, destination, root_directory=root_directory)
        monkeypatch.setattr(files, '_move_no_replace', move)
        result = files.publish(receipt, lease)
        assert result['status'] == 'published'
        assert lease.mode == 'strict' and lease.locks.directory_share == 1
        assert result['directory_phase'] == dict(
            enter_attempted=True, enter_returned=True, pending_enter=False,
            restore_attempted=True, restore_returned=True, pending_restore=False, strict_restored=True)
        original, file_locks, weaker, restored = instances
        assert events.index(('close', original.number)) < events.index(('move', file_locks.number))
        assert events.index(('move', file_locks.number)) < events.index(('close', weaker.number))
        assert events.index(('close', weaker.number)) < events.index(('close', file_locks.number))
        assert not restored.closed and file_locks.closed
    assert restored.closed


def test_restore_failure_retains_exact_file_and_directory_handles_no_cad_or_retry(environment, monkeypatch):
    instances = []
    class RestoreFailureLocks(FakeLocks):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.restoring = self.directory_share == 1 and any(lock.directory_share == 3 for lock in instances)
            instances.append(self)
        def acquire(self, path, *, directory, delete=False):
            if self.restoring and directory:
                raise OSError('Strict lease reacquisition failed')
            return super().acquire(path, directory=directory, delete=delete)
    monkeypatch.setattr(files, '_WindowsLocks', RestoreFailureLocks)
    with staged(environment) as (receipt, lease):
        result = files.publish(receipt, lease)
        assert result['status'] == 'unknown' and result['publication_returned'] is True
        assert result['published'] is False and result['pending_publication'] is True
        assert result['directory_phase']['pending_restore'] is True
        assert result['directory_phase']['strict_restored'] is False
        assert result['file_lease_retained'] is True and result['pending_native_move'] is False
        assert files._RETAINED_PUBLICATIONS[id(receipt)] == (receipt, lease)
        assert environment.exists() and not receipt.filename.exists()
        for call in (lambda: files.publish(receipt, lease), lambda: files.inspect_staged(receipt),
                     lambda: files.cleanup_owned_stage(receipt, lease, verified_terminal=True)):
            with pytest.raises(ExecutionFailure): call()
    assert not receipt.retained_file_locks.closed and not instances[2].closed


def test_unexpected_native_pending_keeps_buffers_file_root_handles_alive(environment, monkeypatch):
    resources, calls = (object(), object(), object()), []
    def pending(locks, handle, destination, *, root_directory):
        calls.append((locks, handle, root_directory))
        raise files.PendingNativeRename(resources)
    monkeypatch.setattr(files, '_move_no_replace', pending)
    with staged(environment) as (receipt, lease):
        result = files.publish(receipt, lease)
        assert result['status'] == 'unknown' and result['pending_native_move'] is True
        assert result['file_lease_retained'] is True and result['pending_publication'] is True
        assert result['directory_phase']['restore_attempted'] is False
        assert lease.mode == 'publication' and lease.retain
        assert receipt.pending_native_resources is resources
        assert files._RETAINED_PUBLICATIONS[id(receipt)][0] is receipt
        with pytest.raises(ExecutionFailure): files.publish(receipt, lease)
    assert len(calls) == 1 and not calls[0][0].closed and not lease.locks.closed
    assert receipt.filename.exists() and not environment.exists()


def test_replacement_directory_identity_mismatch_never_reaches_native_rename(environment, monkeypatch):
    original_snapshot, calls = files._directory_snapshot, []
    def different(locks):
        rows = original_snapshot(locks)
        if locks.directory_share == 3:
            rows[-1] = (rows[-1][0], [123, 456])
        return rows
    monkeypatch.setattr(files, '_directory_snapshot', different)
    monkeypatch.setattr(files, '_move_no_replace', lambda *a, **kw: calls.append(a))
    with staged(environment) as (receipt, lease):
        result = files.publish(receipt, lease)
        assert result['status'] == 'unknown' and calls == []
        assert lease.mode == 'strict' and result['directory_phase']['strict_restored'] is True
        assert receipt.filename.exists() and not environment.exists()
        with pytest.raises(ExecutionFailure): files.publish(receipt, lease)


def test_retained_publication_budget_rejects_before_any_new_write(environment, monkeypatch):
    monkeypatch.setattr(files, '_RETAINED_PUBLICATIONS', {i: object() for i in range(files.MAX_RETAINED_PUBLICATIONS)})
    with staged(environment) as (receipt, lease):
        with pytest.raises(ExecutionFailure, match='reconciliation'): files.publish(receipt, lease)
        assert not receipt.publication_attempted and not environment.exists()
