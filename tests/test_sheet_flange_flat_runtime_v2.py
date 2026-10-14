"""The new state operation must not dispatch to the flange-creation domain."""

from types import SimpleNamespace as NS
import pytest

from solidworks_mcp.runtime_v2 import Runtime
from test_part_creation_domain_v2 import setup as part_setup


@pytest.mark.parametrize('operation',['sheet.prepare_flange_flat_state','sheet.set_flange_flat_state'])
def test_exact_u_state_dispatch_and_apartment_release(part_setup,operation):
    adapter,parts,_,_=part_setup;runtime=Runtime(parts.dimensions.coordinator.store)
    runtime._catalog=parts.dimensions.documents;runtime._dimensions=parts.dimensions;calls=[]
    runtime._sheet_flange_states=NS(prepare_flat_state=lambda **kw:calls.append(('prepare',kw)) or dict(verified=True),
        set_flat_state=lambda op,**kw:calls.append(('change',op,kw)) or dict(verified=True))
    args=dict(document_id='doc_explicit',configuration='Основная',base_object_id='feat_base',flange_object_id='feat_flange',flattened=True)
    assert runtime._execute(operation,args,'job_explicit')==dict(verified=True)
    assert calls==([('prepare',args)] if operation.endswith('prepare_flange_flat_state') else [('change','job_explicit',args)])
    assert runtime._sheet_edge_flanges is None
    runtime._release_catalog();assert runtime._sheet_flange_states is None
