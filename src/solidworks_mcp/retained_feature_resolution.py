"""Resolve an already owned feature while suppressed, never a topology fallback.

The caller retains the original canonical IUnknown and separately checks the
explicit document/configuration and execution revision. This bridge changes
neither generic PID resolution nor public feature reference admission.
"""
from .documents import rejected


def resolve_retained_feature_pid(adapter, model, persistent_id, retained_identity):
    if (type(persistent_id) is not bytes or not persistent_id
            or retained_identity is None):
        raise rejected('retained_feature_binding_required',
            'Original feature PID bytes and a retained native canonical identity are required.')
    try:
        feature = adapter.resolve_persistent_id(model, persistent_id, 'feature')
    except Exception as error:
        if getattr(error, 'code', None) != 'object_suppressed':
            raise
        raw, status = adapter._extension(model).GetObjectByPersistReference3(
            adapter._persistent_variant(persistent_id))
        if (type(status) is not int or status != 2 or raw is None
                or adapter.identity(raw) != retained_identity):
            raise rejected('retained_feature_resolution_unconfirmed',
                'Suppressed PID must return the exact retained raw native feature; no null fallback.')
        candidates = [feature for feature in adapter.features(model)
                      if adapter.persistent_id(model, feature) == persistent_id]
        if len(candidates) != 1 or adapter.identity(candidates[0]) != retained_identity:
            raise rejected('retained_feature_resolution_unconfirmed',
                'Original PID must bind exactly one current retained feature in the complete census.')
        feature = candidates[0]
        suppressed = feature.IsSuppressed2(1, None)
        if (type(suppressed) not in (list, tuple) or len(suppressed) != 1
                or suppressed[0] is not True):
            raise rejected('retained_feature_resolution_unconfirmed',
                'Raw state2 must agree with current-configuration native suppression True.')
    if (feature is None or adapter.identity(feature) != retained_identity
            or adapter.persistent_id(model, feature) != persistent_id):
        raise rejected('retained_feature_resolution_unconfirmed',
            'The resolved feature must retain its original canonical identity and exact PID.')
    return feature
