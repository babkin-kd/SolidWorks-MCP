"""Bounded Windows/local-NTFS first-save staging, not an atomic CAD SaveAs.

The caller owns the durable CAD/job checkpoint and independent native readback.
Strict ancestry handles deny share-write/delete throughout CAD copy/readback.
Only publication uses verified replacement directory handles sharing READ|WRITE
but never DELETE, while the exact staged file is already held RW|DELETE/shareREAD.
The NT rename is relative to its exact directory handle; strict leases are
restored before file release and before any later CAD operation.
No destination is ever removed. Lost filesystem acknowledgements remain unknown.
"""

from contextlib import contextmanager
from copy import deepcopy
import ctypes
import hashlib
from dataclasses import dataclass, field
from itertools import islice
import os
from pathlib import Path
import re
import stat
import threading
import uuid

from .documents import rejected
from .jobs import ExecutionFailure
from .native_document_save import MAX_FILE_BYTES, native_file_facts


SCOPE = 'windows_ntfs_first_save_files_v1'
MAX_ANCESTORS = 128
MAX_PATH_CHARS = 32767
MAX_RETAINED_PUBLICATIONS = 16
_RETAINED_PUBLICATIONS = {}


def _fail(code, message):
    raise rejected(code, message)


def _path(value):
    if (type(value) is not str or not value.strip() or len(value) > MAX_PATH_CHARS
            or '\0' in value):
        _fail('first_save_invalid_path', 'A bounded absolute local path is required.')
    path = Path(value)
    if not path.is_absolute() or '..' in path.parts:
        _fail('first_save_invalid_path', 'Absolute paths without parent traversal are required.')
    return path


def _filename(path):
    name = path.name
    if (not 1 <= len(name) <= 160 or name != name.strip() or name.endswith(('.', ' '))
            or name.startswith('.') or re.search(r'[\x00-\x1f\x7f\\/:*?"<>|]', name)
            or path.suffix.lower() != '.sldprt'
            or name.split('.', 1)[0].upper() in {'CON', 'PRN', 'AUX', 'NUL'}
            or re.fullmatch(r'(COM|LPT)[1-9]', name.split('.', 1)[0].upper())):
        _fail('first_save_invalid_filename', 'One nonreserved native part filename is required.')


def _plain(path, directory):
    value = path.lstat()
    if (stat.S_ISLNK(value.st_mode)
            or getattr(value, 'st_file_attributes', 0) & 0x400
            or not (stat.S_ISDIR(value.st_mode) if directory else stat.S_ISREG(value.st_mode))):
        _fail('first_save_redirect_unsupported', 'Only plain directories/files are supported.')
    return [value.st_dev, value.st_ino]


def _ancestry(parent):
    paths = list(reversed((parent, *parent.parents)))
    if len(paths) > MAX_ANCESTORS:
        _fail('first_save_ancestry_budget', 'Directory ancestry exceeds the bounded scope.')
    return [dict(path=str(path), identity=_plain(path, True)) for path in paths]


def _require_local_ntfs(path):
    if os.name != 'nt' or str(path).startswith(('\\\\', '//')):
        _fail('first_save_filesystem_unsupported', 'Only fixed local Windows NTFS is supported.')
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
    kernel.GetDriveTypeW.restype = wintypes.UINT
    kernel.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR, wintypes.DWORD]
    kernel.GetVolumeInformationW.restype = wintypes.BOOL
    fs = ctypes.create_unicode_buffer(64)
    if (kernel.GetDriveTypeW(path.anchor) != 3 or
            not kernel.GetVolumeInformationW(path.anchor, None, 0, None, None, None, fs, len(fs))
            or fs.value.upper() != 'NTFS'):
        _fail('first_save_filesystem_unsupported', 'Fixed local NTFS volume confirmation failed.')


