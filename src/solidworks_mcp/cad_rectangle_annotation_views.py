"""Passive native view incarnations bound through each current dimension annotation.

Opaque COM identities stay on the owning STA. Server observation IDs describe
view incarnations only; they are not user-selectable CAD or persistent references.
"""
import uuid

from . import binding
from .documents import rejected
from .cad_native_first_save_snapshot import _array,_typed,_number


def rectangle_annotation_view_bindings(adapter,model,display,dimension_roles):
    fail=lambda message:rejected('rectangle_annotation_view_unsupported',message)
    extension=adapter._extension(model)
    native=_array(extension.AnnotationViews,16)
    if len(native)!=extension.AnnotationViewCount or len(native)!=len(display['annotation_views']):
        raise fail('Native views must match the complete display inventory.')
    cache=getattr(adapter,'_rectangle_view_incarnations',None)
    if cache is None:cache=[];adapter._rectangle_view_incarnations=cache
    model_token=adapter.identity(model)
    records=[rows for token,rows in cache if token==model_token]
    if len(records)>1:raise fail('Model view incarnation collision.')
    if records:records=records[0]
    else:
        if len(cache)>=1000:raise fail('View observation model budget exceeded.')
        records=[];cache.append((model_token,records))
    views=[];identities=[];ids=[]
    for raw,row in zip(native,display['annotation_views']):
        view=binding.wrap(raw,adapter._module.IAnnotationView)
        token=adapter.identity(view)
        if token in identities:raise fail('View canonical identities must be unique.')
        values=dict(always_2d=_typed(view.Always2D,bool),flat_pattern=_typed(view.FlatPatternView,bool),
            unassigned=_typed(view.UnassignedView,bool),shown=_typed(view.IsShown(),bool),
            angle=_number(view.AngleMadeWithViewHorizontal),rotation=[_number(v) for v in _array(view.GetViewRotation(),9)],
            annotation_count=_typed(view.AnnotationCount,int))
        if values!=row or _array(view.GetAnnotations2(False,False),128):
            raise fail('Only fully observed empty annotation views are supported.')
        matches=[identifier for old,identifier in records if old==token]
        if len(matches)>1:raise fail('View observation identity collision.')
        if not matches:
            if len(records)>=64:raise fail('Replaced view observation budget exceeded.')
            identifier='av_'+uuid.uuid4().hex;records.append((token,identifier))
        else:identifier=matches[0]
        views.append(view);identities.append(token);ids.append(identifier)
    axes={}
    features=adapter.features(model)
    for dimension in adapter.dimensions(model,features):
        summary=adapter.dimension_summary(dimension,[adapter.snapshot(model)['active_configuration']])
        axis=dimension_roles.get(summary['full_name'])
        if axis not in ('width','height','depth') or axis in axes:
            raise fail('Each exact current dimension requires one declared geometric axis.')
        links=[]
        for native_display in dimension.displays:
            annotation=binding.wrap(native_display.GetAnnotation(),adapter._module.IAnnotation)
            if annotation is None:raise fail('An exact current dimension annotation is required.')
            owner=binding.wrap(annotation.AnnotationView,adapter._module.IAnnotationView)
            if owner is None:raise fail('Every driving dimension must bind an actual annotation view.')
            token=adapter.identity(owner)
            matched=[i for i,current in enumerate(identities) if current==token]
            if len(matched)!=1:raise fail('Dimension annotation view is outside the complete native inventory.')
            links.append(ids[matched[0]])
            # Re-query to reject changing annotations/views inside this read.
            if adapter.identity(annotation.AnnotationView)!=token:
                raise fail('Dimension annotation view changed during observation.')
        if not links or len(set(links))!=1:raise fail('All displays of a dimension must have one exact view.')
        axes[axis]=links[0]
    if set(axes)!=set(dimension_roles.values()):raise fail('Complete dimension/view membership is required.')
    closing=_array(extension.AnnotationViews,16)
    if (extension.AnnotationViewCount!=len(native) or len(closing)!=len(native)
            or any(adapter.identity(raw)!=old for raw,old in zip(closing,identities))):
        raise fail('Native view membership changed during the passive capture.')
    return dict(scope='native_rectangle_annotation_view_bindings_v1',view_ids=ids,dimension_views=axes)
