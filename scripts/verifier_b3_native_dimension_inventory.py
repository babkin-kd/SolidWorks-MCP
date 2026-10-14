"""Direct finite I01 dimension inventory; no connection, setters or cleanup."""
from dataclasses import dataclass
import math

from verifier_b3_native_document_metadata import RetainedDocument, require
from verifier_b3_native_feature_inventory import RetainedFeature


@dataclass(frozen=True)
class RetainedDisplaySlot:
    handle: object
    canonical: object
    persistent_id: bytes
    index: int
    display_type: int


@dataclass(frozen=True)
class RetainedDimension:
    handle: object
    canonical: object
    owner_handle: object
    owner_canonical: object
    owner_persistent_id: bytes
    direct_persistent_id: bytes
    display_slots: tuple


def capture_native_dimension_inventory(*, context, document, features, originals,
        wrap, identity, ordinal, persistent_variant, named_configuration,
        watch, assert_safe, query=None):
    """Rows satisfy verifier_b3_part_objects.capture_inventory dimension ABI.

Original owner supplies retained IDimension/IFeature/full display-slot anchors,
original absorbed-inclusive feature traversal and original 1–2 config handles.
No dimension_summary, dimension_persistent_id or production anchor resolver is
used as an oracle. named_configuration(name) returns typed SAFEARRAY(BSTR) for
GetSystemValue3(3,...), never activation. Optional query(raw, interface_name)
allows only exact E_NOINTERFACE annotation→display recovery; unknown failures
propagate without retry. All original PID/slot/owner/raw fields are reread after
every ordinal callback. Empty original anchors remain unsupported; any formerly
supported anchor changing/invalidating refuses the complete observation.
Current SDK opaque IDs/whole native session/ownership remain separate gates.
"""
    require(type(context) is dict and set(context) == {'document_id', 'configuration'}
            and isinstance(document, RetainedDocument) and context['document_id'] == document.document_id
            and type(features) is tuple and 0 < len(features) <= 100 and all(isinstance(f, RetainedFeature) for f in features)
            and type(originals) is tuple and 0 < len(originals) <= 100 and all(isinstance(d, RetainedDimension) for d in originals)
            and all(callable(f) for f in (wrap, identity, ordinal, persistent_variant, named_configuration, assert_safe)),
            'Original bounded retained model/features/dimensions and owner callbacks required.')
    assert_safe(context)
    event = watch.poll(); require(type(event) is int and event >= 0, 'Typed native event sequence required.')
    require(all(sum(d.canonical == other.canonical for other in originals) == 1 for d in originals)
            and all(sum(f.canonical == other.canonical for other in features) == 1 for f in features), 'Distinct original canonical dimensions/features required.')
    model = document.model; extension = wrap(model.Extension, 'IModelDocExtension')
    configurations = document.configurations; names = [cfg.name for cfg in configurations]
    require(type(configurations) is tuple and 1 <= len(names) <= 2 and len(set(names)) == len(names)
            and context['configuration'] in names, 'Original finite named configuration census required.')

    def metadata():
        require(identity(model) == document.canonical and model.GetType() == 1 and type(model.GetType()) is int,
                'Actual retained original part model required.')
        require(type(model.GetConfigurationNames()) in (tuple, list) and list(model.GetConfigurationNames()) == names,
                'Complete current original configuration roster required.')
        for cfg in configurations:
            current = wrap(model.GetConfigurationByName(cfg.name), 'IConfiguration')
            require(current is not None and current.Name == cfg.name and identity(current) == cfg.canonical
                    and identity(cfg.handle) == cfg.canonical, 'Current original named configuration incarnation required.')
        active = wrap(model.GetActiveConfiguration(), 'IConfiguration')
        require(active is not None and active.Name == context['configuration']
                and identity(active) == next(cfg.canonical for cfg in configurations if cfg.name == active.Name),
                'Original active part context required; named value reads may not switch it.')
        stamp, dirty, title, path = model.GetUpdateStamp(), model.GetSaveFlag(), model.GetTitle(), model.GetPathName()
        require(type(stamp) is int and type(dirty) is bool and type(title) is str and title and type(path) is str,
                'Actual typed current part metadata required.')
        return dict(update_stamp=stamp, needs_save=dirty, title=title, path=path, configurations=names[:], active_configuration=active.Name)
    before = metadata()

    def pid(handle, original, canonical, interface):
        require(identity(handle) == canonical, 'Original retained anchor handle canonical changed.')
        raw = extension.GetPersistReference3(handle); current = b'' if raw is None else bytes(raw)
        require(type(original) is bytes and current == original, 'Current native PID differs from original anchor; no downgrade/alias adoption.')
        if current:
            resolved, state = extension.GetObjectByPersistReference3(persistent_variant(current))
            require(type(state) is int and state == 0 and resolved is not None, 'Original supported PID became invalid; not an unsupported row.')
            if interface == 'IDisplayDimension' and query is not None:
                try: resolved = query(resolved, 'IDisplayDimension')
                except Exception as error:
                    if getattr(error, 'hresult', None) != -2147467262: raise
                    annotation = query(resolved, 'IAnnotation')
                    require(type(annotation.GetType()) is int and annotation.GetType() == 4, 'Display PID annotation must be an actual dimension annotation.')
                    resolved = query(annotation.GetSpecificAnnotation(), 'IDisplayDimension')
                    actual_annotation = query(resolved.GetAnnotation(), 'IAnnotation')
                    require(actual_annotation is not None and identity(actual_annotation) == identity(annotation), 'Exact current annotation/display association required.')
            else: resolved = wrap(resolved, interface)
            require(resolved is not None and identity(resolved) == canonical and identity(handle) == canonical,
                    'Original native PID must resolve to its exact retained canonical.')
        return current

    def census():
        stack = [(wrap(model.FirstFeature(), 'IFeature'), False)]; seen, links, current_features = {}, set(), []
        visits = 0
        while stack:
            feature, sub = stack.pop()
            if feature is None: continue
            visits += 1; require(visits <= 400, 'Finite complete feature traversal budget exceeded.')
            native_id = feature.GetID(); require(type(native_id) is int, 'Typed native traversal feature ID required.')
            canonical = identity(feature); old = seen.get(native_id)
            require(old is None or old == canonical, 'Native feature ID collision; IDs do not replace canonical identity.')
            if (native_id, sub) in links: continue
            links.add((native_id, sub)); stack.append((wrap(feature.GetNextSubFeature() if sub else feature.GetNextFeature(), 'IFeature'), sub))
            if old is not None: continue
            seen[native_id] = canonical; current_features.append(feature)
            require(len(current_features) <= 100, 'Finite original feature census exceeded.')
            stack.append((wrap(feature.GetFirstSubFeature(), 'IFeature'), True))
        require(len(current_features) == len(features) and all(identity(actual) == anchor.canonical and identity(anchor.handle) == anchor.canonical
                for actual, anchor in zip(current_features, features)), 'Whole original absorbed-inclusive feature order/canonical census changed.')
        for feature, anchor in zip(current_features, features):
            pid(feature, anchor.persistent_id, anchor.canonical, 'IFeature')
            parent = wrap(feature.GetOwnerFeature(), 'IFeature')
            require((parent is None and anchor.owner_canonical is None) or parent is not None
                    and identity(parent) == anchor.owner_canonical
                    and any(original.canonical == anchor.owner_canonical for original in features),
                    'Whole original feature parent canonical membership changed; GetID is not an owner proof.')
        records = []; display_visits = 0
        for feature in current_features:
            display = wrap(feature.GetFirstDisplayDimension(), 'IDisplayDimension'); chain = []
            while display is not None:
                display_visits += 1; require(display_visits <= 400, 'Finite complete display traversal budget exceeded.')
                display_id = identity(display)
                require(not any(display_id == old for old in chain), 'Actual display traversal cycle.')
                chain.append(display_id); kind = display.GetType()
                require(type(kind) is int and kind in (2, 3, 4, 5, 6, 10, 11, 12), 'Unmeasured/unknown display enum is a producer gate, never dropped.')
                for slot in ((0, 1) if kind == 10 else (0,)):
                    dim = wrap(display.GetDimension2(slot), 'IDimension'); require(dim is not None, 'Actual native display slot missing IDimension.')
                    canonical = identity(dim); row = next((row for row in records if row[1] == canonical), None)
                    if row is None:
                        require(len(records) < 100, 'Finite complete dimension census exceeded.')
                        row = [dim, canonical, []]; records.append(row)
                    if not any(identity(old) == display_id and index == slot for old, index in row[2]): row[2].append((display, slot))
                display = wrap(feature.GetNextDisplayDimension(display), 'IDisplayDimension')
        require(len(records) == len(originals) and all(row[1] == original.canonical and identity(original.handle) == original.canonical
                for row, original in zip(records, originals)), 'Complete current dimension order/canonical census changed/replaced.')
        for row, original in zip(records, originals):
            require(type(original.display_slots) is tuple and len(row[2]) == len(original.display_slots)
                    and all(identity(display) == anchor.canonical and slot == anchor.index for (display, slot), anchor in zip(row[2], original.display_slots)),
                    'Exact complete original display/slot membership changed; no ordinal fallback.')
        return records

    def feature_summary(owner):
        error = owner.GetErrorCode2(); suppression = owner.IsSuppressed2(1, None); parent = wrap(owner.GetOwnerFeature(), 'IFeature')
        require(type(error) in (tuple, list) and len(error) == 2 and type(error[0]) is int and type(error[1]) is bool
                and type(suppression) in (tuple, list) and len(suppression) == 1 and type(suppression[0]) is bool,
                'Complete typed original owner feature summary required.')
        native_id, name, kind = owner.GetID(), owner.Name, owner.GetTypeName2()
        frozen, rolled, stamp = owner.IsFrozen(), owner.IsRolledBack(), owner.GetUpdateStamp()
        require(type(native_id) is int and type(name) is str and name and type(kind) is str and kind
                and type(frozen) is bool and type(rolled) is bool and type(stamp) is int, 'Typed actual owner feature metadata required.')
        parent_id = None if parent is None else parent.GetID(); require(parent_id is None or type(parent_id) is int, 'Typed native owner parent ID required.')
        return dict(native_id=native_id, name=name, feature_type=kind, suppressed=suppression[0], owner_native_id=parent_id,
                    error_code=error[0], is_warning=error[1] if error[0] else False, frozen=frozen, rolled_back=rolled), stamp

    def raw_row(record, original):
        dimension = record[0]; owner = wrap(dimension.GetFeatureOwner(), 'IFeature')
        require((owner is None) == (original.owner_handle is None) and (owner is None or identity(owner) == original.owner_canonical
                and identity(original.owner_handle) == original.owner_canonical), 'Original native dimension owner changed.')
        require(owner is not None or original.owner_canonical is None and original.owner_persistent_id == b'',
                'Unavailable owner must not fabricate a retained canonical/PID.')
        owner_proven = owner is not None and any(feature.canonical == original.owner_canonical for feature in features)
        owner_pid = b'' if owner is None else pid(owner, original.owner_persistent_id, original.owner_canonical, 'IFeature')
        direct = pid(dimension, original.direct_persistent_id, original.canonical, 'IDimension')
        display_info, display_receipts, anchor = [], [], None
        if owner_proven and direct: anchor = dict(strategy='direct_dimension_v1', dimension_pid_hex=direct.hex())
        for slot in original.display_slots:
            require(type(slot.index) is int and slot.index in (0, 1) and type(slot.display_type) is int
                    and slot.handle.GetType() == slot.display_type and (slot.index == 0 or slot.display_type == 10), 'Original actual display type/slot changed.')
            display_pid = pid(slot.handle, slot.persistent_id, slot.canonical, 'IDisplayDimension')
            require(identity(wrap(slot.handle.GetDimension2(slot.index), 'IDimension')) == original.canonical, 'Retained display slot no longer owns original IDimension.')
            linked, text = slot.handle.IsLinked, slot.handle.GetLinkedText()
            require(type(linked) is bool and (text is None or type(text) is str), 'Actual typed native display link data required.')
            info = dict(type=slot.display_type, linked=linked, linked_text='' if text is None else text)
            # One display can expose both chamfer slots; metadata is per display.
            if not any(identity(prior[0]) == slot.canonical for prior in display_receipts):
                display_info.append(info); display_receipts.append((slot.handle, display_pid))
            if anchor is None and owner_proven and owner_pid and display_pid:
                anchor = dict(strategy='display_dimension_v1', display_pid_hex=display_pid.hex(), dimension_index=slot.index,
                              display_type=slot.display_type, owner_pid_hex=owner_pid.hex())
        display_info.sort(key=lambda row: (row['type'], row['linked'], row['linked_text']))
        kind, driven = dimension.GetType(), dimension.DrivenState
        read_only, reference, design_table = dimension.ReadOnly, dimension.IsReference(), dimension.IsDesignTableDimension()
        require(type(kind) is int and type(driven) is int and all(type(flag) is bool for flag in (read_only, reference, design_table)), 'Typed actual dimension flags/type required.')
        values = {}
        for cfg in names:
            raw = dimension.GetSystemValue3(3, named_configuration(cfg))
            require(type(raw) in (tuple, list) and len(raw) == 1 and type(raw[0]) in (int, float) and math.isfinite(raw[0]),
                    'Actual named-configuration one-value SI array required; no active-config fallback.')
            values[cfg] = float(raw[0])
        full_name, name = dimension.FullName, dimension.Name
        require(type(full_name) is str and full_name and type(name) is str and name, 'Actual native dimension names required as facts only.')
        tol_type, tolerances = dimension.GetToleranceType(), dimension.GetToleranceValues()
        require(type(tol_type) is int and (tolerances is None or type(tolerances) in (tuple, list)), 'Actual typed native tolerance data required.')
        tolerances = [] if tolerances is None else list(tolerances)
        require((tol_type == 0 or len(tolerances) == 2) and all(type(x) in (int, float) and math.isfinite(x) for x in tolerances), 'Complete native tolerance values required.')
        blockers = []
        if kind not in (0, 1): blockers.append('unsupported_parameter_type')
        if driven != 2: blockers.append('driven_or_unknown_state')
        linked = any(row['linked'] or row['linked_text'] for row in display_info)
        for flag, label in ((read_only, 'read_only'), (reference, 'reference'), (design_table, 'design_table'), (linked, 'linked')):
            if flag: blockers.append(label)
        owner_info, owner_stamp = (None, None) if owner is None else feature_summary(owner)
        if owner is None: blockers.append('owner_unavailable')
        else:
            if owner_info['suppressed'] or owner_info['frozen'] or owner_info['rolled_back']: blockers.append('owner_suppressed_frozen_or_rolled_back')
            if owner_info['feature_type'] in ('ProfileFeature', '3DProfileFeature'): blockers.append('sketch_geometry_snapshot_not_implemented')
            elif owner_info['feature_type'] not in ('Boss', 'Extrusion', 'Cut', 'Revolve', 'RevolvCut'): blockers.append('owner_type_not_accepted')
        if any(row['type'] not in (2, 3, 4, 5, 6) for row in display_info): blockers.append('unsupported_display_semantics')
        summary = dict(full_name=full_name, name=name, parameter_type=kind, unit={0:'mm', 1:'deg'}.get(kind), values_si=values,
            values={cfg: value*1000. if kind == 0 else math.degrees(value) if kind == 1 else value for cfg, value in values.items()},
            driven_state=driven, read_only=read_only, reference=reference, design_table=design_table, linked=linked, display_dimensions=display_info,
            owner=owner_info, owner_update_stamp=owner_stamp, tolerance=dict(type=tol_type, values_si=tolerances), write_blockers=blockers, reference_anchor=anchor)
        return dict(summary=summary, reference_supported=anchor is not None,
            native_receipt=dict(direct_pid_hex=direct.hex(), owner_pid_hex=owner_pid.hex(),
                display_slots=[dict(pid_hex=slot.persistent_id.hex(), dimension_index=slot.index, display_type=slot.display_type) for slot in original.display_slots],
                original_owner_in_full_tree=owner_proven, unsupported_reason=None if anchor is not None else 'original_native_anchor_unavailable'))

    records = census(); facts = [raw_row(record, original) for record, original in zip(records, originals)]
    proofs = []
    for row, original in zip(facts, originals):
        native = ordinal(original.canonical); require(type(native) is int and native > 0, 'Positive retained canonical equality ordinal required.')
        proofs.append(dict(row, native_identity=native))
    require(len({row['native_identity'] for row in proofs}) == len(proofs), 'Canonical dimension ordinals must be injective.')
    assert_safe(context)
    closing = census(); require(facts == [raw_row(record, original) for record, original in zip(closing, originals)], 'Full raw dimension/owner/PID/slot facts changed during ordinal callbacks.')
    after = metadata(); require(before == after, 'Original current part/configuration metadata changed.')
    closing_event = watch.poll(); require(type(closing_event) is int and closing_event == event, 'Native events changed, including ABA in all callbacks/getters.')
    return dict(scope='raw_native_original_dimension_inventory_v1', rows=proofs, before=before, after=after, event_sequence=event,
                accepted=False, native_acceptance=False, cleanup_authorized=False,
                open_gates=['actual_owner_private_opaque_ID_and_full_native_session_binding', 'exact_installed_wheel_B3_driver', 'terminal_owned_cleanup'])
