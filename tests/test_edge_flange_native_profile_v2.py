"""Actual bridge reader on artificial API-shaped objects; no SolidWorks calls."""
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.cad_sheet_edge_flange import CadSheetEdgeFlangeMixin,NativeEdgeFlangeReceipt
from solidworks_mcp.jobs import ExecutionFailure
from test_edge_flange_sketch_v2 import profile
from test_part_creation_v2 import IDENTITY


@pytest.fixture
def native_profile(profile,monkeypatch):
    from solidworks_mcp import binding
    monkeypatch.setattr(binding,'wrap',lambda raw,interface:raw)
    sketch,ghost,edge,definition=profile
    a=CadSheetEdgeFlangeMixin();a.identity=id
    interfaces=('IFeature','ISketch','ISketchPoint','ISketchSegment','ISketchLine','IDisplayDimension','IDimension',
        'IEdge','IBody2','IVertex','IConfiguration','IMathTransform','ISketchRelationManager','ISketchRelation')
    a._module=NS(**{name:object for name in interfaces});a._named_configuration=lambda name:[name]
    plane=object();sketch.GetReferenceEntity=lambda option:(plane,4)
    sketch.ModelToSketchTransform=NS(ArrayData=[0.,1.,0.,0.,0.,1.,1.,0.,0.,0.,-.002,-.02,1.,0.,0.,0.])
    feature=NS(GetSpecificFeature2=lambda:sketch,GetID=lambda:60,GetTypeName2=lambda:'ProfileFeature')
    body=object();edge=NS(GetBody=lambda:body)
    sketch.relations[0].definitions=[edge,sketch.lines[0]]
    model=NS(GetActiveConfiguration=lambda:NS(Name='Основная'))
    driver=sketch.relations[-1].display.GetDimension2(0)
    driver.GetSystemValue3=lambda how,names:[.013]
    driver.GetType=lambda:0;driver.DrivenState=2;driver.ReadOnly=False
    driver.IsReference=lambda:False;driver.IsDesignTableDimension=lambda:False;driver.GetToleranceType=lambda:0
    pairs=[(b'feature',feature),(b'edge',edge),(b'body',body)]
    pairs.extend((('point_'+str(i)).encode(),p) for i,p in enumerate(sketch.points))
    pairs.extend((('line_'+str(i)).encode(),p) for i,p in enumerate([*sketch.lines,ghost]))
    refs=dict(pairs);a.persistent_id=lambda model,obj:next(pid for pid,f in pairs if f is obj)
    a.resolve_persistent_id=lambda model,pid,kind:refs[pid]
    a.same_persistent_id=lambda model,p,q:p==q;a._persistent_variant=lambda value:value
    a._extension=lambda model:NS(GetObjectByPersistReference3=lambda pid:(refs[pid],0))
    a._sheet_state_target_current=lambda *args:None
    a._sheet_flange_edge_current=lambda *args:edge
    a._sheet_flange_profile_edge_current=lambda *args:edge
    a.pattern_edge_points=lambda e:((.002,.02,0.),(.002,.02,.03))
    receipt=NativeEdgeFlangeReceipt(NS(body_pid=b'body'),{},edge,id(edge),b'edge',(),{},
        sketch=feature,sketch_identity=id(feature),sketch_pid=b'feature',native_sketch=sketch,
        driver=driver,driver_identity=id(driver))
    return a,model,receipt,definition,sketch,refs,plane,ghost


@pytest.mark.parametrize('phase',['before_factory','after_factory'])
def test_bridge_checks_full_profile_native_driver_and_closing_anonymous_plane(native_profile,phase):
    a,model,receipt,definition,sketch,_,_,ghost=native_profile
    if phase=='after_factory':
        receipt.flange=object();sketch.relations[0].definitions=[ghost,sketch.lines[0]]
    snapshot,members=a.sheet_flange_sketch_snapshot(model,receipt,definition,IDENTITY,phase)
    assert snapshot['driver_value_si']==float(.013).hex()
    assert snapshot['prepared_edge_pid_hex']==b'edge'.hex()
    assert dict(members)['dimension:'+receipt.driver.FullName]==id(receipt.driver)


@pytest.mark.parametrize('defect',['wrong_value','foreign_driver','reference','read_only','design_table','driven',
    'wrong_unit','linked','linked_text','tolerance','partial_value','nonfinite','plane_changed','transform_changed','source_retarget'])
def test_profile_status_and_coordinates_do_not_override_driver_or_reference_failure(native_profile,defect):
    a,model,receipt,definition,sketch,refs,plane,_=native_profile
    driver=receipt.driver
    if defect=='wrong_value':driver.GetSystemValue3=lambda *args:[.015]
    elif defect=='foreign_driver':receipt.driver_identity=1
    elif defect=='reference':driver.IsReference=lambda:True
    elif defect=='read_only':driver.ReadOnly=True
    elif defect=='design_table':driver.IsDesignTableDimension=lambda:True
    elif defect=='driven':driver.DrivenState=1
    elif defect=='wrong_unit':driver.GetType=lambda:1
    elif defect=='linked':sketch.relations[-1].display.IsLinked=True
    elif defect=='linked_text':sketch.relations[-1].display.GetLinkedText=lambda:'external'
    elif defect=='tolerance':driver.GetToleranceType=lambda:1
    elif defect=='partial_value':driver.GetSystemValue3=lambda *args:[]
    elif defect=='nonfinite':driver.GetSystemValue3=lambda *args:[float('nan')]
    elif defect=='plane_changed':
        calls=[]
        def reference(option):
            calls.append(True);return (plane if len(calls)==1 else object(),4)
        sketch.GetReferenceEntity=reference
    elif defect=='transform_changed':
        def change(*args):sketch.ModelToSketchTransform.ArrayData[11]=-.021;return [.013]
        driver.GetSystemValue3=change
    else:refs[b'edge']=object()
    with pytest.raises(ExecutionFailure):a.sheet_flange_sketch_snapshot(model,receipt,definition,IDENTITY,'before_factory')
