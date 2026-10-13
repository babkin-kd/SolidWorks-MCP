"""Direct native I03 component facts; no connection, dispatch or cleanup."""
from dataclasses import dataclass

from verifier_b3_part_geometry import _context, _canonical
from verifier_b3_component_membership import _ordinal, _transform
from verifier_b3_native_part_reference import require, numbers


@dataclass(frozen=True)
class RetainedComponentReference:
    component_id: str
    handle: object
    canonical: object
    persistent_id: bytes
    referenced_model: object
    model_canonical: object
    referenced_configuration: str
    configuration_handle: object
    configuration_canonical: object
    parent_handle: object = None
    parent_canonical: object = None


def capture_native_component(*, context, item, model, model_canonical,
        configuration_canonical, binding, original_instance_census, wrap,
        identity, persistent_variant, ordinal, watches, assert_safe):
    """Direct getter observer on the original owning STA, never an adapter oracle.

Original private component_id→retained PID/IUnknown anchors and complete five
instance census must already be owner-admitted; names/paths never adopt them.
wrap(raw, interface_name), identity, persistent_variant(bytes), ordinal and
assert_safe(context) are owner callbacks. watches are two already attached
root/referenced-model event watchers, covering the entire request. This method
neither creates nor closes them. Referenced configuration can be inactive.
Bodies/topology/full-session ownership and the actual opaque-ID bridge remain
separate open gates; these primitive receipts never certify native acceptance.
"""
    context = _context(context)
    require(isinstance(binding, RetainedComponentReference)
            and type(original_instance_census) in (tuple, list) and len(original_instance_census) == 5
            and all(isinstance(row, RetainedComponentReference) for row in original_instance_census)
            and type(watches) in (tuple, list) and len(watches) == 2
            and all(callable(callback) for callback in (wrap, identity, persistent_variant, ordinal, assert_safe)),
            'Original owner retained bindings, complete instance census and explicit callbacks/watchers required.')
    # No native identity/canonical equality, getters, ordinals or watch reads
    # may occur before this admission.
    assert_safe(context)
    def events():
        values = [watch.poll() for watch in watches]
        require(all(type(value) is int and value >= 0 for value in values), 'Actual typed complete native event sequences required.')
        return values
    event_before = events()
    require(type(item) is dict and item['component_id'] == binding.component_id
            and type(binding.component_id) is str and binding.component_id
            and type(binding.persistent_id) is bytes and binding.persistent_id
            and type(binding.referenced_configuration) is str and binding.referenced_configuration
            and len({row.component_id for row in original_instance_census}) == 5
            and sum(row is binding for row in original_instance_census) == 1
            and all(sum(row.canonical == other.canonical for other in original_instance_census) == 1
                    for row in original_instance_census), 'Exact original private namespace/canonical census binding required.')

    def metadata(doc, canonical, root=False):
        require(identity(doc) == canonical, 'Current retained original model canonical required.')
        cfg = wrap(doc.GetActiveConfiguration(), 'IConfiguration')
        require(cfg is not None, 'Actual current active configuration handle required.')
        active_canonical = identity(cfg)
        kind, stamp, dirty, blocking = doc.GetType(), doc.GetUpdateStamp(), doc.GetSaveFlag(), doc.GetBlockingState()
        title, path, name = doc.GetTitle(), doc.GetPathName(), cfg.Name
        extension = wrap(doc.Extension, 'IModelDocExtension'); rebuild = extension.NeedsRebuild2
        require(type(kind) is int and kind in (1, 2) and type(stamp) is int and type(dirty) is bool
                and type(blocking) is int and type(rebuild) is int and rebuild == 0
                and all(type(value) is str for value in (title, path, name)) and name,
                'Complete typed current native model/configuration metadata; pending rebuild refused.')
        if root:
            require(kind == 2 and active_canonical == configuration_canonical and name == context['configuration'],
                    'Original explicit root assembly configuration incarnation required.')
        return dict(document_type='part' if kind == 1 else 'assembly', update_stamp=stamp, needs_save=dirty,
                    blocking_state=blocking, needs_rebuild=rebuild, title=title, path=path, active_configuration=name), active_canonical
    before_root, root_active = metadata(model, model_canonical, True)
    before_referenced, referenced_active = metadata(binding.referenced_model, binding.model_canonical)

    def current_binding():
        extension = wrap(model.Extension, 'IModelDocExtension')
        raw = extension.GetObjectByPersistReference3(persistent_variant(binding.persistent_id))
        require(type(raw) in (tuple, list) and len(raw) == 2, 'Actual typed native PID resolution result required.')
        resolved, state = raw
        require(type(state) is int and state == 0 and resolved is not None
                and identity(wrap(resolved, 'IComponent2')) == binding.canonical
                and identity(binding.handle) == binding.canonical, 'Original exact state0 PID/current retained component canonical required.')
        pid = extension.GetPersistReference3(binding.handle)
        require(pid is not None and bytes(pid) == binding.persistent_id, 'Current exact original component PID required; no alias/name fallback.')
        assembly = wrap(model, 'IAssemblyDoc'); raw_components = assembly.GetComponents(False)
        require(type(raw_components) in (tuple, list) and len(raw_components) == 5, 'Actual complete five-instance native census required.')
        current = [identity(wrap(component, 'IComponent2')) for component in raw_components]
        require(all(sum(value == retained.canonical for value in current) == 1 for retained in original_instance_census)
                and sum(value == binding.canonical for value in current) == 1, 'Complete current original instance census differs/replaced/foreign.')
        return current
    current = current_binding()
    component = binding.handle
    native_model = wrap(component.GetModelDoc2(), 'IModelDoc2')
    require(native_model is not None and identity(native_model) == binding.model_canonical
            and identity(binding.referenced_model) == binding.model_canonical, 'Exact original referenced model canonical required; no implicit load.')
    configuration = component.ReferencedConfiguration
    require(type(configuration) is str and configuration == binding.referenced_configuration,
            'Actual original referenced configuration required; no switch/adoption.')
    named = wrap(native_model.GetConfigurationByName(configuration), 'IConfiguration')
    require(named is not None and identity(named) == binding.configuration_canonical
            and identity(binding.configuration_handle) == binding.configuration_canonical
            and named.Name == configuration and binding.configuration_handle.Name == configuration,
            'Current original referenced configuration canonical membership required; it need not be active.')
    state = component.GetSuppression2(); hidden = component.IsHidden(False); speedpak = component.IsSpeedPak
    require(type(state) is int and state in (2, 3) and type(hidden) is bool and speedpak is False,
            'Only existing resolved original normal component scope; no implicit resolution/SpeedPak.')
    raw_transform = wrap(component.GetTotalTransform(False), 'IMathTransform')
    require(raw_transform is not None, 'Actual native total transform required.')
    values = numbers(raw_transform.ArrayData, 16)
    transform = dict(origin_mm=[x*1000. for x in values[9:12]], axes_in_assembly=[values[i:i+3] for i in (0, 3, 6)],
                     parity='right_handed', scale=1., includes_presentation_transform=False)
    _transform(transform, values)
    parent_raw = component.GetParent(); parent_id = parent_canonical = None
    if parent_raw is not None:
        parent = wrap(parent_raw, 'IComponent2'); is_root = parent.IsRoot()
        require(type(is_root) is bool, 'Typed actual native parent root state required.')
        if is_root:
            root_model = wrap(parent.GetModelDoc2(), 'IModelDoc2')
            require(root_model is not None and identity(root_model) == model_canonical
                    and binding.parent_handle is None and binding.parent_canonical is None, 'Actual root parent must belong to retained original assembly.')
        else:
            require(binding.parent_handle is not None and binding.parent_canonical is not None
                    and identity(parent) == binding.parent_canonical and identity(binding.parent_handle) == binding.parent_canonical,
                    'Exact retained original native parent canonical required.')
            parents = [row for row in original_instance_census if row.canonical == binding.parent_canonical]
            require(len(parents) == 1, 'Original parent must belong to the complete retained instance census.')
            parent_id, parent_canonical = parents[0].component_id, binding.parent_canonical
    else:
        require(binding.parent_handle is None and binding.parent_canonical is None, 'Original nested parent cannot disappear.')
    path, referenced_path = component.Name2, component.GetPathName()
    require(type(path) is str and path and type(referenced_path) is str and referenced_path
            and referenced_path == before_referenced['path'], 'Actual current instance path/referenced file facts required; no addressing by text.')
    if parent_id is None: require('/' not in path, 'Current root path conflicts with native parent.')
    else: require(path.rsplit('/', 1)[0] == binding.parent_handle.Name2, 'Actual native nested parent path conflicts with canonical parent.')
    info = dict(component_path=path, referenced_path=referenced_path, referenced_configuration=configuration,
        referenced_document_type=before_referenced['document_type'], suppression_state='resolved', native_suppression_state=state,
        hidden=hidden, transform=transform)
    require(_canonical(item) == _canonical(dict(component_id=binding.component_id, **info, parent_component_id=parent_id)),
            'Public component facts differ from direct current native getters.')
    ids = dict(native_identity=_ordinal(ordinal(binding.canonical)), model_identity=_ordinal(ordinal(binding.model_canonical)),
        configuration_identity=_ordinal(ordinal(binding.configuration_canonical)), root_model_native_identity=_ordinal(ordinal(model_canonical)),
        root_configuration_native_identity=_ordinal(ordinal(configuration_canonical)),
        root_active_configuration_native_identity=_ordinal(ordinal(root_active)),
        referenced_active_configuration_native_identity=_ordinal(ordinal(referenced_active)),
        parent_native_identity=None if parent_canonical is None else _ordinal(ordinal(parent_canonical)))
    census_ordinals = [_ordinal(ordinal(value)) for value in current]
    require(len(set(census_ordinals)) == 5 and ids['native_identity'] in census_ordinals, 'Distinct ordinal mappings must preserve original native instance equality.')
    # Closing checks occur AFTER every owner ordinal callback/canonical equality.
    current_binding()
    closing_transform = wrap(component.GetTotalTransform(False), 'IMathTransform')
    closing_parent = component.GetParent()
    if closing_parent is None:
        require(parent_id is None and binding.parent_canonical is None, 'Original current parent changed during observation.')
    else:
        closing_parent = wrap(closing_parent, 'IComponent2')
        if parent_id is None:
            require(closing_parent.IsRoot() is True
                    and identity(wrap(closing_parent.GetModelDoc2(), 'IModelDoc2')) == model_canonical,
                    'Current retained root parent changed during observation.')
        else:
            require(closing_parent.IsRoot() is False and identity(closing_parent) == parent_canonical
                    and path.rsplit('/', 1)[0] == closing_parent.Name2, 'Current retained nested parent changed during observation.')
    require(closing_transform is not None and numbers(closing_transform.ArrayData, 16) == values
            and component.Name2 == path and component.GetPathName() == referenced_path
            and type(component.GetSuppression2()) is int and component.GetSuppression2() == state
            and type(component.IsHidden(False)) is bool and component.IsHidden(False) is hidden
            and component.IsSpeedPak is False, 'Direct current instance facts changed during ordinal/closing callbacks.')
    assert_safe(context)
    after_root, root_after = metadata(model, model_canonical, True)
    after_referenced, referenced_after = metadata(binding.referenced_model, binding.model_canonical)
    closing_configuration = wrap(binding.referenced_model.GetConfigurationByName(configuration), 'IConfiguration')
    require(closing_configuration is not None and identity(closing_configuration) == binding.configuration_canonical
            and closing_configuration.Name == configuration and binding.configuration_handle.Name == configuration
            and component.ReferencedConfiguration == configuration and identity(wrap(component.GetModelDoc2(), 'IModelDoc2')) == binding.model_canonical
            and root_after == root_active and referenced_after == referenced_active
            and before_root == after_root and before_referenced == after_referenced and events() == event_before,
            'Requestwide original model/configuration metadata/canonical/events changed, including ABA during ordinals.')
    return dict(scope='raw_native_retained_component_v1', component_id=binding.component_id,
        component_info=info, total_transform=values, persistent_id=binding.persistent_id.hex(), **ids,
        native_receipt=dict(before=dict(root=before_root, referenced=before_referenced), after=dict(root=after_root, referenced=after_referenced),
            event_sequences=event_before, current_instance_native_identities=census_ordinals),
        accepted=False, native_acceptance=False, cleanup_authorized=False,
        open_gates=['actual_owner_private_opaque_ID_PID_canonical_bridge', 'full_owned_session_and_transition_scope', 'exact_installed_wheel_B3_driver'])
