"""Passive current ancillary reads for trusted N5 owner census, no BASE clone.

The caller retains model/config/body/features/dimensions and brackets this read
with real identity/event/session captures. This collector does not connect, write,
clear selection, rebuild, authorize cleanup or certify a full refusal context.
All observations come from actual current getters, never a creation baseline.
"""
from copy import deepcopy
import json
import math

from solidworks_mcp.jobs import _json


SCOPE='owned_b2_impact_current_ancillary_v1'
AXES={'width','height','depth'}


class AncillaryGate(ValueError):
    code='impact_ancillary_unavailable'
    def __init__(self,field,message):
        self.field=field
        super().__init__(field+': '+message)


def _require(condition,field,message):
    if not condition:raise AncillaryGate(field,message)


def _read(field,callback):
    try:return callback()
    except AncillaryGate:raise
    except Exception as error:
        raise AncillaryGate(field,'Actual current native getter is unavailable: '+str(error)) from error


def _text(value,field):
    _require(type(value) is str and '\0' not in value and len(value)<=16384,field,'Bounded exact native string required.')
    return value


def _material(value,field):
    _require(type(value) is tuple and len(value)==2,field,'Complete material-name/database tuple required.')
    return [_text(item,field) for item in value]


def collect_impact_ancillary(adapter,model,*,configuration,features,summaries,dimensions,
                             dimension_roles,references,body):
    """Read current ancillary data using the installed production getters.

dimension_roles: exact qualified native full_name -> width/height/depth. Only the
three original current dimension records are supported. Fourth plane-offset
dimension/unknown annotations/nonempty annotation views raise a concrete gate.
references: current owner-declared refs BEFORE annotation collection; a detached
copy gains actual annotation refs. Nothing in the caller's containers is changed.
body: exact current native solid retained by the caller's complete target census.
The return carries source data and negative acceptance flags only; it cannot
replace the caller's full target/session/identity/watch before-after oracle.
"""
    from solidworks_mcp import binding
    from solidworks_mcp.cad_native_first_save_snapshot import (
        _properties,_configuration,_empty_auxiliary_data,_display_data,_annotations,_array)
    from solidworks_mcp.cad_rectangle_annotation_views import rectangle_annotation_view_bindings
    from solidworks_mcp.rectangle_annotation_views import validated_view_bindings

    _text(configuration,'configuration')
    _require(bool(configuration),'configuration','Explicit current configuration required.')
    _require(type(features) in (tuple,list) and type(summaries) in (tuple,list)
        and 0<len(features)==len(summaries)<=64,'features','Exact complete owner feature rows required.')
    _require(type(dimensions) in (tuple,list) and len(dimensions)==3,'dimensions',
             'Three exact original dimensions required; new plane-offset dimensions have no supported view-binding axis.')
    _require(type(dimension_roles) is dict and len(dimension_roles)==3
        and set(dimension_roles.values())==AXES,'dimension_roles','Exact qualified width/height/depth role map required.')
    for name in dimension_roles:_text(name,'dimension_roles')
    _require(type(references) is list and all(type(row) is dict for row in references),
             'references','Detached current owner reference rows required.')
    _require(all(row.get('kind')!='annotation' for row in references),'references',
             'Pass current references before annotations; existing annotation rows cannot be reused as observations.')
    native_summaries=_read('dimensions',lambda:[adapter.dimension_summary(record,[configuration]) for record in dimensions])
    names=_read('dimension_roles',lambda:[_text(summary['full_name'],'dimension_roles') for summary in native_summaries])
    _require(len(set(names))==3 and set(names)==set(dimension_roles),'dimension_roles',
             'Owner role map must match all three actual current dimension names.')
    retained=_read('dimensions',lambda:[adapter.identity(adapter.dimension_object(record)) for record in dimensions])
    _require(all(token is not None for token in retained)
        and all(not any(token==previous for previous in retained[:index]) for index,token in enumerate(retained)),
        'dimensions','Original dimension canonical identities must be distinct.')
    current_refs=deepcopy(references)
    result={}
    result['properties']=_read('properties',lambda:_properties(adapter,model,configuration))
    result['configuration_state']=_read('configuration_state',lambda:_configuration(adapter,model,configuration))
    result['auxiliary_data']=_read('auxiliary_data',lambda:_empty_auxiliary_data(adapter,model,features,summaries))
    result['display_data']=_read('display_data',lambda:_display_data(adapter,model,features,summaries))
    result['annotations']=_read('annotations',lambda:_annotations(adapter,model,dimensions,current_refs))
    result['annotation_view_bindings']=_read('annotation_view_bindings',
        lambda:rectangle_annotation_view_bindings(adapter,model,result['display_data'],dimension_roles))
    _read('annotation_view_bindings',lambda:validated_view_bindings(result['display_data'],
            result['annotation_view_bindings'],AXES))
    # The installed view getter independently enumerates current dimensions.
    # Recheck membership against the caller-retained three; names never adopt a
    # fourth/replaced dimension whose metadata happens to have the same text.
    current=_read('dimensions',lambda:adapter.dimensions(model,features))
    _require(type(current) in (tuple,list) and len(current)==3,'dimensions',
             'Actual current dimension census contains unsupported or missing records.')
    identities=_read('dimensions',lambda:[adapter.identity(adapter.dimension_object(record)) for record in current])
    _require(all(sum(token==other for other in identities)==1 for token in retained),'dimensions',
             'Current view-read census must retain the exact original dimension canonical identities.')
    _require(body is not None,'body','Caller must retain the exact current solid body.')
    body_type=_read('body',lambda:body.GetType())
    _require(type(body_type) is int and body_type==0 and _read('body',lambda:body.IsMeshBody()) is False,
             'body','Actual native solid nonmesh body required.')
    part=_read('material',lambda:binding.wrap(model,adapter._module.IPartDoc))
    result['material']=_read('material',lambda:_material(part.GetMaterialPropertyName2(configuration),'material'))
    result['body_material']=_read('body_material',lambda:_material(body.GetMaterialPropertyName(configuration),'body_material'))
    visible=_read('body',lambda:body.Visible)
    _require(type(visible) is bool,'body','Exact current body visibility required.')
    result['body']=dict(name=_read('body',lambda:_text(body.Name,'body')),visible=visible)
    units=_read('units',lambda:_array(model.GetUnits(),16))
    _require(bool(units) and all(type(value) in (int,float,bool)
        and (type(value) is bool or math.isfinite(value)) for value in units),'units',
        'Complete nonempty finite native units array required.')
    result['units']=units
    controls=_read('creation_controls',lambda:adapter.part_creation_controls(model))
    _require(type(controls) is dict and set(controls)=={'add_to_db','auto_solve','display_when_added','dimension_input'}
        and all(type(value) is bool for value in controls.values()),'creation_controls',
        'Complete typed actual creation controls required.')
    result['creation_controls']=controls
    result['references']=current_refs
    detached=_read('serialization',lambda:json.loads(_json(result)))
    return dict(scope=SCOPE,data=detached,accepted=False,native_b2_accepted=False,public_mcp_accepted=False)
