"""Artificial clone/handle/file domain scenarios, never native CAD/NTFS proof."""

from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from solidworks_mcp.documents import DocumentCatalog
from solidworks_mcp.jobs import ExecutionFailure, JobRunner, JobStore
from solidworks_mcp.native_document_save import native_file_facts
from solidworks_mcp.native_first_save import (NativeFirstSaveCatalog, SNAPSHOT_SCOPE,
                                             clone_mapping, validated_part_snapshot)
from test_native_document_close_v2 import Guard, Worker
from test_native_document_open_v2 import OpenAdapter


class FakeFiles:
    """Portable fake effects; no Windows locks or no-replace guarantee claimed."""
    def __init__(self):
        self.creations = self.publications = self.cleanups = 0
        self.fault = None
        self.leases = []
        self.stages = []

    def prepare_destination(self, filename):
        path = Path(filename)
        if not path.is_absolute() or path.suffix.lower() != '.sldprt':
            raise ExecutionFailure('first_save_invalid_path', 'Fake explicit part path required.', uncertain=False)
        if path.exists():
            raise ExecutionFailure('first_save_destination_exists', 'Fake existing destination.', uncertain=False)
        return dict(scope='windows_ntfs_first_save_files_v1', destination=str(path),
                    ancestry=[dict(path=str(path.parent), identity=[path.parent.stat().st_dev, path.parent.stat().st_ino])])

    @contextmanager
    def lease_destination(self, token):
        if self.fault == 'lease':
            raise ExecutionFailure('first_save_lease_invalid', 'Fake lease refused.', uncertain=False)
        lease = SimpleNamespace(token=deepcopy(token), active=True)
        self.leases.append(lease)
        try:
            yield lease
        finally:
            lease.active = False

    def create_owned_stage(self, lease, *, on_owned_change):
        assert lease.active
        self.creations += 1
        directory = Path(lease.token['destination']).parent / f'Служебная папка {self.creations}'
        stage = SimpleNamespace(lease=lease, directory=directory, filename=directory / 'Первая запись.SLDPRT',
            identity=None, facts=None, creation_attempted=False, creation_returned=False, pending_creation=True,
            publication_attempted=False, publication_returned=False, pending_publication=False,
            published=False, uncertain=False, cleaned=False, cleanup_attempted=False,
            cleanup_returned=False, pending_cleanup=False)
        def checkpoint():
            return dict(scope='windows_ntfs_first_save_files_v1', directory=str(stage.directory),
                directory_identity=deepcopy(stage.identity), filename=str(stage.filename), file=deepcopy(stage.facts),
                **{key:getattr(stage,key) for key in ('creation_attempted','creation_returned','pending_creation',
                    'publication_attempted','publication_returned','pending_publication','published','uncertain','cleaned',
                    'cleanup_attempted','cleanup_returned','pending_cleanup')})
        stage.checkpoint = checkpoint
        self.stages.append(stage)
        on_owned_change(checkpoint())
        stage.creation_attempted = True
        directory.mkdir()
        stage.creation_returned, stage.pending_creation = True, False
        stage.identity = [directory.stat().st_dev, directory.stat().st_ino]
        on_owned_change(checkpoint())
        return stage

    def observe_owned_stage(self, stage, lease):
        assert stage.lease is lease and lease.active
        if self.fault == 'sidecar' and stage.filename.exists():
            raise ExecutionFailure('first_save_sidecars', 'Fake foreign stage member.', uncertain=False)
        entries = list(stage.directory.iterdir())
        if entries not in ([], [stage.filename]):
            raise RuntimeError('Fake complete stage inventory changed')
        return dict(checkpoint=stage.checkpoint(), file=native_file_facts(str(stage.filename),'part') if entries else None,
                    empty=not entries)

    def inspect_staged(self, stage):
        stage.facts = native_file_facts(str(stage.filename), 'part')
        return deepcopy(stage.facts)

    def observe_destination(self, token):
        path = Path(token['destination'])
        return native_file_facts(str(path), 'part') if path.exists() else None

    def publish(self, stage, lease):
        assert lease.active and stage.facts is not None and not stage.publication_attempted
        self.publications += 1
        stage.publication_attempted = stage.pending_publication = stage.uncertain = True
        destination = Path(lease.token['destination'])
        if self.fault == 'conflict':
            destination.write_bytes(b'foreign destination must remain')
            stage.pending_publication = stage.uncertain = False
            return {**stage.checkpoint(), 'status':'conflict', 'destination':str(destination)}
        stage.filename.rename(destination)  # Fake controlled move, not NTFS acceptance.
        if self.fault == 'publish_throw':
            raise RuntimeError('Lost fake publication acknowledgement')
        if self.fault == 'publish_unknown':
            return {**stage.checkpoint(), 'status':'unknown', 'destination':str(destination)}
        stage.publication_returned = stage.published = True
        stage.pending_publication = stage.uncertain = False
        return {**stage.checkpoint(), 'status':'published', 'destination':str(destination),
                'destination_file':native_file_facts(str(destination),'part'), 'primitive':'fake_no_replace_move'}

    def cleanup_owned_stage(self, stage, lease, *, verified_terminal):
        assert verified_terminal is True and lease.active and not stage.pending_publication and not stage.uncertain
        self.cleanups += 1
        stage.cleanup_attempted = stage.pending_cleanup = True
        if self.fault == 'cleanup_throw':
            stage.uncertain = True
            raise ExecutionFailure('first_save_cleanup_unknown', 'Fake cleanup acknowledgement lost.', uncertain=True)
        if stage.filename.exists():
            assert native_file_facts(str(stage.filename),'part') == stage.facts
            stage.filename.unlink()
        stage.cleaned = stage.cleanup_returned = True
        stage.pending_cleanup = False
        return dict(status='retained_empty_owned_directory', directory=str(stage.directory),
            directory_identity=deepcopy(stage.identity), file_removed=True, destination_removed=False)