class _WindowsLocks:
    """No filesystem mutation. Fail closed if another writer owns any handle."""
    def __init__(self, *, directory_share=1):
        if directory_share not in (1, 3):
            _fail('first_save_invalid_lease_mode', 'Only strict/publication directory sharing is supported.')
        self.directory_share = directory_share
        import ctypes
        from ctypes import wintypes
        self.ctypes, self.wintypes = ctypes, wintypes
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                           wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        self.kernel.CreateFileW.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.kernel.GetFinalPathNameByHandleW.argtypes = [wintypes.HANDLE, wintypes.LPWSTR,
                                                        wintypes.DWORD, wintypes.DWORD]
        self.kernel.GetFinalPathNameByHandleW.restype = wintypes.DWORD
        self.kernel.FlushFileBuffers.argtypes = [wintypes.HANDLE]
        self.kernel.FlushFileBuffers.restype = wintypes.BOOL
        class Info(ctypes.Structure):
            _fields_ = [('attributes', wintypes.DWORD), ('creation', wintypes.FILETIME),
                ('access', wintypes.FILETIME), ('write', wintypes.FILETIME),
                ('volume', wintypes.DWORD), ('size_high', wintypes.DWORD), ('size_low', wintypes.DWORD),
                ('links', wintypes.DWORD), ('index_high', wintypes.DWORD), ('index_low', wintypes.DWORD)]
        self.Info = Info
        self.kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(Info)]
        self.kernel.GetFileInformationByHandle.restype = wintypes.BOOL
        self.handles = []

    def acquire(self, path, *, directory, delete=False):
        # FILE_READ_ATTRIBUTES alone does not establish read sharing semantics:
        # an actual Windows probe allowed rename despite share-delete denial.
        # Include directory data/list access (GENERIC_READ + LIST_DIRECTORY).
        access = 0x80000081 if directory else 0xC0000000
        if delete:
            access |= 0x10000
        flags = 0x200000 | (0x2000000 if directory else 0)  # OPEN_REPARSE_POINT/BACKUP_SEMANTICS
        sharing = self.directory_share if directory else 1
        handle = self.kernel.CreateFileW(str(path), access, sharing, None, 3, flags, None)
        if handle == self.ctypes.c_void_p(-1).value:
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        self.handles.append((handle, path))
        self.check()
        if not directory and not self.kernel.FlushFileBuffers(handle):
            raise self.ctypes.WinError(self.ctypes.get_last_error())
        return handle

    def check(self):
        for handle, path in self.handles:
            info = self.Info()
            buffer = self.ctypes.create_unicode_buffer(MAX_PATH_CHARS + 1)
            length = self.kernel.GetFinalPathNameByHandleW(handle, buffer, len(buffer), 0)
            if (not self.kernel.GetFileInformationByHandle(handle, self.ctypes.byref(info))
                    or info.attributes & 0x400 or not 0 < length < len(buffer)):
                _fail('first_save_lease_changed', 'An acquired handle is redirected or unverifiable.')
            actual = buffer.value
            if actual.startswith('\\\\?\\'):
                actual = actual[4:]
            if os.path.normcase(os.path.normpath(actual)) != os.path.normcase(os.path.normpath(str(path))):
                _fail('first_save_lease_changed', 'An acquired handle differs from the declared path.')

    def retarget(self, handle, path):
        self.handles = [(current, path if current == handle else original)
                        for current, original in self.handles]
        self.check()

    def directory_paths(self):
        return [path for _, path in self.handles]

    def path_handle(self, path):
        matches = [handle for handle, current in self.handles if current == path]
        if len(matches) != 1:
            _fail('first_save_handle_binding', 'Exactly one prepared directory handle is required.')
        return matches[0]

    def close(self):
        while self.handles:
            handle, _ = self.handles[-1]
            if not self.kernel.CloseHandle(handle):
                raise self.ctypes.WinError(self.ctypes.get_last_error())
            self.handles.pop()


