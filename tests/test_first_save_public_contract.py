"""Public L3-P1 argument forwarding/defaults; no CAD or model changes."""

import importlib.util
from pathlib import Path
import sys


scripts = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0,str(scripts))
from verifier_first_save_public_contract import SPECS
sys.path.pop(0)


def test_activation_is_explicit_mutation_with_revision_and_timeout_outside_payload():
    arguments = dict(request_id='activate',document_id='doc_new',configuration='Основная',
                     expected_revision='rev_current',timeout_s=0.)
    payload = SPECS['document_activate_part_native'].payload(arguments)
    assert payload == dict(arguments={key:value for key,value in arguments.items() if key not in ('request_id','timeout_s')},
        context={key:value for key,value in arguments.items() if key not in ('request_id','timeout_s')},mutates=True)
    assert SPECS['document_prepare_activate_part_native'].mutates is False


def test_open_close_and_depth_edit_have_complete_explicit_defaults_and_units():
    common = dict(request_id='request',document_id='doc_new',configuration='Основная')
    closed = SPECS['document_prepare_close_native'].payload(common)
    assert closed['arguments']['active_after_document_id']==''
    assert closed['arguments']['allowed_hidden_document_ids']==[]
    opened = SPECS['document_prepare_open_native'].payload(dict(request_id='open',filename='/part.SLDPRT',
                                                               document_type='part',configuration='Основная'))
    assert opened['arguments']['read_only'] is False
    edited = SPECS['dimension_set_value'].payload({**common,'object_id':'dimension_bound',
                                                 'expected_revision':'rev_current','value':14,'unit':'mm'})
    assert edited['arguments']['object_id']=='dimension_bound' and type(edited['arguments']['value']) is float
    assert edited['arguments']['unit']=='mm' and edited['mutates'] is True
