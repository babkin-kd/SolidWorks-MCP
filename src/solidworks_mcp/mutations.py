"""Mutation checkpoint protocol for server-owned domain operations on the STA.

No COM dependency and no client-supplied callbacks. Each future CAD operation
must supply its own complete revision, postconditions and scoped restoration;
this protocol does not fabricate a full revision from GetUpdateStamp alone.
"""

from dataclasses import dataclass
from contextlib import nullcontext
import json

from .jobs import ExecutionFailure, _json
from .timings_v2 import timed_call


@dataclass(frozen=True)
class PreparedMutation:
    revision: str
    before: dict
    effect_scope: str = 'document'


class MutationCoordinator:
    def __init__(self, store, connection_epoch: str):
        if not isinstance(connection_epoch, str) or not connection_epoch:
            raise ValueError('A server-owned connection epoch is required.')
        self.store = store
        self.connection_epoch = connection_epoch

    def execute(self, operation_id, *, document_id, configuration, expected_revision,
                prepare, validate, apply, inspect, verify, restore, verify_restored, guard=None):
        """Run on the owning STA; JobRunner supplies the durable running job.

        prepare resolves explicit native identities and computes the operation's
        revision. validate rechecks that target/revision after the disk checkpoint,
        immediately before apply. Restoration is limited to owned changes, never
        a generic Undo of user work. Callbacks are trusted domain implementations.
        """
        try:
            if self.store.mutation_blockers(self.connection_epoch, document_id):
                raise ExecutionFailure('document_mutation_blocked',
                    'Reconcile pending/uncertain changes before another write.', uncertain=False)
            prepared = timed_call('prepare', prepare)
            if not isinstance(prepared, PreparedMutation) or not isinstance(prepared.before, dict):
                raise ValueError('Domain preparation must return a revision and JSON before-state.')
            # Detach the JSON checkpoint: subsequent callbacks cannot rewrite history.
            before = json.loads(_json(prepared.before))
            if not isinstance(expected_revision, str) or not expected_revision or prepared.revision != expected_revision:
                raise ExecutionFailure('stale_revision', 'The document revision changed; prepare a new request.', uncertain=False)
            timed_call('journal', self.store.prepare_mutation, operation_id, connection_epoch=self.connection_epoch,
                document_id=document_id, configuration=configuration,
                expected_revision=expected_revision, before_state=before,
                effect_scope='application' if guard is not None else prepared.effect_scope)
        except Exception as exc:
            # No native write has been attempted at this point.
            raise ExecutionFailure(getattr(exc, 'code', 'mutation_preparation_failed'), str(exc), uncertain=False) from exc

        entered = False
        manager = None
        operation_error = None
        try:
            # The guard can itself change application UI state. Its acquisition
            # therefore occurs after the durable application-wide checkpoint.
            manager = guard(prepared) if guard is not None else nullcontext()
            with manager:
                entered = True
                try:
                    result = self._execute_prepared(operation_id, prepared, before,
                        validate, apply, inspect, verify, restore, verify_restored)
                except Exception as exc:
                    operation_error = exc
            # A clean exit is required before recording release evidence, even
            # when native validation or scoped restoration rejected the write.
            if operation_error is not None:
                if guard is not None and hasattr(manager, 'evidence'):
                    verification = self.store.get(operation_id)['mutation'].get('verification')
                    if verification and verification['outcome'] in ('not_started', 'rolled_back'):
                        evidence = {**verification['evidence'],
                            'execution_guard': json.loads(_json(manager.evidence))}
                        timed_call('journal', self.store.verify_mutation, operation_id, outcome=verification['outcome'], evidence=evidence)
                raise operation_error
            if guard is not None and hasattr(manager, 'evidence'):
                evidence = json.loads(_json(manager.evidence))
                result['execution_guard'] = evidence
                # No rollback after a storage failure here: native effects and
                # guard release have already happened, so retain uncertainty.
                timed_call('journal', self.store.verify_mutation, operation_id, outcome='committed',
                    evidence={'after': result['after'], 'execution_guard': evidence})
            return result
        except Exception as exc:
            if not entered and isinstance(exc, ExecutionFailure) and not exc.uncertain:
                evidence = {'native_mutation_started': False, 'guard_error': str(exc)}
                if manager is not None and hasattr(manager, 'evidence'):
                    evidence['execution_guard'] = json.loads(_json(manager.evidence))
                timed_call('journal', self.store.verify_mutation, operation_id, outcome='not_started',
                    evidence=evidence)
            if operation_error is not None and exc is not operation_error:
                raise ExecutionFailure(getattr(exc, 'code', 'mutation_finalization_unconfirmed'),
                    f'{exc}; original operation error: {operation_error}', uncertain=True) from operation_error
            raise

    def _execute_prepared(self, operation_id, prepared, before,
                          validate, apply, inspect, verify, restore, verify_restored):
        try:
            if timed_call('validate', validate, prepared) is not True:
                raise ExecutionFailure('stale_revision', 'Target/revision changed before native execution.', uncertain=False)
        except Exception as exc:
            # A failed pre-write recheck must not undo a concurrent user's edit.
            timed_call('journal', self.store.verify_mutation, operation_id, outcome='not_started',
                evidence={'native_mutation_started': False, 'reason': str(exc)})
            raise ExecutionFailure(getattr(exc, 'code', 'mutation_validation_failed'), str(exc), uncertain=False) from exc

        try:
            value = timed_call('apply_bundle', apply, prepared)
            after = json.loads(_json(timed_call('postconditions', inspect, prepared)))
            if timed_call('postconditions', verify, before, after, value) is not True:
                raise ExecutionFailure('postcondition_failed', 'Native postconditions were not confirmed.')
            result = json.loads(_json({'value': value, 'before': before, 'after': after, 'verified': True}))
        except Exception as original:
            try:
                timed_call('restoration', restore, before, prepared)
                restored = json.loads(_json(timed_call('restoration', inspect, prepared)))
                if timed_call('restoration', verify_restored, before, restored) is not True:
                    raise RuntimeError('Native restoration was not verified.')
            except Exception as rollback_error:
                raise ExecutionFailure('mutation_rollback_unconfirmed',
                    f'{original}; restoration: {rollback_error}', uncertain=True) from original
            # A storage error here remains uncertain; never claim a durable rollback
            # when its verification was not recorded. JobRunner keeps the hold.
            timed_call('journal', self.store.verify_mutation, operation_id, outcome='rolled_back',
                evidence={'after': restored, 'original_error': str(original)})
            raise ExecutionFailure(getattr(original, 'code', 'mutation_failed'),
                f'{original}; scoped restoration verified.', uncertain=False) from original

        # Separate from the restoration handler: a journal failure after successful
        # COM verification must not trigger another native write as a side effect.
        timed_call('journal', self.store.verify_mutation, operation_id, outcome='committed', evidence={'after': after})
        return result