def prepare_destination(filename):
    """Read-only detached path/ancestry token; no staging ownership yet."""
    path = _path(filename)
    _filename(path)
    _require_local_ntfs(path)
    ancestors = _ancestry(path.parent)
    if os.path.lexists(path):
        _fail('first_save_destination_exists', 'Destination already exists; no overwrite is supported.')
    return dict(scope=SCOPE, destination=str(path), ancestry=ancestors)


@dataclass
class _Lease:
    token: dict
    locks: object
    thread: int = field(default_factory=threading.get_ident)
    active: bool = True
    stages: list = field(default_factory=list)
    mode: str = 'strict'
    retain: bool = False

    def check(self):
        if not self.active or self.retain or self.thread != threading.get_ident():
            _fail('first_save_lease_invalid', 'Lease must remain active on its creating thread.')
        self.locks.check()
        if _ancestry(Path(self.token['destination']).parent) != self.token['ancestry']:
            _fail('first_save_parent_changed', 'Prepared directory ancestry changed.')


@contextmanager
def lease_destination(token):
    if type(token) is not dict or set(token) != {'scope', 'destination', 'ancestry'} or token['scope'] != SCOPE:
        _fail('first_save_invalid_token', 'Exact prepared destination token required.')
    current = prepare_destination(token['destination'])
    if current != token:
        _fail('first_save_parent_changed', 'Prepared directory ancestry changed.')
    locks = _WindowsLocks()
    lease = _Lease(deepcopy(token), locks)
    try:
        for row in current['ancestry']:
            locks.acquire(Path(row['path']), directory=True)
        lease.check()
        yield lease
    finally:
        lease.active = False
        if not lease.retain:
            lease.locks.close()


@dataclass
class OwnedStage:
    """Opaque process/thread-owned stage; never reconstruct from client JSON."""
    lease: _Lease
    directory: Path
    identity: list | None
    filename: Path
    facts: dict | None = None
    publication_attempted: bool = False
    publication_returned: bool = False
    pending_publication: bool = False
    published: bool = False
    uncertain: bool = False
    cleaned: bool = False
    creation_attempted: bool = False
    creation_returned: bool = False
    pending_creation: bool = False
    cleanup_attempted: bool = False
    cleanup_returned: bool = False
    pending_cleanup: bool = False
    destination_facts: dict | None = None
    directory_phase: dict = field(default_factory=lambda: dict(
        enter_attempted=False, enter_returned=False, pending_enter=False,
        restore_attempted=False, restore_returned=False, pending_restore=False, strict_restored=True))
    retained_file_locks: object | None = field(default=None, repr=False)
    retained_directory_locks: list = field(default_factory=list, repr=False)
    pending_native_resources: object | None = field(default=None, repr=False)

    def checkpoint(self):
        return dict(scope=SCOPE, directory=str(self.directory), directory_identity=deepcopy(self.identity),
                    filename=str(self.filename), file=deepcopy(self.facts),
                    creation_attempted=self.creation_attempted, creation_returned=self.creation_returned,
                    pending_creation=self.pending_creation,
                    cleanup_attempted=self.cleanup_attempted, cleanup_returned=self.cleanup_returned,
                    pending_cleanup=self.pending_cleanup,
                    destination_file=deepcopy(self.destination_facts),
                    directory_phase=deepcopy(self.directory_phase),
                    file_lease_retained=self.retained_file_locks is not None,
                    pending_native_move=self.pending_native_resources is not None,
                    publication_attempted=self.publication_attempted,
                    publication_returned=self.publication_returned, pending_publication=self.pending_publication,
                    published=self.published, uncertain=self.uncertain, cleaned=self.cleaned)


class StageCreationFailure(ExecutionFailure):
    def __init__(self, receipt):
        super().__init__('first_save_stage_creation_unknown',
                         'Owned stage creation/locking was not acknowledged; retain the exact path.', uncertain=True)
        self.receipt = receipt


