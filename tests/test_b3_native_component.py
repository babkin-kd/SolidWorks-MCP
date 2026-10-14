"""Direct artificial API getters, genuine ComponentCatalog registration."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from test_b3_component_membership import world

scripts = str(Path(__file__).resolve().parents[1] / 'scripts')
sys.path.insert(0, scripts)
try:
    from verifier_b3_native_component import RetainedComponentReference, capture_native_component
finally:
    sys.path.remove(scripts)


@pytest.fixture
def native_world(world):
    x = world; a = x.a; root = a.models[0]
    rows = x.catalog.list(**x.context)['items']; state = x.catalog._state(x.entry)
    x.native_calls = []; x.identity_calls = 0; x.safe_calls = []; x.sequence = [0, 0]
    x.pid_state = 0; x.pid_override = None; x.pid_resolution = None
    x.ordinal_hook = None; x.admitted = False
    root_cfg = NS(identity=a.configuration_identity(root, x.context['configuration']), Name=x.context['configuration'])
    root.GetType = lambda: 2; root.GetActiveConfiguration = lambda: root_cfg
    root.GetUpdateStamp = lambda: root.state['update_stamp']; root.GetSaveFlag = lambda: root.state['needs_save']
    root.GetBlockingState = lambda: 0; root.GetTitle = lambda: root.state['title']; root.GetPathName = lambda: root.state['path']
    x.native_models = {}; x.native_configurations = {}; x.model_cfgs = {}
    for native in a.instances:
        info, anchors = a.component_info(native)
        if anchors[0] not in x.native_models:
            configurations = {}; x.model_cfgs[anchors[0]] = configurations
            referenced = NS(identity=anchors[0], active_name='Основная', stamp=1, dirty=False,
                path=info['referenced_path'], title='Удерживаемая искусственная модель', kind=1 if info['referenced_document_type'] == 'part' else 2,
                Extension=NS(NeedsRebuild2=0))
            referenced.GetType = lambda model=referenced: model.kind
            referenced.GetUpdateStamp = lambda model=referenced: model.stamp
            referenced.GetSaveFlag = lambda model=referenced: model.dirty
            referenced.GetBlockingState = lambda: 0
            referenced.GetTitle = lambda model=referenced: model.title
            referenced.GetPathName = lambda model=referenced: model.path
            referenced.GetActiveConfiguration = lambda model=referenced, configurations=configurations: configurations[model.active_name]
            referenced.GetConfigurationByName = lambda name, configurations=configurations: configurations.get(name)
            x.native_models[anchors[0]] = referenced
        x.model_cfgs[anchors[0]].setdefault(info['referenced_configuration'], NS(identity=anchors[1], Name=info['referenced_configuration']))
    x.proxies = {}
    class Proxy:
        def __init__(self, native): self.native = native
        @property
        def identity(self): return self.native.identity
        @property
        def persistent_id(self): return self.native.persistent_id
        @property
        def Name2(self): return self.native.info['component_path']
        @property
        def ReferencedConfiguration(self): return self.native.info['referenced_configuration']
        @property
        def IsSpeedPak(self): return getattr(self.native, 'speedpak', False)
        def GetModelDoc2(self):
            x.native_calls.append('GetModelDoc2')
            return x.native_models[self.native.model_identity]
        def GetPathName(self): return self.native.info['referenced_path']
        def GetSuppression2(self): return self.native.info['native_suppression_state']
        def IsHidden(self, parents):
            assert parents is False
            return self.native.info['hidden']
        def GetTotalTransform(self, presentation):
            assert presentation is False
            x.native_calls.append('GetTotalTransform(False)')
            return NS(ArrayData=self.native.raw_total_transform)
        def GetParent(self): return self.native.parent
        def IsRoot(self): return False
    for native in a.instances: x.proxies[id(native)] = Proxy(native)
    def wrap(raw, interface):
        if raw is None: return None
        if interface == 'IComponent2' and id(raw) in x.proxies: return x.proxies[id(raw)]
        return raw
    x.wrap = wrap
    def resolve(pid):
        x.native_calls.append('GetObjectByPersistReference3')
        return (x.pid_resolution if x.pid_resolution is not None else a.registry[bytes(pid)], x.pid_state)
    root.Extension = NS(NeedsRebuild2=0, GetObjectByPersistReference3=resolve,
        GetPersistReference3=lambda component: x.pid_override if x.pid_override is not None else tuple(component.persistent_id))
    def census(top):
        assert top is False
        x.native_calls.append('GetComponents(False)')
        return list(a.instances)
    root.GetComponents = census
    bindings = []
    for row in rows:
        ref = state['refs'][row['component_id']]; native = a.registry[ref.persistent_id]
        referred = x.native_models[ref.model_identity]; cfg = x.model_cfgs[ref.model_identity][ref.referenced_configuration]
        bindings.append(RetainedComponentReference(row['component_id'], x.proxies[id(native)], ref.native_identity,
            ref.persistent_id, referred, ref.model_identity, ref.referenced_configuration, cfg, ref.referenced_configuration_identity,
            None if native.parent is None else x.proxies[id(native.parent)], None if native.parent is None else native.parent.identity))
    x.component_bindings = {role: next(binding for binding in bindings if binding.component_id == x.ids[role]) for role in x.ids}
    x.original_census = tuple(bindings); x.items = {role: next(row for row in rows if row['component_id'] == x.ids[role]) for role in x.ids}
    x.root_cfg = root_cfg
    x.root_model_canonical, x.root_configuration_canonical = root.identity, root_cfg.identity
    ordinals = []
    def identity(value):
        assert x.admitted, 'No native identity call before owner admission'
        x.identity_calls += 1
        return value.identity
    def ordinal(value):
        assert x.admitted
        if x.ordinal_hook: x.ordinal_hook()
        for index, old in enumerate(ordinals):
            if old == value: return index+1
        ordinals.append(value); return len(ordinals)
    def safe(context):
        x.safe_calls.append(deepcopy(context)); x.admitted = True
    x.native_identity = identity; x.native_ordinal = ordinal; x.assert_safe = safe
    # The observer must never call this adapter oracle. Genuine registration
    # already provided the private IDs and retained anchors above.
    a.component_info = lambda *args: (_ for _ in ()).throw(AssertionError('Adapter oracle forbidden'))
    return x


def run(x, role='variant', **overrides):
    args = dict(context=x.context, item=x.items[role], model=x.a.models[0], model_canonical=x.root_model_canonical,
        configuration_canonical=x.root_configuration_canonical, binding=x.component_bindings[role],
        original_instance_census=x.original_census, wrap=x.wrap, identity=x.native_identity,
        persistent_variant=lambda pid: tuple(pid), ordinal=x.native_ordinal,
        watches=(NS(poll=lambda: x.sequence[0]), NS(poll=lambda: x.sequence[1])), assert_safe=x.assert_safe)
    args.update(overrides)
    return capture_native_component(**args)


@pytest.mark.parametrize('role', ['main', 'variant', 'nested', 'parent', 'cylinder'])
def test_direct_component_getters_real_namespace_registration_and_inactive_referenced_cfg(native_world, role):
    x = native_world; result = run(x, role)
    assert result['component_info'] == {key: value for key, value in x.items[role].items() if key not in ('component_id', 'parent_component_id')}
    assert result['persistent_id'] == x.component_bindings[role].persistent_id.hex()
    assert len(x.safe_calls) == 2 and 'GetComponents(False)' in x.native_calls and x.identity_calls > 0
    assert result['native_receipt']['before'] == result['native_receipt']['after']
    assert result['accepted'] is result['native_acceptance'] is result['cleanup_authorized'] is False
    if role == 'variant':
        assert result['native_receipt']['before']['referenced']['active_configuration'] == 'Основная'
        assert result['component_info']['referenced_configuration'] == 'Вариант'
        assert result['configuration_identity'] != result['referenced_active_configuration_native_identity']


@pytest.mark.parametrize('fault', ['replaced', 'state', 'bool_state', 'different_pid', 'foreign_pid', 'missing', 'extra',
    'duplicate', 'foreign_model', 'cfg_identity', 'cfg_name', 'unknown_transform', 'short_transform', 'scaled', 'mirrored',
    'hidden_type', 'unresolved', 'speedpak', 'metadata', 'pending_rebuild', 'wrong_public', 'root_cfg'])
def test_raw_native_identity_pid_model_config_array_scope_and_metadata_mismatch_refused(native_world, fault):
    x = native_world; target = x.originals['variant']; binding = x.component_bindings['variant']
    if fault == 'replaced': target.identity = object()
    elif fault == 'state': x.pid_state = 2
    elif fault == 'bool_state': x.pid_state = False
    elif fault == 'different_pid': x.pid_override = b'other'
    elif fault == 'foreign_pid': x.pid_resolution = x.originals['main']
    elif fault == 'missing': x.a.instances.remove(target)
    elif fault == 'extra': x.a.instances.append(NS(identity=object()))
    elif fault == 'duplicate': x.a.instances[-1] = target
    elif fault == 'foreign_model': binding.referenced_model.identity = object()
    elif fault == 'cfg_identity': binding.configuration_handle.identity = object()
    elif fault == 'cfg_name': binding.configuration_handle.Name = 'Подмена'
    elif fault == 'unknown_transform': target.raw_total_transform = [float('nan')]*16
    elif fault == 'short_transform': target.raw_total_transform.pop()
    elif fault == 'scaled': target.raw_total_transform[12] = 2.
    elif fault == 'mirrored': target.raw_total_transform[6:9] = [0., 0., -1.]
    elif fault == 'hidden_type': target.info['hidden'] = 1
    elif fault == 'unresolved': target.info['native_suppression_state'] = 1
    elif fault == 'speedpak': target.speedpak = True
    elif fault == 'metadata': binding.referenced_model.GetSaveFlag = lambda: 'true'
    elif fault == 'pending_rebuild': binding.referenced_model.Extension.NeedsRebuild2 = 1
    elif fault == 'wrong_public': x.items['variant']['hidden'] = False
    elif fault == 'root_cfg': x.root_cfg.identity = object()
    with pytest.raises((ValueError, AttributeError)): run(x)


def test_nested_parent_native_canonical_cannot_be_adopted_by_same_path(native_world):
    x = native_world
    proxy = x.proxies[id(x.originals['nested'])]
    proxy.GetParent = lambda: NS(identity=object(), IsRoot=lambda: False, Name2=x.originals['parent'].info['component_path'])
    with pytest.raises(ValueError): run(x, 'nested')


@pytest.mark.parametrize('foreign', [False, True])
def test_top_level_root_parent_is_bound_to_actual_original_assembly(native_world, foreign):
    x = native_world
    root_parent = NS(IsRoot=lambda: True, GetModelDoc2=lambda: NS(identity=object()) if foreign else x.a.models[0])
    x.proxies[id(x.originals['variant'])].GetParent = lambda: root_parent
    if foreign:
        with pytest.raises(ValueError): run(x)
    else: assert run(x)['parent_native_identity'] is None


@pytest.mark.parametrize('fault', ['aba_root', 'aba_referenced', 'ordinal_aba', 'ordinal_metadata', 'ordinal_transform',
    'ordinal_cfg', 'closing_safe', 'nonunique_ordinals'])
def test_requestwide_watch_metadata_and_current_canonical_checks_close_after_ordinals(native_world, fault):
    x = native_world; referred = x.component_bindings['variant'].referenced_model
    if fault.startswith('aba_'):
        original = x.proxies[id(x.originals['variant'])].GetTotalTransform
        def transformed(flag):
            x.sequence[0 if fault == 'aba_root' else 1] += 2
            return original(flag)
        x.proxies[id(x.originals['variant'])].GetTotalTransform = transformed
    elif fault == 'nonunique_ordinals': x.native_ordinal = lambda canonical: 1
    elif fault == 'closing_safe':
        original = x.assert_safe
        def safe(context):
            original(context)
            if len(x.safe_calls) == 2: x.sequence[1] += 2
        x.assert_safe = safe
    else:
        once = []
        def ordinal():
            if once: return
            once.append(True)
            if fault == 'ordinal_aba': x.sequence[1] += 2
            elif fault == 'ordinal_metadata': referred.dirty = True
            elif fault == 'ordinal_transform': x.originals['variant'].raw_total_transform[9] += .001
            else: x.component_bindings['variant'].configuration_handle.identity = object()
        x.ordinal_hook = ordinal
    with pytest.raises(ValueError): run(x)


def test_owner_admission_precedes_even_native_census_canonical_equality(native_world):
    x = native_world
    class NativeCanonical:
        def __eq__(self, other): raise AssertionError('Native canonical comparison before admission')
    original = list(x.original_census); original[0] = replace(original[0], canonical=NativeCanonical())
    def unsafe(context): raise RuntimeError('Owner native calls not quiescent')
    with pytest.raises(RuntimeError): run(x, original_instance_census=original, assert_safe=unsafe)
    assert x.identity_calls == 0 and x.native_calls == []


def test_bound_native_instance_cannot_be_adopted_from_public_name_or_path(native_world):
    x = native_world; binding = x.component_bindings['variant']
    bad = replace(binding, component_id='unregistered-looking-id')
    with pytest.raises(ValueError): run(x, binding=bad)
    assert x.native_calls == []