class FirstSaveAdapter(OpenAdapter):
    def __init__(self, folder):
        super().__init__(folder)
        self.copy_calls = 0
        self.copy_fault = self.stage_fault = self.final_fault = self.first_close_fault = None
        self.oracle_states = {}
        self.copy_states = {}
        self.native_events = []
        self.stage_close_activates_survivor = False

    def first_save_part_snapshot(self, current):
        self.alive(current)
        return dict(scope=SNAPSHOT_SCOPE, configuration=current.state['active_configuration'],
            configurations=deepcopy(current.state['configurations']), solid_body_count=1,
            selection_count=len(current.view['selection']),
            clone_state=deepcopy(self.oracle_states.get(current.identity, dict(
                complete_geometry={'box':[40,20,12],'volume':9600,'full_fake_faces':['a','b','c','d','e','f']},
                complete_graph={'features':['Эскиз основания','Основание'],'relations':['fully_defined'],
                                'dimensions':[40,20,12]}, units='mm', material=''))),
            references=[dict(kind='feature',role='base',token=f'feature:{current.identity}'),
                        dict(kind='body',role='solid:0',token=f'body:{current.identity}')])

    def native_first_save_guard(self, survivor_models, source_document_id):
        assert self.active not in survivor_models
        return Guard(self, survivor_models, [source_document_id])

    def new_native_first_save_copy_receipt(self, current, filename, configuration):
        self.alive(current)
        return SimpleNamespace(model=current, filename=filename, configuration=configuration,
            native_call_attempted=False,pending_copy=False,native_call_returned=False,
            acknowledgement_valid=False,success=None,errors=None,warnings=None,raw_return=None)

    def save_native_first_save_copy(self, receipt):
        assert self.busy and self.active is receipt.model and not receipt.native_call_attempted
        assert self.checkpoint_lookup()['mutation']['verification']['native_steps'][-1]['phase']=='pending'
        self.copy_calls += 1
        self.native_events.append('copy')
        receipt.native_call_attempted = receipt.pending_copy = True
        if self.copy_fault=='throw_before':raise RuntimeError('Fake copy return lost before effect')
        if self.copy_fault not in ('false','malformed'):
            Path(receipt.filename).write_bytes(b'artificial persisted complete part')
            self.kinds[receipt.filename]='part'
            self.inventories[receipt.filename]=dict(dependencies=[],configurations=[receipt.configuration])
            self.copy_states[receipt.filename]=(deepcopy(self.first_save_part_snapshot(receipt.model)['clone_state']),deepcopy(receipt.model.view))
        if self.copy_fault=='source_geometry':
            self.oracle_states[receipt.model.identity]={'full_fake_changed_geometry':True}
        if self.copy_fault=='neighbor_geometry':
            neighbor=next(x for x in self.models if x is not receipt.model)
            self.oracle_states[neighbor.identity]={'full_fake_changed_geometry':True}
        if self.copy_fault=='source_dirty':receipt.model.state['needs_save']=False
        if self.copy_fault=='foreign_cwd':self.app['current_directory']=str(self.folder/'Чужая папка')
        if self.copy_fault=='throw_after':raise RuntimeError('Fake copy return lost after effect')
        receipt.native_call_returned,receipt.pending_copy=True,False
        receipt.acknowledgement_valid=self.copy_fault!='malformed'
        receipt.success=self.copy_fault not in ('false','malformed')
        receipt.errors,receipt.warnings=(1 if self.copy_fault=='false' else 0),(1 if self.copy_fault=='warning' else 0)
        receipt.raw_return=(receipt.success,receipt.errors,receipt.warnings)

    def open_native_document(self, receipt):
        assert self.busy and not receipt.native_call_attempted
        is_stage=Path(receipt.filename).name=='Первая запись.SLDPRT'
        fault=self.stage_fault if is_stage else self.final_fault
        self.native_events.append('open_stage' if is_stage else 'open_final')
        self.open_calls += 1
        receipt.native_call_attempted=receipt.pending_open=True
        if fault=='throw_before':raise RuntimeError('Fake open return lost before effect')
        self.app['current_directory']=str(Path(receipt.filename).parent)
        if fault=='null':
            receipt.native_call_returned,receipt.pending_open,receipt.acknowledgement_valid=True,False,True
            receipt.errors,receipt.warnings=1,0
            return
        if not is_stage:
            self.kinds[receipt.filename]='part'
            self.inventories[receipt.filename]=dict(dependencies=[],configurations=[receipt.configuration])
        current=self._load(receipt.filename,configuration=receipt.configuration,read_only=receipt.read_only,visible=True)
        source=next(x for x in self.models if not x.state['path'])
        clone,view=self.copy_states[next(iter(self.copy_states))]
        self.oracle_states[current.identity]=deepcopy(clone)
        current.view=deepcopy(view)
        self.active=current
        if fault=='throw_after':raise RuntimeError('Fake open return lost after effect')
        receipt.model=receipt.raw_model=current;receipt.identity=current.identity
        receipt.returned_new_identity=receipt.acknowledgement_valid=receipt.native_call_returned=True
        receipt.pending_open=False;receipt.errors=0;receipt.warnings=0
        if fault=='geometry':self.oracle_states[current.identity]={'full_fake_foreign_geometry':True}
        if fault=='view':current.view['scale']=8.
        if fault=='foreign_model':self.add('Чужая новая модель',saved=False)
        if fault=='source_geometry':self.oracle_states[source.identity]={'full_fake_foreign_source':True}
        if fault=='foreign_cwd':self.app['current_directory']=str(self.folder/'Чужая папка')
        if fault=='file':Path(receipt.filename).write_bytes(b'foreign bytes after native open')

    def new_native_first_save_close_receipt(self,current,native_name):
        self.alive(current)
        return SimpleNamespace(model=current,native_name=native_name,native_call_attempted=False,
            pending_close=False,native_call_returned=False,acknowledgement_valid=False)

    def close_native_first_save_document(self,receipt):
        source=not receipt.model.state['path']
        self.native_events.append('close_source' if source else 'close_stage')
        receipt.native_call_attempted=receipt.pending_close=True
        fault=self.first_close_fault if source else None
        if fault=='throw_before':raise RuntimeError('Fake source close before effect')
        if fault!='no_effect':
            super().close_native_document(receipt.model,receipt.native_name)
        if fault=='throw_after':raise RuntimeError('Fake source close after effect')
        receipt.native_call_returned,receipt.pending_close,receipt.acknowledgement_valid=True,False,True
        if not source and self.stage_close_activates_survivor:self.active=self.guarded[0]
        if fault=='final_mode':self.active.mode['read_only_state']=1

    def restore_native_open_directory(self,receipt):
        self.native_events.append('restore_directory')
        assert self.busy and not receipt.native_call_attempted
        ledger=self.checkpoint_lookup()['mutation']['verification']['native_steps']
        assert ledger[-1]==dict(sequence=len(ledger),name='first_save_restore_directory_native',phase='pending',
            evidence=dict(original_directory=receipt.original_directory,expected_current_directory=receipt.expected_current_directory))
        if self.directory_fault=='precall_changed':self.app['current_directory']=str(self.folder/'Чужая папка')
        if self.app['current_directory']!=receipt.expected_current_directory:
            raise ExecutionFailure('native_open_directory_changed','CWD changed before setter.',uncertain=False)
        assert Path(receipt.original_directory).is_absolute() and Path(receipt.original_directory).is_dir()
        self.directory_calls+=1
        receipt.native_call_attempted=receipt.pending_directory=True
        if self.directory_fault=='throw_before':raise RuntimeError('Setter return lost before effect')
        if self.directory_fault not in ('false','invalid_ack','no_effect'):
            self.app['current_directory']=receipt.original_directory
        if self.directory_fault=='throw_after':raise RuntimeError('Setter return lost after effect')
        receipt.native_call_returned,receipt.pending_directory=True,False
        receipt.raw_return=None if self.directory_fault=='invalid_ack' else self.directory_fault!='false'
        receipt.acknowledgement_valid=type(receipt.raw_return) is bool
        receipt.setter_succeeded=receipt.raw_return is True
        if self.directory_fault=='foreign_application':self.app['search_folders']='foreign change after setter'
        if not receipt.acknowledgement_valid or not receipt.setter_succeeded:
            raise ExecutionFailure('native_open_directory_unacknowledged','Setter ACK is not true.',uncertain=True)


