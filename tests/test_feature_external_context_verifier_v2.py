"""Pure acceptance-oracle tests; these do not prove native reference behavior."""
import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).parents[1] / 'scripts' / 'verify_feature_external_context.py'
TREE = ast.parse(SOURCE.read_text(encoding='utf-8-sig'))
MODULE = ast.Module(body=[node for node in TREE.body if isinstance(node, (ast.FunctionDef, ast.Assign))
                         and (getattr(node, 'name', None) in ('reference_rows', 'verify_reference_context')
                              or isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'FIELDS' for t in node.targets))], type_ignores=[])
NS = {'Path': Path}
exec(compile(MODULE, str(SOURCE), 'exec'), NS)


def rows():
    return [{'row_index': 0, **dict(zip(NS['FIELDS'], ('private/Основа.SLDPRT', '', 'Контрольная ссылка на основу',
            'Тело', 0, 'Тело@Основа', '', 2, 'Основная')))}]


class References:
    def __init__(self, *, feature=False): self.feature, self.value = feature, rows()
    def ListExternalFileReferencesCount(self): return len(self.value)
    def ListExternalFileReferences2(self):
        return tuple(self.value[0][key] if self.feature and index >= 7
                     else [row[key] for row in self.value] for index, key in enumerate(NS['FIELDS']))


@pytest.mark.parametrize('feature', [False, True])
def test_document_array_and_feature_scalar_configuration_outputs_decode(feature):
    assert NS['reference_rows'](References(feature=feature), feature=feature) == rows()


@pytest.mark.parametrize('fault', ['boolean_count', 'oversize', 'missing_column', 'short_column', 'scalar_in_document', 'array_in_feature', 'count_changes', 'boolean_closing_count', 'boolean_status', 'native_text_object'])
def test_incomplete_native_out_arrays_do_not_become_reference_evidence(fault):
    value = References(feature=fault == 'array_in_feature')
    if fault == 'boolean_count': value.ListExternalFileReferencesCount = lambda: True
    elif fault == 'oversize': value.ListExternalFileReferencesCount = lambda: 5001
    elif fault == 'missing_column': value.ListExternalFileReferences2 = lambda: ([],)
    elif fault == 'short_column': value.ListExternalFileReferences2 = lambda: ([],) * 9
    elif fault == 'scalar_in_document': value.feature = True
    elif fault == 'array_in_feature': value.feature = False
    elif fault == 'boolean_closing_count':
        counts = iter([1, True]); value.ListExternalFileReferencesCount = lambda: next(counts)
    elif fault == 'boolean_status': value.value[0]['status'] = False
    elif fault == 'native_text_object': value.value[0]['data_type'] = object()
    else:
        counts = iter([1, 0]); value.ListExternalFileReferencesCount = lambda: next(counts)
    with pytest.raises(AssertionError): NS['reference_rows'](value, feature=fault == 'array_in_feature')


def result():
    return {'native_inventory_capture_closed': True, 'row_indices_and_names_are_writable_anchors': False,
            'native_context': {'external_references': {'count': 1, 'rows': rows()}},
            'deletion_impact_complete': False, 'deletion_authorized': False,
            'blockers': [{'code': 'unverified_impact_scope', 'scope': 'incoming_external_document_references'}]}


def test_matching_nonempty_document_and_feature_evidence_with_exact_private_source():
    NS['verify_reference_context'](result(), rows(), rows(), Path('private/Основа.SLDPRT'), 'Контрольная ссылка на основу')


@pytest.mark.parametrize('fault', ['empty', 'missing_native_row', 'different_feature', 'wrong_path', 'wrong_name', 'authorized', 'complete', 'missing_blocker', 'unclosed', 'writable_indices'])
def test_incomplete_or_misbound_control_references_do_not_pass(fault):
    data, document, feature = result(), rows(), rows()
    source, name = Path('private/Основа.SLDPRT'), 'Контрольная ссылка на основу'
    if fault == 'empty': data['native_context']['external_references'].update(count=0, rows=[]); document=feature=[]
    elif fault == 'missing_native_row': document=[]
    elif fault == 'different_feature': feature[0]['feature_name']='Другая ссылка'
    elif fault == 'wrong_path': source=Path('private/Чужая.SLDPRT')
    elif fault == 'wrong_name': name='Чужой элемент'
    elif fault == 'authorized': data['deletion_authorized']=True
    elif fault == 'complete': data['deletion_impact_complete']=True
    elif fault == 'missing_blocker': data['blockers']=[]
    elif fault == 'unclosed': data['native_inventory_capture_closed']=False
    else: data['row_indices_and_names_are_writable_anchors']=True
    with pytest.raises(AssertionError): NS['verify_reference_context'](data, document, feature, source, name)


@pytest.mark.parametrize('feature', [False, True])
def test_empty_native_arrays_remain_empty_without_inventing_references(feature):
    value=References(feature=feature)
    value.value=[]
    value.ListExternalFileReferences2=lambda: (None,)*7 + ((0, '') if feature else (None, None))
    assert NS['reference_rows'](value, feature=feature)==[]
