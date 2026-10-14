"""Native-shaped Python fakes for one-enumeration strong identity caching."""

from types import SimpleNamespace

import pytest

from solidworks_mcp import cad_dimensions
from solidworks_mcp.jobs import ExecutionFailure


class CanonicalIdentity:
    __hash__ = None
    def __init__(self, key):
        self.key = key
    def __eq__(self, other):
        return isinstance(other, CanonicalIdentity) and self.key == other.key


class Wrapper:
    """Fresh Python wrapper per native getter, sharing an immutable fake identity."""
    def __init__(self, native):
        self.native = native
    def GetFirstDisplayDimension(self):
        return Wrapper(self.native.first) if self.native.first else None
    def GetNextDisplayDimension(self, previous):
        return Wrapper(previous.native.next) if previous.native.next else None
    def GetType(self):
        return self.native.display_type
    def GetDimension2(self, index):
        self.native.slot_calls.append(index)
        target = self.native.targets.get(index)
        return Wrapper(target) if target else None
    def GetFeatureOwner(self):
        self.native.owner_calls += 1
        return Wrapper(self.native.owner) if self.native.owner else None


def entity(kind, number, **kwargs):
    # Names, GetID/PID-like data deliberately collide. Only the adapter's
    # canonical identity is suitable for native duplicate/membership checks.
    return SimpleNamespace(key=(kind, number), name='Одинаковое имя', native_id=1, pid=b'same-bytes', **kwargs)


def feature(number):
    return entity('feature', number, first=None)


def dimension(number, owner):
    return entity('dimension', number, owner=owner, owner_calls=0)


def display(number, target, *, second=None):
    return entity('display', number, display_type=10 if second is not None else 2,
                  targets={0: target, **({1: second} if second is not None else {})}, next=None, slot_calls=[])


class Adapter(cad_dimensions.CadDimensionsMixin):
    _module = SimpleNamespace(IFeature=object, IDimension=object, IDisplayDimension=object)
    def __init__(self):
        self.identity_calls = []
    def identity(self, obj):
        self.identity_calls.append(obj.native.key)
        # Distinct, unhashable identity wrappers still compare canonically.
        return CanonicalIdentity(obj.native.key)
    def features(self, model):
        raise AssertionError('The complete feature snapshot is already supplied.')


@pytest.fixture(autouse=True)
def pure_binding(monkeypatch):
    monkeypatch.setattr(cad_dimensions.binding, 'wrap', lambda obj, cls: obj)


def chain(owner, count):
    dimensions = [dimension(index, owner) for index in range(count)]
    displays = [display(index, dim) for index, dim in enumerate(dimensions)]
    for current, following in zip(displays, displays[1:]):
        current.next = following
    owner.first = displays[0] if displays else None
    return dimensions, displays


def test_forty_unique_dimensions_use_linear_native_identity_calls_not_quadratic_old_record_queries():
    owner = feature(0)
    dims, displays = chain(owner, 40)
    adapter = Adapter()
    records = adapter.dimensions(object(), iter([Wrapper(owner)]))
    assert [record.dimension.native.key for record in records] == [dim.key for dim in dims]
    # F + V + P + D = 1 + 40 + 40 + 40. Previous implementation adds
    # 40*39/2 = 780 native identity calls inside the previous-record search.
    assert len(adapter.identity_calls) == 121
    assert sum(key[0] == 'dimension' for key in adapter.identity_calls) == 40
    assert sum(key[0] == 'display' for key in adapter.identity_calls) == 40
    assert all(record.owner_tree_identity == CanonicalIdentity(owner.key) for record in records)
    assert all(item.slot_calls == [0] for item in displays)


def test_absorbed_feature_aliases_deduplicate_fresh_python_wrappers_by_unhashable_identity():
    owner, absorbed = feature(0), feature(1)
    dim = dimension(0, owner)
    source = display(0, dim)
    owner.first = absorbed.first = source
    adapter = Adapter()
    records = adapter.dimensions(object(), [Wrapper(owner), Wrapper(absorbed)])
    assert len(records) == 1 and dim.owner_calls == 1
    assert len(records[0].displays) == 1 and len(records[0].display_slots) == 1
    assert source.slot_calls == [0, 0]
    # F2 + V2 + P2 + D1, with no old-record/display/slot QueryInterface.
    assert len(adapter.identity_calls) == 7