@pytest.fixture
def setup(tmp_path):
    adapter=FirstSaveAdapter(tmp_path)
    source=adapter.add('Новая контрольная деталь',saved=False)
    source.state['needs_save']=True
    neighbor=adapter.add('Соседняя рабочая деталь')
    neighbor.state['needs_save']=True
    source.state['configurations']=['Основная'];neighbor.state['configurations']=['Основная']
    adapter.active=source
    original=tmp_path/'Исходная папка';original.mkdir()
    adapter.app['current_directory']=str(original)
    docs=DocumentCatalog(adapter);store=JobStore(tmp_path/'jobs.sqlite');files=FakeFiles()
    catalog=NativeFirstSaveCatalog(docs,store,'epoch',files=files)
    source_id=next(row['document_id'] for row in docs.list()['documents'] if not row['path'])
    filename=str(tmp_path/'Сохранённая контрольная деталь.SLDPRT')
    preparation=catalog.prepare_first_save(source_id,'Основная',filename)
    runner=JobRunner(store,Worker())
    def run(request='first-save',p=None,**changes):
        p=p or preparation
        data=dict(document_id=p['document_id'],configuration=p['configuration'],filename=p['filename'],expected_revision=p['revision'])
        data.update(changes)
        adapter.checkpoint_lookup=lambda:next(row for row in store.list(limit=100)['items'] if row['request_id']==request)
        return runner.submit(request,'document.first_save_native',data,lambda op:catalog.first_save(op,**data),
            context=data,mutates=True,pass_operation_id=True,verify=lambda result:result['verified'] is True)
    yield SimpleNamespace(a=adapter,source=source,neighbor=neighbor,d=docs,s=store,f=files,c=catalog,p=preparation,run=run)
    docs.close();store.close()


