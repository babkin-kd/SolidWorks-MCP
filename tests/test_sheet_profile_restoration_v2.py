"""Synthetic deletion transitions reject any unproved residual state."""

from contextlib import nullcontext
from copy import deepcopy
from types import SimpleNamespace

import pytest

from solidworks_mcp.jobs import ExecutionFailure
from test_sheet_profile_ownership_v2 import setup,Feature


def scenario(monkeypatch,*,fault=None,retain_profile=True):
    a,model,receipt,f,_,_=setup(monkeypatch)
    baseline=[f['plane'],f['origin'],f['body_folder']]
    a.feature_summary=lambda feature:dict(name=feature.Name,suppressed=feature.suppressed)
    receipt.baseline_features=tuple((feature,a.feature_summary(feature)) for feature in baseline)
    manager=SimpleNamespace(ActiveSketch=None)
    model.SketchManager=manager;selected=[];flags=[]
    a._module.ISketchManager=object;a._module.ISelectionMgr=object
    a.part_creation_controls=lambda model:{}
    a._base_selection=lambda model,receipt:nullcontext()
    model.ClearSelection2=lambda _:selected.clear()
    model.SelectionManager=SimpleNamespace(GetSelectedObjectCount2=lambda mark:len(selected),
        GetSelectedObject6=lambda i,mark:selected[i-1] if 0<i<=len(selected) else None)
    def select(feature,append,mark):
        if not append:selected.clear()
        selected.append(feature);return True
    for feature in f.values():feature.Select2=lambda append,mark,feature=feature:select(feature,append,mark)
    snapshot=dict(exact_profile='two lines, five relations, two drivers')
    a.sketch_snapshot=lambda model,feature:(deepcopy(snapshot),())
    a.rebuild_dimension_document=lambda model:True
    a.dimensions=lambda model,features:[SimpleNamespace(owner=f['sketch']) for _ in range(2)]
    def delete(flag):
        flags.append(flag)
        if len(flags)==1:
            assert flag==2
            a.body_members=[];a.tree=baseline+[f['sketch']] if retain_profile else baseline[:]
            f['sketch'].owner=None;f['sketch'].children=[]
            model.FeatureManager.GetSheetMetalFolder=lambda:None
            model.FeatureManager.GetFlatPatternFolder=lambda:None
            if fault=='changed_profile':snapshot['exact_profile']='changed'
            elif fault=='foreign_feature':a.tree.append(Feature(999,'ProfileFeature'))
            elif fault=='foreign_child':f['sketch'].children=[Feature(999,'ProfileFeature')]
            elif fault=='foreign_parent':f['sketch'].parents.append(Feature(999,'RefPlane'))
            elif fault=='changed_baseline':f['plane'].Name='Другая плоскость'
            elif fault=='foreign_driver':a.dimensions=lambda model,features:[SimpleNamespace(owner=f['sketch']),SimpleNamespace(owner=f['plane'])]
            elif fault=='extra_driver':a.dimensions=lambda model,features:[SimpleNamespace(owner=f['sketch']) for _ in range(3)]
            elif fault=='wrong_reference':a.references[b'sketch']=Feature(999,'ProfileFeature')
            elif fault=='unexpected_owned_node':a.tree.append(f['bend'])
        else:
            assert flag==0 and selected==[f['sketch']]
            a.tree=baseline[:]
        return True
    a.DeleteSelection2=delete
    return a,model,receipt,flags


@pytest.mark.parametrize('retain_profile',[False,True])
def test_complete_delete_and_native_unabsorption_are_both_explicit(monkeypatch,retain_profile):
    a,model,receipt,flags=scenario(monkeypatch,retain_profile=retain_profile)
    a.restore_sheet_profile(model,receipt)
    assert receipt.restored is True and flags==([2,0] if retain_profile else [2])


@pytest.mark.parametrize('fault',['changed_profile','foreign_feature','foreign_child','foreign_parent','changed_baseline',
    'foreign_driver','extra_driver','wrong_reference','unexpected_owned_node'])
def test_primary_deletion_does_not_authorize_cleanup_of_unproved_remainder(monkeypatch,fault):
    a,model,receipt,flags=scenario(monkeypatch,fault=fault)
    with pytest.raises(ExecutionFailure):a.restore_sheet_profile(model,receipt)
    assert flags==[2] and receipt.restored is False
