"""Exact public B1 payload contracts; no CAD calls or SDK startup."""
from verifier_lifecycle import ToolSpec


SPECS={
    'document_list':ToolSpec('document.list',False),
    'document_get':ToolSpec('document.get',False),
    'document_list_templates':ToolSpec('document.list_templates',False),
    'document_prepare_create_part':ToolSpec('document.prepare_create_part',False,
        argument_defaults={'configuration_name':'Основная'}),
    'document_create_part':ToolSpec('document.create_part',True,
        argument_map={'application_id':'document_id'},argument_defaults={'configuration_name':'Основная'},
        constant_args={'configuration':''},prewrite_failure_codes=frozenset({'stale_revision'})),
    'feature_list':ToolSpec('feature.list',False,argument_defaults={'limit':100,'cursor':''}),
    'feature_get':ToolSpec('feature.get',False),
    'sketch_prepare_rectangle':ToolSpec('sketch.prepare_rectangle',False,
        argument_defaults={'sketch_name':'Эскиз основания'},float_arguments=frozenset({'width_mm','height_mm'})),
    'sketch_create_rectangle':ToolSpec('sketch.create_rectangle',True,
        argument_defaults={'sketch_name':'Эскиз основания'},float_arguments=frozenset({'width_mm','height_mm'}),
        prewrite_failure_codes=frozenset({'stale_revision'})),
    'part_prepare_rectangle_extrusion':ToolSpec('part.prepare_rectangle_extrusion',False,
        argument_defaults={'feature_name':'Основание','body_name':'Тело основания'},float_arguments=frozenset({'depth_mm'})),
    'part_extrude_rectangle':ToolSpec('part.extrude_rectangle',True,
        argument_defaults={'feature_name':'Основание','body_name':'Тело основания'},float_arguments=frozenset({'depth_mm'}),
        prewrite_failure_codes=frozenset({'stale_revision'})),
}


def created_part_id(job):
    """A committed creation DTO names the new document, never roster/name inference."""
    if (type(job) is not dict or job.get('status')!='succeeded' or job.get('operation')!='document.create_part'
            or job.get('error') is not None or job.get('mutation',{}).get('phase')!='committed'
            or job.get('result',{}).get('verified') is not True):
        raise ValueError('A committed public document creation is required.')
    value=job['result']['after']['created_document_id']
    if type(value) is not str or not value.startswith('doc_') or len(value)!=36:
        raise ValueError('No exact opaque created document ID.')
    return value