def native_steps(result):
    return [(row['name'],row['phase']) for row in result['mutation']['verification']['native_steps']]


def test_complete_fake_roundtrip_replaces_only_source_and_replays_once(setup):
    x=setup
    neighbor=(deepcopy(x.neighbor.state),deepcopy(x.neighbor.view),Path(x.neighbor.state['path']).read_bytes())
    result=x.run()
    assert result['status']=='succeeded' and result['mutation']['phase']=='committed',result
    value=result['result']['value']
    assert value['document_id']!=x.p['document_id'] and value['retired_document_ids']==[x.p['document_id']]
    assert value['source_references_retired'] is True and value['resolve_saved_references_again'] is True
    assert x.source.retired is True and x.a.active.state['path']==x.p['filename']
    assert x.a.active.mode['read_only_state']==0 and x.a.dead_getters==0
    assert (x.neighbor.state,x.neighbor.view,Path(x.neighbor.state['path']).read_bytes())==neighbor
    assert x.a.copy_calls==1 and x.a.open_calls==2 and x.a.calls==2
    assert x.f.publications==1 and x.f.cleanups==1 and x.a.directory_calls==1
    assert x.a.native_events==['copy','open_stage','close_stage','open_final','close_source','restore_directory']
    assert result['result']['after']['semantic']['application']==x.p['baseline']['application']
    assert value['staging_cleanup']['destination_removed'] is False
    assert x.run()==result and x.a.copy_calls==1 and x.f.publications==1
    assert not x.c.receipts and not x.a.busy and all(not lease.active for lease in x.f.leases)


