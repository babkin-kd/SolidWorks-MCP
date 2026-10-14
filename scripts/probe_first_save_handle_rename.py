"""Isolated Win32 research on fresh synthetic files; no CAD/tool acceptance."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import time

from solidworks_mcp import native_first_save_files as files
from solidworks_mcp.native_document_save import native_file_facts


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-windows-filesystem',action='store_true')
    parser.add_argument('--native-ntset',action='store_true')
    parser.add_argument('--state-dir',required=True,type=Path)
    args=parser.parse_args()
    assert args.run_windows_filesystem and os.name=='nt'
    state=args.state_dir.absolute()
    assert state.is_relative_to(Path.cwd()/'work') and not state.exists()
    state.mkdir()
    report=dict(scope='isolated_source_windows_rename_research',native_ntset=args.native_ntset,native_first_save_accepted=False,
                completed=False,cases=[])
    started=time.perf_counter()
    def persist():
        (state/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    try:
        cases=[('strict_full',False,False,False),
                ('strict_relative',True,False,False),('publication_relative',True,True,False),
                ('publication_relative_conflict',True,True,True)]
        if args.native_ntset:cases=cases[1:]
        for label,relative,transition,race in cases:
            target=state/label
            source_dir=target/'stage'
            source_dir.mkdir(parents=True)
            source=source_dir/'Исходная проверка.SLDPRT'
            destination=target/'Итоговая проверка.SLDPRT'
            source.write_bytes(b'Own synthetic payload; no CAD model.\n')
            before=native_file_facts(str(source),'part')
            foreign=b'Foreign synthetic payload; no CAD model.\n'
            if race:destination.write_bytes(foreign)
            strict,weak,file_lock=files._WindowsLocks(),files._WindowsLocks(),files._WindowsLocks()
            row=dict(label=label,relative=relative,transition=transition,race=race,pending=False)
            report['cases'].append(row);persist()
            try:
                root=strict.acquire(target,directory=True)
                strict.acquire(source_dir,directory=True)
                handle=file_lock.acquire(source,directory=False,delete=True)
                assert files._locked_file_facts(file_lock,handle,source)==before
                if transition:
                    # No CAD occurs in this research phase. File remains held
                    # with deny WRITE/DELETE throughout every directory change.
                    for directory in (target,source_dir):
                        value=weak.kernel.CreateFileW(str(directory),0x80000081,3,None,3,0x2200000,None)
                        if value==ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
                        weak.handles.append((value,directory))
                        weak.check()
                        if directory==target:root=value
                    strict.close()
                    moved=target.with_name(target.name+'-moved')
                    assert target.resolve().is_relative_to(state) and moved.resolve().is_relative_to(state)
                    try:target.rename(moved)
                    except PermissionError:row['directory_rename_blocked']=True
                    else:raise AssertionError('Publication directory mode permitted rename.')
                if relative:
                    encoded=destination.name.encode('utf-16-le')
                    offset=files._FileRenameInfo.name.offset
                    buffer=ctypes.create_string_buffer(max(ctypes.sizeof(files._FileRenameInfo),offset+len(encoded)+2))
                    header=files._FileRenameInfo.from_buffer(buffer)
                    header.replace_or_flags=0;header.root_directory=root;header.name_length=len(encoded)
                    ctypes.memmove(ctypes.addressof(buffer)+offset,encoded,len(encoded))
                else:buffer=files._rename_buffer(destination)
                kernel=file_lock.kernel
                kernel.SetFileInformationByHandle.argtypes=[file_lock.wintypes.HANDLE,file_lock.wintypes.INT,
                    file_lock.wintypes.LPVOID,file_lock.wintypes.DWORD]
                kernel.SetFileInformationByHandle.restype=file_lock.wintypes.BOOL
                row['pending']=True;persist()
                if args.native_ntset:
                    # Documented user-mode name, FILE_RENAME_INFORMATION(10).
                    # HANDLE is synchronous: CreateFileW used no OVERLAPPED.
                    class StatusUnion(ctypes.Union):
                        _fields_=[('status',ctypes.c_int32),('pointer',ctypes.c_void_p)]
                    class IOStatus(ctypes.Structure):
                        _fields_=[('result',StatusUnion),('information',ctypes.c_size_t)]
                    iosb=IOStatus();iosb.result.status=0x103
                    library=ctypes.WinDLL('ntdll')
                    library.NtSetInformationFile.argtypes=[ctypes.c_void_p,ctypes.POINTER(IOStatus),
                        ctypes.c_void_p,ctypes.c_uint32,ctypes.c_int32]
                    library.NtSetInformationFile.restype=ctypes.c_int32
                    status=library.NtSetInformationFile(handle,ctypes.byref(iosb),ctypes.byref(buffer),ctypes.sizeof(buffer),10)
                    if status==0x103:
                        # Keep exact handles/buffer/process alive until native
                        # completion; an observation timeout is not cancellation.
                        kernel.WaitForSingleObject.argtypes=[ctypes.c_void_p,ctypes.c_uint32]
                        kernel.WaitForSingleObject.restype=ctypes.c_uint32
                        while iosb.result.status==0x103:
                            print('Own NT filesystem request is pending.',flush=True)
                            result=kernel.WaitForSingleObject(handle,5000)
                            if result not in (0,258):
                                time.sleep(.1)
                        status=iosb.result.status
                    row.update(nt_status=hex(status & 0xffffffff),io_status=hex(iosb.result.status & 0xffffffff),
                               io_information=iosb.information)
                    ack=status==0
                    error=status & 0xffffffff if not ack else 0
                else:
                    ack=kernel.SetFileInformationByHandle(handle,3,ctypes.byref(buffer),ctypes.sizeof(buffer))
                    error=ctypes.get_last_error() if not ack else 0
                row.update(pending=False,returned=True,ack=bool(ack),error=error);persist()
                if ack:
                    file_lock.retarget(handle,destination)
                    after=files._locked_file_facts(file_lock,handle,destination)
                    assert not source.exists() and all(after[key]==before[key] for key in ('identity','sha256','bytes','mtime_ns'))
                    assert not race
                    row['held_file_postconditions']=True
                else:
                    assert files._locked_file_facts(file_lock,handle,source)==before
                    assert destination.read_bytes()==foreign if race else not destination.exists()
                    row['no_effect_proven']=True
                # Reacquire strict mode before any prospective CAD read/open.
                if transition:
                    strict.acquire(target,directory=True)
                    strict.acquire(source_dir,directory=True)
                    weak.close()
                    strict.check()
                    row['strict_directory_mode_restored']=True
                persist()
            finally:
                file_lock.close();weak.close();strict.close()
        report['completed']=True
    except BaseException as error:
        report.update(error_type=type(error).__name__,error=str(error))
    finally:
        report['elapsed_seconds']=time.perf_counter()-started;persist()
    print(json.dumps(dict(completed=report['completed'],cases=[{key:row.get(key) for key in
        ('label','ack','error','no_effect_proven','held_file_postconditions')} for row in report['cases']],
        error=report.get('error'))))
    raise SystemExit(0 if report['completed'] else 1)


if __name__=='__main__':main()
