"""Durable one-shot own leaf deletion; no automatic inverse of a deleted feature."""
from copy import deepcopy

from .documents import rejected
from .jobs import ExecutionFailure,_json
from .mutations import MutationCoordinator,PreparedMutation
from .cad_owned_leaf_deletion import NativeOwnedLeafDeletion
from .rectangle_construction import BlindRectangleExtrusion
from .rectangle_postconditions import same_unmodified_session
from .owned_leaf_deletion_postconditions import verified_owned_leaf_deletion


class OwnLeafDeletionExecutionMixin:
    def delete(self,operation_id,document_id,configuration,object_id,expected_revision):
        context=dict(binding=None,entries=(),target=None,action=None,manager=None,guards=[],guarded_ids=(),
            released=False,release_attempted=False,pending_release=False,journal_failed=False,verified_mode=None)

        def record(name,phase,evidence):
            context['journal_failed']=True
            self.store.record_mutation_step(operation_id,name='leaf_'+name,phase=phase,evidence=evidence)
            context['journal_failed']=False

        def pending():
            action=context['action']
            facts={} if action is None else action.evidence()
            return (context['journal_failed'] or context['pending_release'] or facts.get('pending_apply',False)
                or facts.get('pending_native_step') is not None or facts.get('journal_failed',False)
                or facts.get('selection_uncertain',False) or facts.get('view_state_uncertain',False))

        def prepare():
            if len(self.receipts)>=1000:raise rejected('leaf_receipt_budget','Reconcile retained receipts before another deletion.')
            public=self.prepare(document_id,configuration,object_id)
            binding,_=self._owned(document_id,configuration,object_id)
            entries,state=self._capture_current(binding)
            if _json(state)!=_json(public['baseline']):raise rejected('leaf_revision_changed','Complete prepared state changed.')
            action=NativeOwnedLeafDeletion(self.ownership,binding,recorder=record)
            closing_entries,closing=self._capture_current(binding)
            if (_json(state)!=_json(closing) or [entry.identity for entry in entries]!=[entry.identity for entry in closing_entries]):
                raise rejected('leaf_revision_changed','Full baseline changed during retained receipt construction.')
            target=next(entry for entry in entries if entry.document_id==document_id)
            context.update(binding=binding,entries=entries,target=target,action=action)
            self.receipts[operation_id]=context
            return PreparedMutation(public['revision'],dict(scope=public['scope'],baseline=state,
                feature_native_id=binding.native_id,feature_pid_hex=binding.persistent_id.hex(),
                object_id=object_id,current_definition=public['current_definition']),effect_scope='application')

        def validate(prepared):
            return self._prepare(document_id,configuration,object_id,context['guarded_ids'])['revision']==prepared.revision

        def acquire():
            record('execution_guard','pending',dict(document_ids=[entry.document_id for entry in context['entries']]))
            manager=self.adapter.native_open_guard(tuple(entry.model for entry in context['entries']),
                tuple(entry.document_id for entry in context['entries']))
            context.update(manager=manager,guarded_ids=tuple(entry.document_id for entry in context['entries']))
            context['guards'].append(manager)
            manager.__enter__()
            record('execution_guard','returned',deepcopy(manager.evidence))

        def release(*args,journal=True):
            if context['release_attempted']:raise ExecutionFailure('leaf_guard_release_repeated','Guard release is one-shot.',uncertain=True)
            if journal:record('guard_release','pending',dict(document_ids=list(context['guarded_ids'])))
            context.update(release_attempted=True,pending_release=True)
            result=context['manager'].__exit__(*(args or (None,None,None)))
            context.update(released=True,pending_release=False,guarded_ids=())
            if journal:record('guard_release','returned',deepcopy(context['manager'].evidence))
            return result

        def inspect(prepared):
            binding=context['binding']
            entries,state=self._capture_current(binding,context['guarded_ids'])
            if [entry.identity for entry in entries]!=[entry.identity for entry in context['entries']]:
                raise rejected('leaf_session_changed','The exact original model roster changed.')
            # Only current live handles are queried. The old extrusion is never
            # called after deletion, even to obtain a name or native GetID.
            members=self.adapter.features(binding.model)
            sketch=binding.receipt.borrowed_sketch
            canonical=self.adapter.identity(sketch)
            before=prepared.before['baseline']['snapshots'][document_id]
            sketch_id=before['clone_state']['sketch']['feature_native_id']
            old_rows=before['clone_state']['features']
            role='feature:'+str(next(i for i,row in enumerate(old_rows) if row['native_id']==sketch_id))
            pid=bytes.fromhex(next(row['token'] for row in before['references'] if row['kind']=='feature' and row['role']==role))
            sketch_current=self.adapter.resolve_persistent_id(binding.model,pid,'feature')
            sketch_proven=(canonical==binding.receipt.borrowed_sketch_identity
                and self.adapter.identity(sketch_current)==canonical
                and sum(self.adapter.identity(member)==canonical for member in members)==1)
            raw,status=self.adapter._extension(binding.model).GetObjectByPersistReference3(
                self.adapter._persistent_variant(binding.persistent_id))
            return dict(state=state,guard_released=context['released'],pending=pending(),
                receipt=context['action'].evidence(),sketch_canonical_and_pid_confirmed=sketch_proven,
                target_canonical_absent=not any(self.adapter.identity(member)==binding.feature_identity for member in members),
                old_feature_pid=dict(native_state=status if type(status) is int else None,native_state_is_integer=type(status) is int,
                    native_object_is_null=raw is None),
                original_files=self.observations.sessions.census._disk_files(prepared.before['baseline']['semantic']))

        def apply(prepared):
            context['action'].apply()
            release()
            definition=prepared.before['current_definition']
            return dict(document_id=document_id,configuration=configuration,
                deleted_feature_object_ids=[object_id],preserved_sketch_object_id=definition['sketch_object_id'],
                geometry_references_require_refresh=True)

        def verify(before,after,value):
            old=after['old_feature_pid']
            good=(after['pending'] is False and after['guard_released'] is True
                and after['receipt']['bridge_returned'] is True and after['receipt']['deletion_bridge_verified'] is True
                and after['sketch_canonical_and_pid_confirmed'] is True and after['target_canonical_absent'] is True
                and old['native_state_is_integer'] is True and old['native_state'] in (1,4)
                and old['native_object_is_null'] is True
                and after['original_files']==before['baseline']['semantic']['files']
                and verified_owned_leaf_deletion(before['baseline'],after['state'],document_id=document_id,
                    configuration=configuration,object_id=object_id,feature_native_id=before['feature_native_id'],
                    feature_pid_hex=before['feature_pid_hex'],
                    current_definition=BlindRectangleExtrusion.validate(**before['current_definition'])))
            record('released_check','pending',dict(document_id=document_id))
            record('released_check','returned',dict(verified=good,observed=after))
            if good:context['verified_mode']='deleted'
            return good

        def same_before(before,after):
            return (after['pending'] is False
                and after['original_files']==before['baseline']['semantic']['files']
                and same_unmodified_session(before['baseline'],after['state'],document_id)
                and _json(before['baseline']['snapshots'][document_id])==_json(after['state']['snapshots'][document_id]))

        def restore(before,prepared):
            if pending():raise ExecutionFailure('leaf_restore_unconfirmed','Pending COM/ledger prohibits recovery dispatch.',uncertain=True)
            after=inspect(prepared)
            if not same_before(before,after):
                raise ExecutionFailure('leaf_restore_unconfirmed','Deleted/changed feature is not recreated or globally undone; retain the hold.',uncertain=True)
            if not context['release_attempted']:release()

        def restored(before,after):
            good=after['guard_released'] is True and same_before(before,after)
            if good:context['verified_mode']='no_effect'
            return good

        class Guard:
            def __enter__(self):acquire();return self
            def __exit__(self,*args):
                if not context['release_attempted'] and context['manager'] is not None:return release(*args,journal=False)
                return False
            @property
            def evidence(self):
                return dict(scope='owned_leaf_deletion_guard_v1',native_guards=[deepcopy(item.evidence) for item in context['guards']],
                    guard_released=context['released'],pending_release=context['pending_release'],
                    journal_failed=context['journal_failed'],full_release_check=context['verified_mode'])

        try:
            result=MutationCoordinator(self.store,self.connection_epoch).execute(operation_id,
                document_id=document_id,configuration=configuration,expected_revision=expected_revision,
                prepare=prepare,validate=validate,apply=apply,inspect=inspect,verify=verify,
                restore=restore,verify_restored=restored,guard=lambda _:Guard())
        except ExecutionFailure as error:
            if context['action'] is not None and context['action'].attempted:context['target'].geometry.clear()
            if not error.uncertain:self.receipts.pop(operation_id,None)
            raise
        # No new COM or inverse after commit. Late in-memory retirement failure
        # still cannot turn a real deletion into a repeatable operation.
        try:
            self.ownership.forget_feature(context['binding'])
            context['target'].geometry.clear()
            references=context['target'].features.get('references',{})
            references.pop(object_id,None)
            index=context['target'].features.get('reference_index',{})
            for key,ref in tuple(index.items()):
                if ref.object_id==object_id:index.pop(key)
        except Exception as error:
            raise ExecutionFailure('leaf_retirement_unconfirmed',str(error),uncertain=True) from error
        self.receipts.pop(operation_id,None)
        return result
