"""Bounded own-feature suppression with full session revisions and ownership.

The target is the exact B1-created extrusion in its original connection epoch.
Saved/user features, multiple configurations and arbitrary dependency graphs
remain unsupported. Suppressed native handles are retained, never rehydrated
from a journal or addressed by display names.
"""
from contextlib import ExitStack
import hashlib

from .documents import rejected
from .jobs import _json
from .native_document_open import NativeDocumentOpenCatalog
from .native_document_save import MAX_OPEN_DOCUMENTS
from .rectangle_snapshot import BASE, validated_rectangle_snapshot
from .cad_owned_suppression_snapshot import OwnedSuppressionSnapshot
from .owned_suppression_postconditions import verified_owned_suppression
from .feature_suppression_execution import FeatureSuppressionExecutionMixin


SCOPE = 'owned_rectangular_blind_base_suppression_v1'


class FeatureSuppressionCatalog(FeatureSuppressionExecutionMixin):
    def __init__(self, documents, store, connection_epoch, ownership):
        if (ownership.documents is not documents or ownership.store is not store
                or ownership.connection_epoch != connection_epoch):
            raise rejected('suppression_ownership_invalid', 'Reuse the exact current construction ownership registry.')
        self.documents, self.adapter, self.store = documents, documents.adapter, store
        self.connection_epoch, self.ownership = connection_epoch, ownership
        self.sessions = NativeDocumentOpenCatalog(documents, store, connection_epoch)
        self.contexts, self.receipts = {}, {}

    def _resolve(self, document_id, configuration, object_id):
        binding, feature = self.ownership.resolve(document_id, configuration, object_id,
            connection_epoch=self.connection_epoch)
        if binding.kind != 'extrusion':
            raise rejected('suppression_feature_unsupported', 'Only the original owned blind rectangular extrusion is supported.')
        value = list(feature.IsSuppressed2(1, None))
        if len(value) != 1 or type(value[0]) is not bool:
            raise rejected('suppression_state_unconfirmed', 'Actual current-configuration native boolean required.')
        return binding, value[0]

    def _capture(self, binding, producer=None, guarded_ids=()):
        entries, semantic = self.sessions._capture_session(guarded_ids)
        if not len(entries) < MAX_OPEN_DOCUMENTS:
            raise rejected('suppression_session_budget', 'A complete bounded supported session is required.')
        snapshots = {}
        for entry in entries:
            row = next(row for row in semantic['documents'] if row['document_id'] == entry.document_id)
            if row['document_type'] != 'part':
                raise rejected('suppression_neighbor_unsupported', 'All neighbors need the full supported part oracle.')
            if entry.document_id == binding.document_id:
                if entry.identity != binding.model_identity:
                    raise rejected('suppression_target_changed', 'Original current target incarnation required.')
                suppressed = list(binding.feature.IsSuppressed2(1, None))
                if len(suppressed) != 1 or type(suppressed[0]) is not bool:
                    raise rejected('suppression_state_unconfirmed', 'Complete typed current state required.')
                if suppressed[0]:
                    if producer is None:
                        raise rejected('suppression_context_missing', 'Suppressed data require original live retained handles.')
                    reader = producer.capture
                else:
                    reader = lambda: validated_rectangle_snapshot(self.adapter.rectangle_construction_snapshot(entry.model))
            else:
                reader = lambda: validated_rectangle_snapshot(self.adapter.rectangle_construction_snapshot(entry.model))
            first, second = reader(), reader()
            if (_json(first) != _json(second) or second['configuration'] != row['active_configuration']
                    or second['configurations'] != row['configurations']):
                raise rejected('suppression_snapshot_changed', 'Complete target/neighbor read changed during capture.')
            if entry.document_id != binding.document_id and second['clone_state']['profile'] != BASE:
                raise rejected('suppression_neighbor_unsupported', 'Every neighbor requires the fully observed BASE profile.')
            snapshots[entry.document_id] = second
        closing_entries, closing = self.sessions._capture_session(guarded_ids)
        if (_json(semantic) != _json(closing)
                or [entry.identity for entry in entries] != [entry.identity for entry in closing_entries]):
            raise rejected('suppression_session_changed', 'Complete roster, references, UI or files changed during observation.')
        if binding.document_id not in snapshots:
            raise rejected('document_not_open','The original target disappeared before complete capture.')
        return closing_entries, dict(semantic=semantic,snapshots=snapshots)

    def _committed_context(self, binding):
        context = self.contexts.get((binding.document_id,binding.object_id))
        if context is None or context['binding'] is not binding or not context.get('operation_id'):
            raise rejected('suppression_context_missing', 'Return requires the original successfully committed suppression context.')
        row = self.store.get(context['operation_id'])
        mutation = row.get('mutation') or {}
        if (row['status'] != 'succeeded' or row['operation'] != 'feature.set_suppressed'
                or row['payload']['arguments']['suppressed'] is not True
                or row['payload']['arguments']['document_id'] != binding.document_id
                or row['payload']['arguments']['configuration'] != binding.configuration
                or row['payload']['arguments']['object_id'] != binding.object_id
                or mutation.get('phase') != 'committed'
                or mutation.get('connection_epoch') != self.connection_epoch
                or mutation.get('document_id') != binding.document_id
                or mutation.get('configuration') != binding.configuration
                or row['error'] is not None or _json(row['result']) != context.get('committed_result_json')
                or (mutation.get('verification') or {}).get('outcome') != 'committed'):
            raise rejected('suppression_context_unconfirmed', 'Unfinished or uncertain suppression cannot authorize return.')
        return context

    def _prepare(self, document_id, configuration, object_id, suppressed, guarded_ids=()):
        if any(type(value) is not str or not value.strip() for value in (document_id,configuration,object_id)):
            raise rejected('suppression_context_invalid','Explicit current document, configuration and owned object IDs required.')
        if type(suppressed) is not bool:
            raise rejected('suppression_input_invalid', 'Use an explicit native suppression boolean.')
        if not guarded_ids and self.adapter.application_busy():
            raise rejected('application_busy', 'An existing command cannot be borrowed.')
        binding, original = self._resolve(document_id,configuration,object_id)
        if original == suppressed:
            raise rejected('suppression_already_requested', 'An actual transition is required.')
        context = self._committed_context(binding) if original else None
        entries, state = self._capture(binding,context['producer'] if context else None,guarded_ids)
        row = next(row for row in state['semantic']['documents'] if row['document_id'] == document_id)
        if (state['semantic']['active_document_id'] != document_id or row['path'] != ''
                or row['configurations'] != [configuration] or row['active_configuration'] != configuration
                or row['needs_save'] is not True or row['mode']['read_only_state'] != 0
                or not row['visible'] or row['dependencies'] or state['semantic']['reference_graph']
                or len([window for window in state['semantic']['windows'] if window['document_id'] == document_id]) != 1
                or any(not item['visible'] or item['dependencies'] for item in state['semantic']['documents'])
                or state['snapshots'][document_id]['selection_count'] != 0):
            raise rejected('suppression_target_unsupported', 'Use the active visible dirty unsaved one-configuration own part without references or selections.')
        if original:
            if not verified_owned_suppression(context['baseline'],state,document_id,binding.native_id):
                raise rejected('suppression_current_state_changed', 'The complete original suppression effect no longer matches.')
        else:
            if len(self.contexts) >= 32 and (document_id,object_id) not in self.contexts:
                raise rejected('suppression_context_budget','Retained suppression contexts exhausted before any write.')
            if state['snapshots'][document_id]['clone_state']['profile'] != BASE:
                raise rejected('suppression_target_unsupported', 'A complete original rectangular BASE is required.')
            producer = OwnedSuppressionSnapshot(self.adapter,binding.model,binding,state['snapshots'][document_id])
            context = dict(binding=binding,producer=producer,baseline=state,operation_id=None)
            # Retention performs reads only; repeat full observation afterwards.
            closing_entries, closing = self._capture(binding,None,guarded_ids)
            if (_json(state) != _json(closing)
                    or [entry.identity for entry in entries] != [entry.identity for entry in closing_entries]):
                raise rejected('suppression_snapshot_changed', 'Native retention changed or raced the full baseline.')
            self.contexts[(document_id,object_id)] = context
        payload = dict(scope=SCOPE,connection_epoch=self.connection_epoch,document_id=document_id,
            configuration=configuration,object_id=object_id,suppressed=suppressed,
            original_suppressed=original,feature_pid_hex=binding.persistent_id.hex(),
            creation_operation_id=binding.creation_operation_id,
            original_suppression_operation_id=context['operation_id'],baseline=state)
        return dict(**payload,revision='rev_'+hashlib.sha256(_json(payload).encode('utf8')).hexdigest(),
                    revision_scope=SCOPE,expected_solid_body_count=0 if suppressed else 1)

    def prepare(self, document_id, configuration, object_id, suppressed):
        with ExitStack() as cleanup:
            watches = []
            models = self.adapter.documents()
            if not len(models) < MAX_OPEN_DOCUMENTS:
                raise rejected('suppression_session_budget','A complete bounded session is required.')
            self.documents._refresh()
            live = [(entry.document_id,entry.identity) for entry in self.documents._entries]
            retired = [key for key,context in self.contexts.items()
                if not any(document_id == context['binding'].document_id
                    and identity == context['binding'].model_identity for document_id,identity in live)]
            for key in retired: del self.contexts[key]
            for model in models:
                if self.adapter.snapshot(model)['document_type'] != 'part':
                    raise rejected('suppression_neighbor_unsupported','All session models need the supported part oracle.')
                watch = self.adapter.watch_part(model)
                cleanup.callback(watch.close)
                watches.append((watch,watch.poll()))
            result = self._prepare(document_id,configuration,object_id,suppressed)
            if any(watch.poll() != sequence for watch,sequence in watches):
                raise rejected('suppression_session_changed', 'A baseline model changed during full preparation.')
            return result
