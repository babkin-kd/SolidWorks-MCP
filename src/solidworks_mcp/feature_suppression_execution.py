"""Suppression domain executor; guarded writes and full independent admission."""
from copy import deepcopy

from .documents import rejected
from .jobs import ExecutionFailure, _json
from .mutations import MutationCoordinator, PreparedMutation
from .cad_owned_feature_suppression import NativeOwnedFeatureSuppression
from .owned_suppression_postconditions import (
    verified_owned_suppression, verified_owned_return, owned_body_name_delta)


class FeatureSuppressionExecutionMixin:
    def set_suppressed(self, operation_id, document_id, configuration, object_id,
                       suppressed, expected_revision):
        context = dict(entries=(), binding=None, retained=None, action=None, actions=[],
            manager=None, guards=[], guarded_ids=(), released=False, release_attempted=False,
            pending_release=False, journal_failed=False, pending_body_name=False, verified_mode=None)

        def record(name, phase, evidence):
            context['journal_failed'] = True
            self.store.record_mutation_step(operation_id,name='suppression_'+name,
                phase=phase,evidence=evidence)
            context['journal_failed'] = False

        def uncertain():
            return (context['journal_failed'] or context['pending_release'] or context['pending_body_name']
                or any(action.receipt.pending_native_step is not None or action.receipt.journal_failed
                       for action in context['actions']))

        def prepare():
            if len(self.receipts) >= 1000:
                raise rejected('suppression_receipt_budget','Reconcile retained uncertain receipts before another write.')
            public = self.prepare(document_id,configuration,object_id,suppressed)
            binding, original = self._resolve(document_id,configuration,object_id)
            retained = self.contexts[(document_id,object_id)]
            entries, state = self._capture(binding,retained['producer'])
            if _json(state) != _json(public['baseline']) or original != public['original_suppressed']:
                raise rejected('suppression_snapshot_changed','Complete prepared state changed before checkpointing.')
            action = NativeOwnedFeatureSuppression(self.ownership,binding,suppressed,
                recorder=lambda name,phase,evidence:record('apply_'+name,phase,evidence))
            target = next(entry for entry in entries if entry.document_id == document_id)
            context.update(binding=binding,retained=retained,entries=entries,action=action,target=target)
            context['actions'].append(action)
            self.receipts[operation_id] = context
            return PreparedMutation(public['revision'],dict(scope=public['scope'],baseline=state,
                original_base=retained['baseline'],object_id=object_id,suppressed=suppressed,
                original_suppressed=original,feature_pid_hex=binding.persistent_id.hex()),effect_scope='application')

        def validate(prepared):
            public = self._prepare(document_id,configuration,object_id,suppressed,context['guarded_ids'])
            return public['revision'] == prepared.revision

        def acquire(label):
            record(label,'pending',dict(document_ids=[entry.document_id for entry in context['entries']]))
            manager = self.adapter.native_open_guard(tuple(entry.model for entry in context['entries']),
                tuple(entry.document_id for entry in context['entries']))
            context.update(manager=manager,guarded_ids=tuple(entry.document_id for entry in context['entries']),
                released=False,release_attempted=False)
            context['guards'].append(manager)
            manager.__enter__()
            record(label,'returned',deepcopy(manager.evidence))

        def release(*args, journal=True):
            if context['release_attempted']:
                raise ExecutionFailure('suppression_guard_release_repeated','Guard release is one-shot.',uncertain=True)
            label = 'guard_release_'+str(len(context['guards']))
            if journal: record(label,'pending',dict(document_ids=list(context['guarded_ids'])))
            context.update(release_attempted=True,pending_release=True)
            value = context['manager'].__exit__(*(args or (None,None,None)))
            context.update(pending_release=False,released=True,guarded_ids=())
            if journal: record(label,'returned',deepcopy(context['manager'].evidence))
            return value

        def inspect(prepared):
            entries, state = self._capture(context['binding'],context['retained']['producer'],context['guarded_ids'])
            if [entry.identity for entry in entries] != [entry.identity for entry in context['entries']]:
                raise rejected('suppression_session_changed','Original full model incarnations changed.')
            return dict(state=state,pending=uncertain(),guard_released=context['released'],
                native_actions=[action.receipt.evidence() for action in context['actions']],
                original_files=self.sessions.census._disk_files(prepared.before['baseline']['semantic']))

        def effect(before, observed, requested):
            if (observed['pending'] is not False
                    or observed['original_files'] != before['baseline']['semantic']['files']):
                return False
            oracle = before['original_base']
            return (verified_owned_suppression(oracle,observed['state'],document_id,context['binding'].native_id)
                if requested else verified_owned_return(oracle,observed['state'],document_id))

        def repair_body_name(prepared):
            """A distinct guarded write, only after a full independent name-only proof."""
            observed = inspect(prepared)
            if uncertain() or observed['original_files'] != prepared.before['baseline']['semantic']['files']:
                raise ExecutionFailure('suppression_body_return_unconfirmed','No repair after pending or foreign file effects.',uncertain=True)
            proof = owned_body_name_delta(prepared.before['original_base'],observed['state'],document_id)
            if proof is None: return
            acquire('body_name_guard')
            closing = inspect(prepared)
            if owned_body_name_delta(prepared.before['original_base'],closing['state'],document_id) != proof:
                raise ExecutionFailure('suppression_body_return_changed','The independently proved name-only effect changed.',uncertain=True)
            binding, state = self._resolve(document_id,configuration,object_id)
            if binding is not context['binding'] or state is not False:
                raise ExecutionFailure('suppression_body_owner_changed','Original current owner must be unsuppressed.',uncertain=True)
            snapshot = prepared.before['original_base']['snapshots'][document_id]
            refs = [row for row in snapshot['references'] if row['kind'] == 'body' and row['role'] == 'body:0']
            if len(refs) != 1:
                raise ExecutionFailure('suppression_body_pid_unconfirmed','Exactly one original body PID required.',uncertain=True)
            pid = bytes.fromhex(refs[0]['token'])
            body = self.adapter.resolve_persistent_id(binding.model,pid,'body')
            bodies = self.adapter.bodies(binding.model,'all')
            if (len(bodies) != 1 or self.adapter.identity(bodies[0]) != self.adapter.identity(body)
                    or self.adapter.persistent_id(binding.model,body) != pid or body.Name != proof['previous_name']):
                raise ExecutionFailure('suppression_body_pid_changed','Exact current own body changed before name repair.',uncertain=True)
            context['pending_body_name'] = True
            record('body_name','pending',dict(body_pid_hex=pid.hex(),**proof))
            body.Name = proof['original_name']
            record('body_name','returned',dict(native_call_returned=True))
            context['pending_body_name'] = False
            if body.Name != proof['original_name']:
                raise ExecutionFailure('suppression_body_name_unconfirmed','Body name readback failed.',uncertain=True)
            release()
            # Whole restored BASE/session re-read; the setter/readback is insufficient.
            if not effect(prepared.before,inspect(prepared),False):
                raise ExecutionFailure('suppression_body_return_unconfirmed','Full body-name repair postcondition failed.',uncertain=True)

        def apply(prepared):
            context['action'].apply()
            release()
            if suppressed is False: repair_body_name(prepared)
            return dict(document_id=document_id,configuration=configuration,object_id=object_id,suppressed=suppressed)

        def verify(before, after, value):
            good = after['guard_released'] is True and effect(before,after,suppressed)
            record('released_check','pending',dict(document_id=document_id))
            record('released_check','returned',dict(verified=good,observed=after))
            if good: context['verified_mode'] = 'effect'
            return good

        def restore(before, prepared):
            if uncertain():
                raise ExecutionFailure('suppression_restore_unconfirmed','Pending native/storage effects prohibit an inverse.',uncertain=True)
            observed = inspect(prepared)
            if effect(before,observed,before['original_suppressed']):
                if not context['release_attempted']: release()
                return
            if not effect(before,observed,suppressed):
                raise ExecutionFailure('suppression_restore_unconfirmed','Only the complete proved own transition permits an inverse.',uncertain=True)
            if not context['release_attempted']: release()
            acquire('restoration_guard')
            if not effect(before,inspect(prepared),suppressed):
                raise ExecutionFailure('suppression_restore_changed','The proved own effect changed before its inverse.',uncertain=True)
            inverse = NativeOwnedFeatureSuppression(self.ownership,context['binding'],before['original_suppressed'],
                recorder=lambda name,phase,evidence:record('inverse_'+name,phase,evidence))
            context['actions'].append(inverse)
            inverse.apply()
            release()
            if before['original_suppressed'] is False: repair_body_name(prepared)

        def restored(before, after):
            good = after['guard_released'] is True and effect(before,after,before['original_suppressed'])
            if good:
                record('restored_check','pending',dict(document_id=document_id))
                record('restored_check','returned',dict(verified=True,observed=after))
                context['verified_mode'] = 'restored'
            return good

        class Guard:
            def __enter__(self):
                acquire('execution_guard')
                return self
            def __exit__(self, *args):
                if not context['release_attempted'] and context['manager'] is not None:
                    return release(*args,journal=False)
                return False
            @property
            def evidence(self):
                return dict(scope='owned_feature_suppression_guard_v1',
                    native_guards=[deepcopy(manager.evidence) for manager in context['guards']],
                    guard_released=context['released'],pending_release=context['pending_release'],
                    journal_failed=context['journal_failed'],full_release_check=context['verified_mode'])

        try:
            result = MutationCoordinator(self.store,self.connection_epoch).execute(operation_id,
                document_id=document_id,configuration=configuration,expected_revision=expected_revision,
                prepare=prepare,validate=validate,apply=apply,inspect=inspect,verify=verify,
                restore=restore,verify_restored=restored,guard=lambda _:Guard())
        except ExecutionFailure as error:
            if any(action.receipt.attempted for action in context['actions']):
                # Even a restored or uncertain transition may recreate topology.
                # Retire only in-memory geometry aliases; no COM or recovery here.
                context['target'].geometry.clear()
            if not error.uncertain: self.receipts.pop(operation_id,None)
            raise
        # No fallible getter/storage/inverse after the domain committed boundary.
        retained = context['retained']
        if suppressed:
            retained['operation_id'] = operation_id
            retained['committed_result_json'] = _json(result)
            self.contexts[(document_id,object_id)] = retained
        else:
            self.contexts.pop((document_id,object_id),None)
        context['target'].geometry.clear()
        self.receipts.pop(operation_id,None)
        return result
