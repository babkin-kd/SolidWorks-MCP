"""Independent filesystem checks for explicit staging cleanup evidence; no CAD."""
import os
from pathlib import Path
import re
import stat


def _plain(path):
    for part in (path, *path.parents):
        info = part.lstat()
        assert not stat.S_ISLNK(info.st_mode)
        assert not (getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400))


def inspect_staging_cleanup(manifest, mutation, output_root):
    """Return a retained directory only after durable and independent proof."""
    assert mutation['phase'] == 'committed' and mutation['verification']['outcome'] == 'committed'
    cleanup = manifest['staging_cleanup']
    assert cleanup == mutation['verification']['evidence']['after']['staging_cleanup']
    before = mutation['before_state']
    directory = Path(before['staging_directory'])
    temporary = Path(before['temporary_path'])
    root = Path(output_root).absolute()
    assert directory.is_absolute() and directory.parent == root
    assert re.fullmatch(r'\.mcp-export-[0-9a-f]{32}', directory.name)
    assert temporary.parent == directory
    _plain(root)
    if cleanup == {'status': 'removed'}:
        assert not os.path.lexists(directory)
        return None
    assert type(cleanup) is dict and cleanup.get('status') == 'retained_empty_directory'
    assert set(cleanup) == {'status', 'directory', 'identity', 'temporary_file_removed',
                            'directory_empty_verified', 'reason', 'winerror'}
    assert cleanup['directory'] == str(directory)
    assert cleanup['temporary_file_removed'] is True and cleanup['directory_empty_verified'] is True
    assert cleanup['reason'] == 'windows_sharing_violation'
    assert type(cleanup['winerror']) is int and cleanup['winerror'] == 32
    identity = cleanup['identity']
    assert type(identity) is list and len(identity) == 2 and all(type(value) is int for value in identity)
    _plain(directory)
    info = directory.lstat()
    assert stat.S_ISDIR(info.st_mode) and [info.st_dev, info.st_ino] == identity
    assert not os.path.lexists(temporary) and list(directory.iterdir()) == []
    return directory


def assert_output_inventory(output_root, confirmed_files, retained_directories):
    """A verified empty directory never excuses a sidecar or later intrusion."""
    for directory, identity in retained_directories.items():
        _plain(directory)
        info = directory.lstat()
        assert stat.S_ISDIR(info.st_mode) and (info.st_dev, info.st_ino) == identity
        assert list(directory.iterdir()) == []
    assert set(Path(output_root).iterdir()) == set(confirmed_files) | set(retained_directories)
