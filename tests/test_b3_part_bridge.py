"""Actual registration tables plus API-shaped artificial retained CAD objects."""
from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from test_b3_native_part_reference import world

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from verifier_b3_part_bridge import OriginalPartObject,PartReferenceBridge
from verifier_b3_registered_references import export_registered_references


def setup(x):
    body=x.bindings['body'].handle
    originals=tuple(OriginalPartObject(obj.kind,obj,obj.identity,obj.persistent_id,body.identity)
        for obj in [body,*body.faces,*body.edges])
    x.a.native_close_windows=lambda:[(model,dict(hwnd=101+i,title='Одинаковое имя'))
        for i,model in enumerate(x.a.models)]
    bridge=PartReferenceBridge(model=x.model,model_canonical=x.model.identity,
        configuration_canonical=x.cfg.identity,hwnd=101,original_objects=originals,
        adapter=x.a,watch=NS(poll=lambda:x.sequence),wrap=lambda raw,name:raw,
        persistent_variant=lambda pid:pid,ordinal=x.ordinal,assert_safe=x.safe)
    proof=dict(scope='b3_actual_child_trace_job_binding_v1',accepted=False,trace=dict(
        document_window_bindings=[dict(document_id=entry.document_id,hwnd=101+i)
            for i,entry in enumerate(x.docs._entries)],
        registered_references=[export_registered_references(entry,assert_safe=lambda:None)
            for entry in x.docs._entries]))
    return bridge,proof


@pytest.mark.parametrize('kind',['body','face','edge'])
def test_actual_child_pid_and_hwnd_bind_original_handles_to_direct_native_oracle(world,kind):
    x=world;bridge,proof=setup(x)
    observed=bridge.capture(x.context,x.items[kind],proof)
    assert observed['object_id']==x.items[kind]['object_id']
    assert observed['persistent_id']==x.bindings[kind].persistent_id.hex()
    assert observed['accepted'] is observed['native_acceptance'] is False


@pytest.mark.parametrize('fault',['pid','body_owner','configuration','hwnd','duplicate_window',
                                'extra_window','root_replaced','closing_window_swap'])
def test_foreign_stale_or_changed_association_is_never_adopted(world,fault):
    x=world;bridge,proof=setup(x);item=x.items['face']
    record=next(row for row in proof['trace']['registered_references'][0]['rows']
                if row['object_id']==item['object_id'])
    if fault=='pid':record['persistent_id_hex']='ffff'
    elif fault=='body_owner':record['body_id']='foreign'
    elif fault=='configuration':record['configuration']='Вариант'
    elif fault=='hwnd':proof['trace']['document_window_bindings'][0]['hwnd']=999
    elif fault=='root_replaced':x.model.identity=object()
    else:
        original=x.a.native_close_windows;calls=[]
        def windows():
            calls.append(True);rows=original()
            if fault=='duplicate_window':rows[1]=(rows[1][0],rows[0][1])
            elif fault=='extra_window':rows.append(rows[0])
            elif len(calls)==2:rows=[(rows[0][0],rows[1][1]),(rows[1][0],rows[0][1])]
            return rows
        x.a.native_close_windows=windows
    with pytest.raises(ValueError):bridge.capture(x.context,item,proof)


def test_no_native_window_or_identity_call_before_owner_admission(world):
    x=world;bridge,proof=setup(x)
    def forbidden(*args):raise AssertionError('Native access before admission')
    def reject(context):raise RuntimeError('Unconfirmed owner')
    bridge.assert_safe=reject;x.a.identity=forbidden;x.a.native_close_windows=forbidden
    with pytest.raises(RuntimeError):bridge.capture(x.context,x.items['body'],proof)


def test_final_root_admission_aba_invalidates_bridge_proof(world):
    x=world;bridge,proof=setup(x);calls=[]
    def safe(context):
        calls.append(True)
        if len(calls)==6:x.sequence+=2
    bridge.assert_safe=safe
    with pytest.raises(ValueError):bridge.capture(x.context,x.items['body'],proof)
