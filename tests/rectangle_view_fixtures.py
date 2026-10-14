"""Explicit artificial native-view evidence; not CAD acceptance."""
from copy import deepcopy


def view_data(axes):
    row=dict(always_2d=False,angle=0..hex(),annotation_count=0,flat_pattern=False,
        rotation=[float(v).hex() for v in (1,0,0,0,1,0,0,0,1)],shown=True,unassigned=True)
    views=[row];ids=['av_'+'a'*32];links={}
    if 'width' in axes:
        views.append({**deepcopy(row),'shown':False,'unassigned':False});ids.append('av_'+'b'*32)
        links.update(width=ids[-1],height=ids[-1])
    if 'depth' in axes:
        views.append({**deepcopy(row),'shown':False,'unassigned':False});ids.append('av_'+'c'*32)
        links['depth']=ids[-1]
    return views,dict(scope='native_rectangle_annotation_view_bindings_v1',view_ids=ids,dimension_views=links)


def bind_artificial_views(snapshot,axes):
    views,binding=view_data(axes)
    snapshot['clone_state']['display_data']['annotation_views']=views
    snapshot['native_observations']['annotation_view_bindings']=binding
    return snapshot