def test_stage_reader_close_releases_survivor_ui_then_activates_exact_source_once(setup):
    x=setup;x.a.stage_close_activates_survivor=True
    result=x.run()
    assert result['status']=='succeeded',result
    assert x.a.activations==[x.source] and x.a.dead_getters==0
    steps=native_steps(result)
    release=steps.index(('first_save_release_survivor_ui','returned'))
    activation=steps.index(('first_save_activate_source_native','pending'))
    publication=steps.index(('first_save_publish','pending'))
    assert release < activation < publication
    assert x.run()==result and x.a.activations==[x.source]


@pytest.mark.parametrize('fault',['activation_throw','activation_no_effect','activation_release_foreign'])
def test_unconfirmed_source_activation_has_no_publication_retirement_or_retry(setup,fault):
    x=setup;x.a.stage_close_activates_survivor=True
    if fault=='activation_release_foreign':x.a.fault=fault
    else:x.a.open_fault=fault
    result=x.run()
    assert result['status']=='unknown',result
    assert not x.source.retired and x.a.calls==1 and x.f.publications==0 and x.f.cleanups==0
    assert len(x.a.activations)==int(fault!='activation_release_foreign')
    assert x.run()==result and len(x.a.activations)==int(fault!='activation_release_foreign')


@pytest.mark.parametrize('change',['revision','source_geometry','neighbor_geometry','source_view','active','config','file'])
def test_stale_full_checkpoint_does_not_create_stage_or_copy(setup,change):
    x=setup;changes={}
    if change=='revision':changes['expected_revision']='rev_stale'
    elif change.endswith('geometry'):
        current=x.source if change.startswith('source') else x.neighbor
        x.a.oracle_states[current.identity]={'full_fake_changed_shape':True}
    elif change=='source_view':x.source.view['scale']=2.
    elif change=='active':x.a.active=x.neighbor
    elif change=='config':x.source.state['active_configuration']='Чужая конфигурация'
    else:Path(x.neighbor.state['path']).write_bytes(b'foreign existing native file')
    result=x.run(**changes)
    assert result['status']=='failed' and result['error']['requires_reconciliation'] is False,result
    assert x.f.creations==0 and x.a.copy_calls==0 and not x.c.receipts


@pytest.mark.parametrize('change',['saved','selected','multiple_configs','read_only','hidden','wrong_type'])
def test_unsupported_source_or_baseline_refused_before_write(setup,change):
    x=setup
    if change=='saved':x.source.state['path']=x.neighbor.state['path']
    elif change=='selected':x.source.view['selection']=['Выбранная грань']
    elif change=='multiple_configs':x.source.state['configurations'].append('Вариант')
    elif change=='read_only':x.source.mode['read_only_state']=1
    elif change=='hidden':x.a.windows=[(m,v) for m,v in x.a.windows if m is not x.neighbor]
    else:x.neighbor.state['document_type']='assembly'
    result=x.run()
    assert result['status']=='failed' and x.f.creations==0 and x.a.copy_calls==0,result


