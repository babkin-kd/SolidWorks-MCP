"""Validate a fork wheel offline. No imports from the wheel or CAD calls."""
import argparse
import ast
import configparser
from email.parser import Parser
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from zipfile import ZipFile

FORK_REPOSITORY = 'https://github.com/babkin-kd/SolidWorks-MCP'
PACKAGE = 'solidworks_mcp'
ENTRYPOINT = {'solidworks-mcp-v2': 'solidworks_mcp.server_v2:main'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_json(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate build metadata field.')
        result[key] = value
    return result


def validate_wheel(path, *, expected_version, expected_git_sha):
    path = Path(path)
    require(re.fullmatch(r'[0-9a-f]{40}', expected_git_sha) is not None, 'Expected a full Git SHA.')
    with ZipFile(path) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)), 'Duplicate wheel member.')
        for name in names:
            require(archive.getinfo(name).orig_filename == name, 'Unsafe wheel member path.')
            parts = PurePosixPath(name).parts
            require(name and not name.startswith('/') and '\\' not in name
                    and not any(part in ('', '.', '..') for part in name.rstrip('/').split('/')),
                    'Unsafe wheel member path.')
            require(parts and ':' not in parts[0], 'Unsafe wheel member path.')
            require((archive.getinfo(name).external_attr >> 16) & 0o170000 != 0o120000,
                    'Symbolic wheel members are not supported.')
        metadata_paths = [name for name in names if name.endswith('.dist-info/METADATA')]
        require(len(metadata_paths) == 1, 'Expected one wheel distribution.')
        distribution = metadata_paths[0].rsplit('/', 1)[0]
        require('/' not in distribution, 'Unexpected metadata directory.')
        metadata = Parser().parsestr(archive.read(metadata_paths[0]).decode('utf8'))
        require(metadata.get_all('Name') == ['solidworks-mcp'], 'Unexpected distribution name.')
        require(metadata.get_all('Version') == [expected_version], 'Wheel version mismatch.')
        require(distribution == f'solidworks_mcp-{expected_version}.dist-info', 'Metadata directory mismatch.')
        urls = [value.split(',', 1) for value in metadata.get_all('Project-URL', [])]
        repositories = [parts[1].strip() for parts in urls if len(parts) == 2 and parts[0].strip() == 'Repository']
        require(repositories == [FORK_REPOSITORY], 'Wheel does not identify our fork.')
        require(all(name.startswith(PACKAGE + '/') or name.startswith(distribution + '/')
                    for name in names), 'Unexpected files outside package/metadata.')
        for name in names:
            require(PurePosixPath(name).suffix.lower() not in {
                '.sldprt', '.sldasm', '.slddrw', '.prtdot', '.asmdot', '.drwdot',
                '.step', '.stp', '.iges', '.igs', '.x_t', '.x_b', '.stl', '.3mf',
                '.dxf', '.dwg', '.sqlite', '.sqlite3', '.db', '.jsonl'},
                'CAD or private job data must not ship in the wheel.')
        config = configparser.ConfigParser(interpolation=None)
        config.read_string(archive.read(distribution + '/entry_points.txt').decode('utf8'))
        require(config.has_section('console_scripts') and dict(config['console_scripts']) == ENTRYPOINT,
                'Missing or unexpected v2 console entry point.')
        require(PACKAGE + '/server_v2.py' in names, 'V2 entry point module is absent.')
        build = json.loads(archive.read(PACKAGE + '/build_info.json'), object_pairs_hook=unique_json)
        require(type(build) is dict and set(build) == {
            'git_sha', 'source_dirty', 'source_digest', 'package_version', 'api_version'},
            'Invalid build metadata schema.')
        require(build['git_sha'] == expected_git_sha, 'Wheel Git SHA mismatch.')
        require(build['source_dirty'] is False, 'Dirty source wheel is not a clean candidate.')
        require(build['package_version'] == expected_version and type(build['api_version']) is int
                and build['api_version'] == 2, 'Build API/version mismatch.')
        digest = hashlib.sha256()
        source_members = sorted(name for name in names if name.startswith(PACKAGE + '/')
                                and PurePosixPath(name).suffix in ('.py', '.md')
                                and '__pycache__' not in PurePosixPath(name).parts and not archive.getinfo(name).is_dir())
        require(source_members, 'Wheel lacks package source files.')
        for name in source_members:
            digest.update(name[len(PACKAGE) + 1:].encode('utf8') + b'\0')
            digest.update(archive.read(name).replace(b'\r\n', b'\n') + b'\0')
        actual_digest = digest.hexdigest()
        require(build['source_digest'] == actual_digest, 'Wheel source digest mismatch.')
        tree = ast.parse(archive.read(PACKAGE + '/__init__.py').decode('utf8'))
        versions = [node.value.value for node in tree.body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == '__version__' for target in node.targets)
                    and isinstance(node.value, ast.Constant) and type(node.value.value) is str]
        require(versions == [expected_version], 'Package version literal mismatch.')
    return {'accepted': True, 'scope': 'fork_wheel_python_and_guides_v1',
            'wheel_filename': path.name, 'wheel_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'package_version': expected_version, 'git_sha': expected_git_sha,
            'source_dirty': False, 'source_digest': actual_digest, 'api_version': 2,
            'repository': FORK_REPOSITORY, 'console_scripts': ENTRYPOINT,
            'native_acceptance': False, 'public_registry_publication_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wheel', type=Path, required=True)
    parser.add_argument('--expected-version', required=True)
    parser.add_argument('--expected-git-sha', required=True)
    args = parser.parse_args()
    print(json.dumps(validate_wheel(args.wheel, expected_version=args.expected_version,
                                   expected_git_sha=args.expected_git_sha), ensure_ascii=True))


if __name__ == '__main__':
    main()