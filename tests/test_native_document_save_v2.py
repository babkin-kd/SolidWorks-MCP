"""Declared native/file effects, stale checkpoints and non-replay of save."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from concurrent.futures import Future
from types import SimpleNamespace
import pytest
from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import JobRunner, JobStore, JobError
from solidworks_mcp.native_document_save import NativeDocumentSaveCatalog, native_file_facts
from test_document_catalog_v2 import Adapter, model


class SaveAdapter(Adapter):
    def __init__(self, folder):
        super().__init__(); self.folder=folder;self.busy=False;self.active=None
        self.calls=0;self.fault=None;self.read_only=0;self.mode=None;self.guard_hook=None
    def active_document(self):return self.active
    def documents(self):return list(self.models)
    def application_busy(self):return self.busy
    def application_visible(self):return True
    def native_save_context(self, current):
        return dict(blocking_state=0,read_only_state=self.read_only if current is self.models[0] else 0,
                    editing_sketch=self.mode=='sketch',editing_component=self.mode=='component',view_only=self.mode=='view')
    def document_view_snapshot(self,current):return deepcopy(current.view)
    @contextmanager
    def native_save_guard(self, models):
        assert tuple(models)==tuple(self.models)
        assert not self.busy;self.busy=True
        try:
            if self.guard_hook:self.guard_hook()
            yield SimpleNamespace(evidence={'released':True})
        finally:self.busy=False
    def save_native_current_file(self,current):
        self.calls+=1
        if self.fault=='throw_before':raise RuntimeError('Native acknowledgement lost')
        if self.fault=='no_effect':return dict(success=False,errors=1,warnings=0)
        Path(current.state['path']).write_bytes(b'new native bytes '+str(self.calls).encode())
        current.state['needs_save']=False;current.state['update_stamp']+=1
        if self.fault=='foreign_file':Path(self.models[1].state['path']).write_bytes(b'foreign changed')
        if self.fault=='foreign_model':self.models[1].state['needs_save']=True
        if self.fault=='view':current.view['scale']=2.
        if self.fault=='activation':self.active=self.models[0]
        if self.fault=='throw_after':raise RuntimeError('Lost return after writing')
        return dict(success=True,errors=0,warnings=2 if self.fault=='warning' else 0)


class Worker:
    def submit(self, function):
        future=Future()
        try:future.set_result(function())
        except BaseException as exc:future.set_exception(exc)
        return future


@pytest.fixture
def setup(tmp_path):
    adapter=SaveAdapter(tmp_path)
    for index in (1,2):
        path=tmp_path/f'Деталь {index}.SLDPRT';path.write_bytes(b'artificial native original')
        item=model(title=f'Деталь {index}',path=str(path));item.view={'scale':1.}
        adapter.models.append(item)
    adapter.active=adapter.models[1];adapter.models[0].state['needs_save']=True
    docs=DocumentCatalog(adapter);store=JobStore(tmp_path/'jobs.sqlite');catalog=NativeDocumentSaveCatalog(docs,store,'epoch')
    doc=docs.list()['documents'][0];args=dict(document_id=doc['document_id'],configuration=doc['active_configuration'])
    prepared=catalog.prepare_save(**args);runner=JobRunner(store,Worker())
    def run(request='save',revision=prepared['revision']):
        data=dict(args,expected_revision=revision)
        return runner.submit(request,'document.save_native',data,lambda op:catalog.save(op,**data),context=data,
                             mutates=True,pass_operation_id=True,verify=lambda result:result['verified'] is True)
    yield adapter,docs,store,catalog,args,prepared,run
    docs.close();store.close()


def test_save_exact_nonactive_document_file_and_native_ack_once(setup):
    a,d,s,c,args,p,run=setup;other=(deepcopy(a.models[1].state),Path(a.models[1].state['path']).read_bytes())
    result=run();assert result['status']=='succeeded' and result['mutation']['phase']=='committed'
    saved=next(row for row in result['result']['after']['semantic']['documents'] if row['document_id']==args['document_id'])
    assert saved['needs_save'] is False and saved['file']['sha256']!=p['file']['sha256']
    assert (a.models[1].state,Path(a.models[1].state['path']).read_bytes())==other
    assert a.active is a.models[1] and a.busy is False and result==run() and a.calls==1


@pytest.mark.parametrize('kind,extension,configuration',[('assembly','.SLDASM','Основная'),('drawing','.SLDDRW','')])
def test_all_native_document_types_without_geometry_restriction(setup,kind,extension,configuration):
    a,d,s,c,args,p,run=setup;item=a.models[0];path=Path(item.state['path']).with_suffix(extension)
    Path(item.state['path']).rename(path);item.state.update(path=str(path),document_type=kind,
        active_configuration=configuration,configurations=[configuration] if configuration else [])
    args['configuration']=configuration;fresh=c.prepare_save(**args)
    assert run(revision=fresh['revision'])['status']=='succeeded'


@pytest.mark.parametrize('change',['file','model','view','activation','guard_file'])
def test_stale_native_or_file_checkpoint_never_writes(setup,change):
    a,d,s,c,args,p,run=setup
    if change=='file':Path(a.models[0].state['path']).write_bytes(b'external change')
    elif change=='model':a.models[0].state['update_stamp']+=1
    elif change=='view':a.models[1].view['scale']=3.
    elif change=='activation':a.active=a.models[0]
    else:a.guard_hook=lambda:Path(a.models[0].state['path']).write_bytes(b'changed under guard')
    result=run();assert result['status']=='failed' and result['error']['code']=='stale_revision' and a.calls==0


def test_false_native_return_with_proved_no_effect_is_known_failure(setup):
    a,d,s,c,args,p,run=setup;a.fault='no_effect'
    result=run();assert result['status']=='failed' and result['mutation']['phase']=='rolled_back'
    assert not result['error']['requires_reconciliation'] and a.calls==1 and a.busy is False


@pytest.mark.parametrize('fault',['throw_before','throw_after','warning','foreign_file','foreign_model','view','activation'])
def test_uncertain_or_changed_save_never_rewrites_or_undoes_user_changes(setup,fault):
    a,d,s,c,args,p,run=setup;a.fault=fault;result=run()
    assert result['status']=='unknown' and result['error']['requires_reconciliation'] and a.calls==1 and a.busy is False
    assert run()==result and a.calls==1
    blocked=run('another-save');assert blocked['status']=='failed' and blocked['error']['code']=='document_mutation_blocked'
    assert a.calls==1


@pytest.mark.parametrize('mode',['sketch','component','view'])
def test_editing_modes_refused_before_native_write(setup,mode):
    a,d,s,c,args,p,run=setup;a.mode=mode
    assert run()['status']=='failed' and a.calls==0


def test_readonly_first_save_and_busy_refused(setup):
    a,d,s,c,args,p,run=setup;a.read_only=1
    assert run('readonly')['error']['code']=='native_document_read_only'
    a.read_only=0;a.busy=True
    assert run('busy')['error']['code']=='application_busy'
    a.busy=False;a.models[0].state['path']=''
    assert run('first')['error']['code']=='native_document_first_save_required' and a.calls==0


def test_native_path_type_size_and_redirect_checks(tmp_path,monkeypatch):
    from solidworks_mcp import native_document_save as module
    path=tmp_path/'Модель.SLDPRT';path.write_bytes(b'native')
    assert native_file_facts(str(path),'part')['bytes']==6
    for name,kind in [('relative.SLDPRT','part'),(str(path),'drawing')]:
        with pytest.raises(Exception) as error:native_file_facts(name,kind)
        assert error.value.code=='native_document_path_required'
    monkeypatch.setattr(module,'MAX_FILE_BYTES',5)
    with pytest.raises(Exception) as error:native_file_facts(str(path),'part')
    assert error.value.code=='native_file_budget_exceeded'


def test_runtime_native_save_uses_same_document_catalog_and_durable_context(tmp_path):
    import asyncio
    from solidworks_mcp.runtime_v2 import Runtime
    from test_runtime_v2 import Worker as RuntimeWorker
    adapter=SaveAdapter(tmp_path);path=tmp_path/'Пластина.SLDPRT';path.write_bytes(b'old')
    current=model(path=str(path));current.view={'scale':1.};current.state['needs_save']=True
    adapter.models=[current];adapter.active=current
    store=JobStore(tmp_path/'runtime.sqlite');runtime=Runtime(store,worker_factory=RuntimeWorker,catalog_factory=lambda:DocumentCatalog(adapter))
    async def exercise():
        row=(await runtime.read('list','document.list',{}))['result']['documents'][0]
        args=dict(document_id=row['document_id'],configuration=row['active_configuration'])
        prepared=await runtime.read('prepare','document.prepare_save_native',args)
        assert prepared['status']=='succeeded'
        args['expected_revision']=prepared['result']['revision']
        saved=await runtime.mutate('save','document.save_native',args)
        assert saved['status']=='succeeded' and saved['mutation']['phase']=='committed'
        assert saved['payload']['context']['document_id']==row['document_id']
        assert await runtime.mutate('save','document.save_native',args)==saved and adapter.calls==1
    try:asyncio.run(exercise())
    finally:assert runtime.shutdown();assert runtime._native_document_saves is None;store.close()
