"""Run before building a wheel. No CAD access, secrets, or network operations."""

import importlib.util
import json
from pathlib import Path
import subprocess
import tomllib


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'src' / 'solidworks_mcp'
spec = importlib.util.spec_from_file_location('build_provenance', PACKAGE / 'build_info.py')
provenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provenance)


def git(*arguments):
    return subprocess.check_output(['git', *arguments], cwd=ROOT).decode('utf-8').strip()


project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
manifest = {'git_sha': git('rev-parse', 'HEAD'),
            'source_dirty': bool(git('status', '--porcelain', '--untracked-files=normal')),
            'source_digest': provenance.source_digest(PACKAGE),
            'package_version': project['version'], 'api_version': 2}
(PACKAGE / 'build_info.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
print(json.dumps(manifest))
