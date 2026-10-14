"""Real Windows/NTFS source-primitive probe, without CAD or installed acceptance.

Only fresh private work/ directories and synthetic bytes are used. No actual
CAD save/open occurs and a .SLDPRT extension does not imply a valid CAD model.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

from solidworks_mcp import native_first_save_files as files
from solidworks_mcp.jobs import ExecutionFailure


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-windows-filesystem',action='store_true')
    parser.add_argument('--state-dir',required=True,type=Path)
    args=parser.parse_args()
    assert args.run_windows_filesystem and os.name=='nt'
    state=args.state_dir.absolute()
    assert state.is_relative_to(Path.cwd()/'work') and not state.exists()
    state.mkdir()
    report=dict(probe_passed=False,native_first_save_accepted=False,
                scope='source_windows_ntfs_primitives_only',cases=[])
    start=time.perf_counter()
    def persist():
        (state/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    def add(label,**evidence):
        report['cases'].append(dict(label=label,passed=True,**evidence))
        persist()
    try:
        parent=state/'publication'
        parent.mkdir()
        destination=parent/'Проверка публикации.SLDPRT'
        token=files.prepare_destination(str(destination))
        with files.lease_destination(token) as lease:
            # Verify actual directory rename is denied while the exact ancestry
            # handle is held. Both candidate paths are fresh probe-owned paths.
            moved=parent.with_name(parent.name+'-moved')
            assert parent.resolve().is_relative_to(state) and moved.resolve().is_relative_to(state)
            try:parent.rename(moved)
            except PermissionError:add('ancestry_rename_blocked')
            else:raise AssertionError('Directory lease did not deny rename.')
            def owned(checkpoint):
                assert type(checkpoint) is dict
                report['stage']=checkpoint
                persist()
            stage=files.create_owned_stage(lease,on_owned_change=owned)
            payload=b'Synthetic filesystem bytes; not a CAD file.\n'
            stage.filename.write_bytes(payload)
            facts=files.inspect_staged(stage)
            original_move=files._move_no_replace
            def checked_move(locks,handle,target,*,root_directory):
                try:
                    with stage.filename.open('r+b'):
                        pass
                except PermissionError:
                    add('staged_write_blocked_during_insertion')
                else:raise AssertionError('File lease did not deny write.')
                return original_move(locks,handle,target,root_directory=root_directory)
            files._move_no_replace=checked_move
            try:
                ack=files.publish(stage,lease)
            finally:
                files._move_no_replace=original_move
            report['publication']=ack
            persist()
            assert ack['status']=='published' and ack['published'] is True
            assert destination.read_bytes()==payload
            assert ack['destination_file']['identity']==facts['identity']
            assert not stage.filename.exists()
            assert ack['primitive']=='windows_ntfs_atomic_no_replace_nt_handle_move'
            assert ack['directory_phase']['strict_restored'] is True
            add('no_replace_handle_move_published')
            cleanup=files.cleanup_owned_stage(stage,lease,verified_terminal=True)
            assert cleanup['status']=='retained_empty_owned_directory'
            assert not stage.filename.exists() and not list(stage.directory.iterdir())
            assert destination.read_bytes()==payload
            # Writable final open after stage locks are released is essential
            # for later native Save3; this is only an OS access test.
            with destination.open('r+b') as stream:
                assert stream.read()==payload
            add('handle_cleanup_preserves_writable_final',cleanup=cleanup)
        before=hashlib.sha256(destination.read_bytes()).hexdigest()
        try:files.prepare_destination(str(destination))
        except ExecutionFailure as error:
            assert error.code=='first_save_destination_exists'
        else:raise AssertionError('Existing file was not refused.')
        assert hashlib.sha256(destination.read_bytes()).hexdigest()==before
        add('existing_destination_unchanged')
        parent=state/'race'
        parent.mkdir()
        destination=parent/'Занятый результат.SLDPRT'
        token=files.prepare_destination(str(destination))
        with files.lease_destination(token) as lease:
            stage=files.create_owned_stage(lease)
            stage.filename.write_bytes(b'Own synthetic stage.\n')
            files.inspect_staged(stage)
            foreign=b'Other process synthetic destination.\n'
            destination.write_bytes(foreign)
            ack=files.publish(stage,lease)
            report['race_publication']=ack
            persist()
            assert ack['status']=='conflict' and ack['uncertain'] is False
            assert destination.read_bytes()==foreign
            files.cleanup_owned_stage(stage,lease,verified_terminal=True)
            assert destination.read_bytes()==foreign and not stage.filename.exists()
            add('raced_destination_unchanged')
        report['probe_passed']=True
    except BaseException as error:
        report.update(error_type=type(error).__name__,error=str(error))
    finally:
        report['elapsed_seconds']=time.perf_counter()-start
        persist()
    print(json.dumps(dict(probe_passed=report['probe_passed'],cases=len(report['cases']),
                         error=report.get('error'))))
    raise SystemExit(0 if report['probe_passed'] else 1)


if __name__=='__main__':main()
