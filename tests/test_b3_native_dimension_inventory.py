"""Artificial native API getters; actual summary/unit predicates, no CAD."""
from copy import deepcopy
from dataclasses import dataclass, replace
import math
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_dimensions import CadDimensionsMixin, NativeDimension
from solidworks_mcp.cad_features import CadFeaturesMixin
from solidworks_mcp import cad_features
from test_b3_native_feature_inventory import tree
from test_b3_native_document_metadata import world

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b3_native_dimension_inventory import RetainedDimension, RetainedDisplaySlot, capture_native_dimension_inventory
    from verifier_b3_part_objects import dimension_units
finally:
    sys.path.remove(scripts)


@dataclass(frozen=True)
class NamedBSTR:
    name: str


@pytest.fixture(params=[False, True], ids=['ordinary', 'chamfer'])
def inventory(tree, request):
    x = tree; boss, sketch = x.features[1:]
    x.dimensions = []; x.displays = []; x.value_calls = []; x.unknown_query = False; x.annotation_mode = False
    x.query_calls = []; x.native_states = {}; x.ordinal_hook = None
    for feature in x.features:
        feature.IsFrozen = lambda: False; feature.IsRolledBack = lambda: False
        feature.GetUpdateStamp = lambda: 1
        feature.GetFirstDisplayDimension = lambda feature=feature: getattr(feature, 'first_display', None)
        feature.GetNextDisplayDimension = lambda display: display.next_display
    def dimension(name, owner, *, kind=0, direct=b'', values=None):
        d = NS(canonical=object(), owner=owner, pid=direct, FullName=name+'@'+owner.Name+'@Контрольная деталь.SLDPRT', Name=name,
            kind=kind, DrivenState=2, ReadOnly=False, reference=False, design_table=False,
            values=values or {'Основная': .01, 'Вариант': .012}, tolerance_type=0, tolerance_values=None)
        d.GetFeatureOwner = lambda: d.owner; d.GetType = lambda: d.kind
        d.IsReference = lambda: d.reference; d.IsDesignTableDimension = lambda: d.design_table
        d.GetToleranceType = lambda: d.tolerance_type; d.GetToleranceValues = lambda: d.tolerance_values
        def value(scope, variant):
            assert scope == 3 and isinstance(variant, NamedBSTR)
            x.value_calls.append((d.Name, variant.name))
            return [d.values[variant.name]]
        d.GetSystemValue3 = value
        x.dimensions.append(d); return d
    def display(name, dims, pid=b'', kind=2):
        d = NS(canonical=object(), name=name, pid=pid, kind=kind, dims=dims, IsLinked=False, text=None, next_display=None)
        d.GetType = lambda: d.kind; d.GetDimension2 = lambda index: d.dims[index]
        d.GetLinkedText = lambda: d.text
        annotation = NS(canonical=object(), display=d, native_kind='annotation', GetType=lambda: 4)
        annotation.GetSpecificAnnotation = lambda: annotation.display
        d.annotation = annotation; d.GetAnnotation = lambda: d.annotation
        x.displays.append(d); return d
    length = dimension('Толщина', boss, direct=b'direct-length')
    angle = dimension('Угол', boss, kind=1, values={'Основная': math.pi/2, 'Вариант': math.pi/3})
    first = display('length', [length], b'display-length')
    second = display('angle', [angle], b'display-angle', 4)
    first.next_display = second
    if request.param:
        c0 = dimension('Фаска длина', boss, values={'Основная': .003, 'Вариант': .004})
        c1 = dimension('Фаска угол', boss, kind=1, values={'Основная': math.pi/4, 'Вариант': math.pi/6})
        chamfer = display('chamfer', [c0, c1], b'display-chamfer', 10)
        second.next_display = chamfer; tail = chamfer
    else: tail = second
    unsupported = dimension('Ширина эскиза', sketch, values={'Основная': -.04, 'Вариант': -.05})
    last = display('unsupported', [unsupported])
    tail.next_display = last; boss.first_display = first; sketch.first_display = last  # Absorbed alias, same canonical/slot.
    def current_pid(obj): return obj.pid
    def resolve(pid):
        pid = bytes(pid)
        if pid in x.native_states: return None, x.native_states[pid]
        objects = x.features+x.dimensions+x.displays
        obj = next(obj for obj in objects if obj.pid == pid)
        if x.annotation_mode and obj in x.displays: return obj.annotation, 0
        return obj, 0
    x.model.Extension = NS(GetPersistReference3=current_pid, GetObjectByPersistReference3=resolve)
    originals = []
    for dim in x.dimensions:
        slots = tuple(RetainedDisplaySlot(display, display.canonical, display.pid, index, display.kind)
            for display in x.displays for index, target in enumerate(display.dims) if target is dim)
        originals.append(RetainedDimension(dim, dim.canonical, dim.owner, dim.owner.canonical, dim.owner.pid, dim.pid, slots))
    x.original_dimensions = tuple(originals)
    anchors = [x.model.canonical, *(cfg.canonical for cfg in x.cfgs), *(feature.canonical for feature in x.features),
               *(dim.canonical for dim in x.dimensions), *(display.canonical for display in x.displays)]
    def ordinal(canonical):
        if x.ordinal_hook: x.ordinal_hook(canonical)
        return next(index+1 for index, old in enumerate(anchors) if canonical == old)
    x.ordinal = ordinal
    class QueryFailure(Exception):
        def __init__(self, hresult): self.hresult = hresult
    x.QueryFailure = QueryFailure
    def query(raw, interface):
        x.query_calls.append(interface)
        if x.unknown_query: raise QueryFailure(-2147418111)
        if interface == 'IDisplayDimension' and getattr(raw, 'native_kind', '') == 'annotation': raise QueryFailure(-2147467262)
        return raw
    x.query = query
    return x


