"""A marker typo must never implicitly opt into native legacy CAD tests."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


def sw_fixture(factory):
    path = Path(__file__).with_name('conftest.py')
    tree = ast.parse(path.read_text(encoding='utf8'))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'sw')
    function.decorator_list = []
    namespace = {'pytest': pytest, 'SolidWorksSession': factory,
                 'SolidWorksError': type('FakeSolidWorksError', (Exception,), {})}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace['sw']


def test_missing_native_opt_in_skips_before_constructing_com_session():
    events = []
    def factory():
        events.append('constructed')
        raise AssertionError('CAD session must not be constructed by default.')
    request = SimpleNamespace(config=SimpleNamespace(getoption=lambda name, default=False: default))
    with pytest.raises(pytest.skip.Exception, match='explicit --run-solidworks'):
        next(sw_fixture(factory)(request))
    assert events == []


def test_explicit_native_opt_in_reaches_factory_without_connecting_to_real_cad():
    events = []
    def factory():
        events.append('constructed')
        raise RuntimeError('Fake constructor reached.')
    def option(name, default=False):
        assert name == '--run-solidworks'
        return True
    request = SimpleNamespace(config=SimpleNamespace(getoption=option))
    with pytest.raises(RuntimeError, match='Fake constructor reached'):
        next(sw_fixture(factory)(request))
    assert events == ['constructed']

class FakeSession:
    def __init__(self, documents=(), busy=False):
        self.events = []
        self._sw = SimpleNamespace(GetDocuments=lambda: documents, CommandInProgress=busy)

    def connect(self):
        self.events.append('connected')

    def _command_in_progress(self, value):
        before = self._sw.CommandInProgress
        self.events.append(('guard', value))
        self._sw.CommandInProgress = value
        return before


def enabled_request():
    return SimpleNamespace(config=SimpleNamespace(getoption=lambda name, default=False: True))


@pytest.mark.parametrize('documents,busy,message', [
    ([object()], False, 'empty disposable'), ([], True, 'existing CommandInProgress'),
])
def test_explicit_opt_in_cannot_take_over_existing_documents_or_guard(documents, busy, message):
    session = FakeSession(documents, busy)
    with pytest.raises(pytest.fail.Exception, match=message):
        next(sw_fixture(lambda: session)(enabled_request()))
    assert session.events == ['connected']
    assert session._sw.CommandInProgress is busy


def test_owned_empty_session_restores_known_guard_when_fixture_generator_closes():
    session = FakeSession()
    generator = sw_fixture(lambda: session)(enabled_request())
    assert next(generator) is session
    assert session._sw.CommandInProgress is True
    generator.close()
    assert session.events == ['connected', ('guard', True), ('guard', False)]
    assert session._sw.CommandInProgress is False
