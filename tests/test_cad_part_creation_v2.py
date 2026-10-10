"""Mock COM contracts for exact sketch ownership, not native CAD acceptance."""

from types import SimpleNamespace

import pytest

from solidworks_mcp.cad_part_creation import CadPartCreationMixin
from solidworks_mcp.jobs import ExecutionFailure
import solidworks_mcp.cad_part_creation as native


class Adapter(CadPartCreationMixin):
    _module = SimpleNamespace(ISketch=object())
    def identity(self, obj): return obj.token
    def features(self, model): return model


def feature(sketch, name='Эскиз'):
    return SimpleNamespace(Name=name, GetTypeName2=lambda: 'ProfileFeature', GetSpecificFeature2=lambda: sketch)


def test_exact_sketch_is_resolved_without_nonexistent_get_feature_or_name_guess(monkeypatch):
    monkeypatch.setattr(native.binding, 'wrap', lambda raw, cls: raw)
    sketch = SimpleNamespace(token=object())  # Deliberately has no GetFeature API.
    same_wrapper = SimpleNamespace(token=sketch.token)
    foreign = feature(SimpleNamespace(token=object()), name='Эскиз основания')
    owned = feature(same_wrapper, name='Другое имя')
    assert Adapter()._feature_for_exact_sketch([foreign, owned], sketch) is owned


@pytest.mark.parametrize('duplicate', [False, True])
def test_missing_or_ambiguous_native_sketch_interface_cannot_prove_ownership(monkeypatch, duplicate):
    monkeypatch.setattr(native.binding, 'wrap', lambda raw, cls: raw)
    sketch = SimpleNamespace(token=object())
    objects = [feature(sketch), feature(sketch)] if duplicate else [feature(SimpleNamespace(token=object()))]
    with pytest.raises(ExecutionFailure) as error: Adapter()._feature_for_exact_sketch(objects, sketch)
    assert error.value.code == 'construction_sketch_feature_unavailable'
