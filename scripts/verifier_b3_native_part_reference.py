"""Raw native I02 reference observer; no connection, dispatch or cleanup.

The owner supplies retained original handles/identities and an actual private
opaque-ID binding. This observer supports solid/surface bodies, plane faces,
line edges of the finite I02 fixture. Whole-session/namespace/ownership proof
stays with the driver; these raw receipts never constitute native acceptance.
"""
from dataclasses import dataclass
import math

from verifier_b3_part_geometry import _context, _canonical


@dataclass(frozen=True)
class RetainedPartReference:
    object_id: str
    kind: str
    handle: object
    canonical: object
    persistent_id: bytes


def require(condition, message):
    if not condition:
        raise ValueError(message)


def numbers(values, size):
    require(type(values) in (list, tuple) and len(values) == size
            and all(type(x) in (int, float) and math.isfinite(x) for x in values), 'Complete finite raw native numbers required.')
    return [float(x) for x in values]


def capture_native_part_reference(*, context, item, model, model_canonical,
        configuration_canonical, binding, owner_body, wrap, identity, persistent_variant,
        original_body_census, ordinal, watch, assert_safe):
    """Direct CAD getters, original retained membership, bracketed notifications.

wrap(raw, interface_name), identity(raw), persistent_variant(bytes), ordinal
and assert_safe(context) are provided by the original owning STA. Binding IDs
must come from actual reference registration, not name/path/shape inference.
owner_body is binding itself for a body, otherwise its retained current body.
    original_body_census retains every original normal-body canonical anchor;
    even an unreported extra body must invalidate this finite fixture scope.
No adapter.geometry_summary or public DTO is used as the native oracle.
"""
    context = _context(context)
    require(isinstance(binding, RetainedPartReference) and isinstance(owner_body, RetainedPartReference)
            and binding.kind in ('body', 'face', 'edge') and owner_body.kind == 'body'
            and item['object_id'] == binding.object_id and item['kind'] == binding.kind
            and item.get('body_id') == (None if binding.kind == 'body' else owner_body.object_id),
            'Actual original private namespace binding/owner required.')
    for ref in (binding, owner_body):
        require(type(ref.persistent_id) is bytes and ref.persistent_id, 'Original retained native PID required.')
    require(type(original_body_census) in (tuple, list) and 0 < len(original_body_census) <= 100,
            'Complete original body canonical census required.')
    assert_safe(context)
    event_before = watch.poll()
    require(type(event_before) is int and event_before >= 0, 'Actual complete native event sequence required.')
    require(all(sum(anchor == other for other in original_body_census) == 1
                for anchor in original_body_census), 'Distinct original body canonical anchors required.')
    def metadata():
        cfg = wrap(model.GetActiveConfiguration(), 'IConfiguration')
        require(identity(model) == model_canonical and identity(cfg) == configuration_canonical
                and cfg.Name == context['configuration'], 'Current original model/active configuration incarnation required.')
        stamp, dirty = model.GetUpdateStamp(), model.GetSaveFlag()
        require(type(stamp) is int and type(dirty) is bool and type(cfg.Name) is str, 'Typed native metadata required.')
        return dict(update_stamp=stamp, needs_save=dirty, configuration=cfg.Name)
    before = metadata()
    extension = wrap(model.Extension, 'IModelDocExtension')
    resolved, state = extension.GetObjectByPersistReference3(persistent_variant(binding.persistent_id))
    require(type(state) is int and state == 0 and resolved is not None
            and identity(resolved) == binding.canonical and identity(binding.handle) == binding.canonical,
            'Actual original PID must resolve to the retained original canonical object.')
    require(bytes(extension.GetPersistReference3(binding.handle)) == binding.persistent_id,
            'Current native PID differs from the retained I02 anchor.')
    part = wrap(model, 'IPartDoc')
    bodies = [wrap(raw, 'IBody2') for raw in (part.GetBodies2(-1, False) or ())]
    current_bodies = [identity(body) for body in bodies]
    require(len(current_bodies) == len(original_body_census)
            and all(sum(current == original for current in current_bodies) == 1
                    for original in original_body_census), 'Whole original normal-body census changed or is incomplete.')
    require(sum(identity(body) == owner_body.canonical for body in bodies) == 1
            and identity(owner_body.handle) == owner_body.canonical, 'Exactly one current original owner body required.')
    obj = binding.handle
    if binding.kind == 'body':
        require(binding.canonical == owner_body.canonical, 'Original body binding must own itself.')
        kind = obj.GetType()
        require(type(kind) is int and kind in (0, 1), 'Only original normal solid/surface supported.')
        box = numbers(obj.GetBodyBox(), 6)
        faces, edges = obj.GetFaces() or (), obj.GetEdges() or ()
        require(type(obj.Name) is str, 'Actual native body name required.')
        summary = dict(body_type='solid' if kind == 0 else 'surface', name=obj.Name,
            face_count=len(faces), edge_count=len(edges), bounding_box_mm=dict(
                min_mm=[x*1000. for x in box[:3]], max_mm=[x*1000. for x in box[3:]], approximate=True))
        require(obj.GetFaceCount() == len(faces) and obj.GetEdgeCount() == len(edges), 'Full native body census differs.')
    else:
        require(identity(wrap(obj.GetBody(), 'IBody2')) == owner_body.canonical, 'Actual native topology owner differs.')
        members = owner_body.handle.GetFaces() if binding.kind == 'face' else owner_body.handle.GetEdges()
        require(sum(identity(raw) == binding.canonical for raw in members or ()) == 1, 'Original topology must be a current owner member.')
        if binding.kind == 'face':
            surface = wrap(obj.GetSurface(), 'ISurface')
            require(surface is not None and surface.IsPlane() is True, 'Finite I02 observer requires an actual plane face.')
            area = numbers([obj.GetArea()], 1)[0]*1e6
            require(area > 0, 'Positive actual native face area required.')
            summary = dict(area_mm2=area, surface_type='plane', edge_count=len(obj.GetEdges() or ()))
        else:
            curve = wrap(obj.GetCurve(), 'ICurve')
            params = obj.GetCurveParams2()
            curve_kind = None if curve is None else curve.Identity()
            require(curve is not None and type(curve_kind) is int and curve_kind == 3001
                    and type(params) in (list, tuple) and len(params) >= 8, 'Finite I02 observer requires an actual line edge.')
            data = numbers(list(params[:8]), 8)
            length = numbers([curve.GetLength3(data[6], data[7])], 1)[0]*1000.
            require(length > 0, 'Positive actual native edge length required.')
            summary = dict(curve_type='line', length_mm=length,
                start_mm=[x*1000. for x in data[:3]], end_mm=[x*1000. for x in data[3:6]])
    require(_canonical(summary) == _canonical({key: value for key, value in item.items()
        if key not in ('object_id', 'kind', 'body_id')}), 'Public facts differ from direct native getters.')
    native_ordinal, body_ordinal = ordinal(binding.canonical), ordinal(owner_body.canonical)
    require(all(type(x) is int and x > 0 for x in (native_ordinal, body_ordinal)), 'Retained canonical equality ordinals required.')
    after = metadata()
    require(before == after and watch.poll() == event_before, 'Native model/configuration/events changed during reference observation.')
    assert_safe(context)
    return dict(scope='raw_native_retained_part_reference_v1', object_id=binding.object_id,
        kind=binding.kind, persistent_id=binding.persistent_id.hex(), native_identity=native_ordinal,
        owner_body_native_identity=body_ordinal, native_summary=summary,
        before=before, after=after, event_sequence=event_before,
        accepted=False, native_acceptance=False, cleanup_authorized=False)
