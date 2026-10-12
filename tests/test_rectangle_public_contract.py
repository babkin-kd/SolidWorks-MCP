"""Passive public payload mapping; no native/SDK session is opened."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys

import pytest


scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
try:
    spec=importlib.util.spec_from_file_location('rectangle_public_contract',scripts/'verifier_rectangle_public_contract.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
finally:sys.path.remove(str(scripts))


def test_explicit_rectangle_payload_has_defaults_and_preserves_ids_and_request_shape():
    value=helper.SPECS['sketch_create_rectangle'].payload(dict(request_id='r',timeout_s=0.,
        document_id='doc_current',configuration='Основная',expected_revision='rev_current',
        plane_object_id='feat_current',width_mm=40,height_mm=20))
    assert value['mutates'] is True
    assert value['arguments']==dict(document_id='doc_current',configuration='Основная',
        expected_revision='rev_current',plane_object_id='feat_current',width_mm=40.,height_mm=20.,sketch_name='Эскиз основания')
    assert value['context']==dict(document_id='doc_current',configuration='Основная',expected_revision='rev_current')


def test_extrusion_payload_uses_returned_sketch_as_explicit_baseline():
    value=helper.SPECS['part_extrude_rectangle'].payload(dict(request_id='r',document_id='doc',
        configuration='Основная',expected_revision='rev_new',sketch_object_id='feat_exact',depth_mm=10))
    assert value['arguments']['sketch_object_id']=='feat_exact'
    assert value['arguments']['feature_name']=='Основание' and value['arguments']['body_name']=='Тело основания'
    assert value['arguments']['depth_mm']==10. and value['mutates'] is True
    assert helper.SPECS['part_prepare_rectangle_extrusion'].mutates is False


def test_boolean_length_is_not_silently_coerced_by_supervisor_before_schema_rejection():
    value=helper.SPECS['sketch_prepare_rectangle'].payload(dict(width_mm=True,height_mm=20))
    assert value['arguments']['width_mm'] is True


def test_new_document_payload_binds_the_application_and_russian_configuration():
    value=helper.SPECS['document_create_part'].payload(dict(application_id='app_exact',
        expected_revision='rev',template_id='template_exact',name='Контрольная деталь'))
    assert value['arguments']['document_id']=='app_exact' and value['arguments']['configuration']==''
    assert value['arguments']['configuration_name']=='Основная' and value['mutates'] is True


@pytest.fixture
def creation():
    return dict(status='succeeded',operation='document.create_part',error=None,mutation={'phase':'committed'},
        result=dict(verified=True,after={'created_document_id':'doc_'+'a'*32}))


def test_created_id_is_taken_from_the_bound_creation_result(creation):
    assert helper.created_part_id(creation)=='doc_'+'a'*32


@pytest.mark.parametrize('fault',['running','unknown','wrong_operation','unverified','phase','name','missing'])
def test_unconfirmed_or_guessed_created_id_is_refused(creation,fault):
    if fault in ('running','unknown'):creation['status']=fault
    elif fault=='wrong_operation':creation['operation']='document.open_native'
    elif fault=='unverified':creation['result']['verified']=False
    elif fault=='phase':creation['mutation']['phase']='unresolved'
    elif fault=='name':creation['result']['after']['created_document_id']='Контрольная деталь'
    else:creation['result']['after'].pop('created_document_id')
    with pytest.raises((ValueError,KeyError)):helper.created_part_id(creation)
