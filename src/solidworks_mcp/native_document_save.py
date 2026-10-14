"""One native Save3; lifecycle/file observation revision, not full BREP/CAS."""
import hashlib
from pathlib import Path
import stat
from .documents import rejected
from .exports_v2 import _is_reparse
from .jobs import ExecutionFailure, _json
from .mutations import MutationCoordinator, PreparedMutation

SCOPE = 'native_document_current_file_save_v1'
EXTENSIONS = {'part': '.sldprt', 'assembly': '.sldasm', 'drawing': '.slddrw'}
MAX_OPEN_DOCUMENTS = 5000
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024


def native_file_facts(filename, document_type):
    path = Path(filename)
    if not path.is_absolute() or path.suffix.lower() != EXTENSIONS.get(document_type):
        raise rejected('native_document_path_required', 'An existing absolute native file matching the document type is required.')
    try:
        for item in (path, *path.parents):
            if _is_reparse(item):
                raise rejected('native_file_redirect_unsupported', 'Native file and ancestors must not be symlinks/junctions.')
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_FILE_BYTES:
            raise rejected('native_file_budget_exceeded', 'A nonempty regular native file up to 512 MiB is required.')
        digest = hashlib.sha256(); count = 0
        with path.open('rb') as source:
            while chunk := source.read(1024 * 1024):
                count += len(chunk)
                if count > MAX_FILE_BYTES:
                    raise rejected('native_file_changed_during_read', 'Native file exceeded the read budget.')
                digest.update(chunk)
        after = path.lstat()
    except OSError as exc:
        raise rejected('native_file_unavailable', 'The bound native file cannot be fingerprinted.') from exc
    signature = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if signature(before) != signature(after) or count != before.st_size:
        raise rejected('native_file_changed_during_read', 'Native file changed during fingerprinting.')
    return dict(path=str(path), bytes=count, sha256=digest.hexdigest(), identity=[before.st_dev, before.st_ino],
                mtime_ns=before.st_mtime_ns, ctime_ns=before.st_ctime_ns)


