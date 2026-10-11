"""Native reference and write ordering faults, with artificial COM surfaces."""

from types import SimpleNamespace as NS
import pytest

from solidworks_mcp.cad_sheet_flange_flat import CadSheetFlangeFlatMixin
from solidworks_mcp.jobs import ExecutionFailure
from test_sheet_edge_flange_views_v2 import views


def test_fresh_body_feature_view_requires_full_native_proof(views):
    a,model,retained,view,_,_,_=views
    assert CadSheetFlangeFlatMixin._u_flat_canonical(a,model,view) is retained


@pytest.mark.parametrize('fault',['late_retarget','wrong_status','bool_status','null','name','pid'])
def test_native_view_never_binds_by_id_or_name_alone(views,fault):
    a,model,retained,view,resolved,_,feature=views
    if fault=='late_retarget':view.GetOwnerFeature=lambda:resolved.update({b'48':(feature(48),2)}) or None
    elif fault=='wrong_status':resolved[b'48']=(retained,0)
    elif fault=='bool_status':resolved[b'48']=(retained,True)
    elif fault=='null':resolved[b'48']=(None,2)
    elif fault=='name':view.summary['name']='Подменённая развёртка'
    else:view.pid=b'foreign'
    with pytest.raises((ExecutionFailure,KeyError)):
        CadSheetFlangeFlatMixin._u_flat_canonical(a,model,view)


@pytest.mark.parametrize('state',[False,True])
def test_same_native_state_does_not_write_or_rebuild(state):
    calls=[];flat=NS(SetSuppression2=lambda *args:calls.append('write'))
    a=NS(sheet_flange_flat_target=lambda *args:(NS(members=[NS(role='flat',feature=flat)]),object()),
        feature_summary=lambda _:dict(suppressed=not state))
    model=NS(ForceRebuild3=lambda _:calls.append('rebuild'))
    assert CadSheetFlangeFlatMixin.sheet_change_flange_flat_state(a,model,NS(base=object(),flange=object()),state) is False
    assert not calls


def test_unconfirmed_setter_never_rebuilds_or_reports_success():
    calls=[];flat=NS(SetSuppression2=lambda *args:calls.append(args) or False)
    a=NS(sheet_flange_flat_target=lambda *args:(NS(members=[NS(role='flat',feature=flat)]),object()),
        feature_summary=lambda _:dict(suppressed=True))
    model=NS(ForceRebuild3=lambda _:pytest.fail('Setter not confirmed.'))
    with pytest.raises(ExecutionFailure,match='did not confirm'):
        CadSheetFlangeFlatMixin.sheet_change_flange_flat_state(a,model,NS(base=object(),flange=object()),True)
    assert calls==[(1,1,None)]
