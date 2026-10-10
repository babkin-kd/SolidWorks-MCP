"""Capture-local binding reduction plus independent late native proof; no CAD."""

from copy import copy
from types import SimpleNamespace

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.linear_sketch import LinearSketchReader, SketchEntityBinder
from test_linear_sketch_v2 import Point, Sketch


def make_binder(sketch, coalesce):
    items=sketch.points+[sketch.origin,sketch.projected]+sketch.lines
    for i,item in enumerate(items):item.pid=str(i).encode()
    current={item.pid:item for item in items}
    calls={'reference':0,'resolve':0}
    def reference(obj):
        calls['reference']+=1
        return obj.pid
    def resolve(pid,name):
        calls['resolve']+=1
        return current[pid]
    binder=SketchEntityBinder(wrap=lambda raw,name:raw,reference=reference,resolve=resolve,identity=id,coalesce=coalesce)
    return binder,current,calls


def capture(sketch,coalesce):
    binder,current,calls=make_binder(sketch,coalesce)
    result,members=LinearSketchReader(sketch,binder(sketch.origin,'ISketchPoint'),wrap=binder,identity=id).read()
    binder.close()
    return result,members,calls


def test_repeated_native_bindings_are_reduced_without_changing_full_capture_or_members():
    sketch=Sketch()
    plain,plain_members,plain_calls=capture(sketch,False)
    cached,cached_members,cached_calls=capture(sketch,True)
    assert cached==plain and cached_members==plain_members
    assert cached_calls['reference']<plain_calls['reference']
    assert cached_calls['resolve']<plain_calls['resolve']
    # Ten distinct persistent entities, each resolved at entry and closing.
    assert cached_calls['resolve']==20


@pytest.mark.parametrize('fault',['retarget','pid','owner','coordinates','status','bool_type','id'])
def test_closing_proof_catches_event_free_change_after_cached_alias_was_read(fault):
    sketch=Sketch();binder,current,_=make_binder(sketch,True)
    point=sketch.points[0]
    assert binder(point,'ISketchPoint') is point
    if fault=='retarget':current[point.pid]=copy(point)
    if fault=='pid':point.pid=b'retargeted'
    if fault=='owner':point.owner=object()
    if fault=='coordinates':point.X=.001
    if fault=='status':point.Status=1
    if fault=='bool_type':point.Type=False
    if fault=='id':point.number=9
    # A previously observed canonical interface is reused only until closing.
    assert binder(point,'ISketchPoint') is point
    with pytest.raises(ExecutionFailure):binder.close()


def test_alternate_interface_is_validated_even_when_native_pid_was_already_resolved():
    sketch=Sketch();binder,_,_=make_binder(sketch,True)
    point=sketch.points[0]
    binder(point,'ISketchPoint')
    alternate=copy(point)
    assert binder(alternate,'ISketchPoint') is point
    foreign=copy(point);foreign.X=.001
    with pytest.raises(ExecutionFailure):binder(foreign,'ISketchPoint')


def test_geometry_changes_between_alternate_bind_and_close_cannot_be_hidden_by_cache():
    sketch=Sketch();binder,_,_=make_binder(sketch,True)
    point=sketch.points[0]
    binder(point,'ISketchPoint')
    alternate=copy(point)
    binder(alternate,'ISketchPoint')
    point.X=.001
    with pytest.raises(ExecutionFailure):binder.close()


def test_cache_never_survives_one_closed_capture():
    sketch=Sketch();binder,_,calls=make_binder(sketch,True)
    binder(sketch.points[0],'ISketchPoint');binder.close()
    old=dict(calls)
    with pytest.raises(ExecutionFailure):binder(sketch.points[0],'ISketchPoint')
    with pytest.raises(ExecutionFailure):binder.close()
    assert calls==old


def test_distinct_capture_revalidates_reference_even_for_same_retained_native_object():
    sketch=Sketch();first,_,_=make_binder(sketch,True)
    first(sketch.points[0],'ISketchPoint');first.close()
    second,_,calls=make_binder(sketch,True)
    second(sketch.points[0],'ISketchPoint');second.close()
    assert calls['resolve']==2 and calls['reference']==3
