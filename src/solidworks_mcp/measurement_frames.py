"""Explicit rigid measurement axes: p_model_mm = origin_mm + axes * p_frame_mm."""
import math
from pydantic import BaseModel,ConfigDict,StrictFloat,model_validator
from .documents import rejected

IDENTITY=((1.,0.,0.),(0.,1.,0.),(0.,0.,1.))


class RigidMeasurementFrame(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    origin_mm:tuple[StrictFloat,StrictFloat,StrictFloat]
    axes_in_model:tuple[tuple[StrictFloat,StrictFloat,StrictFloat],
        tuple[StrictFloat,StrictFloat,StrictFloat],tuple[StrictFloat,StrictFloat,StrictFloat]]

    @model_validator(mode='after')
    def rigid(self):
        values=(*self.origin_mm,*(x for axis in self.axes_in_model for x in axis))
        if not all(math.isfinite(value) for value in values):raise ValueError('Frame values must be finite.')
        for i,a in enumerate(self.axes_in_model):
            for j,b in enumerate(self.axes_in_model):
                if abs(sum(x*y for x,y in zip(a,b))-(1. if i==j else 0.))>1e-10:
                    raise ValueError('Frame axes must be unit and orthogonal; no scale or shear.')
        a,b,c=self.axes_in_model
        determinant=a[0]*(b[1]*c[2]-b[2]*c[1])-a[1]*(b[0]*c[2]-b[2]*c[0])+a[2]*(b[0]*c[1]-b[1]*c[0])
        if abs(determinant-1.)>1e-10:raise ValueError('Frame must be right-handed; no reflection.')
        return self


def measurement_frame(value):
    if value is None:return RigidMeasurementFrame(origin_mm=(0.,0.,0.),axes_in_model=IDENTITY)
    try:return RigidMeasurementFrame.model_validate(value)
    except (TypeError,ValueError) as exc:raise rejected('invalid_measurement_frame','Explicit finite rigid axes/origin are required.') from exc


def project_point_m(frame,point_m):
    if (type(point_m) not in (tuple,list) or len(point_m)!=3
            or any(type(x) not in (int,float) or not math.isfinite(x) for x in point_m)):
        raise rejected('invalid_extreme_point','Native extreme point must be three finite SI values.')
    result=[sum(a*x for a,x in zip(axis,point_m))*1000.
            -sum(a*x for a,x in zip(axis,frame.origin_mm)) for axis in frame.axes_in_model]
    if not all(math.isfinite(x) for x in result):raise rejected('measurement_numeric_overflow','Projected bounds overflowed.')
    return result