def create_owned_stage(lease, *, on_owned_change=None):
    lease.check()
    if lease.mode != 'strict':
        _fail('first_save_lease_invalid', 'CAD stage creation requires a strict directory lease.')
    directory = Path(lease.token['destination']).parent / ('sw-first-save-' + uuid.uuid4().hex)
    receipt = OwnedStage(lease, directory, None, directory / 'Первая запись.SLDPRT')
    lease.stages.append(receipt)
    try:
        receipt.pending_creation = True
        if on_owned_change is not None:
            on_owned_change(receipt.checkpoint())  # durable planned path BEFORE mkdir
        receipt.creation_attempted = True
        directory.mkdir()
        receipt.creation_returned = True
        receipt.identity = _plain(directory, True)
        lease.locks.acquire(directory, directory=True)
        lease.check()
        receipt.pending_creation = False
        if on_owned_change is not None:
            on_owned_change(receipt.checkpoint())
        return receipt
    except BaseException as error:
        if receipt.creation_attempted:
            receipt.uncertain = True
            raise StageCreationFailure(receipt) from error
        raise


def _stage_owner(receipt, lease, *, allow_cleaned=False):
    if (type(receipt) is not OwnedStage or receipt.lease is not lease
            or (receipt.cleaned and not allow_cleaned)
            or receipt.pending_creation or not receipt.creation_returned or receipt.identity is None
            or not any(receipt is item for item in lease.stages)):
        _fail('first_save_stage_not_owned', 'An exact live owned stage receipt is required.')
    lease.check()
    if (_plain(receipt.directory, True) != receipt.identity
            or receipt.filename.parent != receipt.directory
            or receipt.directory.parent != Path(lease.token['destination']).parent):
        _fail('first_save_stage_changed', 'Owned staging directory binding changed.')


def _stage_entries(receipt):
    # Two entries suffice to reject any unsupported sidecar inventory.
    return list(islice(receipt.directory.iterdir(), 2))


def _stage_check(receipt, lease):
    _stage_owner(receipt, lease)
    entries = _stage_entries(receipt)
    if len(entries) != 1 or entries[0] != receipt.filename:
        _fail('first_save_sidecars', 'Exactly one declared staging file is supported; no sidecar cleanup.')


def observe_owned_stage(receipt, lease):
    """Passive owned-stage observation, including empty normal-false/cleaned states.

    Observing bytes does not adopt a native handle or grant publication/cleanup.
    In particular this does not assign receipt.facts or clear pending/unknown.
    """
    _stage_owner(receipt, lease, allow_cleaned=True)
    entries = _stage_entries(receipt)
    if len(entries) > 1 or (entries and entries[0] != receipt.filename):
        _fail('first_save_sidecars', 'Unexpected staged entries prohibit a bounded observation.')
    facts = native_file_facts(str(receipt.filename), 'part') if entries else None
    if receipt.cleaned and facts is not None:
        _fail('first_save_stage_changed', 'A cleaned stage acquired an unexpected file.')
    lease.check()
    return dict(checkpoint=receipt.checkpoint(), file=facts, empty=not entries)


def observe_destination(token):
    """Passive file fingerprint with exact ancestry; absence is not a CAD oracle."""
    if type(token) is not dict or set(token) != {'scope', 'destination', 'ancestry'} or token['scope'] != SCOPE:
        _fail('first_save_invalid_token', 'Exact prepared destination token required.')
    path = _path(token['destination'])
    _filename(path)
    _require_local_ntfs(path)
    if _ancestry(path.parent) != token['ancestry']:
        _fail('first_save_parent_changed', 'Prepared ancestry changed before destination observation.')
    facts = native_file_facts(str(path), 'part') if os.path.lexists(path) else None
    if _ancestry(path.parent) != token['ancestry']:
        _fail('first_save_parent_changed', 'Prepared ancestry changed during destination observation.')
    return facts


def inspect_staged(receipt):
    _stage_check(receipt, receipt.lease)
    facts = native_file_facts(str(receipt.filename), 'part')
    if receipt.facts is not None and facts != receipt.facts:
        _fail('first_save_staged_file_changed', 'Previously inspected staged file changed.')
    receipt.facts = facts
    return deepcopy(facts)