def run(x, **overrides):
    args = dict(context=dict(document_id='original-doc', configuration='Основная'), document=x.binding,
        features=x.originals, originals=x.original_dimensions, wrap=lambda raw, interface: raw,
        identity=x.identity, ordinal=x.ordinal, persistent_variant=lambda pid: pid,
        named_configuration=NamedBSTR, watch=NS(poll=lambda: x.sequence), assert_safe=x.safe, query=x.query)
    args.update(overrides)
    return capture_native_dimension_inventory(**args)


def test_complete_original_direct_display_unsupported_units_inactive_values_and_absorbed_slots(inventory, monkeypatch):
    x = inventory; result = run(x)
    assert len(result['rows']) == len(x.dimensions)
    assert [row['reference_supported'] for row in result['rows']] == [True]*(len(x.dimensions)-1)+[False]
    assert result['rows'][0]['summary']['reference_anchor'] == {'strategy': 'direct_dimension_v1', 'dimension_pid_hex': x.dimensions[0].pid.hex()}
    assert result['rows'][1]['summary']['reference_anchor']['strategy'] == 'display_dimension_v1'
    assert result['rows'][0]['summary']['values'] == {'Основная': 10., 'Вариант': 12.}
    assert result['rows'][1]['summary']['values']['Основная'] == 90.
    assert result['rows'][-1]['summary']['values']['Основная'] == -40.
    assert result['rows'][-1]['summary']['reference_anchor'] is None and result['rows'][-1]['native_receipt']['unsupported_reason']
    assert x.active is x.cfgs[0] and all(cfg in ('Основная', 'Вариант') for _, cfg in x.value_calls)
    assert result['before'] == result['after']
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False
    # Actual production summary logic is exercised only as an independent ABI
    # comparison in tests; the observer never calls it as its native oracle.
    adapter = NS(_named_configuration=NamedBSTR, _module=NS(IFeature=object()))
    adapter.feature_summary = lambda feature: CadFeaturesMixin.feature_summary(adapter, feature)
    with monkeypatch.context() as boundary:
        boundary.setattr(cad_features.binding, 'wrap', lambda raw, interface: raw)
        for dim, original, row in zip(x.dimensions, x.original_dimensions, result['rows']):
            record = NativeDimension(dim, dim.owner, displays=[slot.handle for slot in original.display_slots], owner_tree_identity=dim.owner.canonical)
            expected = CadDimensionsMixin.dimension_summary(adapter, record, ['Основная', 'Вариант'])
            expected['reference_anchor'] = row['summary']['reference_anchor']
            assert expected == row['summary']; dimension_units(row['summary'])
    if len(x.dimensions) > 3:
        assert result['rows'][2]['summary']['reference_anchor']['dimension_index'] == 0
        assert result['rows'][3]['summary']['reference_anchor']['dimension_index'] == 1


def test_explicit_annotation_pid_bridge_uses_only_exact_enointerface_and_current_association(inventory):
    x = inventory; x.annotation_mode = True
    result = run(x)
    assert result['rows'][1]['reference_supported'] is True and 'IAnnotation' in x.query_calls
    x.unknown_query = True
    with pytest.raises(x.QueryFailure) as caught: run(x)
    assert caught.value.hresult == -2147418111


@pytest.mark.parametrize('fault', ['extra_dimension', 'missing_dimension', 'replacement', 'display_cycle', 'slot', 'display_type',
    'direct_pid', 'display_pid', 'owner_pid', 'direct_invalid', 'display_invalid', 'owner', 'owner_replaced',
    'native_array', 'bool_value', 'nonfinite', 'tolerance', 'flags', 'display_link', 'unknown_display', 'owner_summary', 'feature_parent'])
