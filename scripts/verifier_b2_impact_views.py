"""Passive exact four-dimension N5 view binding, no CAD connection or setters.

Only width/height/depth and one caller-proven own-plane offset are supported.
The existing production empty display/annotation getters remain unchanged.
View observation IDs use the same live adapter cache as the production getter.
"""
import uuid

from solidworks_mcp.jobs import _json


AXES={'width','height','depth','plane_offset'}
# Documented swDimensionType_e: linear=2, horizontal linear=11, vertical=12.
# https://help.solidworks.com/2021/english/api/swconst/SolidWorks.Interop.swconst~SolidWorks.Interop.swconst.swDimensionType_e.html
LINEAR_TYPES={2,11,12}


def _require(condition,message):
    if not condition:raise ValueError('N5 current view binding: '+message)


def impact_annotation_view_bindings(adapter,model,display,dimension_roles,*,configuration,features,dimensions):
    """Bind four current native records, displays, annotations and empty views.

The owner supplies PID/created-plane authorization separately. Names classify
already retained records; they never resolve or adopt a native dimension/view.
No fifth dimension, replaced DIM, unsupported enum or nonempty view is ignored.
"""
    from solidworks_mcp import binding
    from solidworks_mcp.cad_native_first_save_snapshot import _array,_typed,_number
    from solidworks_mcp.rectangle_annotation_views import validated_view_bindings
    _require(type(dimensions) in (tuple,list) and len(dimensions)==4,'Exactly four retained records required.')
    _require(type(dimension_roles) is dict and len(dimension_roles)==4
        and set(dimension_roles.values())==AXES,'Exactly one declared record per supported axis required.')
    extension=adapter._extension(model)
    native=_array(extension.AnnotationViews,16)
    count=_typed(extension.AnnotationViewCount,int)
    _require(1<=count<=16 and len(native)==count and len(display['annotation_views'])==count,
             'Complete bounded native display-view inventory required.')
    model_identity=adapter.identity(model)
    cache=getattr(adapter,'_rectangle_view_incarnations',None)
    if cache is None:cache=[];adapter._rectangle_view_incarnations=cache
    _require(type(cache) is list and len(cache)<=1000,'Bounded existing view observation cache required.')
    matches=[rows for token,rows in cache if token==model_identity]
    _require(len(matches)<=1,'Model canonical view cache collision.')
    if matches:records=matches[0]
    else:
        _require(len(cache)<1000,'Live model view observation budget exceeded.')
        records=[];cache.append((model_identity,records))
    ids=[];view_identities=[]
    for raw,row in zip(native,display['annotation_views']):
        view=binding.wrap(raw,adapter._module.IAnnotationView)
        _require(view is not None,'A current native annotation view is required.')
        identity=adapter.identity(view)
        _require(identity is not None and not any(identity==prior for prior in view_identities),
                 'View canonical identities must be unique.')
        values=dict(always_2d=_typed(view.Always2D,bool),flat_pattern=_typed(view.FlatPatternView,bool),
            unassigned=_typed(view.UnassignedView,bool),shown=_typed(view.IsShown(),bool),
            angle=_number(view.AngleMadeWithViewHorizontal),rotation=[_number(value) for value in _array(view.GetViewRotation(),9)],
            annotation_count=_typed(view.AnnotationCount,int))
        _require(values==row and values['annotation_count']==0 and not _array(view.Annotations,128)
            and not _array(view.GetAnnotations2(False,False),128),'Only completely measured empty views are supported.')
        identifiers=[identifier for token,identifier in records if token==identity]
        _require(len(identifiers)<=1,'View observation identity collision.')
        if identifiers:identifier=identifiers[0]
        else:
            _require(len(records)<64,'Replaced native view observation budget exceeded.')
            identifier='av_'+uuid.uuid4().hex;records.append((identity,identifier))
        ids.append(identifier);view_identities.append(identity)

    dim_identities=[adapter.identity(adapter.dimension_object(record)) for record in dimensions]
    _require(all(identity is not None and not any(identity==previous for previous in dim_identities[:index])
        for index,identity in enumerate(dim_identities)),'Retained dimension canonical identities must be distinct.')
    current=adapter.dimensions(model,features)
    _require(type(current) in (tuple,list) and len(current)==4,'Current complete native DIM census must contain exactly four.')
    current_identities=[adapter.identity(adapter.dimension_object(record)) for record in current]
    _require(all(sum(identity==other for other in current_identities)==1 for identity in dim_identities),
             'Current DIM census replaced or omitted a retained dimension.')
    def display_membership(record):
        displays=_array(record.displays,16);slots=_array(record.display_slots,16)
        identities=[adapter.identity(raw) for raw in displays]
        _require(bool(identities) and len(identities)==len(slots)
            and all(identity is not None and not any(identity==old for old in identities[:index])
                    for index,identity in enumerate(identities)),
            'Complete unique current native display membership required.')
        result=[]
        for identity in identities:
            matched=[slot for raw,slot in slots if adapter.identity(raw)==identity]
            _require(len(matched)==1 and type(matched[0]) is int and matched[0]==0,
                     'Each current linear display must bind exactly slot zero.')
            result.append((identity,matched[0]))
        return result
    memberships=[display_membership(record) for record in dimensions]
    def same_memberships(values):
        for identity,expected in zip(dim_identities,memberships):
            matches=[record for record in values if adapter.identity(adapter.dimension_object(record))==identity]
            _require(len(matches)==1,'One current record per retained DIM canonical required.')
            actual=display_membership(matches[0])
            _require(len(actual)==len(expected) and all(sum(token==other and slot==other_slot
                for other,other_slot in actual)==1 for token,slot in expected),
                'Current display/slot census replaced or omitted a retained DIM alias.')
    same_memberships(current)
    axes={};closing_displays=[]
    for record,dim_identity in zip(dimensions,dim_identities):
        summary=adapter.dimension_summary(record,[configuration])
        axis=dimension_roles.get(summary['full_name'])
        _require(axis in AXES and axis not in axes,'Every retained DIM needs exactly one declared axis.')
        dimension=adapter.dimension_object(record)
        owner=binding.wrap(dimension.GetFeatureOwner(),adapter._module.IFeature)
        owner_identity=adapter.identity(owner) if owner is not None else None
        _require(record.owner is not None and owner_identity is not None
            and owner_identity==adapter.identity(record.owner)==record.owner_tree_identity,
            'Native DIM owner must be the exact retained original feature/own new plane.')
        displays=_array(record.displays,16);slots=_array(record.display_slots,16)
        _require(bool(displays) and len(displays)==len(slots),'Complete direct display-slot membership required.')
        links=[];seen=[]
        for raw in displays:
            view_dimension=binding.wrap(raw,adapter._module.IDisplayDimension)
            _require(view_dimension is not None,'Actual current display dimension required.')
            display_identity=adapter.identity(view_dimension)
            _require(not any(display_identity==old for old in seen),'Duplicate native display membership.')
            seen.append(display_identity)
            matched=[index for display_object,index in slots if adapter.identity(display_object)==display_identity]
            _require(len(matched)==1 and type(matched[0]) is int and matched[0]==0,
                     'Only one exact documented linear DIM slot zero is supported.')
            code=view_dimension.GetType()
            _require(type(code) is int and code in LINEAR_TYPES and (axis!='plane_offset' or code==2),
                     'Only documented linear displays; plane offset requires linear type 2.')
            native_dimension=binding.wrap(view_dimension.GetDimension2(0),adapter._module.IDimension)
            _require(native_dimension is not None and adapter.identity(native_dimension)==dim_identity,
                     'Display slot must point to the retained exact IDimension.')
            annotation=binding.wrap(view_dimension.GetAnnotation(),adapter._module.IAnnotation)
            _require(annotation is not None and type(annotation.GetType()) is int and annotation.GetType()==4,
                     'Only a normally returned native display-dimension annotation is supported.')
            annotation_identity=adapter.identity(annotation)
            specific=binding.wrap(annotation.GetSpecificAnnotation(),adapter._module.IDisplayDimension)
            _require(specific is not None and adapter.identity(specific)==display_identity,
                     'Annotation must bind the exact current native display dimension.')
            annotation_view=binding.wrap(annotation.AnnotationView,adapter._module.IAnnotationView)
            view_identity=adapter.identity(annotation_view) if annotation_view is not None else None
            matches=[index for index,identity in enumerate(view_identities) if identity==view_identity]
            _require(len(matches)==1,'DIM annotation owner view is outside the complete current inventory.')
            links.append(ids[matches[0]])
            closing_displays.append((record,view_dimension,display_identity,dim_identity,annotation_identity,view_identity,owner_identity,code))
        _require(len(set(links))==1,'One DIM cannot borrow displays belonging to different views.')
        axes[axis]=links[0]
    _require(set(axes)==AXES,'Complete four-axis annotation membership required.')
    for record,view_dimension,display_identity,dim_identity,annotation_identity,view_identity,owner_identity,code in closing_displays:
        annotation=binding.wrap(view_dimension.GetAnnotation(),adapter._module.IAnnotation)
        native_dimension=binding.wrap(view_dimension.GetDimension2(0),adapter._module.IDimension)
        _require(annotation is not None and native_dimension is not None
            and adapter.identity(annotation)==annotation_identity and adapter.identity(native_dimension)==dim_identity
            and adapter.identity(annotation.AnnotationView)==view_identity
            and adapter.identity(annotation.GetSpecificAnnotation())==display_identity
            and adapter.identity(native_dimension.GetFeatureOwner())==owner_identity
            and type(view_dimension.GetType()) is int and view_dimension.GetType()==code,
            'Current display/DIM/owner/annotation/view association changed while collecting.')
    closing=_array(extension.AnnotationViews,16)
    _require(type(extension.AnnotationViewCount) is int and extension.AnnotationViewCount==count and len(closing)==count
        and all(adapter.identity(raw)==identity for raw,identity in zip(closing,view_identities)),
        'Current complete native view census changed while collecting.')
    closing_dims=adapter.dimensions(model,features)
    _require(type(closing_dims) in (tuple,list) and len(closing_dims)==4
        and all(sum(adapter.identity(adapter.dimension_object(record))==identity for record in closing_dims)==1
                for identity in dim_identities),'Complete native DIM membership changed during view capture.')
    same_memberships(closing_dims)
    result=dict(scope='native_rectangle_annotation_view_bindings_v1',view_ids=ids,dimension_views=axes)
    validated_view_bindings(display,result,AXES)
    _json(result)
    return result
