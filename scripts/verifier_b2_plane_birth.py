"""Bind a normally returned InsertRefPlane object before any later mutation.

No CAD connection, selection cleanup, rebuild, mutation or PID synthesis. The
original owner supplies complete ordered pre/post feature censuses under its
guard/watch. This narrow birth receipt never proves full fixture acceptance.
"""
from dataclasses import dataclass

E_NOINTERFACE = -2147467262


@dataclass(frozen=True)
class OriginalFeature:
    handle: object
    canonical: object


@dataclass(frozen=True)
class RetainedPlaneBirth:
    feature: object
    feature_canonical: object
    evidence: dict


def require(condition, message):
    if not condition:
        raise ValueError(message)


def bind_returned_plane(returned, originals, current_features, query, wrap, identity, *, diagnostic=None):
    """Resolve only the normally returned raw object, never a guessed tree row.

query(raw, 'IFeature'|'IRefPlane') explicitly QueryInterfaces. Only an exact
E_NOINTERFACE on the first query permits the specific-plane path; unknown
HRESULTs propagate unchanged. wrap(raw,'IFeature') types owner-enumerated tree
members. Canonical equality must be actual retained IUnknown equality.
OriginalFeature holds the complete original feature order/strong canonicals.
The sole new feature may occur anywhere in current order, but every original
must occur exactly once in its unchanged relative order. Native complete-census
capture/owner admission/transition watch and all subsequent graph/PID/readback
checks remain with the owner. Retain the returned feature immediately; a later
GetSpecificFeature2 interface may differ after normally returned rebuild.
diagnostic, if provided, is a caller-owned plain dict of scalar comparisons.
It preserves partial observations on failure without additional native getters,
fallbacks, acceptance or cleanup authority. The owner persists it separately.
"""
    require(diagnostic is None or type(diagnostic) is dict, 'Plain owner diagnostic dict required.')
    if diagnostic is not None:
        diagnostic.clear()
        diagnostic.update(scope='returned_plane_binding_diagnostic_v1', accepted=False,
                          native_acceptance=False, cleanup_authorized=False, phase='admission')

    def note(**values):
        if diagnostic is not None: diagnostic.update(values)

    require(returned is not None and type(originals) in (tuple, list) and 0 < len(originals) <= 100
            and all(isinstance(original, OriginalFeature) for original in originals)
            and type(current_features) in (tuple, list) and len(current_features) == len(originals)+1
            and all(callable(callback) for callback in (query, wrap, identity)),
            'Normally returned object and original complete bounded feature censuses required.')
    originals = tuple(originals)
    raw_canonical = identity(returned)

    def census():
        require(len(current_features) == len(originals)+1
                and all(identity(original.handle) == original.canonical for original in originals)
                and all(sum(original.canonical == other.canonical for other in originals) == 1 for original in originals),
                'Every original retained feature canonical must remain distinct/unchanged.')
        members = [wrap(raw, 'IFeature') for raw in current_features]
        require(all(member is not None for member in members), 'Complete current typed feature members required.')
        canonicals = [identity(member) for member in members]
        require(all(sum(current == other for other in canonicals) == 1 for current in canonicals)
                and all(sum(current == original.canonical for current in canonicals) == 1 for original in originals),
                'Original full feature membership changed, replaced or duplicated.')
        old_order = [current for current in canonicals if any(current == original.canonical for original in originals)]
        require(all(current == original.canonical for current, original in zip(old_order, originals)),
                'Original complete feature order changed.')
        additions = [(member, canonical) for member, canonical in zip(members, canonicals)
                     if not any(canonical == original.canonical for original in originals)]
        require(len(additions) == 1, 'Exactly one new current native feature required; no last/name/GetID adoption.')
        feature, canonical = additions[0]
        kind = feature.GetTypeName2()
        require(type(kind) is str and kind == 'RefPlane', 'Sole new native feature must actually be a reference plane.')
        return feature, canonical

    feature, feature_canonical = census()
    note(phase='feature_query', raw_equals_current_feature=raw_canonical == feature_canonical)
    try:
        queried = query(returned, 'IFeature')
    except Exception as error:
        note(feature_query_hresult=getattr(error, 'hresult', None), feature_query_returned=False)
        if getattr(error, 'hresult', None) != E_NOINTERFACE:
            raise
        queried = query(returned, 'IRefPlane')
        queried_canonical = identity(queried) if queried is not None else None
        note(phase='specific_query', specific_query_nonnull=queried is not None,
             specific_query_equals_raw=queried is not None and queried_canonical == raw_canonical)
        require(queried is not None and queried_canonical == raw_canonical,
                'Queried specific-plane interface must preserve raw returned canonical identity.')
        raw_specific = feature.GetSpecificFeature2()
        require(raw_specific is not None, 'New feature must provide its actual normally current specific plane.')
        specific = query(raw_specific, 'IRefPlane')
        specific_canonical = identity(specific) if specific is not None else None
        current_raw_canonical = identity(raw_specific)
        note(phase='specific_comparison', current_specific_nonnull=specific is not None,
             current_specific_query_preserves_canonical=specific is not None and specific_canonical == current_raw_canonical,
             current_specific_equals_raw=specific is not None and specific_canonical == raw_canonical)
        require(specific is not None and specific_canonical == current_raw_canonical
                and specific_canonical == raw_canonical,
                'Sole new feature specific-plane canonical must equal the actual returned plane canonical.')
        path = 'returned_specific_plane_v1'
    else:
        queried_canonical = identity(queried) if queried is not None else None
        note(phase='feature_comparison', feature_query_returned=True, queried_feature_nonnull=queried is not None,
             raw_equals_queried_feature=queried is not None and queried_canonical == raw_canonical,
             queried_feature_equals_current_feature=queried is not None and queried_canonical == feature_canonical)
        require(queried is not None and queried_canonical == raw_canonical and queried_canonical == feature_canonical,
                'Queried feature must be the actual returned canonical and the sole new current feature.')
        path = 'returned_feature_v1'
    closing, closing_canonical = census()
    require(closing_canonical == feature_canonical and identity(feature) == feature_canonical
            and identity(closing) == feature_canonical and identity(returned) == raw_canonical,
            'Actual returned/new/original feature canonicals changed during binding.')
    note(phase='bound', interface_path=path, binding_confirmed=True)
    return RetainedPlaneBirth(feature, feature_canonical, dict(scope='normally_returned_plane_birth_binding_v1',
        interface_path=path, original_feature_count=len(originals), current_feature_count=len(current_features),
        accepted=False, native_acceptance=False, cleanup_authorized=False,
        open_gates=['actual_owner_complete_census_admission_and_transition_watch',
                    'current_PID_parent_child_and_full_fixture_postconditions']))