class _FileRenameInfo(ctypes.Structure):
    # Windows ABI widths must remain fixed even when pure tests run on POSIX.
    # The first DWORD is the BOOLEAN ReplaceIfExists/DWORD Flags union; all
    # bits remain zero for NT FileRenameInformation(10), never extended flags.
    _fields_ = [('replace_or_flags', ctypes.c_uint32), ('root_directory', ctypes.c_void_p),
                ('name_length', ctypes.c_uint32), ('name', ctypes.c_uint16 * 1)]


def _rename_buffer(destination, *, root_directory=None):
    # https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info
    # Length counts UTF-16 BYTES, not code points or the optional terminator.
    path = _path(str(destination))
    _filename(path)
    encoded = (path.name if root_directory is not None else str(path)).encode('utf-16-le')
    if len(encoded) > 2 * MAX_PATH_CHARS:
        _fail('first_save_invalid_path', 'Destination exceeds the UTF-16 path budget.')
    offset = _FileRenameInfo.name.offset
    buffer = ctypes.create_string_buffer(max(ctypes.sizeof(_FileRenameInfo), offset + len(encoded) + 2))
    header = _FileRenameInfo.from_buffer(buffer)
    header.replace_or_flags, header.root_directory, header.name_length = 0, root_directory, len(encoded)
    ctypes.memmove(ctypes.addressof(buffer) + offset, encoded, len(encoded))
    return buffer


class _StatusUnion(ctypes.Union):
    _fields_ = [('status', ctypes.c_int32), ('pointer', ctypes.c_void_p)]


class _IoStatusBlock(ctypes.Structure):
    _fields_ = [('state', _StatusUnion), ('information', ctypes.c_size_t)]


class PendingNativeRename(ExecutionFailure):
    def __init__(self, resources):
        super().__init__('first_save_pending_native_rename',
                         'Unexpected pending NT rename: preserve buffers/handles; no retry or CAD.', uncertain=True)
        self.resources = resources


def _move_no_replace(locks, handle, destination, *, root_directory):
    # https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_rename_information
    # https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/ns-wdm-_io_status_block
    # CreateFile is synchronous (no OVERLAPPED). Nevertheless STATUS_PENDING
    # must retain IOSB/name memory and every relevant handle until reconciliation.
    if root_directory is None:
        _fail('first_save_handle_binding', 'NT publication requires an exact target-parent handle.')
    buffer = _rename_buffer(destination, root_directory=root_directory)
    iosb = _IoStatusBlock()
    iosb.state.status = 0x103
    ntdll = ctypes.WinDLL('ntdll', use_last_error=True)
    ntdll.NtSetInformationFile.argtypes = [ctypes.c_void_p, ctypes.POINTER(_IoStatusBlock),
                                         ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int32]
    ntdll.NtSetInformationFile.restype = ctypes.c_int32
    status = int(ntdll.NtSetInformationFile(handle, ctypes.byref(iosb), ctypes.byref(buffer),
                                           ctypes.sizeof(buffer), 10)) & 0xFFFFFFFF
    if status == 0x103:
        raise PendingNativeRename((buffer, iosb, ntdll, handle, root_directory))
    if status == 0xC0000035:
        raise FileExistsError(status, 'NT no-replace rename refused an existing destination.')
    if status != 0 or iosb.state.status != 0 or iosb.information != 0:
        raise OSError(f'NT rename returned 0x{status:08x}; IOSB 0x{iosb.state.status & 0xFFFFFFFF:08x}.')


def _directory_snapshot(locks):
    locks.check()
    paths = locks.directory_paths()
    if not 1 <= len(paths) <= MAX_ANCESTORS + 1 or len(set(paths)) != len(paths):
        _fail('first_save_handle_binding', 'Bounded unique ancestry/stage handles are required.')
    return [(path, _plain(path, True)) for path in paths]


