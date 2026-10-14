"""Pure profile classification tests, not native COM-call acceptance."""
import ast
from pathlib import Path
from types import SimpleNamespace
import sys
import time
import pytest

SOURCE=Path(__file__).parents[1]/'scripts'/'verifier_native_read_metrics.py'
TREE=ast.parse(SOURCE.read_text(encoding='utf-8-sig'))
MODULE=ast.Module(body=[node for node in TREE.body if getattr(node,'name',None) in ('NativeReadMetrics','measure_read')],type_ignores=[])
NS={'sys':sys,'time':time}
exec(compile(MODULE,str(SOURCE),'exec'),NS)


def native_call(name,owner='PyIDispatch'):
    return SimpleNamespace(__name__=name,__self__=type(owner,(),{})())


def test_profile_counts_only_explicit_dispatch_and_query_calls_without_arguments():
    measured=NS['NativeReadMetrics'](None)
    for name,owner,event in [('InvokeTypes','PyIDispatch','c_call'),('Invoke','PyIDispatch','c_call'),
            ('QueryInterface','PyIUnknown','c_call'),('GetID','PyIDispatch','call'),
            ('InvokeTypes','Other','c_call'),('InvokeTypes','PyIDispatch','c_return')]:
        measured._profile(None,event,native_call(name,owner))
    assert measured.dispatches==2 and measured.interface_queries==1 and measured.data is None


def test_profile_hook_is_removed_and_original_read_error_preserved():
    assert sys.getprofile() is None
    adapter=SimpleNamespace(full_tree_enumerations=0,feature_metadata_reads=0)
    error=OSError('read failed')
    measured=NS['NativeReadMetrics'](adapter)
    with pytest.raises(OSError) as caught:
        with measured:
            adapter.full_tree_enumerations+=1
            raise error
    assert caught.value is error and sys.getprofile() is None
    assert measured.data['full_tree_enumerations']==1 and measured.data['native_internal_calls_measured'] is False


def test_existing_profile_hook_is_preserved_without_stealing_it():
    old=sys.getprofile()
    callback=lambda *args:None
    sys.setprofile(callback)
    try:
        with pytest.raises(RuntimeError):NS['NativeReadMetrics'](None).__enter__()
        assert sys.getprofile() is callback
    finally:sys.setprofile(old)


@pytest.mark.parametrize('trees,dispatches',[(1,1),(4,1),(2,0)])
def test_measurement_cannot_certify_missing_boundaries_or_unobserved_native_dispatches(trees,dispatches):
    adapter=SimpleNamespace(full_tree_enumerations=0,feature_metadata_reads=0)
    def read():
        adapter.full_tree_enumerations=trees
        for _ in range(dispatches):sys.getprofile()(None,'c_call',native_call('InvokeTypes'))
        return {'modeled':True}
    with pytest.raises(AssertionError):NS['measure_read'](adapter,read)
    assert sys.getprofile() is None


def test_modeled_measurement_preserves_result_and_declares_metric_scope():
    adapter=SimpleNamespace(full_tree_enumerations=0,feature_metadata_reads=0)
    result={'modeled_only':True}
    def read():
        adapter.full_tree_enumerations=2;adapter.feature_metadata_reads=4
        sys.getprofile()(None,'c_call',native_call('InvokeTypes'))
        return result
    returned,metrics=NS['measure_read'](adapter,read)
    assert returned is result and metrics['full_tree_enumerations']==2 and metrics['feature_metadata_reads']==4
    assert metrics['python_com_api_dispatches']==1 and metrics['native_internal_calls_measured'] is False
    assert metrics['elapsed_seconds']>=0 and sys.getprofile() is None
