"""Owned native assembly fixtures: repeated configs, nested paths, hidden BREP and curves."""
import math,uuid
from pathlib import Path
from solidworks_mcp import binding
from solidworks_mcp.constants import SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE
from verify_export_operations import activate_owned


def setup_component_fixtures(session,owned,state,sw,module,record):
    """Called only with empty-source ownership established and owned setup flag True."""
    assert len(owned)==2 and sw.CommandInProgress is True
    first,other=owned
    activate_owned(sw,first,first.GetTitle());session._model=first
    assert first.ShowConfiguration2('Вариант')
    feature=next(f for f in session._iter_features() if f.Name=='Контрольный блок 2')
    assert feature.SetSuppression2(0,1,None) and first.ForceRebuild3(False)
    assert first.ShowConfiguration2('Основная') and first.ForceRebuild3(False)
    solids=[binding.wrap(x,module.IBody2) for x in binding.wrap(first,module.IPartDoc).GetBodies2(0,False)]
    hidden=max(solids,key=lambda x:x.GetBodyBox()[0]);hidden.HideBody(True);assert hidden.Visible is False
    # The other owned part becomes an independently known curved BREP, not a
    # second copy of the same planar fixture. Its old box stays suppressed.
    activate_owned(sw,other,other.GetTitle());session._model=other
    feature=next(f for f in session._iter_features() if f.Name=='Контрольный чужой блок')
    assert feature.SetSuppression2(0,1,None) and other.ForceRebuild3(False)
    preference=sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)
    sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE,False)
    assert sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE) is False
    try:session.add_cylinder(12.,30.,name='Контрольный цилиндр топологии')
    finally:
        sw.SetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE,preference)
        assert sw.GetUserPreferenceToggle(SW_TOGGLE_INPUT_DIM_VAL_ON_CREATE)==preference
    for index,feature in enumerate(session._iter_features()):
        if feature.GetTypeName2() in ('RefPlane','ProfileFeature'):
            name=('Контрольная плоскость ' if feature.GetTypeName2()=='RefPlane' else 'Контрольный эскиз ')+str(index)
            feature.Name=name;assert feature.Name==name
    assert other.ForceRebuild3(False)
    bodies=[binding.wrap(x,module.IBody2) for x in binding.wrap(other,module.IPartDoc).GetBodies2(-1,False)]
    assert len(bodies)==1 and bodies[0].GetType()==0
    bodies[0].Name='Контрольное тело цилиндра';assert bodies[0].Name=='Контрольное тело цилиндра'
    assert math.isclose(bodies[0].GetMassProperties(1.)[3]*1e9,math.pi*6.**2*30.,rel_tol=1e-9)
    paths=[state/'Контрольная деталь.sldprt',state/'Контрольный цилиндр.sldprt',state/'Контрольная подсборка.sldasm']
    for model,path in zip((first,other),paths):
        activate_owned(sw,model,model.GetTitle());session._model=model;session.save_part(str(path));record(owned)
        assert Path(model.GetPathName()).resolve()==path
    session.new_assembly();sub=session._model;owned.append(sub);record(owned)
    assert sub.SetTitle2('Контрольная подсборка '+uuid.uuid4().hex[:8]);record(owned)
    binding.wrap(sub.GetActiveConfiguration(),module.IConfiguration).Name='Основная'
    session.insert_component(str(paths[0]),x_mm=30.,fixed=False)
    child=binding.wrap(binding.wrap(sub,module.IAssemblyDoc).GetComponents(False)[0],module.IComponent2)
    child.ReferencedConfiguration='Вариант';assert child.ReferencedConfiguration=='Вариант'
    assert sub.ForceRebuild3(False);session.save_assembly(str(paths[2]));record(owned)
    session.new_assembly();asm=session._model;owned.append(asm);record(owned)
    assert asm.SetTitle2('Контрольная сборка топологии '+uuid.uuid4().hex[:8]);record(owned)
    binding.wrap(asm.GetActiveConfiguration(),module.IConfiguration).Name='Основная'
    assert asm.AddConfiguration3('Вариант','','',128) is not None
    for path,x in ((paths[0],0.),(paths[0],50.),(paths[2],100.),(paths[1],150.)):
        session.insert_component(str(path),x_mm=x,fixed=False)
    top=[binding.wrap(x,module.IComponent2) for x in binding.wrap(asm,module.IAssemblyDoc).GetComponents(True)]
    target=next(c for c in top if Path(c.GetPathName()).resolve()==paths[0] and math.isclose(binding.wrap(c.Transform2,module.IMathTransform).ArrayData[9],.05))
    target.ReferencedConfiguration='Вариант';assert target.ReferencedConfiguration=='Вариант'
    session._apply_transform(target,50.,10.,20.,0.,0.,90.)
    target.Visible=0;assert target.IsHidden(False) is True
    assert asm.ForceRebuild3(False);record(owned)
    return paths
