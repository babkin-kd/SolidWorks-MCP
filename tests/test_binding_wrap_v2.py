"""Pure wrapping contract tests; no native connection, QI or CAD invocation."""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def binding_wrap(monkeypatch):
    # Load the actual file in isolation so Linux CI and Windows use exactly the
    # same pure test. Stub only imports; no production wrapping implementation
    # or native object identities are replaced by an alternative algorithm.
    pythoncom = ModuleType('pythoncom')
    client = ModuleType('win32com.client')
    client.gencache = SimpleNamespace()
    win32 = ModuleType('win32com')
    win32.client = client
    monkeypatch.setitem(sys.modules, 'pythoncom', pythoncom)
    monkeypatch.setitem(sys.modules, 'win32com', win32)
    monkeypatch.setitem(sys.modules, 'win32com.client', client)
    path = Path(__file__).resolve().parents[1] / 'src' / 'solidworks_mcp' / 'binding.py'
    spec = importlib.util.spec_from_file_location('solidworks_mcp._binding_wrap_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.wrap


def test_none_does_not_touch_requested_constructor(binding_wrap):
    def prohibited(raw):
        pytest.fail('None must not call a wrapper constructor.')
    assert binding_wrap(None, prohibited) is None


def test_exact_generated_type_preserves_object_without_constructor_or_qi(binding_wrap):
    class Pointer:
        def QueryInterface(self, *args):
            pytest.fail('Exact-type wrapping must not invoke native QI.')
    class Wrapper:
        calls = 0
        def __init__(self, raw):
            type(self).calls += 1
            self._oleobj_ = raw
    obj = Wrapper(Pointer())
    assert binding_wrap(obj, Wrapper) is obj
    assert binding_wrap(obj, Wrapper) is obj
    assert Wrapper.calls == 1


def test_exact_type_does_not_even_read_oleobj_property(binding_wrap):
    class Wrapper:
        @property
        def _oleobj_(self):
            pytest.fail('Exact-type fast path must precede any dispatch property access.')
    obj = Wrapper()
    assert binding_wrap(obj, Wrapper) is obj


@pytest.mark.parametrize('source_kind', ['raw', 'dynamic', 'different_interface', 'subclass'])
def test_other_representations_use_existing_requested_constructor(binding_wrap, source_kind):
    pointer = object()
    calls = []
    class Requested:
        def __init__(self, raw):
            calls.append(raw)
            self._oleobj_ = raw
    class Different:
        def __init__(self, raw): self._oleobj_ = raw
    class Subclass(Requested):
        pass
    if source_kind == 'raw':
        source = pointer
    elif source_kind == 'dynamic':
        source = SimpleNamespace(_oleobj_=pointer)
    elif source_kind == 'different_interface':
        source = Different(pointer)
    else:
        source = Subclass(pointer)
        calls.clear()
    wrapped = binding_wrap(source, Requested)
    assert type(wrapped) is Requested
    assert wrapped is not source
    assert wrapped._oleobj_ is pointer
    assert calls == [pointer]


def test_subclass_interface_query_is_not_silently_skipped(binding_wrap):
    class Pointer:
        calls = 0
        def QueryInterface(self):
            self.calls += 1
            return self
    class Requested:
        def __init__(self, pointer):
            self._oleobj_ = pointer.QueryInterface()
    class Subclass(Requested):
        pass
    pointer = Pointer()
    subclass = Subclass(pointer)
    assert pointer.calls == 1
    wrapped = binding_wrap(subclass, Requested)
    assert type(wrapped) is Requested and wrapped is not subclass
    assert pointer.calls == 2


def test_requested_constructor_failure_propagates(binding_wrap):
    failure = RuntimeError('Requested interface QI failed.')
    pointer = object()
    class Requested:
        def __init__(self, raw):
            assert raw is pointer
            raise failure
    with pytest.raises(RuntimeError) as exc:
        binding_wrap(SimpleNamespace(_oleobj_=pointer), Requested)
    assert exc.value is failure


def test_exact_type_is_not_a_stale_native_wrapper_health_check(binding_wrap):
    class StaleWrapper:
        def __init__(self): self._oleobj_ = None
        def GetType(self): raise RuntimeError('Native object has been deleted.')
    stale = StaleWrapper()
    assert binding_wrap(stale, StaleWrapper) is stale
    with pytest.raises(RuntimeError, match='Native object has been deleted'):
        stale.GetType()


def test_requested_base_type_cannot_be_inferred_from_isinstance(binding_wrap):
    class Requested:
        def __init__(self, raw): self._oleobj_ = raw
    class Subclass(Requested):
        pass
    raw = object()
    source = Subclass(raw)
    assert isinstance(source, Requested)
    result = binding_wrap(source, Requested)
    assert type(result) is Requested and result is not source