@contextmanager
def _publication_directories(lease, receipt):
    lease.check()
    if lease.mode != 'strict':
        _fail('first_save_lease_invalid', 'Publication must start with strict directory leases.')
    phase = receipt.directory_phase
    original = lease.locks
    expected = _directory_snapshot(original)
    weaker = _WindowsLocks(directory_share=3)
    phase['enter_attempted'] = phase['pending_enter'] = True
    try:
        for path, _ in expected:
            weaker.acquire(path, directory=True)
        if _directory_snapshot(weaker) != expected:
            raise RuntimeError('Replacement publication handles do not match strict directories.')
        # New READ handles acquired/verified while old strict leases still held.
        lease.locks, lease.mode = weaker, 'publication'
        phase['strict_restored'] = False
        original.close()
        phase['enter_returned'], phase['pending_enter'] = True, False
        yield weaker.path_handle(Path(lease.token['destination']).parent)
    finally:
        if receipt.pending_native_resources is not None:
            # Native operation may still use target/root/name resources. Do
            # not restore/close any current handles while the outcome is pending.
            lease.retain = True
            receipt.retained_directory_locks.extend([original, weaker])
        elif lease.mode == 'publication':
            phase['restore_attempted'] = phase['pending_restore'] = True
            strict = _WindowsLocks()
            try:
                for path, _ in expected:
                    strict.acquire(path, directory=True)
                if _directory_snapshot(strict) != expected:
                    raise RuntimeError('Strict restore directory identity/reparse proof failed.')
                lease.locks, lease.mode = strict, 'strict'
                phase['strict_restored'] = True
                weaker.close()
                phase['restore_returned'], phase['pending_restore'] = True, False
            except BaseException:
                receipt.pending_publication = receipt.uncertain = True
                receipt.retained_directory_locks.extend([original, weaker, strict])
                lease.retain = True
                raise
        else:
            weaker.close()


@contextmanager
def _duplicate_reader(locks, handle):
    """Read via an owned duplicate, never reopen by path or close original."""
    import msvcrt
    kernel, ctypes_api, types = locks.kernel, locks.ctypes, locks.wintypes
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = types.HANDLE
    kernel.DuplicateHandle.argtypes = [types.HANDLE, types.HANDLE, types.HANDLE,
                                      ctypes.POINTER(types.HANDLE), types.DWORD, types.BOOL, types.DWORD]
    kernel.DuplicateHandle.restype = types.BOOL
    process = kernel.GetCurrentProcess()
    duplicate = types.HANDLE()
    if not kernel.DuplicateHandle(process, handle, process, ctypes.byref(duplicate), 0, False, 2):
        raise ctypes_api.WinError(ctypes_api.get_last_error())
    # open_osfhandle transfers ONLY the duplicated handle to the CRT descriptor.
    try:
        descriptor = msvcrt.open_osfhandle(duplicate.value, os.O_RDONLY | os.O_BINARY)
    except BaseException:
        kernel.CloseHandle(duplicate)
        raise
    try:
        stream = os.fdopen(descriptor, 'rb')
    except BaseException:
        os.close(descriptor)
        raise
    with stream:
        yield stream


