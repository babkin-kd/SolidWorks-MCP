"""Actual binding reader through native-shaped getters; no CAD writes/connection."""
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp import binding
from solidworks_mcp.cad_rectangle_annotation_views import rectangle_annotation_view_bindings as read
from solidworks_mcp.jobs import ExecutionFailure
from rectangle_view_fixtures import view_data


class Extension:
    def __init__(self,adapter):self.adapter=adapter
    @property
    def AnnotationViewCount(self):return len(self.adapter.views)
    @property
    def AnnotationViews(self):
        self.adapter.reads+=1
        if self.adapter.changed and self.adapter.reads==2:return self.adapter.views[:-1]
        return self.adapter.views[:]


@pytest.fixture
def native(monkeypatch):
    monkeypatch.setattr(binding,'wrap',lambda raw,interface:raw)
    a=NS(model=object(),views=[],dimensions=[],reads=0,changed=False)
    a._module=NS(IAnnotationView=object,IAnnotation=object)
    data,ignored=view_data({'width','height'})
    def make(row):
        return NS(Always2D=row['always_2d'],FlatPatternView=row['flat_pattern'],UnassignedView=row['unassigned'],
            IsShown=lambda:row['shown'],AngleMadeWithViewHorizontal=float.fromhex(row['angle']),
            GetViewRotation=lambda:[float.fromhex(v) for v in row['rotation']],AnnotationCount=row['annotation_count'],
            GetAnnotations2=lambda x,y:None)
    a.views=[make(row) for row in data]
    for axis in ('width','height'):
        annotation=NS(AnnotationView=a.views[1])
        a.dimensions.append(NS(full_name=axis,displays=[NS(GetAnnotation=lambda obj=annotation:obj)]))
    extension=Extension(a)
    a.identity=id;a._extension=lambda model:extension
    a.features=lambda model:[];a.snapshot=lambda model:{'active_configuration':'Основная'}
    a.dimension_summary=lambda dimension,cfg:{'full_name':dimension.full_name}
    a.dimension_rows=a.dimensions;a.dimensions=lambda model,features:a.dimension_rows
    return a,dict(lights=[],annotation_views=data),{'width':'width','height':'height'}


def test_reader_binds_actual_dimension_annotations_to_stable_observed_view_incarnations(native):
    a,data,roles=native
    first=read(a,a.model,data,roles);second=read(a,a.model,data,roles)
    assert first==second
    assert first['view_ids'][0]!=first['view_ids'][1]
    assert set(first['dimension_views'].values())=={first['view_ids'][1]}
    assert all(type(v) is str and len(v)==35 for v in first['view_ids'])


def test_scalar_identical_replacement_view_gets_a_new_observation_identity(native):
    a,data,roles=native
    first=read(a,a.model,data,roles)
    a.views[0]=NS(**vars(a.views[0]))
    second=read(a,a.model,data,roles)
    assert first['view_ids'][0]!=second['view_ids'][0]
    assert first['view_ids'][1]==second['view_ids'][1]


@pytest.mark.parametrize('fault',['duplicate_view','missing_member','foreign_owner','no_annotation',
    'empty_displays','mixed_views','unknown_axis','metadata_change','nonempty_view','closing_change',
    'boolean_count','budget'])
def test_missing_changing_foreign_or_partial_native_data_is_refused(native,fault):
    a,data,roles=native
    if fault=='duplicate_view':a.views[0]=a.views[1]
    elif fault=='missing_member':a.views.pop()
    elif fault=='foreign_owner':a.dimension_rows[0].displays[0].GetAnnotation=lambda:NS(AnnotationView=object())
    elif fault=='no_annotation':a.dimension_rows[0].displays[0].GetAnnotation=lambda:None
    elif fault=='empty_displays':a.dimension_rows[0].displays=[]
    elif fault=='mixed_views':a.dimension_rows[0].displays.append(NS(GetAnnotation=lambda:NS(AnnotationView=a.views[0])))
    elif fault=='unknown_axis':roles.pop('width')
    elif fault=='metadata_change':a.views[1].IsShown=lambda:True
    elif fault=='nonempty_view':a.views[1].GetAnnotations2=lambda x,y:[object()]
    elif fault=='closing_change':a.changed=True
    elif fault=='boolean_count':a.views[1].AnnotationCount=False
    else:a._rectangle_view_incarnations=[(object(),[]) for _ in range(1000)]
    with pytest.raises(ExecutionFailure):read(a,a.model,data,roles)
