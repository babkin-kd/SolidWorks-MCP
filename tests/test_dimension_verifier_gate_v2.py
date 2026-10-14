"""Same-wheel acceptance gates, extracted without importing the CAD verifier."""

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'verify_dimension_mcp.py'
VERSION = '2.0.0.dev13'
SHA = 'a' * 40
DIGEST = 'b' * 64
GATES = (
    'native_typed_configuration_setter',
    'explicit_dimension_reference_survives_rebuild',
    'verified_scoped_restoration_after_injected_error',
    'original_document_baseline_restored',
)
PROVENANCE = {
    'package_version': VERSION, 'git_sha': SHA, 'source_dirty': False,
    'installed_source_digest': DIGEST, 'installed_build_matches_package': True,
}
VALID = {**PROVENANCE, 'accepted': True, **dict.fromkeys(GATES, True)}


class CadBoundaryReached(Exception):
    """A pure sentinel; no CAD module or apartment is involved."""


@pytest.fixture
def isolated():
    """Compile only the gates and their actual caller, with explicit fake inputs."""
    tree = ast.parse(SCRIPT.read_text(encoding='utf8'), filename=str(SCRIPT))
    names = {'_provenance', '_require_internal_acceptance', 'check'}
    nodes = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    assert {node.name for node in nodes} == names
    # This path is an input token only: fake resources/digests never read it.
    package = SCRIPT.parent.parent / 'work' / 'pure-gate-placeholder' / 'site-packages' / 'solidworks_mcp'
    state = SimpleNamespace(
        build={'package_version': VERSION, 'git_sha': SHA,
               'source_dirty': False, 'source_digest': DIGEST},
        actual_digest=DIGEST, digest_reads=[], resource_reads=[], cad_calls=[],
        environ={}, report=dict(VALID),
    )

    class BuildResource:
        def joinpath(self, filename):
            assert filename == 'build_info.json'
            return self

        def read_text(self, *, encoding):
            assert encoding == 'utf8'
            state.resource_reads.append('build_info.json')
            return json.dumps(state.build)

    def files(name):
        assert name == 'solidworks_mcp'
        return BuildResource()

    def actual_digest(root):
        assert root == Path(module.__file__).resolve().parent
        state.digest_reads.append(root)
        return state.actual_digest

    def native_snapshot():
        state.cad_calls.append('native_snapshot')
        raise CadBoundaryReached

    class InternalReport:
        def read_text(self, *, encoding):
            assert encoding == 'utf8'
            return json.dumps(state.report)

    module = SimpleNamespace(__file__=str(package / '__init__.py'), __version__=VERSION)
    namespace = {
        'Path': Path, 'json': json, 'os': SimpleNamespace(environ=state.environ),
        'resources': SimpleNamespace(files=files), 'solidworks_mcp': module,
        'source_digest': actual_digest, 'native_snapshot': native_snapshot,
    }
    # No imports, top-level script execution, package binding or native calls.
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SCRIPT), 'exec'), namespace)
    return state, module, namespace, InternalReport()


def reject_before_cad(isolated):
    state, _, namespace, report = isolated
    with pytest.raises(AssertionError):
        asyncio.run(namespace['check'](Path('unused-state'), report))
    assert state.cad_calls == []


def test_exact_report_is_accepted_with_actual_installed_provenance(isolated):
    state, _, namespace, report = isolated
    current = namespace['_provenance']()
    assert current == PROVENANCE
    assert len(state.digest_reads) == 1
    namespace['_require_internal_acceptance'](dict(VALID), current)
    # Execute the real caller until the fake CAD boundary to verify the order.
    with pytest.raises(CadBoundaryReached):
        asyncio.run(namespace['check'](Path('unused-state'), report))
    assert state.cad_calls == ['native_snapshot']


@pytest.mark.parametrize('key', list(VALID))
def test_every_missing_report_field_rejects_before_cad(isolated, key):
    isolated[0].report.pop(key)
    reject_before_cad(isolated)


@pytest.mark.parametrize('key,value', [
    ('accepted', False), ('accepted', 1), ('accepted', 'true'),
    ('package_version', '2.0.0.dev10'), ('git_sha', 'c' * 40),
    ('installed_source_digest', 'd' * 64),
    ('source_dirty', True), ('source_dirty', 0), ('source_dirty', 'false'),
    ('installed_build_matches_package', False), ('installed_build_matches_package', 1),
] + [(key, value) for key in GATES for value in (False, 1, 'true', None)])
def test_wrong_or_coerced_report_fields_reject_before_cad(isolated, key, value):
    isolated[0].report[key] = value
    reject_before_cad(isolated)


def test_historical_sidecar_cannot_supply_missing_same_wheel_fields(isolated):
    isolated[0].report = {
        'accepted': True, 'package_version': VERSION, **dict.fromkeys(GATES, True),
        'provenance_sidecar': dict(PROVENANCE),
    }
    reject_before_cad(isolated)


@pytest.mark.parametrize('key', ['package_version', 'source_digest', 'source_dirty', 'git_sha'])
def test_missing_installed_build_field_rejects_before_cad(isolated, key):
    isolated[0].build.pop(key)
    reject_before_cad(isolated)


@pytest.mark.parametrize('key,value', [
    ('package_version', '2.0.0.dev10'), ('source_dirty', True),
    ('source_dirty', 0), ('source_dirty', 'false'),
    ('git_sha', None), ('git_sha', ''), ('git_sha', 'a' * 7),
    ('git_sha', 'A' * 40), ('git_sha', 'g' * 40), ('git_sha', 123),
])
def test_unverified_or_dirty_installed_build_rejects_before_cad(isolated, key, value):
    isolated[0].build[key] = value
    reject_before_cad(isolated)


def test_matching_report_and_metadata_cannot_replace_actual_source_digest(isolated):
    state = isolated[0]
    state.build['source_digest'] = 'd' * 64
    state.report['installed_source_digest'] = 'd' * 64
    reject_before_cad(isolated)
    assert len(state.digest_reads) == 1


@pytest.mark.parametrize('location', ['source-tree', 'site-packages-backup'])
def test_source_package_or_substring_path_is_not_installed_proof(isolated, location):
    isolated[1].__file__ = str(Path('unused') / location / 'solidworks_mcp' / '__init__.py')
    reject_before_cad(isolated)
    assert isolated[0].resource_reads == isolated[0].digest_reads == []


def test_source_pythonpath_rejects_before_build_or_cad_reads(isolated):
    isolated[0].environ['PYTHONPATH'] = 'source-tree'
    reject_before_cad(isolated)
    assert isolated[0].resource_reads == isolated[0].digest_reads == []