def _locked_file_facts(locks, handle, filename):
    """Bounded native_file_facts shape from the exact held move/delete handle."""
    path = _path(str(filename))
    _filename(path)
    locks.check()
    for item in (path, *path.parents):
        _plain(item, item != path)
    path_before = path.lstat()
    with _duplicate_reader(locks, handle) as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_FILE_BYTES:
            _fail('first_save_staged_file_budget', 'A nonempty regular staged part up to 512 MiB is required.')
        stream.seek(0)
        digest, count = hashlib.sha256(), 0
        while chunk := stream.read(1024 * 1024):
            count += len(chunk)
            if count > MAX_FILE_BYTES:
                _fail('first_save_staged_file_changed', 'Held file exceeded the bounded read budget.')
            digest.update(chunk)
        after = os.fstat(stream.fileno())
    signature = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    path_info = path.lstat()  # Metadata-only identity binding, no CRT data reopen.
    locks.check()
    # Windows Python fstat/lstat can expose different ctime semantics. Bind
    # handle and path by exact identity/size/mtime, while independently requiring
    # BOTH providers' full raw metadata (including ctime) to remain unchanged.
    binding = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    if (signature(before) != signature(after) or signature(path_before) != signature(path_info)
            or binding(after) != binding(path_info)
            or count != before.st_size):
        _fail('first_save_staged_file_changed', 'Held/path file identity or metadata changed during hashing.')
    return dict(path=str(path), bytes=count, sha256=digest.hexdigest(), identity=[after.st_dev, after.st_ino],
                mtime_ns=after.st_mtime_ns, ctime_ns=path_info.st_ctime_ns)


def publish(receipt, lease):
    """One handle-bound no-replace move; truthful ACK, no CAD acceptance."""
    _stage_check(receipt, lease)
    if receipt.publication_attempted:
        _fail('first_save_publication_repeated', 'Publication is one-shot, including uncertain outcomes.')
    if receipt.facts is None:
        _fail('first_save_staged_file_unverified', 'Inspect staged file after native readback before publication.')
    if len(_RETAINED_PUBLICATIONS) >= MAX_RETAINED_PUBLICATIONS:
        _fail('first_save_retained_budget', 'Retained unknown publications require reconciliation before another write.')
    destination = Path(lease.token['destination'])
    locks = _WindowsLocks()
    failure = None
    try:
        handle = locks.acquire(receipt.filename, directory=False, delete=True)
        held_facts = _locked_file_facts(locks, handle, receipt.filename)
        if held_facts != receipt.facts:
            _fail('first_save_staged_file_changed', 'Held staged file differs from its inspected receipt.')
        if held_facts['identity'][0] != lease.token['ancestry'][-1]['identity'][0]:
            _fail('first_save_volume_mismatch', 'Staging and destination must remain on the same volume.')
        lease.check()
        receipt.publication_attempted = receipt.pending_publication = receipt.uncertain = True
        with _publication_directories(lease, receipt) as root_directory:
            try:
                _move_no_replace(locks, handle, destination, root_directory=root_directory)
            except PendingNativeRename as error:
                # Set before the context exits: its finalizer must not release
                # any directory handle the pending operation may still use.
                receipt.pending_native_resources = error.resources
                raise
            except FileExistsError:
                # A collision is known only with the unchanged original held
                # file and a distinct foreign destination, never our own alias.
                lease.check()
                if (_locked_file_facts(locks, handle, receipt.filename) == receipt.facts
                        and os.path.lexists(destination)
                        and _plain(destination, False) != receipt.facts['identity']):
                    receipt.pending_publication = receipt.uncertain = False
                raise
            receipt.publication_returned = True
            locks.retarget(handle, destination)
            lease.check()
            _stage_owner(receipt, lease)
            if _stage_entries(receipt):
                raise RuntimeError('Moved owned stage is not empty.')
            facts = _locked_file_facts(locks, handle, destination)
            if any(facts[key] != receipt.facts[key] for key in ('identity', 'bytes', 'sha256', 'mtime_ns')):
                raise RuntimeError('Published destination does not match the owned file receipt.')
            # The move can change path/ctime, but bytes/id/mtime are bound by
            # the same continuously held file handle. Strict restoration is
            # required before the outcome below can become published.
            receipt.destination_facts = facts
        lease.check()
        receipt.published = True
        receipt.pending_publication = receipt.uncertain = False
    except BaseException as error:
        if receipt.publication_attempted:
            failure = error
        else:
            raise
    finally:
        if lease.retain:
            receipt.retained_file_locks = locks
            # Strong process ownership keeps pending native buffers and exact
            # handles alive even if the caller drops its opaque receipt.
            _RETAINED_PUBLICATIONS[id(receipt)] = (receipt, lease)
        else:
            try:
                locks.close()  # only after directory restoration completed
            except BaseException as error:
                if not receipt.publication_attempted:
                    raise
                receipt.pending_publication = receipt.uncertain = True
                receipt.retained_file_locks = locks
                _RETAINED_PUBLICATIONS[id(receipt)] = (receipt, lease)
                failure = error
    if failure is not None:
        return {**receipt.checkpoint(), 'status': 'unknown' if receipt.uncertain else 'conflict',
                'destination': str(destination), 'error_type': type(failure).__name__, 'error': str(failure)}
    return {**receipt.checkpoint(), 'status': 'published', 'destination': str(destination),
            'primitive': 'windows_ntfs_atomic_no_replace_nt_handle_move'}


