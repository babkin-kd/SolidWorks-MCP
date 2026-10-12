"""No CAD; native bindings are declared artificial evidence."""
from copy import deepcopy
import pytest
from solidworks_mcp.rectangle_annotation_views import verified_new_sketch_view


@pytest.fixture
def evidence():
    row=dict(always_2d=False,angle=0..hex(),annotation_count=0,flat_pattern=False,
        rotation=[float(x).hex() for x in (1,0,0,0,1,0,0,0,1)],shown=True,unassigned=True)
    before=dict(lights=[{'unchanged':'all native light data'}],annotation_views=[row])
    after=deepcopy(before);after['annotation_views'].append({**deepcopy(row),'shown':False,'unassigned':False})
    old=dict(scope='native_rectangle_annotation_view_bindings_v1',view_ids=['av_'+'a'*32],dimension_views={})
    new=deepcopy(old);new['view_ids'].append('av_'+'b'*32);new['dimension_views']={'width':'av_'+'b'*32,'height':'av_'+'b'*32}
    return before,after,old,new


def test_one_new_view_requires_preserved_native_incarnations_and_both_owned_dimension_bindings(evidence):
    assert verified_new_sketch_view(*evidence)


@pytest.mark.parametrize('fault',['missing_bindings','foreign_view','split_views','baseline_changed','lights',
    'baseline_replaced','duplicate_id','missing_view','extra_view','nonempty_view','shown','unassigned',
    'bad_rotation','unknown_field','boolean_count','opaque'])
def test_scalar_lookalike_foreign_or_incomplete_view_never_admits_creation(evidence,fault):
    before,after,old,new=evidence
    if fault=='missing_bindings':new['dimension_views']={}
    elif fault=='foreign_view':new['dimension_views']={'width':'av_'+'c'*32,'height':'av_'+'c'*32}
    elif fault=='split_views':new['dimension_views']['height']=old['view_ids'][0]
    elif fault=='baseline_changed':after['annotation_views'][0]['shown']=False
    elif fault=='lights':after['lights']=[]
    elif fault=='baseline_replaced':new['view_ids'][0]='av_'+'c'*32
    elif fault=='duplicate_id':new['view_ids'][1]=new['view_ids'][0]
    elif fault=='missing_view':after['annotation_views'].pop()
    elif fault=='extra_view':after['annotation_views'].append(deepcopy(after['annotation_views'][1]))
    elif fault=='nonempty_view':after['annotation_views'][1]['annotation_count']=1
    elif fault in ('shown','unassigned'):after['annotation_views'][1][fault]=True
    elif fault=='bad_rotation':after['annotation_views'][1]['rotation'][0]='nan'
    elif fault=='unknown_field':after['annotation_views'][1]['foreign']='unknown'
    elif fault=='boolean_count':after['annotation_views'][1]['annotation_count']=False
    else:new['view_ids'][1]=object()
    assert not verified_new_sketch_view(before,after,old,new)
