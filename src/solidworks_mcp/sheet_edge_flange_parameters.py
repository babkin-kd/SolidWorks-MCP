"""Pure explicit native edge-flange option contract; no COM imports."""

import math

def flange_options(definition):
    return dict(UseDefaultBendRadius=False,BendRadius=definition.bend_radius_mm/1000.,
        GapDistance=.001,BendAngle=math.pi/2.,LockAngle=True,OffsetType=1,
        OffsetDistance=definition.flange_length_mm/1000.,OffsetDimType=1,
        PositionType=1,UsePositionOffset=False,ReverseOffset=False,
        UseDefaultBendAllowance=False,UseDefaultBendRelief=True)


def native_flange_parameters_match(parameters,definition):
    """Strict complete readback, never inferred from CreateFeature/rebuild."""
    try:
        expected=flange_options(definition)
        if set(parameters)!= {*expected,'allowance_type','k_factor','edge_count'}:return False
        for name,value in expected.items():
            actual=parameters[name]
            if type(value) in (bool,int):
                if type(actual) is not type(value) or actual!=value:return False
            elif type(actual) not in (float,int) or not math.isfinite(actual) or not math.isclose(actual,value,rel_tol=0.,abs_tol=1e-12):return False
        return (type(parameters['allowance_type']) is int and parameters['allowance_type']==2
            and type(parameters['edge_count']) is int and parameters['edge_count']==1
            and type(parameters['k_factor']) in (float,int) and math.isfinite(parameters['k_factor'])
            and math.isclose(parameters['k_factor'],definition.k_factor,rel_tol=0.,abs_tol=1e-12))
    except (KeyError,TypeError,ValueError):return False


