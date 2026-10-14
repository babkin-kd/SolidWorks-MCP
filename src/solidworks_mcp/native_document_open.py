"""Explicit native open with a full session/file checkpoint and exact receipts.

Only handles returned by OpenDoc6 or reached through its native reference
accessors can enter a loaded-model receipt. Roster deltas never grant ownership.
"""

from dataclasses import dataclass
import hashlib
import ntpath
import posixpath
from pathlib import Path, PurePosixPath, PureWindowsPath
import uuid

from .documents import rejected
from .jobs import ExecutionFailure, _json
from .mutations import MutationCoordinator, PreparedMutation
from .native_document_close import NativeDocumentCloseCatalog
from .native_document_open_manifest import NativeOpenFileManifest
from .native_document_open_policy import validate_native_open_arguments
from .native_document_save import MAX_OPEN_DOCUMENTS, native_file_facts


SCOPE = 'native_document_open_resolved_v1'


def _directory_key(value, *, parent=False):
    """Normalize only bounded absolute directory strings, never resolve aliases."""
    if type(value) is not str or not value.strip() or len(value) > 32767 or '\0' in value:
        return None
    windows = PureWindowsPath(value)
    if windows.is_absolute():
        path = str(windows.parent) if parent else value
        return 'windows', ntpath.normcase(ntpath.normpath(path))
    path = PurePosixPath(value)
    if path.is_absolute():
        return 'posix', posixpath.normpath(str(path.parent) if parent else value)
    return None


@dataclass(frozen=True)
class NativeFileReference:
    native_file_id: str
    document_type: str
    signature: dict