def _remove_owned_file(filename, facts):
    # Delete by the locked handle, not a path with a check/unlink race.
    locks = _WindowsLocks()
    try:
        handle = locks.acquire(filename, directory=False, delete=True)
        if _locked_file_facts(locks, handle, filename) != facts:
            _fail('first_save_cleanup_unverified', 'Exact staged file changed before handle deletion.')
        class Disposition(locks.ctypes.Structure):
            _fields_ = [('delete', locks.ctypes.c_ubyte)]
        value = Disposition(1)
        locks.kernel.SetFileInformationByHandle.argtypes = [locks.wintypes.HANDLE, locks.wintypes.INT,
                                                           locks.wintypes.LPVOID, locks.wintypes.DWORD]
        locks.kernel.SetFileInformationByHandle.restype = locks.wintypes.BOOL
        if not locks.kernel.SetFileInformationByHandle(handle, 4, locks.ctypes.byref(value),
                                                       locks.ctypes.sizeof(value)):
            raise locks.ctypes.WinError(locks.ctypes.get_last_error())
    finally:
        locks.close()


def cleanup_owned_stage(receipt, lease, *, verified_terminal=False):
    """Remove only exact staged file; retain locked empty owned directory.

    Directory removal is intentionally left out: its live lease denies delete.
    A retained empty owned directory is truthful, not a claim of full cleanup.
    """
    if (verified_terminal is not True or receipt.pending_publication or receipt.uncertain
            or receipt.cleanup_attempted):
        _fail('first_save_cleanup_held', 'Independent terminal/known outcome proof is required for cleanup.')
    _stage_owner(receipt, lease)
    if receipt.published:
        if (_stage_entries(receipt) or receipt.destination_facts is None
                or observe_destination(lease.token) != receipt.destination_facts):
            _fail('first_save_cleanup_unverified', 'Moved stage/final file postconditions changed.')
        receipt.cleanup_attempted = receipt.cleanup_returned = receipt.cleaned = True
        return dict(status='retained_empty_owned_directory', directory=str(receipt.directory),
                    directory_identity=list(receipt.identity), file_removed=True, file_moved=True,
                    destination_removed=False)
    _stage_check(receipt, lease)
    if receipt.facts is None or native_file_facts(str(receipt.filename), 'part') != receipt.facts:
        _fail('first_save_cleanup_unverified', 'Only the exact inspected staged file may be removed.')
    receipt.cleanup_attempted = receipt.pending_cleanup = receipt.uncertain = True
    try:
        _remove_owned_file(receipt.filename, receipt.facts)
        receipt.cleanup_returned = True
        if _stage_entries(receipt) or _plain(receipt.directory, True) != receipt.identity:
            raise RuntimeError('Exact empty owned directory was not confirmed.')
    except BaseException as error:
        raise ExecutionFailure('first_save_cleanup_unknown',
                               'Exact owned-file cleanup was not confirmed; do not repeat.', uncertain=True) from error
    receipt.pending_cleanup = receipt.uncertain = False
    receipt.cleaned = True
    return dict(status='retained_empty_owned_directory', directory=str(receipt.directory),
                directory_identity=list(receipt.identity), file_removed=True, destination_removed=False)
