"""Detached preflight tests; never import COM, connect CAD or launch a console."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest


def loader(tmp_path):
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / 'scripts/probe_native_first_save_domain.py').read_text(encoding='utf-8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'package_evidence')
    calls = []
    wheel = {'package_version': '2.0.0.dev88', 'git_sha': 'a' * 40}

    def validate(*args, **kwargs):
        calls.append('wheel')
        assert kwargs == {'expected_version': wheel['package_version'], 'expected_git_sha': wheel['git_sha']}
        return wheel

    def identity(value):
        calls.append('origin')
        assert value is wheel
        return 'installed-console'

    async def metadata(entry, state, value):
        calls.append('catalog')
        assert entry == 'installed-console' and state.is_dir() and value is wheel
        return {'public_tool_count': 73}

    namespace = dict(Path=Path, asyncio=asyncio, validate_wheel=validate,
                     installed_identity=identity, check=metadata,
                     solidworks_mcp=SimpleNamespace(__file__=str(tmp_path / 'site-packages/solidworks_mcp/__init__.py')))
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'first_save_preflight', 'exec'), namespace)
    args = SimpleNamespace(wheel=tmp_path / 'candidate.whl', expected_version=wheel['package_version'],
                           expected_git_sha=wheel['git_sha'], state_dir=tmp_path)
    return namespace['package_evidence'], namespace, args, calls


def test_installed_origin_wheel_and_catalog_are_bound_before_native(tmp_path):
    function, namespace, args, calls = loader(tmp_path)
    result = function(args, installed=True)
    assert calls == ['wheel', 'origin', 'catalog']
    assert result['package_origin_verified'] is True
    assert result['wheel']['package_version'] == args.expected_version
    assert result['metadata_catalog']['public_tool_count'] == 73
    assert 'native_acceptance' not in result and 'accepted' not in result


@pytest.mark.parametrize('failed_gate,expected_calls', [
    ('validate_wheel', []), ('installed_identity', ['wheel']), ('check', ['wheel', 'origin'])])
def test_failed_preflight_does_not_advance_to_later_gates(tmp_path, failed_gate, expected_calls):
    function, namespace, args, calls = loader(tmp_path)
    def refuse(*args, **kwargs):
        raise ValueError('rejected preflight')
    namespace[failed_gate] = refuse
    with pytest.raises(ValueError, match='rejected preflight'):
        function(args, installed=True)
    assert calls == expected_calls


def test_source_mode_cannot_adopt_installed_package(tmp_path):
    function, namespace, args, calls = loader(tmp_path)
    with pytest.raises(AssertionError):
        function(args, installed=False)
    assert calls == []