class NativeDocumentSaveCatalog:
    def __init__(self, documents, store, connection_epoch):
        self.documents, self.adapter = documents, documents.adapter
        self.coordinator = MutationCoordinator(store, connection_epoch)
        self.connection_epoch = connection_epoch

    def _capture_once(self):
        self.documents._refresh(); entries = tuple(self.documents._entries)
        if len(entries) > MAX_OPEN_DOCUMENTS:
            raise rejected('native_session_budget_exceeded', 'Complete open-document census exceeds 5000; no partial checkpoint.')
        rows = []; total = 0; files = {}
        for entry in entries:
            observed = self.documents._observe(entry)
            if observed['document_type'] not in EXTENSIONS:
                raise rejected('unsupported_document_type', 'Only native part/assembly/drawing documents are supported.')
            mode = self.adapter.native_save_context(entry.model)
            if mode['editing_sketch'] or mode['editing_component'] or mode['view_only'] or mode['blocking_state'] not in (0, 2):
                raise rejected('native_document_edit_mode', 'Finish active editing/commands before native save.')
            facts = None
            if observed['path']:
                key = str(Path(observed['path']).absolute()).casefold()
                if key not in files:
                    files[key] = native_file_facts(observed['path'], observed['document_type'])
                    total += files[key]['bytes']
                    if total > MAX_TOTAL_BYTES:
                        raise rejected('native_session_file_budget_exceeded', 'Complete open-native-file checkpoint exceeds 2 GiB.')
                facts = files[key]
            rows.append({**observed, 'view': self.adapter.document_view_snapshot(entry.model),
                         'read_only_state': mode['read_only_state'], 'file': facts,
                         'drawing_state': mode.get('drawing_state')})
        active = self.adapter.active_document()
        token = self.adapter.identity(active) if active is not None else None
        current = next((entry for entry in entries if entry.identity == token), None)
        if token is not None and current is None:
            raise rejected('native_session_changed_during_read', 'Active document is outside the complete census.')
        return entries, dict(documents=sorted(rows, key=lambda row: row['document_id']),
                             active_document_id=current.document_id if current else None,
                             visible=self.adapter.application_visible())

    def _capture(self):
        first, before = self._capture_once(); second, after = self._capture_once()
        if [entry.identity for entry in first] != [entry.identity for entry in second] or before != after:
            raise rejected('native_session_changed_during_read', 'Native documents, files or views changed during checkpointing.')
        _json(before); return first, before

    def _state(self, document_id, configuration):
        entries, semantic = self._capture()
        entry = next((entry for entry in entries if entry.document_id == document_id), None)
        if entry is None:raise rejected('document_not_open', 'List documents again; the exact document is not open.')
        target = next(row for row in semantic['documents'] if row['document_id'] == document_id)
        if target['active_configuration'] != configuration or (target['configurations'] and configuration not in target['configurations']):
            raise rejected('configuration_not_active', 'Use the explicitly active configuration; no implicit activation.')
        if target['file'] is None:raise rejected('native_document_first_save_required', 'First save is a separate operation.')
        if target['read_only_state'] != 0:raise rejected('native_document_read_only', 'No save, checkout or attribute change of read-only documents.')
        payload = dict(scope=SCOPE, connection_epoch=self.connection_epoch, document_id=document_id,
                       configuration=configuration, semantic=semantic)
        return entry, entries, semantic, 'rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest()

    def prepare_save(self, document_id, configuration):
        if self.adapter.application_busy():raise rejected('application_busy', 'An existing command flag is never borrowed.')
        _, _, semantic, revision = self._state(document_id, configuration)
        target = next(row for row in semantic['documents'] if row['document_id'] == document_id)
        return dict(document_id=document_id, configuration=configuration, revision=revision, revision_scope=SCOPE,
                    path=target['path'], file=target['file'], baseline=semantic, save_referenced_documents=False,
                    first_save_supported=False, native_operation='IModelDoc2.Save3(Silent)')

    @staticmethod
    def _same_saved_document(before, after):
        ignored = {'needs_save', 'update_stamp', 'observation_revision', 'observation_sequence', 'file'}
        if before['document_type'] == 'drawing' and before.get('drawing_state'):
            expected_title = before['drawing_state']['saved_display_title']
            if before['title'] != after['title']:
                if after['title'] != expected_title:
                    return False
                ignored.add('title')
        return {k: v for k, v in before.items() if k not in ignored} == {k: v for k, v in after.items() if k not in ignored}

    def save(self, operation_id, document_id, configuration, expected_revision):
        context = dict(pending_native_call=False, native=None)
        def prepare():
            if self.adapter.application_busy():raise rejected('application_busy', 'An existing command flag is never borrowed.')
            entry, entries, semantic, revision = self._state(document_id, configuration)
            context.update(entry=entry, entries=entries)
            return PreparedMutation(revision, {'scope': SCOPE, 'semantic': semantic}, effect_scope='application')
        def validate(prepared):
            entry, _, _, revision = self._state(document_id, configuration)
            return entry is context['entry'] and revision == prepared.revision
        def apply(prepared):
            context['pending_native_call'] = True
            result = self.adapter.save_native_current_file(context['entry'].model)
            context['native'] = result; context['pending_native_call'] = False
            if (not isinstance(result, dict) or result.get('success') is not True
                    or type(result.get('errors')) is not int or result['errors'] != 0
                    or type(result.get('warnings')) is not int or result['warnings'] != 0):
                raise rejected('native_document_save_not_acknowledged', 'Save3 must return True with zero native errors/warnings.')
            return dict(document_id=document_id, path=next(row['path'] for row in prepared.before['semantic']['documents']
                        if row['document_id'] == document_id), native=result, save_referenced_documents=False)
        def inspect(prepared):
            _, semantic = self._capture()
            return dict(semantic=semantic, native=context['native'], pending_native_call=context['pending_native_call'])
        def verify(before, after, value):
            left, right = before['semantic'], after['semantic']
            a = next(row for row in left['documents'] if row['document_id'] == document_id)
            b = next((row for row in right['documents'] if row['document_id'] == document_id), None)
            return (b is not None and self._same_saved_document(a, b) and b['needs_save'] is False
                    and b['file'] is not None and b['file']['path'] == a['file']['path']
                    and left['active_document_id'] == right['active_document_id'] and left['visible'] == right['visible']
                    and [row for row in left['documents'] if row['document_id'] != document_id] ==
                        [row for row in right['documents'] if row['document_id'] != document_id]
                    and after['pending_native_call'] is False and after['native'] == value['native'])
        def restore(before, prepared):
            if context['pending_native_call']:
                raise ExecutionFailure('native_save_outcome_unknown', 'Throwing native save is never retried or replaced by observations.', uncertain=True)
            _, current = self._capture()
            if current != before['semantic']:
                raise ExecutionFailure('native_save_restore_unsupported', 'Changed native/file effects are never rewritten/deleted or reset automatically.', uncertain=True)
        return self.coordinator.execute(operation_id, document_id=document_id, configuration=configuration,
            expected_revision=expected_revision, prepare=prepare, validate=validate, apply=apply,
            inspect=inspect, verify=verify, restore=restore,
            verify_restored=lambda before, after: after['semantic'] == before['semantic'] and after['pending_native_call'] is False,
            guard=lambda prepared: self.adapter.native_save_guard(tuple(entry.model for entry in context['entries'])))
