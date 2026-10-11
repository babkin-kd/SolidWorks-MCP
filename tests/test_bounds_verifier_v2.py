"""Verifier control plane and independent analytical oracle, no native calls."""
import importlib
import math
from pathlib import Path
import pytest


@pytest.fixture
def verifier(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1]/'scripts'))
    module=importlib.import_module('verify_bounds_measurements')
    monkeypatch.setattr(module.binding,'connect',lambda **kw:pytest.fail('No native connection'))
    monkeypatch.delenv('PYTHONPATH',raising=False)
    return module


def test_opt_in_precedes_any_wheel_state_or_native_effect(verifier,monkeypatch,tmp_path):
    monkeypatch.setattr('sys.argv',['bounds','--wheel','missing.whl','--expected-version','dev','--expected-git-sha','a'*40,'--state-dir',str(tmp_path/'state')])
    monkeypatch.setattr(verifier,'validate_wheel',lambda *a,**kw:pytest.fail('No wheel before native opt-in'))
    with pytest.raises(SystemExit) as error:verifier.main()
    assert error.value.code==2 and not (tmp_path/'state').exists()


def test_public_payload_includes_typed_frame_as_read_not_mutation(verifier):
    args=dict(request_id='r',timeout_s=0.,document_id='doc',configuration='Основная',expected_observation_revision='obs',coordinate_frame=verifier.frame(True))
    payload=verifier.SPECS['measurement_get_bounds'].payload(args)
    assert payload['mutates'] is False and payload['arguments']['coordinate_frame']==args['coordinate_frame']
    assert payload['arguments']['body_id'] is None and payload['arguments']['body_type']=='all'
    assert 'request_id' not in payload['arguments'] and 'timeout_s' not in payload['arguments']


def test_oracle_for_cylinder_uses_round_support_not_aabb_corners(verifier):
    f=verifier.frame(True)
    values=verifier.analytical(coordinate_frame=f,cylinder=True)
    # Cylinder axis is Y; rotation of X/Z leaves circular transverse extent12.
    assert values['size_mm']==pytest.approx([12.,30.,12.])
    box=verifier.analytical([((-6.,0.,-6.),(6.,30.,6.))],f)
    assert box['size_mm'][0]>values['size_mm'][0]+1.


def test_full_public_scenario_flow_with_protocol_fake(verifier,monkeypatch):
    """Catch missing scenario arguments before spending an installed/native run."""
    import asyncio
    from types import SimpleNamespace as NS
    models=[NS(GetTitle=lambda:'Деталь',GetBlockingState=lambda:0) for _ in range(3)]
    store={};calls=[];report={'cases':[]}
    async def context(model):return dict(document_id=str(models.index(model)),configuration='Основная',expected_observation_revision='obs')
    # Equal SimpleNamespace models are unsuitable as identities; make titles unique.
    for i,model in enumerate(models):model.identity=object()
    async def read(args):
        calls.append(args)
        if args.get('document_id')=='1' and args.get('body_id')=='solid0':
            return dict(status='failed',operation_id='foreign',error={'code':'object_reference_not_found'})
        request=args.get('request_id',str(len(calls)))
        if request in store:return store[request]
        cylinder=args['document_id']=='2';body=args.get('body_id')
        boxes=verifier.BOXES[:2] if args.get('body_type')=='solid' else [verifier.BOXES[1]] if body=='solid1' else [verifier.BOXES[2]] if body=='surface' else verifier.BOXES
        value=dict(body_count=1 if cylinder else len(boxes),measurement_scope='part_native_support_bounds_v1',
            approximate_body_box_used=False,model_geometry_modified=False,
            bounding_box_mm=verifier.analytical(boxes,args.get('coordinate_frame'),cylinder))
        result=dict(status='succeeded',operation_id=request,data=value,error=None);store[request]=result;return result
    async def bodies(ctx):return [dict(object_id=name,body_type=kind,bounding_box_mm={'min_mm':[x,0.,0.]}) for name,kind,x in [('solid0','solid',0.),('solid1','solid',40.),('surface','surface',80.)]]
    async def safe():pass
    monkeypatch.setattr(verifier,'source_state',lambda *a:None)
    monkeypatch.setattr(verifier,'confirm_source',lambda *a:None)
    asyncio.run(verifier.cases(read,context,bodies,safe,NS(CommandInProgress=False),None,models,None,report,lambda:None,True))
    assert len(report['cases'])==6 and all(row['passed'] for row in report['cases'])
    assert len(calls)==7 and calls[-1]==calls[-2]
