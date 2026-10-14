"""Passive part bounds via native support points, never an approximate body box."""
import math
from .documents import rejected
from .geometry import GeometryCatalog
from .measurement_frames import measurement_frame,project_point_m

SCOPE='part_native_support_bounds_v1'


class BoundsMeasurementCatalog(GeometryCatalog):
    def _bodies(self,entry,configuration,identity,body_id,body_type):
        if body_id is None:bodies=tuple(self.adapter.bodies(entry.model,body_type))
        else:bodies=(self._resolve(entry,body_id,configuration,identity,'body')[0],)
        if not bodies:raise rejected('no_measurable_bodies','No bodies in the explicit measurement scope.')
        if len(bodies)>500:raise rejected('bounds_scope_budget_exceeded','Bounds support at most 500 bodies.')
        result=[]
        for body in bodies:
            kind=self.adapter.measurement_body_type(body)
            if body_type!='all' and kind!=body_type:
                raise rejected('unsupported_body_type','Explicit body does not match the requested body type.')
            ref=self._register(entry,body,'body',configuration,identity)
            result.append((ref.persistent_id.hex(),self.adapter.identity(body),kind,ref.object_id,body))
        result.sort(key=lambda item:item[0])
        if len({row[0] for row in result})!=len(result):
            raise rejected('bounds_body_roster_ambiguous','Body roster has duplicate native references.')
        return result

    def _extents(self,bodies,frame):
        result=[]
        for _,_,_,_,body in bodies:
            low=[];high=[]
            for i,axis in enumerate(frame.axes_in_model):
                points=[self.adapter.measurement_extreme_point(body,tuple(sign*x for x in axis)) for sign in (-1.,1.)]
                minimum,maximum=(project_point_m(frame,point)[i] for point in points)
                span=sum(a*(maximum_point-minimum_point) for a,minimum_point,maximum_point in zip(axis,*points))*1000.
                if not math.isclose(maximum-minimum,span,rel_tol=1e-10,abs_tol=1e-8):
                    raise rejected('measurement_precision_lost','Frame translation loses significant extent precision.')
                if minimum>maximum:
                    if minimum-maximum>1e-8:raise rejected('invalid_extreme_bounds','Native extreme bounds are reversed.')
                    minimum=maximum=(minimum+maximum)/2.
                low.append(minimum);high.append(maximum)
            result.append((low,high))
        return result

    def measure(self,document_id,configuration,expected_observation_revision,*,body_id=None,
                body_type='all',coordinate_frame=None):
        if body_type not in ('all','solid','surface'):raise rejected('invalid_geometry_query','Body type must be all/solid/surface.')
        frame=measurement_frame(coordinate_frame)
        entry,observed,identity=self._context(document_id,configuration,expected_observation_revision)
        bodies=self._bodies(entry,configuration,identity,body_id,body_type)
        values=self._extents(bodies,frame)
        self._confirm(entry,observed,configuration,identity)
        closing=self._bodies(entry,configuration,identity,body_id,body_type)
        if [row[:4] for row in bodies]!=[row[:4] for row in closing]:
            raise rejected('bounds_body_roster_changed','Native body membership changed during the read.')
        repeated=self._extents(closing,frame)
        if not all(math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-8)
                for first,second in zip(values,repeated) for xs,ys in zip(first,second) for a,b in zip(xs,ys)):
            raise rejected('bounds_changed_during_read','Support bounds changed during the read.')
        self._confirm(entry,observed,configuration,identity)
        low=[min(item[0][i] for item in values) for i in range(3)]
        high=[max(item[1][i] for item in values) for i in range(3)]
        sizes=[b-a for a,b in zip(low,high)]
        if not all(math.isfinite(x) for x in sizes):raise rejected('measurement_numeric_overflow','Bounds size overflowed.')
        return dict(document_id=document_id,configuration=configuration,observation_revision=observed['observation_revision'],
            body_id=body_id,body_ids=[row[3] for row in bodies],body_type=body_type,body_count=len(bodies),
            includes_hidden_bodies=True,measurement_scope=SCOPE,length_unit='mm',model_geometry_modified=False,
            coordinate_frame=dict(kind='model' if coordinate_frame is None else 'explicit_rigid',**frame.model_dump(mode='json')),
            bounding_box_mm=dict(min_mm=low,max_mm=high,size_mm=sizes),
            method='native_extreme_points',approximate_body_box_used=False,
            read_postconditions=dict(body_membership_confirmed=True,repeated_extrema_confirmed=True))