class NativeDocumentOpenCatalog:
    def __init__(self, documents, store, connection_epoch):
        self.documents, self.adapter, self.store = documents, documents.adapter, store
        self.connection_epoch = connection_epoch
        self.application_id = 'app_' + uuid.uuid4().hex
        self.coordinator = MutationCoordinator(store, connection_epoch)
        self.census = NativeDocumentCloseCatalog(documents, store, connection_epoch)
        self.manifests = NativeOpenFileManifest(self.adapter)
        self.references, self.receipts = {}, {}

    def _reference(self, native_file_id):
        if type(native_file_id) is not str or native_file_id not in self.references:
            raise rejected('native_file_reference_not_found', 'Use an exact native_file_id prepared on this connection.')
        ref = self.references[native_file_id]
        current = native_file_facts(ref.signature['path'], ref.document_type)
        current['path'] = str(Path(ref.signature['path']).resolve(strict=True))
        if current != ref.signature:
            raise rejected('native_file_reference_stale', 'The bound native source changed; prepare a fresh file reference.')
        return ref

    def _capture_session(self, guarded_ids=()):
        """Observe live reference handles twice as well as the full census.

        Loaded file names and update stamps do not prove that a baseline
        component/view still references the same model and configuration.
        """
        def capture():
            entries, semantic = self.census._capture(guarded_ids)
            rows = {row['document_id']: row for row in semantic['documents']}
            graph = []
            for parent in entries:
                references = self.adapter.native_open_model_references(parent.model)
                if type(references) is not list or len(references) > MAX_OPEN_DOCUMENTS:
                    raise rejected('native_open_resolution_invalid', 'A bounded complete native reference list is required.')
                for raw, info in references:
                    identity = self.adapter.identity(raw)
                    target = next((entry for entry in entries if entry.identity == identity), None)
                    if target is None or type(info) is not dict:
                        raise rejected('native_open_reference_not_current', 'Baseline references require exact current model handles.')
                    row = rows[target.document_id]
                    path, cfg = info.get('path'), info.get('configuration')
                    if (row['file'] is None or type(path) is not str or not Path(path).is_absolute()
                            or str(Path(path).resolve(strict=True)).casefold() != row['file']['path'].casefold()
                            or type(cfg) is not str or not cfg or cfg not in row['configurations']
                            or type(info.get('name')) is not str or not info['name']
                            or info.get('origin') not in ('component', 'drawing_view')):
                        raise rejected('native_open_reference_not_current', 'Live references must match saved paths and exact configurations.')
                    graph.append(dict(parent_document_id=parent.document_id, document_id=target.document_id, **info))
                    if len(graph) > MAX_OPEN_DOCUMENTS:
                        raise rejected('native_open_resolution_invalid', 'Complete session reference-edge budget exceeds 5000.')
            semantic['reference_graph'] = sorted(graph, key=lambda row: (row['parent_document_id'], row['name'], row['document_id']))
            _json(semantic)
            return entries, semantic
        entries, first = capture()
        final_entries, second = capture()
        if first != second or [entry.identity for entry in entries] != [entry.identity for entry in final_entries]:
            raise rejected('native_session_changed_during_read', 'Complete live reference graph changed between session observations.')
        return final_entries, second

    def _state(self, ref, configuration, read_only, guarded_ids=()):
        validate_native_open_arguments(ref.signature['path'], ref.document_type, configuration, read_only)
        entries, semantic = self._capture_session(guarded_ids)
        manifest = self.manifests.capture(ref.signature['path'], ref.document_type, configuration, entries, semantic)
        final_entries, final_semantic = self._capture_session(guarded_ids)
        if semantic != final_semantic or [entry.identity for entry in entries] != [entry.identity for entry in final_entries]:
            raise rejected('native_session_changed_during_read', 'Complete application census changed while preparing the file manifest.')
        if len(entries) + sum(row['borrowed_document_id'] is None for row in manifest['files']) > MAX_OPEN_DOCUMENTS:
            raise rejected('native_session_budget_exceeded', 'Baseline and maximum planned new models exceed 5000.')
        # File dependencies of a native part have no component/view accessor
        # receipts in this scope; do not promise that they are resolved/owned.
        if any(row['document_type'] == 'part' and row['dependencies'] for row in manifest['files']):
            raise rejected('native_open_part_reference_mode_unsupported', 'Part external-reference handles require a separate accepted receipt bridge.')
        payload = dict(scope=SCOPE, connection_epoch=self.connection_epoch, application_id=self.application_id,
            native_file_id=ref.native_file_id, document_type=ref.document_type, configuration=configuration,
            read_only=read_only, ui_policy='preserve_existing_active', semantic=semantic, manifest=manifest)
        revision = 'rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
        return entries, semantic, manifest, revision

    def prepare_open(self, filename, document_type, configuration, read_only=False):
        validate_native_open_arguments(filename, document_type, configuration, read_only)
        if self.adapter.application_busy():
            raise rejected('application_busy', 'An existing command flag is never borrowed.')
        facts = native_file_facts(filename, document_type)
        facts['path'] = str(Path(filename).resolve(strict=True))
        ref = next((value for value in self.references.values()
                    if value.document_type == document_type and value.signature == facts), None)
        if ref is None:
            if len(self.references) >= 1000:
                raise rejected('native_file_reference_budget_exceeded', 'Native file references are bounded to 1000 on this connection.')
            ref = NativeFileReference('native_file_' + uuid.uuid4().hex, document_type, facts)
            self.references[ref.native_file_id] = ref
        _, semantic, manifest, revision = self._state(ref, configuration, read_only)
        return dict(application_id=self.application_id, native_file_id=ref.native_file_id, revision=revision,
            revision_scope=SCOPE, source=ref.signature, document_type=document_type, configuration=configuration,
            read_only=read_only, ui_policy='preserve_existing_active', baseline=semantic, manifest=manifest)

    @staticmethod
    def _same_baseline(before, after):
        ids = {row['document_id'] for row in before['documents']}
        return (before['documents'] == [row for row in after['documents'] if row['document_id'] in ids]
                and before['windows'] == [row for row in after['windows'] if row['document_id'] in ids]
                and before['reference_graph'] == [row for row in after['reference_graph'] if row['parent_document_id'] in ids]
                and before['application'] == after['application'])

    @classmethod
    def _same_intermediate_baseline(cls, before, after, source, receipt):
        if cls._same_baseline(before, after):
            return True
        if (receipt is None or receipt.native_call_attempted is not True
                or receipt.native_call_returned is not True or receipt.pending_open is not False
                or receipt.acknowledgement_valid is not True):
            return False
        original = before['application'].get('current_directory')
        observed = after['application'].get('current_directory')
        if (_directory_key(original) is None or _directory_key(observed) is None
                or _directory_key(observed) != _directory_key(source, parent=True)):
            return False
        # Only this receipt-bound intermediate change is tolerated. Final
        # verification continues to compare the unmodified application context.
        patched = dict(after, application=dict(after['application'], current_directory=original))
        return cls._same_baseline(before, patched)

    @staticmethod
    def _manifest_disk(manifest):
        result = []
        for row in manifest['files']:
            facts = native_file_facts(row['file']['path'], row['document_type'])
            facts['path'] = str(Path(row['file']['path']).resolve(strict=True))
            result.append(dict(document_type=row['document_type'], file=facts))
        return result

    def _resolve_once(self, prepared, receipt, entries, semantic, *, cleanup=False):
        if (receipt.pending_open or not receipt.native_call_returned or not receipt.acknowledgement_valid
                or not receipt.returned_new_identity or receipt.model is None or receipt.identity is None):
            raise rejected('native_open_returned_model_unconfirmed', 'No complete exact returned new native model receipt.')
        before = prepared.before
        source = next((entry for entry in entries if entry.identity == receipt.identity), None)
        if source is None:
            raise rejected('native_open_returned_model_not_current', 'Exact returned native data is absent from the full census.')
        rows = {row['document_id']:row for row in semantic['documents']}
        files = before['manifest']['files']
        def file_record(row):
            facts = row['file']
            return next((item for item in files if facts is not None and item['document_type'] == row['document_type']
                and item['file']['path'].casefold() == facts['path'].casefold() and item['file'] == facts), None)
        root = rows[source.document_id]
        if (file_record(root) is None or root['file'] != before['source']
                or root['document_type'] != before['document_type']
                or (not cleanup and (root['active_configuration'] != before['configuration']
                    or (before['configuration'] and before['configuration'] not in root['configurations'])
                    or (root['mode']['read_only_state'] != 0) != before['read_only']))):
            raise rejected('native_open_source_not_verified', 'Returned source type/path/file/configuration/read-only mode does not match preparation.')
        queue, reached, edges = [source], [], []
        while queue:
            parent = queue.pop()
            if any(parent.identity == item.identity for item in reached):
                continue
            reached.append(parent)
            if len(reached) > MAX_OPEN_DOCUMENTS:
                raise rejected('native_open_resolution_invalid', 'Returned-handle reference graph exceeds 5000 models.')
            references = self.adapter.native_open_model_references(parent.model)
            if type(references) is not list or len(references) > MAX_OPEN_DOCUMENTS:
                raise rejected('native_open_resolution_invalid', 'Complete bounded exact native reference handles required.')
            parent_file = file_record(rows[parent.document_id])
            if parent_file is None:
                raise rejected('native_open_resolution_not_prepared', 'A reached native model has no exact prepared file.')
            for raw, info in references:
                identity = self.adapter.identity(raw)
                target = next((entry for entry in entries if entry.identity == identity), None)
                if target is None or type(info) is not dict:
                    raise rejected('native_open_reference_not_current', 'A reference must identify one exact model in the complete census.')
                target_row = rows[target.document_id]
                target_file = file_record(target_row)
                path = info.get('path'); configuration = info.get('configuration')
                if (target_file is None or type(path) is not str or not Path(path).is_absolute()
                        or str(Path(path).resolve(strict=True)).casefold() != target_file['file']['path'].casefold()
                        or configuration not in target_file['configurations']
                        or configuration not in target_row['configurations'] or not configuration
                        or type(info.get('name')) is not str or not info['name']
                        or info.get('origin') not in ('component','drawing_view')):
                    raise rejected('native_open_reference_not_prepared', 'A resolved native reference must match its prepared path/configuration/file.')
                if not any(str(Path(dependency['path']).resolve(strict=True)).casefold() == target_file['file']['path'].casefold()
                           for dependency in parent_file['dependencies']):
                    raise rejected('native_open_reference_not_prepared', 'A native reference edge is absent from the prepared saved closure.')
                edges.append(dict(parent_document_id=parent.document_id, document_id=target.document_id, **info))
                if len(edges) > MAX_OPEN_DOCUMENTS:
                    raise rejected('native_open_resolution_invalid', 'Complete native reference-edge budget exceeds 5000.')
                if not any(target.identity == entry.identity for entry in reached + queue):
                    queue.append(target)
        baseline_ids = {row['document_id'] for row in before['semantic']['documents']}
        new = [entry for entry in entries if entry.document_id not in baseline_ids]
        if any(not any(entry.identity == known.identity for known in reached) for entry in new):
            raise rejected('native_open_unexpected_model', 'New roster entries outside exact returned-reference handles cannot be adopted.')
        # Every prepared dependency must have a canonical returned-reference
        # receipt. Suppressed/unloaded file names alone are not resolution proof.
        reached_paths = {rows[entry.document_id]['file']['path'].casefold() for entry in reached}
        if reached_paths != {row['file']['path'].casefold() for row in files}:
            raise rejected('native_open_dependency_resolution_incomplete', 'Prepared saved dependencies and exact live reference handles disagree.')
        return dict(source_document_id=source.document_id, new_document_ids=sorted(entry.document_id for entry in new),
            borrowed_document_ids=sorted(entry.document_id for entry in reached if entry.document_id in baseline_ids),
            references=sorted(edges,key=lambda item:(item['parent_document_id'],item['name'],item['document_id'])))

    def open(self, operation_id, document_id, configuration, expected_revision, native_file_id, read_only=False):
        if document_id != self.application_id:
            raise rejected('application_reference_mismatch', 'Use the server-owned application_id as the explicit mutation target.')
        context = dict(guarded_ids=(), receipt=None, activation=None, directory=None, directory_restore_started=False, journal_failed=False,
                       pending_release=False, ui_released=False, cleanup_started=False, pending_cleanup=False)

        def state():
            ref = self._reference(native_file_id)
            entries, semantic, manifest, revision = self._state(ref, configuration, read_only, context['guarded_ids'])
            return ref, entries, semantic, manifest, revision

        def prepare():
            if self.adapter.application_busy():
                raise rejected('application_busy', 'An existing command flag is never borrowed.')
            ref, entries, semantic, manifest, revision = state()
            if len(self.receipts) >= 1000:
                raise rejected('native_open_receipt_budget_exceeded', 'Native receipt budget exhausted on this connection.')
            context.update(entries=entries, guarded_ids=tuple(row['document_id'] for row in semantic['documents']))
            before = dict(scope=SCOPE, application_id=self.application_id, native_file_id=ref.native_file_id,
                source=ref.signature, document_type=ref.document_type, configuration=configuration, read_only=read_only,
                semantic=semantic, manifest=manifest, ui_policy='preserve_existing_active')
            return PreparedMutation(revision, before, effect_scope='application')

        def validate(prepared):
            _, entries, _, _, revision = state()
            return revision == prepared.revision and [entry.identity for entry in entries] == [entry.identity for entry in context['entries']]

        def record(name, phase, evidence):
            context['journal_failed'] = True
            self.store.record_mutation_step(operation_id, name=name, phase=phase, evidence=evidence)
            context['journal_failed'] = False

        def receipt_evidence(receipt):
            return dict(native_call_attempted=receipt.native_call_attempted, native_call_returned=receipt.native_call_returned,
                pending_open=receipt.pending_open, returned_model_retained=receipt.raw_model is not None,
                returned_new_identity=receipt.returned_new_identity, acknowledgement_valid=receipt.acknowledgement_valid,
                errors=receipt.errors if type(receipt.errors) is int else None,
                warnings=receipt.warnings if type(receipt.warnings) is int else None)

        def inspect(prepared):
            entries, semantic = self._capture_session(context['guarded_ids'])
            receipt = context['receipt']
            resolution = None
            if receipt and receipt.returned_new_identity and receipt.acknowledgement_valid and not context['cleanup_started']:
                first = self._resolve_once(prepared, receipt, entries, semantic)
                second = self._resolve_once(prepared, receipt, entries, semantic)
                if first != second:
                    raise rejected('native_open_resolution_changed', 'Exact native references changed between complete observations.')
                resolution = second
            return dict(semantic=semantic, original_files=self.census._disk_files(prepared.before['semantic']),
                manifest_files=self._manifest_disk(prepared.before['manifest']), resolution=resolution,
                receipt=receipt_evidence(receipt) if receipt else None,
                pending_activation=bool(context['activation'] and context['activation'].pending_activation),
                pending_directory=bool(context['directory'] and context['directory'].pending_directory),
                pending_release=context['pending_release'], pending_cleanup=context['pending_cleanup'],
                journal_failed=context['journal_failed'])

        def release_ui():
            if context['entries'] and not context['ui_released']:
                record('release_baseline_ui','pending',dict(baseline_document_ids=list(context['guarded_ids'])))
                context['pending_release'] = True
                context['manager'].release_baseline_ui_for_activation()
                context['pending_release'] = False
                context['ui_released'] = True
                record('release_baseline_ui','returned',dict(verified=True))

        def activate(target, name):
            _, current = self._capture_session(context['guarded_ids'])
            row = next(item for item in current['documents'] if item['document_id'] == target.document_id)
            title = row['title']
            if (type(title) is not str or not title.strip()
                    or sum(type(item['title']) is str and item['title'].casefold() == title.casefold()
                           for item in current['documents']) != 1):
                raise rejected('native_open_activation_name_ambiguous', 'Native activation requires an exact unique live title.')
            activation = self.adapter.new_native_activation_receipt(target.model)
            context['activation'] = activation
            record(name,'pending',dict(document_id=target.document_id))
            try:
                self.adapter.activate_native_open_document(activation)
            finally:
                if activation.native_call_returned or not activation.native_call_attempted:
                    record(name,'returned',dict(native_call_attempted=activation.native_call_attempted,
                        native_call_returned=activation.native_call_returned, native_error=activation.native_error
                        if type(activation.native_error) is int else None))

        def effect(before, after):
            return (self._same_baseline(before['semantic'],after['semantic'])
                and after['original_files']==before['semantic']['files']
                and after['manifest_files']==[dict(document_type=row['document_type'],file=row['file']) for row in before['manifest']['files']])

        def intermediate_effect(before, after):
            return (self._same_intermediate_baseline(before['semantic'], after['semantic'],
                        before['source']['path'], context['receipt'])
                and after['original_files'] == before['semantic']['files']
                and after['manifest_files'] == [dict(document_type=row['document_type'], file=row['file'])
                    for row in before['manifest']['files']])

        def restore_directory(prepared):
            before = prepared.before
            observed = inspect(prepared)
            if not intermediate_effect(before, observed):
                raise ExecutionFailure('native_open_directory_restore_unconfirmed',
                    'Complete baseline/files/references changed before directory restoration.', uncertain=True)
            original = before['semantic']['application']['current_directory']
            current = observed['semantic']['application']['current_directory']
            if current == original:
                return
            if context['directory'] is not None:
                raise ExecutionFailure('native_open_directory_restore_unconfirmed',
                    'Directory restoration cannot be retried.', uncertain=True)
            context['directory_restore_started'] = True
            receipt = self.adapter.new_native_directory_restore_receipt(original, current)
            context['directory'] = receipt
            record('restore_directory_native', 'pending', dict(original_directory=original,
                expected_current_directory=current))
            try:
                self.adapter.restore_native_open_directory(receipt)
            finally:
                if receipt.native_call_returned or not receipt.native_call_attempted:
                    record('restore_directory_native', 'returned', {
                        name: getattr(receipt, name) for name in ('native_call_attempted', 'pending_directory',
                            'native_call_returned', 'acknowledgement_valid', 'setter_succeeded')})
            if (receipt.native_call_attempted is not True or receipt.pending_directory is not False
                    or receipt.native_call_returned is not True or receipt.acknowledgement_valid is not True
                    or receipt.setter_succeeded is not True or not effect(before, inspect(prepared))):
                raise ExecutionFailure('native_open_directory_restore_unconfirmed',
                    'One normally acknowledged setter and exact final baseline are required.', uncertain=True)

        def apply(prepared):
            before = prepared.before
            receipt = self.adapter.new_native_open_receipt(tuple(entry.model for entry in context['entries']),
                before['source']['path'], before['document_type'], configuration, read_only)
            context['receipt'] = receipt
            self.receipts[operation_id] = receipt
            record('open_native','pending',dict(native_file_id=native_file_id, source=before['source']))
            try:
                self.adapter.open_native_document(receipt)
            finally:
                if receipt.native_call_returned or not receipt.native_call_attempted:
                    record('open_native','returned',receipt_evidence(receipt))
            if not receipt.acknowledgement_valid or receipt.model is None or receipt.errors != 0 or receipt.warnings != 0:
                raise rejected('native_open_not_acknowledged', 'Zero native errors/warnings and one exact returned new model are required.')
            observed = inspect(prepared)
            if observed['resolution'] is None or not intermediate_effect(before,observed):
                raise rejected('native_open_effect_not_verified', 'Exact returned references and unchanged baseline/files were not confirmed.')
            active_after = before['semantic']['active_document_id'] or observed['resolution']['source_document_id']
            if observed['semantic']['active_document_id'] != active_after:
                if context['entries']:
                    release_ui()
                    if not intermediate_effect(before,inspect(prepared)):
                        raise rejected('native_open_effect_not_verified', 'Baseline/files changed while releasing owned UI locks.')
                target = next(entry for entry in self.documents._entries if entry.document_id == active_after)
                activate(target, 'activate_native')
            final = inspect(prepared)
            if (not intermediate_effect(before, final)
                    or final['semantic']['active_document_id'] != active_after
                    or final['resolution'] != observed['resolution']):
                raise rejected('native_open_effect_not_verified', 'Exact source and baseline activation were not confirmed.')
            restore_directory(prepared)
            return dict(native_file_id=native_file_id, **observed['resolution'], active_after_document_id=active_after,
                read_only=read_only, native_errors=receipt.errors, native_warnings=receipt.warnings)

        def verify(before, after, value):
            source_id = value['source_document_id']
            root = next((row for row in after['semantic']['documents'] if row['document_id']==source_id),None)
            return (effect(before,after) and root is not None and root['visible'] is True
                and any(window['document_id']==source_id for window in after['semantic']['windows'])
                and after['semantic']['active_document_id']==value['active_after_document_id']
                and after['resolution']=={key:value[key] for key in ('source_document_id','new_document_ids','borrowed_document_ids','references')}
                and not after['receipt']['pending_open'] and not after['pending_activation'] and not after['pending_directory']
                and not after['pending_release'] and not after['pending_cleanup'] and not after['journal_failed'])

        def restore(before, prepared):
            receipt, activation = context['receipt'], context['activation']
            if (context['journal_failed'] or context['pending_release'] or (receipt and receipt.pending_open)
                    or (activation and activation.pending_activation) or context['directory_restore_started']):
                raise ExecutionFailure('native_open_outcome_unknown', 'Pending native/journal steps prohibit retry or automatic cleanup.',uncertain=True)
            # Inspect without getters on returned handles: a wrong source
            # configuration can be a known clean failure, not a valid open.
            entries, semantic = self._capture_session(context['guarded_ids'])
            observed = dict(semantic=semantic, original_files=self.census._disk_files(before['semantic']),
                            manifest_files=self._manifest_disk(before['manifest']))
            if semantic == before['semantic'] and effect(before, observed):
                return
            if receipt is None or not intermediate_effect(before, observed):
                raise ExecutionFailure('native_open_restore_unconfirmed', 'Baseline or files changed; cleanup cannot adopt this effect.', uncertain=True)
            # A normally returned null has no root to retire. Restore only the
            # proven directory change and require the independent full oracle.
            patched = dict(semantic, application=before['semantic']['application'])
            if (receipt.model is None and receipt.raw_model is None and receipt.returned_new_identity is False
                    and receipt.native_call_attempted is True and receipt.native_call_returned is True
                    and receipt.pending_open is False and receipt.acknowledgement_valid is True
                    and patched == before['semantic']):
                restore_directory(prepared)
                return
            first = self._resolve_once(prepared, receipt, entries, semantic, cleanup=True)
            second = self._resolve_once(prepared, receipt, entries, semantic, cleanup=True)
            if first != second:
                raise ExecutionFailure('native_open_restore_unconfirmed', 'Exact owned reference graph changed before cleanup.', uncertain=True)
            own = set(second['new_document_ids'])
            root_id = second['source_document_id']
            root = next(row for row in semantic['documents'] if row['document_id'] == root_id)
            hidden = sorted(row['document_id'] for row in semantic['documents'] if row['document_id'] in own
                            and row['document_id'] != root_id and row['document_id'] != semantic['active_document_id']
                            and not row['visible'])
            desired = before['semantic']['active_document_id']
            survivor = desired if semantic['active_document_id'] == root_id and before['semantic']['windows'] else ''
            entry, _, _, impact, _ = self.census._state(root_id, root['active_configuration'],
                survivor or '', hidden, context['guarded_ids'])
            baseline_ids = set(context['guarded_ids'])
            if (set(impact['retiring_document_ids']) != own or set(impact['survivor_document_ids']) != baseline_ids
                    or not self._same_intermediate_baseline(before['semantic'], semantic, before['source']['path'], receipt)):
                raise ExecutionFailure('native_open_restore_unconfirmed', 'Only an exact require-clean owned-new retirement is permitted.', uncertain=True)
            # The close preview has no reference-graph field; independently
            # reobserve the full session after it, before any cleanup write.
            final_entries, final = self._capture_session(context['guarded_ids'])
            if final != semantic or [entry.identity for entry in entries] != [item.identity for item in final_entries]:
                raise ExecutionFailure('native_open_restore_unconfirmed', 'Session changed during cleanup preparation.', uncertain=True)
            record('rollback_close_native', 'pending', dict(impact=impact))
            context['cleanup_started'] = context['pending_cleanup'] = True
            native = self.adapter.close_native_document(entry.model, impact['native_name'])
            context['pending_cleanup'] = False
            record('rollback_close_native', 'returned', dict(native_call_returned=True,
                acknowledgement_valid=type(native) is dict and native.get('native_call_returned') is True))
            # Never read retired returned models or their reference handles.
            after = inspect(prepared)
            if (type(native) is not dict or native.get('native_call_returned') is not True
                    or not intermediate_effect(before, after) or after['semantic']['documents'] != before['semantic']['documents']
                    or after['semantic']['windows'] != before['semantic']['windows']):
                raise ExecutionFailure('native_open_restore_unconfirmed', 'Normally returned close is not exact retirement proof.', uncertain=True)
            if desired is not None and after['semantic']['active_document_id'] != desired:
                release_ui()
                released = inspect(prepared)
                if (not intermediate_effect(before, released) or released['semantic']['documents'] != before['semantic']['documents']
                        or released['semantic']['windows'] != before['semantic']['windows']):
                    raise ExecutionFailure('native_open_restore_unconfirmed', 'Baseline changed during cleanup UI release.', uncertain=True)
                target = next(item for item in self.documents._entries if item.document_id == desired)
                activate(target, 'rollback_activate_native')
            final = inspect(prepared)
            patched = dict(final['semantic'], application=before['semantic']['application'])
            if not intermediate_effect(before, final) or patched != before['semantic']:
                raise ExecutionFailure('native_open_restore_unconfirmed', 'Exact baseline must precede directory restoration.', uncertain=True)
            restore_directory(prepared)

        def restored(before, after):
            return (after['semantic']==before['semantic'] and effect(before,after)
                and not after['pending_activation'] and not after['pending_release'] and not after['pending_directory']
                and not after['pending_cleanup'] and not after['journal_failed'])

        def guard(prepared):
            context['manager'] = self.adapter.native_open_guard(tuple(entry.model for entry in context['entries']),context['guarded_ids'])
            return context['manager']

        try:
            result = self.coordinator.execute(operation_id,document_id=document_id,configuration=configuration,
                expected_revision=expected_revision,prepare=prepare,validate=validate,apply=apply,inspect=inspect,
                verify=verify,restore=restore,verify_restored=restored,guard=guard)
        except ExecutionFailure as exc:
            if not exc.uncertain:
                self.receipts.pop(operation_id,None)
            raise
        return result
