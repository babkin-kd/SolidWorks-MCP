"""Explicit activation of one fully observed rectangular part, never open policy.

Reuses the passive first-save oracle for every baseline part. No configuration
switch, implicit activation by another tool, inverse retry, or model ownership
is inferred from a title/roster delta.
"""

from copy import deepcopy
import hashlib

from .documents import rejected
from .jobs import ExecutionFailure, _json
from .mutations import MutationCoordinator, PreparedMutation
from .native_first_save import NativeFirstSaveCatalog
from .native_document_save import MAX_OPEN_DOCUMENTS


SCOPE = 'native_rectangular_part_activation_v1'
PROFILE = 'single_rectangular_blind_base_v1'


class NativePartActivationCatalog:
    def __init__(self, documents, store, connection_epoch):
        self.documents, self.adapter, self.store = documents, documents.adapter, store
        self.connection_epoch = connection_epoch
        self.oracle = NativeFirstSaveCatalog(documents, store, connection_epoch)
        self.coordinator = MutationCoordinator(store, connection_epoch)
        self.receipts = {}

    def _state(self, document_id, configuration, guarded_ids=()):
        if (type(document_id) is not str or not document_id.strip()
                or type(configuration) is not str or not configuration.strip()):
            raise rejected('native_activation_context_invalid', 'Specify a current document ID and configuration.')
        resolved, _ = self.documents.resolve(document_id, configuration)
        entries, semantic, snapshots = self.oracle._capture(guarded_ids)
        if len(entries) >= MAX_OPEN_DOCUMENTS:
            raise rejected('native_session_budget_exceeded', 'The owned guard requires fewer than 5000 baseline models.')
        entry = next((item for item in entries if item.document_id == document_id), None)
        if entry is None or entry.identity != resolved.identity:
            raise rejected('document_not_open', 'The exact target must remain open on this connection.')
        target = next(row for row in semantic['documents'] if row['document_id'] == document_id)
        if (target['document_type'] != 'part' or target['active_configuration'] != configuration
                or target['configurations'] != [configuration] or target['mode']['read_only_state'] != 0
                or not target['visible'] or target['dependencies'] or semantic['reference_graph']
                or len([row for row in semantic['windows'] if row['document_id'] == document_id]) != 1
                or any(not row['visible'] or row['dependencies'] for row in semantic['documents'])
                or any(snapshot['clone_state'].get('profile') != PROFILE for snapshot in snapshots.values())):
            raise rejected('native_activation_profile_unsupported',
                           'Use a visible writable one-configuration rectangular part and fully supported self-contained neighbors.')
        title = target['title']
        if (type(title) is not str or not title.strip()
                or sum(row['title'].casefold() == title.casefold() for row in semantic['documents']) != 1):
            raise rejected('native_activation_title_ambiguous', 'The bound native title must be unique in the complete census.')
        before = dict(scope=SCOPE, connection_epoch=self.connection_epoch, document_id=document_id,
                      configuration=configuration, semantic=semantic, snapshots=snapshots)
        revision = 'rev_' + hashlib.sha256(_json(before).encode('utf-8')).hexdigest()
        return entry, entries, before, revision

    def prepare_activation(self, document_id, configuration):
        if self.adapter.application_busy():
            raise rejected('application_busy', 'An existing application command is never borrowed.')
        _, _, before, revision = self._state(document_id, configuration)
        return dict(document_id=document_id, configuration=configuration, revision=revision,
                    revision_scope=SCOPE, active_after_document_id=document_id,
                    already_active=before['semantic']['active_document_id'] == document_id,
                    baseline=before['semantic'], configuration_switch_supported=False)

    @staticmethod
    def _matches(before, after, active_id):
        semantic = deepcopy(before['semantic'])
        semantic['active_document_id'] = active_id
        return (_json(after['semantic']) == _json(semantic)
                and _json(after['snapshots']) == _json(before['snapshots'])
                and _json(after['original_files']) == _json(before['semantic']['files'])
                and after['pending_release'] is False and after['pending_guard_release'] is False
                and after['journal_failed'] is False and after['pending_activation'] is False)

    def activate(self, operation_id, document_id, configuration, expected_revision):
        context = dict(guarded_ids=(), activation=None, activation_confirmed=False,
                       pending_release=False, pending_guard_release=False,
                       journal_failed=False, verified_mode=None,
                       guard_release_attempted=False, guard_released=False)

        def record(name, phase, evidence):
            context['journal_failed'] = True
            self.store.record_mutation_step(operation_id, name=name, phase=phase, evidence=evidence)
            context['journal_failed'] = False

        def receipt_evidence():
            receipt = context['activation']
            if receipt is None:
                return None
            return dict(native_call_attempted=receipt.native_call_attempted,
                        native_call_returned=receipt.native_call_returned,
                        pending_activation=receipt.pending_activation,
                        native_error=receipt.native_error if type(receipt.native_error) is int else None,
                        activation_confirmed=context['activation_confirmed'])

        def prepare():
            if self.adapter.application_busy():
                raise rejected('application_busy', 'An existing application command is never borrowed.')
            entry, entries, before, revision = self._state(document_id, configuration)
            if len(self.receipts) >= 1000:
                raise rejected('native_activation_receipt_budget', 'Reconcile retained receipts before further activation.')
            context.update(entry=entry, entries=entries, guarded_ids=tuple(item.document_id for item in entries))
            self.receipts[operation_id] = context
            return PreparedMutation(revision, before, effect_scope='application')

        def validate(prepared):
            entry, entries, _, revision = self._state(document_id, configuration, context['guarded_ids'])
            return (revision == prepared.revision and entry.identity == context['entry'].identity
                    and [item.identity for item in entries] == [item.identity for item in context['entries']])

        def inspect(prepared):
            _, semantic, snapshots = self.oracle._capture(context['guarded_ids'])
            return dict(semantic=semantic, snapshots=snapshots,
                        original_files=self.oracle.sessions.census._disk_files(prepared.before['semantic']),
                        receipt=receipt_evidence(), pending_release=context['pending_release'],
                        pending_guard_release=context['pending_guard_release'],
                        pending_activation=bool(context['activation'] and context['activation'].pending_activation),
                        journal_failed=context['journal_failed'])

        def release_guard(*args, journal=True):
            if context['guard_release_attempted']:
                raise ExecutionFailure('native_activation_guard_release_repeated',
                                       'An attempted guard release cannot be repeated.', uncertain=True)
            if journal:
                record('part_activation_guard_release', 'pending', dict(document_ids=list(context['guarded_ids'])))
            context['guard_release_attempted'] = True
            context['pending_guard_release'] = True
            outcome = context['manager'].__exit__(*(args or (None, None, None)))
            context['guard_released'] = True
            context['pending_guard_release'] = False
            context['guarded_ids'] = ()
            if journal:
                record('part_activation_guard_release', 'returned', deepcopy(context['manager'].evidence))
            return outcome

        def apply(prepared):
            if prepared.before['semantic']['active_document_id'] == document_id:
                release_guard()
                return dict(document_id=document_id, configuration=configuration,
                            active_after_document_id=document_id, already_active=True, native_call_attempted=False)
            record('part_activation_release_ui', 'pending', dict(document_ids=list(context['guarded_ids'])))
            context['pending_release'] = True
            context['manager'].release_baseline_ui_for_activation()
            context['pending_release'] = False
            record('part_activation_release_ui', 'returned', dict(verified=True))
            # Reobserve the complete supported data after the UI phase, before
            # native activation. No guard-phase delta is silently adopted.
            if not validate(prepared):
                raise rejected('stale_revision', 'Full baseline changed during the owned UI release.')
            receipt = self.adapter.new_native_activation_receipt(context['entry'].model)
            context['activation'] = receipt
            record('part_activation_native', 'pending', dict(document_id=document_id, configuration=configuration))
            try:
                self.adapter.activate_native_open_document(receipt)
                context['activation_confirmed'] = True
            finally:
                if receipt.native_call_returned or not receipt.native_call_attempted:
                    record('part_activation_native', 'returned', receipt_evidence())
            # Release while the durable outcome is still unverified. The
            # coordinator's independent inspect/verify now observes the true
            # unlocked application, not a normalized pre-release projection.
            release_guard()
            return dict(document_id=document_id, configuration=configuration,
                        active_after_document_id=document_id, already_active=False,
                        native_call_attempted=True, receipt=receipt_evidence())

        def verify(before, after, value):
            normal = (value['already_active'] is True or
                      (after['receipt'] is not None
                       and after['receipt']['native_call_attempted'] is True
                       and after['receipt']['native_call_returned'] is True
                       and after['receipt']['activation_confirmed'] is True
                       and type(after['receipt']['native_error']) is int
                       and after['receipt']['native_error'] in (0, 2)))
            if normal and self._matches(before, after, document_id):
                record('part_activation_released_check', 'pending', dict(document_id=document_id))
                record('part_activation_released_check', 'returned', dict(verified=True, observed=after))
                context['verified_mode'] = 'effect'
                return True
            record('part_activation_effect_check', 'pending', dict(document_id=document_id))
            record('part_activation_effect_check', 'returned', dict(verified=False, observed=after))
            return False

        def restore(before, prepared):
            receipt = context['activation']
            if receipt is not None and receipt.native_call_attempted:
                # A structured native error plus an independently unchanged
                # full baseline can prove no effect. Lost/malformed ACK and a
                # successful activation never authorize a second/inverse call.
                if (receipt.native_call_returned is not True or receipt.pending_activation is not False
                        or type(receipt.native_error) is not int or receipt.native_error in (0, 2)
                        or not 0 < receipt.native_error < 2**31):
                    raise ExecutionFailure('native_activation_outcome_unconfirmed',
                                           'No inverse activation or retry is allowed for an unconfirmed effect.', uncertain=True)
            if not self._matches(before, inspect(prepared), before['semantic']['active_document_id']):
                raise ExecutionFailure('native_activation_baseline_changed',
                                       'Only independently proved no-effect restoration is supported.', uncertain=True)
            if not context['guard_release_attempted']:
                release_guard()

        def restored(before, after):
            if self._matches(before, after, before['semantic']['active_document_id']):
                record('part_activation_restored_release_check', 'pending', dict(document_id=document_id))
                record('part_activation_restored_release_check', 'returned', dict(verified=True, observed=after))
                context['verified_mode'] = 'restored'
                return True
            return False

        catalog = self

        class Guard:
            def __enter__(self):
                self.manager = catalog.adapter.native_open_guard(
                    tuple(item.model for item in context['entries']), context['guarded_ids'])
                context['manager'] = self.manager
                self.manager.__enter__()
                return self

            def __exit__(self, *args):
                if not context['guard_release_attempted']:
                    # Unknown/pending native steps cannot be extended with a
                    # fictitious return. Release only this owned guard, retaining
                    # the original uncertain journal and application hold.
                    return release_guard(*args, journal=False)
                return False

            @property
            def evidence(self):
                manager = getattr(self, 'manager', None)
                return dict(scope='native_part_activation_guard_v1',
                            native_guard=deepcopy(manager.evidence) if manager else None,
                            pending_guard_release=context['pending_guard_release'],
                            guard_release_attempted=context['guard_release_attempted'],
                            guard_released=context['guard_released'],
                            full_release_check=context['verified_mode'])

        def guard(value):
            return Guard()

        try:
            result = self.coordinator.execute(operation_id, document_id=document_id, configuration=configuration,
                expected_revision=expected_revision, prepare=prepare, validate=validate, apply=apply,
                inspect=inspect, verify=verify, restore=restore, verify_restored=restored, guard=guard)
        except ExecutionFailure as error:
            if not error.uncertain:
                self.receipts.pop(operation_id, None)
            raise
        self.receipts.pop(operation_id, None)
        return result
