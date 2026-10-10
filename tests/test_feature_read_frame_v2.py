"""Two complete boundaries, late changes and uncommitted outer read frames."""
import pytest
from solidworks_mcp.feature_dependency_graph import FeatureGraphRead
from solidworks_mcp.jobs import ExecutionFailure
from test_feature_domain_v2 import setup
from test_feature_dependency_graph_v2 import install
from test_feature_deletion_context_v2 import install_context


def counted(adapter):
    counts={'trees':0,'metadata':0}
    old_tree,old_summary=adapter.features,adapter.feature_summary
    def tree(model):
        counts['trees']+=1
        return old_tree(model)
    def summary(obj):
        counts['metadata']+=1
        return old_summary(obj)
    adapter.features,adapter.feature_summary=tree,summary
    return counts


@pytest.mark.parametrize('operation',['graph','context','structure'])
def test_each_read_uses_two_full_trees_and_two_relation_captures(setup,operation):
    adapter,_,catalog,_,ids=setup
    calls=install(adapter,owner=True)
    install_context(adapter)
    if operation=='structure':target=catalog.list(ids[0],'Основная')['items'][0]['object_id']
    counts=counted(adapter)
    if operation=='graph': result=catalog.dependencies(ids[0],'Основная')
    elif operation=='context': result=catalog.deletion_context(ids[0],'Основная')
    else:result=catalog.deletion_structure(ids[0],'Основная',[target],True,True)
    assert counts=={'trees':2,'metadata':4} and calls==['capture','capture']
    assert result['deletion_authorized'] is result['deletion_impact_complete'] is False
    assert adapter.writes==[]


@pytest.mark.parametrize('previous_cache',[False,True])
def test_failed_outer_context_does_not_commit_inner_graph_cache(setup,previous_cache):
    adapter,documents,catalog,_,ids=setup
    install(adapter)
    if previous_cache:catalog.dependencies(ids[0],'Основная')
    entry=documents._entries[0]
    old=entry.features.get('dependency_incarnations')
    def change(number,value):
        if number==2:value['equations']['rows'][0]['expression']='"Высота" = 99'
    install_context(adapter,change)
    with pytest.raises(ExecutionFailure):catalog.deletion_context(ids[0],'Основная')
    assert entry.features.get('dependency_incarnations') is old


def test_silent_metadata_change_during_last_context_getter_is_in_final_full_snapshot(setup):
    adapter,documents,catalog,_,ids=setup
    install(adapter)
    def change(number,value):
        if number==2:adapter.models[0].features[0].state['name']='Изменено без уведомления'
    install_context(adapter,change)
    counts=counted(adapter)
    with pytest.raises(ExecutionFailure) as error:catalog.deletion_context(ids[0],'Основная')
    assert error.value.code=='document_changed_during_read' and counts['trees']==2
    assert not documents._entries[0].features.get('dependency_incarnations')


@pytest.mark.parametrize('late_event',[False,True])
def test_context_final_canonical_comparison_is_before_last_notification_poll(setup,late_event):
    adapter,documents,catalog,_,ids=setup
    armed=[False]
    class Canonical:
        __hash__=None
        def __init__(self,value):self.value=value
        def __eq__(self,other):
            if armed[0]:
                armed[0]=False
                adapter.watches[id(adapter.models[0].identity)].sequence+=1
            return isinstance(other,Canonical) and self.value==other.value
    original=adapter.identity
    adapter.identity=lambda obj:Canonical(original(obj)) if hasattr(obj,'pid') else original(obj)
    def change(number,value):
        if number==2 and late_event:armed[0]=True
    install(adapter,change=change);install_context(adapter)
    if late_event:
        with pytest.raises(ExecutionFailure) as error:catalog.deletion_context(ids[0],'Основная')
        assert error.value.code=='document_changed_during_read'
        assert not documents._entries[0].features.get('dependency_incarnations')
    else:
        first=catalog.deletion_context(ids[0],'Основная')
        assert catalog.deletion_context(ids[0],'Основная')['revision']==first['revision']


@pytest.mark.parametrize('phase',['second','close'])
def test_native_read_frame_cannot_repeat_a_completed_phase(setup,phase):
    adapter,_,catalog,_,ids=setup
    calls=install(adapter)
    first=catalog._state(ids[0],'Основная')
    frame=FeatureGraphRead(catalog,ids[0],'Основная',first)
    frame.capture_second_relations()
    last=catalog._state(ids[0],'Основная')
    if phase=='close':frame.close(last)
    with pytest.raises(ExecutionFailure):
        if phase=='second':frame.capture_second_relations()
        else:frame.close(last)
    assert calls==['capture','capture']