@pytest.mark.parametrize('same_parameter', [False, True])
def test_chamfer_slots_survive_alias_dedup_with_distinct_or_same_canonical_dimension(same_parameter):
    owner, absorbed = feature(0), feature(1)
    first = dimension(0, owner)
    second = first if same_parameter else dimension(1, owner)
    source = display(0, first, second=second)
    owner.first = absorbed.first = source
    adapter = Adapter()
    records = adapter.dimensions(object(), [Wrapper(owner), Wrapper(absorbed)])
    assert source.slot_calls == [0, 1, 0, 1]
    assert len(records) == (1 if same_parameter else 2)
    assert all(len(record.displays) == 1 for record in records)
    if same_parameter:
        assert [slot for _, slot in records[0].display_slots] == [0, 1]
    else:
        assert [slot for _, slot in records[0].display_slots] == [0]
        assert [slot for _, slot in records[1].display_slots] == [1]
    assert len(adapter.identity_calls) == 2 + 2 + 4 + len(records)


@pytest.mark.parametrize('owner_available', [False, True])
def test_foreign_or_missing_owner_never_acquires_current_tree_proof(owner_available):
    current, foreign = feature(0), feature(99)
    dim = dimension(0, foreign if owner_available else None)
    current.first = display(0, dim)
    record = Adapter().dimensions(object(), [Wrapper(current)])[0]
    assert record.owner_tree_identity is None
    assert (record.owner is not None) is owner_available


def test_two_different_canonical_dimensions_with_identical_names_nativeids_and_pidbytes_are_never_merged():
    owner = feature(0)
    dims, _ = chain(owner, 2)
    assert dims[0].name == dims[1].name and dims[0].native_id == dims[1].native_id and dims[0].pid == dims[1].pid
    records = Adapter().dimensions(object(), [Wrapper(owner)])[0:2]
    assert len(records) == 2 and records[0].dimension.native.key != records[1].dimension.native.key


def test_cyclic_display_chain_is_rejected_even_when_each_visit_uses_a_new_python_wrapper():
    owner = feature(0)
    dim = dimension(0, owner)
    source = display(0, dim)
    source.next = source
    owner.first = source
    adapter = Adapter()
    with pytest.raises(ExecutionFailure) as error:
        adapter.dimensions(object(), [Wrapper(owner)])
    assert error.value.code == 'dimension_traversal_cycle' and source.slot_calls == [0]


def test_second_enumeration_is_fresh_and_has_no_retained_source_identity_cache():
    owner = feature(0)
    old = dimension(0, owner)
    source = display(0, old)
    owner.first = source
    adapter = Adapter()
    first = adapter.dimensions(object(), [Wrapper(owner)])
    initial_calls = len(adapter.identity_calls)
    replacement = dimension(1, owner)
    source.targets[0] = replacement
    second = adapter.dimensions(object(), [Wrapper(owner)])
    assert first[0].dimension.native.key == old.key and second[0].dimension.native.key == replacement.key
    assert len(adapter.identity_calls) - initial_calls == initial_calls == 4
    assert set(adapter.__dict__) == {'identity_calls'}
    assert old.owner_calls == replacement.owner_calls == 1


def test_dimension_budget_still_rejects_complete_enumeration_instead_of_truncating():
    owner = feature(0)
    dims, _ = chain(owner, 5001)
    with pytest.raises(ExecutionFailure) as error:
        Adapter().dimensions(object(), [Wrapper(owner)])
    assert error.value.code == 'dimension_budget_exceeded'
    assert dims[-1].owner_calls == 0


def test_display_visit_budget_counts_aliases_instead_of_skipping_cached_memberships():
    owner = feature(0)
    dim = dimension(0, owner)
    displays = [display(index, dim) for index in range(5)]
    for current, following in zip(displays, displays[1:]):
        current.next = following
    owner.first = displays[0]
    adapter = Adapter()
    # Each independent feature walk contains five distinct displays, so this
    # is not a cycle. F=4001 stays within the upstream 5000-feature budget;
    # aliases still consume the 20000-visit global display budget.
    with pytest.raises(ExecutionFailure) as error:
        adapter.dimensions(object(), (Wrapper(owner) for _ in range(4001)))
    assert error.value.code == 'dimension_budget_exceeded'
    assert sum(len(source.slot_calls) for source in displays) == 20000 and dim.owner_calls == 1