def test_current_native_census_pid_slot_owner_arrays_or_summary_change_is_never_partial_unsupported(inventory, fault):
    x = inventory; d = x.dimensions[0]; display = x.displays[0]
    if fault == 'extra_dimension':
        extra = NS(**vars(d)); extra.canonical = object()
        display.dims[0] = extra
    elif fault == 'missing_dimension': x.features[1].first_display = x.displays[1]
    elif fault == 'replacement': d.canonical = object()
    elif fault == 'display_cycle': x.displays[-1].next_display = x.displays[0]
    elif fault == 'slot': display.dims[0] = x.dimensions[1]
    elif fault == 'display_type': display.kind = 4
    elif fault == 'direct_pid': d.pid = b'changed'
    elif fault == 'display_pid': display.pid = b'changed'
    elif fault == 'owner_pid': x.features[1].pid = b'changed'
    elif fault == 'direct_invalid': x.native_states[d.pid] = 4
    elif fault == 'display_invalid': x.native_states[x.displays[1].pid] = 2
    elif fault == 'owner': d.owner = x.features[2]
    elif fault == 'owner_replaced': x.features[1].canonical = object()
    elif fault == 'native_array': d.GetSystemValue3 = lambda *args: []
    elif fault == 'bool_value': d.values['Основная'] = True
    elif fault == 'nonfinite': d.values['Вариант'] = math.nan
    elif fault == 'tolerance': d.tolerance_type = 1; d.tolerance_values = [0.]
    elif fault == 'flags': d.ReadOnly = 1
    elif fault == 'display_link': display.IsLinked = 1
    elif fault == 'unknown_display': display.kind = 0
    elif fault == 'owner_summary': x.features[1].error = (True, False)
    elif fault == 'feature_parent': x.features[2].owner = x.features[0]
    with pytest.raises((ValueError, StopIteration)): run(x)


@pytest.mark.parametrize('fault', ['value', 'owner', 'direct_pid', 'display_pid', 'slot', 'display_type', 'name',
    'tolerance', 'flags', 'link', 'ordinal_aba', 'metadata', 'config', 'noninjective'])
def test_all_native_getters_pid_owner_and_slots_reread_after_every_ordinal_callback(inventory, fault):
    x = inventory; once = []
    def hook(canonical):
        if once: return
        once.append(True); d = x.dimensions[0]; display = x.displays[0]
        if fault == 'value': d.values['Вариант'] += .001
        elif fault == 'owner': d.owner = x.features[2]
        elif fault == 'direct_pid': d.pid = b'changed'
        elif fault == 'display_pid': display.pid = b'changed'
        elif fault == 'slot': display.dims[0] = x.dimensions[1]
        elif fault == 'display_type': display.kind = 4
        elif fault == 'name': d.Name = 'Изменённое имя'
        elif fault == 'tolerance': d.tolerance_values = [.001, .002]
        elif fault == 'flags': d.ReadOnly = True
        elif fault == 'link': display.text = 'Ссылка'
        elif fault == 'ordinal_aba': x.sequence += 2
        elif fault == 'metadata': x.dirty = False
        elif fault == 'config': x.cfgs[1].canonical = object()
    x.ordinal_hook = hook
    overrides = {'ordinal': lambda canonical: 1} if fault == 'noninjective' else {}
    with pytest.raises((ValueError, StopIteration)): run(x, **overrides)


def test_truthful_empty_original_anchor_cannot_mask_formerly_supported_invalidation(inventory):
    x = inventory; result = run(x)
    assert result['rows'][-1]['reference_supported'] is False
    x.native_states[x.dimensions[0].pid] = 1
    with pytest.raises(ValueError, match='supported PID'): run(x)


def test_owner_gate_before_all_canonical_comparisons_getters_or_ordinals(inventory):
    x = inventory
    class NativeCanonical:
        def __eq__(self, other): raise AssertionError('Native comparison before owner admission')
    originals = (replace(x.original_dimensions[0], canonical=NativeCanonical()), *x.original_dimensions[1:])
    def forbidden(*args): raise AssertionError('Native call before owner admission')
    def reject(context): raise RuntimeError('Owner not admitted')
    with pytest.raises(RuntimeError): run(x, originals=originals, identity=forbidden, ordinal=forbidden, assert_safe=reject)
    assert x.calls == [] and x.value_calls == []


def test_named_configuration_reader_cannot_silently_activate_requested_configuration(inventory):
    x = inventory
    def bad_named(name):
        x.active = next(cfg for cfg in x.cfgs if cfg.Name == name)
        return NamedBSTR(name)
    with pytest.raises(ValueError): run(x, named_configuration=bad_named)
