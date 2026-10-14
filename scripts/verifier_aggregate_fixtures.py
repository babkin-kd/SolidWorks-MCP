"""Own repeated multi-part subassemblies; existing fixture helper stays unchanged."""
from pathlib import Path
from solidworks_mcp import binding
from verify_export_operations import activate_owned
from verifier_component_fixtures import setup_component_fixtures


def setup_aggregate_fixtures(session, owned, state, sw, module, record):
    paths = setup_component_fixtures(session, owned, state, sw, module, record)
    first, other, sub, root = owned
    activate_owned(sw, sub, sub.GetTitle());session._model = sub
    session.insert_component(str(paths[1]), x_mm=90., fixed=False)
    assert sub.ForceRebuild3(False)
    assert sub.AddConfiguration3('Вариант','','',128) is not None
    assert sub.ShowConfiguration2('Вариант')
    child = next(binding.wrap(x,module.IComponent2) for x in binding.wrap(sub,module.IAssemblyDoc).GetComponents(True) if Path(binding.wrap(x,module.IComponent2).GetPathName()).resolve() == paths[0])
    child.ReferencedConfiguration = 'Основная';assert child.ReferencedConfiguration == 'Основная'
    assert sub.ForceRebuild3(False) and sub.ShowConfiguration2('Основная')
    child = next(binding.wrap(x,module.IComponent2) for x in binding.wrap(sub,module.IAssemblyDoc).GetComponents(True) if Path(binding.wrap(x,module.IComponent2).GetPathName()).resolve() == paths[0])
    assert child.ReferencedConfiguration == 'Вариант'
    assert sub.ForceRebuild3(False);session.save_assembly(str(paths[2]));record(owned)
    activate_owned(sw, root, root.GetTitle());session._model = root
    assert root.ForceRebuild3(False)
    session.insert_component(str(paths[2]), x_mm=250., fixed=False)
    assert root.ForceRebuild3(False);record(owned)
    native = [binding.wrap(x, module.IComponent2) for x in binding.wrap(root, module.IAssemblyDoc).GetComponents(False)]
    assert len(native) == 9
    subs = [c for c in native if Path(c.GetPathName()).resolve() == paths[2]]
    assert len(subs) == 2 and all(c.ReferencedConfiguration == 'Основная' for c in subs)
    # One hidden leaf must participate in the aggregate-to-aggregate minimum.
    # Choose the cylinder under the FIRST subassembly by its full native root transform.
    candidates = [c for c in native if '/' in c.Name2 and Path(c.GetPathName()).resolve() == paths[1]]
    hidden = next(c for c in candidates if abs(binding.wrap(c.GetTotalTransform(False), module.IMathTransform).ArrayData[9]-.19) < 1e-9)
    hidden.Visible = 0;assert hidden.IsHidden(False) is True
    assert root.ForceRebuild3(False);record(owned)
    return paths
