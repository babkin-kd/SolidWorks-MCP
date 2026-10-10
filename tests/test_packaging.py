"""Fork candidate metadata stays separate from an unpublished registry template."""
import json
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _project():
    return tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf8'))['project']


def _template():
    return json.loads((ROOT / 'Docs/registry-server.template.json').read_text(encoding='utf8'))


def test_registry_template_is_not_an_active_upstream_pypi_descriptor():
    assert not (ROOT / 'server.json').exists()
    template = _template()
    assert template['name'] == 'io.github.babkin-kd/solidworks-mcp'
    assert template['repository']['url'] == 'https://github.com/babkin-kd/SolidWorks-MCP'
    assert template['packages'][0]['identifier'] == '__FORK_PYPI_PACKAGE__'
    assert template['packages'][0]['identifier'] != _project()['name']


def test_registry_template_version_tracks_the_candidate_without_claiming_publication():
    template = _template()
    assert template['version'] == template['packages'][0]['version'] == _project()['version']


def test_package_reports_its_own_version():
    import solidworks_mcp
    assert solidworks_mcp.__version__ == _project()['version']


def test_unpublished_readme_cannot_supply_an_active_registry_ownership_marker():
    readme = (ROOT / 'README.md').read_text(encoding='utf8')
    assert not re.search(r'<!--\s*mcp-name:', readme)
    assert 'registry-template-name: ' + _template()['name'] in readme


def test_dependency_lock_has_the_current_project_and_public_sources_only():
    from urllib.parse import urlsplit
    lock = tomllib.loads((ROOT / 'uv.lock').read_text(encoding='utf8'))
    projects = [package for package in lock['package'] if package['name'] == _project()['name']]
    assert len(projects) == 1 and projects[0]['version'] == _project()['version']
    for package in lock['package']:
        for url in [package.get('source', {}).get('registry')] + [
            item.get('url') for item in package.get('wheels', [])] + [package.get('sdist', {}).get('url')]:
            if url:
                parsed = urlsplit(url)
                assert parsed.username is parsed.password is None
                assert parsed.scheme == 'https' and parsed.hostname in {'pypi.org', 'files.pythonhosted.org'}