def test_existing_destination_and_nonrussian_name_are_prewrite_failures(setup):
    x=setup
    Path(x.p['filename']).write_bytes(b'foreign destination')
    result=x.run()
    assert result['status']=='failed' and Path(x.p['filename']).read_bytes()==b'foreign destination'
    assert x.f.creations==0 and x.a.copy_calls==0
    with pytest.raises(ExecutionFailure):x.c.prepare_first_save(x.p['document_id'],'Основная',str(x.a.folder/'Foreign.SLDPRT'))


@pytest.mark.parametrize('fault',['false'])
def test_normal_false_without_any_copy_effect_is_known_failure_with_truthful_empty_stage(setup,fault):
    x=setup;x.a.copy_fault=fault
    result=x.run()
    assert result['status']=='failed' and result['mutation']['phase']=='rolled_back',result
    assert result['error']['requires_reconciliation'] is False
    assert x.a.copy_calls==1 and x.a.open_calls==0 and x.a.calls==0 and x.f.cleanups==0
    assert x.source in x.a.models and not x.source.retired and x.source.state['path']==''
    assert result['mutation']['verification']['evidence']['after']['stage']['empty'] is True
    assert not Path(x.p['filename']).exists() and not x.c.receipts


@pytest.mark.parametrize('code',[True,None,-1,2**31])
def test_null_reader_with_malformed_native_code_cannot_authorize_cleanup(setup,code):
    x=setup;x.a.stage_fault='null'
    original=x.a.open_native_document
    def open_with_malformed_code(receipt):
        original(receipt);receipt.errors=code
    x.a.open_native_document=open_with_malformed_code
    result=x.run()
    assert result['status']=='unknown',result
    assert x.a.open_calls==1 and x.a.calls==0 and x.a.directory_calls==0
    assert x.f.publications==0 and x.f.cleanups==0 and not x.source.retired
    assert x.run()==result and x.a.open_calls==1
    assert not Path(x.p['filename']).exists() and x.c.receipts


@pytest.mark.parametrize('kind',['stage_null','conflict'])
def test_verified_noeffect_failure_restores_source_and_removes_only_staged_artifact(setup,kind):
    x=setup
    if kind=='stage_null':x.a.stage_fault='null'
    else:x.f.fault='conflict'
    result=x.run()
    assert result['status']=='failed' and result['mutation']['phase']=='rolled_back',result
    assert result['error']['requires_reconciliation'] is False and x.a.active is x.source
    assert x.f.cleanups==1 and x.a.directory_calls==1 and not x.source.retired
    assert x.a.app==x.p['baseline']['application'] and not x.c.receipts
    if kind=='conflict':assert Path(x.p['filename']).read_bytes()==b'foreign destination must remain'
    else:assert not Path(x.p['filename']).exists()


@pytest.mark.parametrize('fault',['throw_before','throw_after','malformed','warning','source_geometry',
                                  'neighbor_geometry','source_dirty','foreign_cwd'])
def test_copy_pending_foreign_or_unverified_artifact_is_unknown_without_cleanup(setup,fault):
    x=setup;x.a.copy_fault=fault
    result=x.run()
    assert result['status']=='unknown' and result['error']['requires_reconciliation'] is True,result
    assert x.a.copy_calls==1 and x.a.calls==0 and x.f.publications==0 and x.f.cleanups==0
    assert x.source in x.a.models and not x.source.retired and result['operation_id'] in x.c.receipts
    assert x.run()==result and x.a.copy_calls==1
    assert x.run('blocked')['error']['code']=='document_mutation_blocked'


@pytest.mark.parametrize('phase',['stage','final'])
@pytest.mark.parametrize('fault',['throw_before','throw_after','geometry','view','foreign_model','source_geometry','foreign_cwd','file'])
def test_unconfirmed_readback_never_retires_source_or_retries_native_open(setup,phase,fault):
    x=setup
    setattr(x.a,phase+'_fault',fault)
    result=x.run()
    assert result['status']=='unknown' and result['error']['requires_reconciliation'] is True,result
    assert not x.source.retired and x.source in x.a.models
    assert x.a.calls==int(phase=='final') and result['operation_id'] in x.c.receipts
    assert x.run()==result and x.a.open_calls==(2 if phase=='final' else 1)
    assert x.f.publications==int(phase=='final')


