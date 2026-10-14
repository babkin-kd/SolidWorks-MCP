"""Independent bounded I01 feature tree getters on an already owned STA.

No connection, mutation, public DTO oracle, ownership adoption or cleanup.
The original driver retains every feature in traversal order before reads.
"""
from dataclasses import dataclass

from verifier_b3_native_document_metadata import capture_native_document_metadata, require


@dataclass(frozen=True)
class RetainedFeature:
    handle: object
    canonical: object
    persistent_id: bytes
    owner_canonical: object = None


def capture_native_feature_inventory(*, context, document, originals, wrap,
        identity, ordinal, persistent_variant, watch, assert_safe):
    """Exact original feature census, raw summaries and direct PID roundtrips.

Empty original PID is truthful unsupported reference evidence. A formerly
supported PID becoming invalid fails this unchanged fixture observation.
GetID is traversal duplicate detection only; canonical/PID bind identity.
Dimension inventories and whole-session/SDK namespace gates remain separate.
"""
    require(type(context) is dict and set(context) == {'document_id', 'configuration'}
            and type(originals) in (tuple, list) and 0 < len(originals) <= 100
            and all(isinstance(x, RetainedFeature) and type(x.persistent_id) is bytes for x in originals),
            'Explicit original part context and complete retained feature census required.')
    assert_safe(context)
    event = watch.poll()
    require(type(event) is int and event >= 0, 'Typed native event sequence required.')
    require(all(sum(x.canonical == y.canonical for y in originals) == 1 for x in originals),
            'Distinct original feature canonical anchors required.')

    def metadata():
        observed = capture_native_document_metadata(**context, binding=document,
            wrap=wrap, identity=identity, ordinal=ordinal, watch=watch, assert_safe=assert_safe)
        require(observed['metadata']['configuration_is_active'] is True,
                'Feature inventory requires the original active configuration; no switch.')
        return observed['metadata']

    before = metadata()
    model = document.model
    extension = wrap(model.Extension, 'IModelDocExtension')

    def census():
        queue = [(wrap(model.FirstFeature(), 'IFeature'), False)]
        seen, links, rows = {}, set(), []
        steps = 0
        while queue:
            feature, sub = queue.pop()
            if feature is None:
                continue
            steps += 1
            require(steps <= 400, 'Finite native traversal budget exceeded; no partial census.')
            native_id = feature.GetID()
            require(type(native_id) is int, 'Typed native feature ID required.')
            canonical = identity(feature)
            prior = seen.get(native_id)
            require(prior is None or prior == canonical, 'Native feature ID collision.')
            link = (native_id, sub)
            if link in links:
                continue
            links.add(link)
            raw_next = feature.GetNextSubFeature() if sub else feature.GetNextFeature()
            queue.append((wrap(raw_next, 'IFeature'), sub))
            if prior is not None:
                continue
            require(len(rows) < 100, 'Finite original feature budget exceeded.')
            seen[native_id] = canonical
            rows.append(feature)
            queue.append((wrap(feature.GetFirstSubFeature(), 'IFeature'), True))
        require(len(rows) == len(originals)
                and all(identity(current) == original.canonical and identity(original.handle) == original.canonical
                        for current, original in zip(rows, originals)),
                'Complete current feature order/canonical membership differs from original.')
        return rows

    current = census()
    def raw_row(feature, original):
        actual_pid = extension.GetPersistReference3(feature)
        pid = b'' if actual_pid is None else bytes(actual_pid)
        require(pid == original.persistent_id, 'Current feature PID differs from original retained anchor.')
        if pid:
            resolved, state = extension.GetObjectByPersistReference3(persistent_variant(pid))
            require(type(state) is int and state == 0 and resolved is not None
                    and identity(wrap(resolved, 'IFeature')) == original.canonical,
                    'Original state0 feature PID must resolve to the same canonical feature.')
        else:
            state = None
        owner = wrap(feature.GetOwnerFeature(), 'IFeature')
        owner_id = None
        if owner is not None:
            require(original.owner_canonical is not None and identity(owner) == original.owner_canonical
                    and sum(x.canonical == original.owner_canonical for x in originals) == 1,
                    'Actual owner must be its original retained feature in the full census.')
            owner_id = owner.GetID()
            require(type(owner_id) is int, 'Typed native owner ID required.')
        else:
            require(original.owner_canonical is None, 'Original feature owner disappeared.')
        error = feature.GetErrorCode2()
        suppression = feature.IsSuppressed2(1, None)
        name, kind, native_id = feature.Name, feature.GetTypeName2(), feature.GetID()
        require(type(error) in (tuple, list) and len(error) == 2
                and type(error[0]) is int and type(error[1]) is bool
                and type(suppression) in (tuple, list) and len(suppression) == 1 and type(suppression[0]) is bool
                and type(name) is str and name and type(kind) is str and kind and type(native_id) is int,
                'Complete typed raw native feature summary required.')
        return dict(summary=dict(native_id=native_id, name=name, feature_type=kind,
            suppressed=suppression[0], owner_native_id=owner_id, error_code=error[0],
            is_warning=error[1] if error[0] else False),
            reference_supported=bool(pid), native_receipt=dict(persistent_id_hex=pid.hex(),
                resolution_state=state, original_owner_present=owner is not None))
    raw = [raw_row(feature, original) for feature, original in zip(current, originals)]
    proofs = []
    for facts, original in zip(raw, originals):
        native_ordinal = ordinal(original.canonical)
        require(type(native_ordinal) is int and native_ordinal > 0, 'Positive original canonical equality ordinal required.')
        proofs.append(dict(facts, native_identity=native_ordinal))
    require(len({x['native_identity'] for x in proofs}) == len(proofs), 'Canonical ordinal mapping is not injective.')
    closing_features = census()
    require(raw == [raw_row(feature, original) for feature, original in zip(closing_features, originals)],
            'Current native PID/owner/feature facts changed during callbacks.')
    after = metadata()
    require(before == after, 'Original part/configuration metadata changed during inventory.')
    assert_safe(context)
    closing = watch.poll()
    require(type(closing) is int and closing == event, 'Native events changed, including ABA during getters/ordinals.')
    return dict(scope='raw_native_original_feature_inventory_v1', rows=proofs,
                before=before, after=after, event_sequence=event,
                accepted=False, native_acceptance=False, cleanup_authorized=False)