@pytest.mark.parametrize('fault',['publish_unknown','publish_throw','cleanup_throw'])
def test_unknown_filesystem_effect_retains_source_and_destination_without_retry(setup,fault):
    x=setup;x.f.fault=fault
    result=x.run()
    assert result['status']=='unknown' and not x.source.retired,result
    assert x.a.open_calls==1 and x.a.calls==1 and x.f.publications==1
    assert Path(x.p['filename']).exists() and x.run()==result and x.f.publications==1


@pytest.mark.parametrize('fault',['throw_before','throw_after','no_effect','final_mode'])
def test_unconfirmed_source_retirement_is_unknown_without_second_close_or_directory_setter(setup,fault):
    x=setup;x.a.first_close_fault=fault
    result=x.run()
    assert result['status']=='unknown' and result['operation_id'] in x.c.receipts,result
    assert x.a.open_calls==2 and x.f.publications==1 and x.a.directory_calls==0
    assert x.run()==result and x.a.native_events.count('close_source')==1 and x.a.dead_getters==0


@pytest.mark.parametrize('fault',['throw_before','throw_after','false','invalid_ack','no_effect','foreign_application','precall_changed','constructor'])
def test_directory_restoration_failure_preserves_unknown_after_one_source_retirement(setup,fault):
    x=setup;x.a.directory_fault=fault
    result=x.run()
    assert result['status']=='unknown' and x.source.retired,result
    assert x.a.native_events.count('close_source')==1 and x.a.open_calls==2
    assert x.a.directory_calls==int(fault not in ('precall_changed','constructor'))
    assert x.run()==result and x.a.native_events.count('close_source')==1


@pytest.mark.parametrize('name,phase',[('first_save_stage_create','pending'),('first_save_stage_create','returned'),
    ('first_save_copy_native','pending'),('first_save_copy_native','returned'),
    ('first_save_publish','pending'),('first_save_publish','returned'),
    ('first_save_cleanup_stage','pending'),('first_save_cleanup_stage','returned'),
    ('first_save_close_source_native','pending'),('first_save_close_source_native','returned')])
def test_durable_step_failure_never_triggers_extra_native_or_filesystem_cleanup(setup,monkeypatch,name,phase):
    x=setup;original=x.s.record_mutation_step
    def fail(op,**kwargs):
        if (kwargs['name'],kwargs['phase'])==(name,phase):raise OSError('Fake journal lost')
        return original(op,**kwargs)
    monkeypatch.setattr(x.s,'record_mutation_step',fail)
    result=x.run()
    assert result['status']=='unknown' and result['error']['requires_reconciliation'] is True,result
    counts=(x.a.copy_calls,x.a.open_calls,x.a.calls,x.f.publications,x.f.cleanups,x.a.directory_calls)
    assert x.run()==result and counts==(x.a.copy_calls,x.a.open_calls,x.a.calls,x.f.publications,x.f.cleanups,x.a.directory_calls)
    assert result['operation_id'] in x.c.receipts


def snapshot():
    return dict(scope=SNAPSHOT_SCOPE,configuration='Основная',configurations=['Основная'],solid_body_count=1,
        selection_count=0,clone_state={'full_fake_geometry':[1,2,3]},
        references=[dict(kind='body',role='solid:0',token='old')])


def test_clone_reference_mapping_is_structural_bijection_not_raw_pid_equality():
    a=snapshot();b=deepcopy(a);b['references'][0]['token']='new'
    assert clone_mapping(a,b)==[dict(kind='body',role='solid:0',source_token='old',saved_token='new')]
    b['clone_state']['unmapped_pid']='foreign'
    with pytest.raises(ExecutionFailure):clone_mapping(a,b)


@pytest.mark.parametrize('changes',[{'scope':'foreign'},{'solid_body_count':True},{'selection_count':True},
    {'configurations':['Основная','Вариант']},{'clone_state':{}},{'references':[]},
    {'references':[dict(kind='body',role='solid:0',token='old')]*2}])
def test_malformed_or_incomplete_oracle_is_not_accepted(changes):
    value=snapshot();value.update(changes)
    with pytest.raises((ExecutionFailure,ValueError)):validated_part_snapshot(value)
