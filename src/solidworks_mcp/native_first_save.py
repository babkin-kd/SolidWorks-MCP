"""First save by verified copy/publication and explicit source replacement.

Initial CAD oracle: a self-contained simple rectangular blind-base part. Every
baseline model must admit that same full passive oracle. This is not generic
SaveAs, a delta-ownership protocol, or a registered/publicly accepted tool.
"""

from contextlib import ExitStack
from copy import deepcopy
import hashlib
from pathlib import Path

from . import native_first_save_files as default_files
from .documents import rejected
from .features import russian_name
from .jobs import ExecutionFailure, _json
from .mutations import MutationCoordinator, PreparedMutation
from .native_document_open import NativeDocumentOpenCatalog, _directory_key
from .native_document_save import MAX_OPEN_DOCUMENTS


SCOPE = 'native_first_save_replace_part_v1'
SNAPSHOT_SCOPE = 'native_first_save_part_snapshot_v1'
SNAPSHOT_KEYS = {'scope', 'configuration', 'configurations', 'solid_body_count',
                 'selection_count', 'clone_state', 'references', 'native_observations'}


def validated_part_snapshot(value):
    """Require complete typed oracle shape; do not strip opaque identities."""
    if (type(value) is not dict or set(value) != SNAPSHOT_KEYS
            or value['scope'] != SNAPSHOT_SCOPE
            or type(value['configuration']) is not str or not value['configuration'].strip()
            or value['configurations'] != [value['configuration']]
            or type(value['configurations']) is not list
            or type(value['solid_body_count']) is not int or value['solid_body_count'] != 1
            or type(value['selection_count']) is not int or not 0 <= value['selection_count'] <= MAX_OPEN_DOCUMENTS
            or type(value['clone_state']) is not dict or not value['clone_state']
            or type(value['native_observations']) is not dict
            or type(value['references']) is not list or not 1 <= len(value['references']) <= MAX_OPEN_DOCUMENTS):
        raise rejected('first_save_snapshot_unsupported', 'A full single-configuration/solid, unselected clone oracle is required.')
    roles, tokens = set(), set()
    for row in value['references']:
        if (type(row) is not dict or set(row) != {'kind', 'role', 'token'}
                or any(type(row[key]) is not str or not row[key].strip() or '\0' in row[key]
                       or len(row[key]) > 65536 for key in row)):
            raise rejected('first_save_snapshot_unsupported', 'Each persistent reference requires exact kind/structural role/token.')
        role, token = (row['kind'], row['role']), row['token']
        if role in roles or token in tokens:
            raise rejected('first_save_snapshot_unsupported', 'Structural roles and native persistent references must be bijective.')
        roles.add(role); tokens.add(token)
    _json(value)
    if value['clone_state'].get('profile')=='single_rectangular_blind_base_v1':
        observations=value['native_observations']
        if (set(observations)!={'document_dimension_namespace','qualified_dimensions','unavailable_extrusion_auto_select'}
                or type(observations['document_dimension_namespace']) is not str
                or not observations['document_dimension_namespace']
                or type(observations['unavailable_extrusion_auto_select']) is not bool
                or type(observations['qualified_dimensions']) is not list or len(observations['qualified_dimensions'])!=3):
            raise rejected('first_save_snapshot_unsupported','Only exact document qualifications and the unavailable AutoSelect observation may differ.')
        clone=value['clone_state']
        if (clone.get('extrusion',{}).get('FeatureScope') is not False
                or clone['extrusion'].get('AutoSelect')!={'availability':'unavailable_feature_scope_disabled_v1'}):
            raise rejected('first_save_snapshot_unsupported','An available feature-scope control cannot be excluded from copy equivalence.')
        seen=set()
        for row in observations['qualified_dimensions']:
            if (type(row) is not dict or set(row)!={'role','full_name','name','owner_role'}
                    or any(type(v) is not str or not v or '\0' in v for v in row.values())
                    or row['role'] not in {'dimension:width','dimension:height','dimension:depth'}
                    or row['role'] in seen):
                raise rejected('first_save_snapshot_unsupported','Complete qualified dimension observations must be bijective.')
            seen.add(row['role'])
            dims=[d for d in clone.get('dimensions',[]) if d.get('full_name')=={'reference_role':row['role']}]
            owners=[(index,f) for index,f in enumerate(clone.get('features',[])) if 'feature:'+str(index)==row['owner_role']]
            if (len(dims)!=1 or len(owners)!=1 or dims[0].get('name')!=row['name']
                    or dims[0].get('owner',{}).get('native_id')!=owners[0][1].get('native_id')
                    or row['full_name']!=row['name']+'@'+owners[0][1]['name']+'@'+observations['document_dimension_namespace']+'.Part'
                    or ('dimension',row['role']) not in roles):
                raise rejected('first_save_snapshot_unsupported','Every qualification must agree with the complete bound native dimension and owner role.')
    return deepcopy(value)


def clone_mapping(original, saved):
    # All observations remain in source/baseline snapshots. Only the native
    # document qualification and a documented unavailable getter live outside
    # persisted semantic state; every other field is compared exactly.
    original, saved = validated_part_snapshot(original), validated_part_snapshot(saved)
    fields = ('configuration', 'configurations', 'solid_body_count', 'selection_count', 'clone_state')
    if any(original[key] != saved[key] for key in fields):
        raise rejected('first_save_copy_not_equivalent', 'Full declared clone state/configuration/geometry differs.')
    left = {(row['kind'], row['role']): row['token'] for row in original['references']}
    right = {(row['kind'], row['role']): row['token'] for row in saved['references']}
    if left.keys() != right.keys():
        raise rejected('first_save_copy_not_equivalent', 'Complete native structural reference inventories differ.')
    return [dict(kind=kind, role=role, source_token=left[(kind, role)], saved_token=right[(kind, role)])
            for kind, role in sorted(left)]


def _normal(receipt, pending):
    return (receipt is not None and receipt.native_call_attempted is True
            and receipt.native_call_returned is True and getattr(receipt, pending) is False
            and receipt.acknowledgement_valid is True)


class NativeFirstSaveCatalog:
    def __init__(self, documents, store, connection_epoch, *, files=None):
        self.documents, self.adapter, self.store = documents, documents.adapter, store
        self.connection_epoch, self.files = connection_epoch, files or default_files
        self.coordinator = MutationCoordinator(store, connection_epoch)
        self.sessions = NativeDocumentOpenCatalog(documents, store, connection_epoch)
        self.receipts = {}

    def _capture(self, guarded_ids=()):
        entries, semantic = self.sessions._capture_session(guarded_ids)
        snapshots = {}
        for entry in entries:
            row = next(row for row in semantic['documents'] if row['document_id'] == entry.document_id)
            if row['document_type'] != 'part':
                raise rejected('first_save_baseline_unsupported', 'Initial first-save baseline admits supported parts only.')
            first = validated_part_snapshot(self.adapter.first_save_part_snapshot(entry.model))
            second = validated_part_snapshot(self.adapter.first_save_part_snapshot(entry.model))
            if first != second or first['configuration'] != row['active_configuration'] or first['configurations'] != row['configurations']:
                raise rejected('first_save_snapshot_changed', 'Complete native part oracle changed during observation.')
            snapshots[entry.document_id] = second
        final_entries, final = self.sessions._capture_session(guarded_ids)
        if final != semantic or [entry.identity for entry in entries] != [entry.identity for entry in final_entries]:
            raise rejected('native_session_changed_during_read', 'Session changed while collecting complete part oracles.')
        return final_entries, semantic, snapshots

    def _state(self, document_id, configuration, filename, guarded_ids=()):
        if type(filename) is not str:
            raise rejected('first_save_invalid_path', 'Use an explicit absolute native part destination.')
        russian_name(Path(filename).stem)
        token = self.files.prepare_destination(filename)
        entries, semantic, snapshots = self._capture(guarded_ids)
        entry = next((item for item in entries if item.document_id == document_id), None)
        if entry is None:
            raise rejected('document_not_open', 'First save requires the exact current source document.')
        source = next(row for row in semantic['documents'] if row['document_id'] == document_id)
        if (source['path'] or source['file'] is not None or source['active_configuration'] != configuration
                or source['configurations'] != [configuration] or source['mode']['read_only_state'] != 0
                or source['dependencies'] or semantic['reference_graph']
                or semantic['active_document_id'] != document_id or not source['visible']
                or snapshots[document_id]['selection_count'] != 0
                or len([row for row in semantic['windows'] if row['document_id'] == document_id]) != 1):
            raise rejected('first_save_source_unsupported', 'Use one active, writable, unsaved, visible self-contained part/configuration/window.')
        if any(not row['visible'] for row in semantic['documents']):
            raise rejected('first_save_hidden_baseline_unsupported', 'Hidden collateral cannot enter the initial first-save close scope.')
        if len(entries) >= MAX_OPEN_DOCUMENTS:
            raise rejected('native_session_budget_exceeded', 'A temporary exact readback model requires one free census slot.')
        payload = dict(scope=SCOPE, connection_epoch=self.connection_epoch, document_id=document_id,
            configuration=configuration, destination=token, semantic=semantic, snapshots=snapshots,
            replacement_policy='retire_source_only_after_verified_persisted_copy')
        revision = 'rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
        return entry, entries, payload, revision

    def prepare_first_save(self, document_id, configuration, filename):
        if self.adapter.application_busy():
            raise rejected('application_busy', 'An existing command flag is never borrowed.')
        _, _, before, revision = self._state(document_id, configuration, filename)
        return dict(document_id=document_id, configuration=configuration, filename=before['destination']['destination'],
            revision=revision, revision_scope=SCOPE, baseline=before['semantic'],
            replacement_policy=before['replacement_policy'], source_document_id=document_id,
            source_references_will_retire=True, native_first_save_available=True)

    def first_save(self, operation_id, document_id, configuration, expected_revision, filename):
        context = dict(guarded_ids=(), stage=None, stage_plan=None, copy=None, stage_open=None, final_open=None,
            stage_close=None, source_close=None, activation=None, directory=None, journal_failed=False,
            published=None, cleanup=None, stage_closed=False, source_closed=False, released_ui=False,
            pending_release=False, final_file=None, final_id=None, stage_id=None)

        def record(name, phase, evidence):
            context['journal_failed'] = True
            self.store.record_mutation_step(operation_id, name=name, phase=phase, evidence=evidence)
            context['journal_failed'] = False

        def prepare():
            if self.adapter.application_busy():
                raise rejected('application_busy', 'An existing command flag is never borrowed.')
            entry, entries, before, revision = self._state(document_id, configuration, filename)
            if len(self.receipts) >= 1000:
                raise rejected('first_save_receipt_budget', 'First-save unresolved receipt budget is exhausted.')
            context.update(source=entry, entries=entries, guarded_ids=tuple(item.document_id for item in entries if item is not entry))
            self.receipts[operation_id] = context
            return PreparedMutation(revision, before, effect_scope='application')

        def validate(prepared):
            entry, entries, _, revision = self._state(document_id, configuration, filename, context['guarded_ids'])
            return revision == prepared.revision and entry.identity == context['source'].identity and [x.identity for x in entries] == [x.identity for x in context['entries']]

        def inspect(prepared):
            entries, semantic, snapshots = self._capture(context['guarded_ids'])
            context['current_entries'] = entries
            stage = self.files.observe_owned_stage(context['stage'], context['lease']) if context['stage'] else None
            return dict(semantic=semantic, snapshots=snapshots,
                original_files=self.sessions.census._disk_files(prepared.before['semantic']),
                stage=stage, destination_file=self.files.observe_destination(prepared.before['destination']),
                published=context['published'], cleanup=context['cleanup'],
                pending=any(bool(receipt and getattr(receipt, name)) for receipt, name in (
                    (context['copy'], 'pending_copy'), (context['stage_open'], 'pending_open'),
                    (context['final_open'], 'pending_open'), (context['stage_close'], 'pending_close'),
                    (context['source_close'], 'pending_close'), (context['activation'], 'pending_activation'),
                    (context['directory'], 'pending_directory'))),
                pending_release=context['pending_release'], journal_failed=context['journal_failed'])

        def baseline_matches(before, observed, *, source_present=True, extra_ids=()):
            a, b = before['semantic'], observed['semantic']
            source_ids = {document_id} if not source_present else set()
            wanted = [row for row in a['documents'] if row['document_id'] not in source_ids]
            actual = [row for row in b['documents'] if row['document_id'] not in extra_ids]
            windows = [row for row in a['windows'] if row['document_id'] not in source_ids]
            if (wanted != actual or windows != [row for row in b['windows'] if row['document_id'] not in extra_ids]
                    or a['reference_graph'] != b['reference_graph'] or observed['original_files'] != a['files']
                    or any(observed['snapshots'].get(key) != value for key, value in before['snapshots'].items() if key not in source_ids)):
                return False
            application = dict(b['application'])
            if application != a['application']:
                cwd = application.get('current_directory')
                allowed = []
                for receipt in (context['stage_open'], context['final_open']):
                    if _normal(receipt, 'pending_open'):
                        allowed.append(_directory_key(receipt.filename, parent=True))
                if (_directory_key(a['application']['current_directory']) is None
                        or _directory_key(cwd) is None or _directory_key(cwd) not in allowed):
                    return False
                application['current_directory'] = a['application']['current_directory']
            return application == a['application']

        def check(prepared, *, source_present=True, extra_ids=(), active=None):
            observed = inspect(prepared)
            if (observed['pending'] or observed['pending_release'] or observed['journal_failed']
                    or not baseline_matches(prepared.before, observed, source_present=source_present, extra_ids=extra_ids)
                    or (active is not None and observed['semantic']['active_document_id'] != active)):
                raise ExecutionFailure('first_save_effect_unconfirmed', 'Complete source/baseline/files/reference/UI oracle does not match.', uncertain=True)
            if context.get('final_expected') is not None:
                final_id = context['final_id']
                actual = dict(row=next((row for row in observed['semantic']['documents'] if row['document_id'] == final_id), None),
                    windows=[row for row in observed['semantic']['windows'] if row['document_id'] == final_id],
                    snapshot=observed['snapshots'].get(final_id))
                if actual != context['final_expected'] or observed['destination_file'] != context['final_file']:
                    raise ExecutionFailure('first_save_final_changed', 'Full verified final CAD/file/window state changed.', uncertain=True)
            return observed

        def native_step(name, receipt, pending, call, fields, evidence, *, activation=False):
            record(name, 'pending', evidence)
            try:
                call(receipt)
            finally:
                if receipt.native_call_returned or not receipt.native_call_attempted:
                    record(name, 'returned', {key: getattr(receipt, key) for key in fields})
            normal = (_normal(receipt, pending) if not activation else
                receipt.native_call_attempted is True and receipt.native_call_returned is True
                and receipt.pending_activation is False and type(receipt.native_error) is int
                and receipt.native_error in (0, 2) and receipt.raw_model is not None)
            if not normal:
                raise ExecutionFailure('first_save_native_unconfirmed', 'One normal exact native receipt is required.', uncertain=True)

        def open_copy(prepared, key, path, read_only, name, expected_file):
            current = check(prepared, active=document_id)
            if self.adapter.native_open_loaded_identity(path) is not None:
                raise ExecutionFailure('first_save_copy_already_loaded', 'No preexisting file handle may become an owned reader.', uncertain=True)
            receipt = self.adapter.new_native_open_receipt(tuple(entry.model for entry in context['current_entries']),
                path, 'part', configuration, read_only)
            context[key] = receipt
            fields = ('native_call_attempted', 'pending_open', 'native_call_returned', 'acknowledgement_valid',
                      'returned_new_identity', 'errors', 'warnings')
            native_step(name, receipt, 'pending_open', self.adapter.open_native_document, fields,
                dict(filename=path, configuration=configuration, read_only=read_only, file=expected_file))
            if (receipt.model is None or receipt.raw_model is None or receipt.returned_new_identity is not True
                    or type(receipt.errors) is not int or receipt.errors != 0
                    or type(receipt.warnings) is not int or receipt.warnings != 0):
                raise rejected('first_save_copy_open_failed', 'Persisted readback requires one returned new model and zero native codes.')
            entries, semantic, snapshots = self._capture(context['guarded_ids'])
            target = next((entry for entry in entries if entry.identity == receipt.identity), None)
            if target is None:
                raise ExecutionFailure('first_save_reader_unconfirmed', 'Exact native returned reader is absent.', uncertain=True)
            target_id = target.document_id
            context['stage_id' if key == 'stage_open' else 'final_id'] = target_id
            observed = check(prepared, extra_ids=(target_id,), active=target_id)
            row = next(row for row in observed['semantic']['documents'] if row['document_id'] == target_id)
            original = next(row for row in prepared.before['semantic']['documents'] if row['document_id'] == document_id)
            if (row['file'] != expected_file or row['active_configuration'] != configuration
                    or row['configurations'] != [configuration] or row['needs_save'] is not False
                    or row['mode']['read_only_state'] != int(read_only) or row['dependencies']
                    or not row['visible'] or row['view'] != original['view']
                    or len([window for window in semantic['windows'] if window['document_id'] == target_id]) != 1):
                raise ExecutionFailure('first_save_reader_unconfirmed', 'Persisted reader/config/mode/view/file oracle differs.', uncertain=True)
            mapping = clone_mapping(prepared.before['snapshots'][document_id], snapshots[target_id])
            if key == 'final_open':
                context['final_expected'] = dict(row=deepcopy(row),
                    windows=[deepcopy(window) for window in observed['semantic']['windows'] if window['document_id'] == target_id],
                    snapshot=deepcopy(snapshots[target_id]))
            return target, mapping

        def close_exact(prepared, target, key, name, *, source=False):
            target_id = target.document_id
            extra = (context['final_id'],) if source else (target_id,)
            observed = check(prepared, extra_ids=extra)
            row = next(item for item in observed['semantic']['documents'] if item['document_id'] == target_id)
            if (not source and row['needs_save'] is not False) or any(
                    not item['visible'] and item['document_id'] != target_id for item in observed['semantic']['documents']):
                raise ExecutionFailure('first_save_close_impact_unconfirmed', 'No dirty reader/hidden collateral may retire.', uncertain=True)
            title = row['title']
            if type(title) is not str or not title.strip() or sum(item['title'].casefold() == title.casefold() for item in observed['semantic']['documents']) != 1:
                raise ExecutionFailure('first_save_close_name_ambiguous', 'Close requires one unique exact native title.', uncertain=True)
            receipt = self.adapter.new_native_first_save_close_receipt(target.model, title)
            context[key] = receipt
            native_step(name, receipt, 'pending_close', self.adapter.close_native_first_save_document,
                ('native_call_attempted', 'pending_close', 'native_call_returned', 'acknowledgement_valid'),
                dict(document_id=target_id, native_name=title, retiring_document_ids=[target_id],
                     source_replacement=source))
            context['source_closed' if source else 'stage_closed'] = True
            observed = check(prepared, source_present=not source, extra_ids=(context['final_id'],) if source else ())
            if any(item['document_id'] == target_id for item in observed['semantic']['documents']):
                raise ExecutionFailure('first_save_retirement_unconfirmed', 'Normal close is not exact retirement proof.', uncertain=True)

        def activate_source(prepared):
            observed = check(prepared)
            if observed['semantic']['active_document_id'] == document_id:
                return
            if context['guarded_ids'] and not context['released_ui']:
                record('first_save_release_survivor_ui', 'pending', dict(document_ids=list(context['guarded_ids'])))
                context['pending_release'] = True
                context['native_guard'].release_survivor_ui_for_activation()
                context['pending_release'] = False
                context['released_ui'] = True
                record('first_save_release_survivor_ui', 'returned', dict(verified=True))
                check(prepared)
            receipt = self.adapter.new_native_activation_receipt(context['source'].model)
            context['activation'] = receipt
            native_step('first_save_activate_source_native', receipt, 'pending_activation', self.adapter.activate_native_open_document,
                ('native_call_attempted', 'pending_activation', 'native_call_returned', 'native_error'),
                dict(document_id=document_id), activation=True)
            check(prepared, active=document_id)

        def restore_directory(prepared, *, source_present=True, extra_ids=(), active=None):
            observed = check(prepared, source_present=source_present, extra_ids=extra_ids, active=active)
            original = prepared.before['semantic']['application']['current_directory']
            current = observed['semantic']['application']['current_directory']
            if original == current:
                return
            if context['directory'] is not None:
                raise ExecutionFailure('first_save_directory_repeated', 'Directory restoration is one-shot.', uncertain=True)
            # Mark factory start too: a failed preparation never enables cleanup.
            context['directory_started'] = True
            receipt = self.adapter.new_native_directory_restore_receipt(original, current)
            context['directory'] = receipt
            native_step('first_save_restore_directory_native', receipt, 'pending_directory', self.adapter.restore_native_open_directory,
                ('native_call_attempted', 'pending_directory', 'native_call_returned', 'acknowledgement_valid', 'setter_succeeded'),
                dict(original_directory=original, expected_current_directory=current))
            if receipt.setter_succeeded is not True:
                raise ExecutionFailure('first_save_directory_unconfirmed', 'Directory setter did not acknowledge success.', uncertain=True)
            observed = check(prepared, source_present=source_present, extra_ids=extra_ids, active=active)
            if observed['semantic']['application'] != prepared.before['semantic']['application']:
                raise ExecutionFailure('first_save_directory_unconfirmed', 'Final full application context differs.', uncertain=True)

        def cleanup_stage(prepared):
            stage = context['stage']
            record('first_save_cleanup_stage', 'pending', dict(stage=stage.checkpoint()))
            context['cleanup_started'] = True
            cleanup = self.files.cleanup_owned_stage(stage, context['lease'], verified_terminal=True)
            context['cleanup'] = cleanup
            record('first_save_cleanup_stage', 'returned', dict(cleanup=cleanup, stage=stage.checkpoint()))
            if (type(cleanup) is not dict or cleanup.get('file_removed') is not True
                    or cleanup.get('destination_removed') is not False or cleanup.get('status') != 'retained_empty_owned_directory'):
                raise ExecutionFailure('first_save_cleanup_unconfirmed', 'Only exact owned staging cleanup without destination removal is acknowledged.', uncertain=True)

        def apply(prepared):
            before = prepared.before
            check(prepared, active=document_id)
            def owned_change(checkpoint):
                context['stage_plan'] = checkpoint
                record('first_save_stage_create', 'returned' if checkpoint['creation_returned'] else 'pending', dict(stage=checkpoint))
            try:
                context['stage'] = self.files.create_owned_stage(context['lease'], on_owned_change=owned_change)
            except Exception as error:
                if hasattr(error, 'receipt'):
                    context['stage'] = error.receipt
                raise
            check(prepared, active=document_id)
            stage = context['stage']
            copy = self.adapter.new_native_first_save_copy_receipt(context['source'].model, str(stage.filename), configuration)
            context['copy'] = copy
            native_step('first_save_copy_native', copy, 'pending_copy', self.adapter.save_native_first_save_copy,
                ('native_call_attempted', 'pending_copy', 'native_call_returned', 'acknowledgement_valid', 'success', 'errors', 'warnings'),
                dict(document_id=document_id, filename=str(stage.filename), configuration=configuration))
            if (copy.success is not True or type(copy.errors) is not int or copy.errors != 0
                    or type(copy.warnings) is not int or copy.warnings != 0):
                raise rejected('first_save_copy_failed', 'SaveAs copy requires True and zero native codes.')
            check(prepared, active=document_id)
            staged_file = self.files.inspect_staged(stage)
            context['staged_file'] = staged_file
            reader, mapping = open_copy(prepared, 'stage_open', str(stage.filename), True,
                'first_save_open_stage_native', staged_file)
            context['stage_mapping'] = mapping
            if self.files.inspect_staged(stage) != staged_file:
                raise ExecutionFailure('first_save_staged_file_changed', 'Persisted readback changed staged bytes.', uncertain=True)
            close_exact(prepared, reader, 'stage_close', 'first_save_close_stage_native')
            activate_source(prepared)
            check(prepared, active=document_id)
            record('first_save_publish', 'pending', dict(stage=stage.checkpoint(), destination=before['destination']))
            published = self.files.publish(stage, context['lease'])
            context['published'] = published
            record('first_save_publish', 'returned', dict(publication=published))
            if type(published) is not dict or published.get('status') != 'published':
                raise rejected('first_save_publication_failed', 'Publication requires one verified no-replace filesystem effect.')
            if (stage.published is not True or stage.pending_publication is not False or stage.uncertain is not False
                    or published.get('destination') != before['destination']['destination']):
                raise ExecutionFailure('first_save_publication_unconfirmed', 'Exact publication receipt is required.', uncertain=True)
            check(prepared, active=document_id)
            cleanup_stage(prepared)
            context['final_file'] = self.files.observe_destination(before['destination'])
            if context['final_file'] is None or any(context['final_file'][key] != published['destination_file'][key]
                    for key in ('identity', 'bytes', 'sha256', 'mtime_ns', 'path')):
                raise ExecutionFailure('first_save_final_file_unconfirmed', 'Final file differs after verified owned staging cleanup.', uncertain=True)
            final, mapping = open_copy(prepared, 'final_open', before['destination']['destination'], False,
                'first_save_open_final_native', context['final_file'])
            observed = check(prepared, extra_ids=(final.document_id,), active=final.document_id)
            if observed['destination_file'] != context['final_file']:
                raise ExecutionFailure('first_save_final_file_changed', 'Final persisted file changed during native open.', uncertain=True)
            context['final_mapping'] = mapping
            close_exact(prepared, context['source'], 'source_close', 'first_save_close_source_native', source=True)
            restore_directory(prepared, source_present=False, extra_ids=(final.document_id,), active=final.document_id)
            observed = check(prepared, source_present=False, extra_ids=(final.document_id,), active=final.document_id)
            if observed['destination_file'] != context['final_file']:
                raise ExecutionFailure('first_save_final_file_changed', 'Final persisted file changed during source retirement.', uncertain=True)
            return dict(source_document_id=document_id, document_id=final.document_id,
                retired_document_ids=[document_id], filename=before['destination']['destination'],
                file=context['final_file'], reference_mapping=mapping, source_references_retired=True,
                resolve_saved_references_again=True, replacement_policy=before['replacement_policy'],
                view_mapping=dict(source_document_id=document_id, saved_document_id=final.document_id,
                    source_window_handles=[row['hwnd'] for row in before['semantic']['windows'] if row['document_id'] == document_id],
                    saved_window_handles=[row['hwnd'] for row in observed['semantic']['windows'] if row['document_id'] == final.document_id],
                    preserved=True), staging_cleanup=context['cleanup'])

        def verify(before, after, value):
            saved_id = value['document_id']
            return (context['source_closed'] and context['stage_closed']
                and _normal(context['source_close'], 'pending_close')
                and not after['pending'] and not after['pending_release'] and not after['journal_failed']
                and baseline_matches(before, after, source_present=False, extra_ids=(saved_id,))
                and after['semantic']['application'] == before['semantic']['application']
                and after['semantic']['active_document_id'] == saved_id
                and after['destination_file'] == value['file']
                and clone_mapping(before['snapshots'][document_id], after['snapshots'][saved_id]) == value['reference_mapping']
                and after['stage']['empty'] is True and after['stage']['file'] is None
                and after['cleanup'] == value['staging_cleanup'])

        def restore(before, prepared):
            stage = context['stage']
            if (context['journal_failed'] or context['pending_release'] or context.get('directory_started')
                    or context.get('cleanup_started') or context['source_close'] is not None
                    or (stage and (stage.pending_creation or stage.uncertain or stage.pending_publication or stage.published))):
                raise ExecutionFailure('first_save_restore_held', 'Pending/irreversible/native/journal effects prohibit cleanup or retry.', uncertain=True)
            copy = context['copy']
            if copy is not None and copy.native_call_attempted and (
                    not _normal(copy, 'pending_copy') or type(copy.success) is not bool
                    or any(type(getattr(copy, key)) is not int or not 0 <= getattr(copy, key) < 2 ** 31
                           for key in ('errors', 'warnings'))):
                raise ExecutionFailure('first_save_copy_held', 'Malformed native copy acknowledgement is never a cleanup receipt.', uncertain=True)
            observed = check(prepared)
            if context['stage_open'] is not None and not context['stage_closed']:
                receipt = context['stage_open']
                if not (_normal(receipt, 'pending_open') and receipt.raw_model is None
                        and receipt.model is None and receipt.returned_new_identity is False
                        and all(type(getattr(receipt, key)) is int and 0 <= getattr(receipt, key) < 2 ** 31
                                for key in ('errors', 'warnings'))):
                    raise ExecutionFailure('first_save_readback_held', 'Unconfirmed reader cannot be closed as rollback.', uncertain=True)
            if observed['semantic']['documents'] != before['semantic']['documents'] or observed['semantic']['windows'] != before['semantic']['windows']:
                raise ExecutionFailure('first_save_restore_unconfirmed', 'Rollback requires exactly the untouched source/baseline census.', uncertain=True)
            if context['published'] is not None and context['published'].get('status') != 'conflict':
                raise ExecutionFailure('first_save_publication_held', 'Only verified foreign no-effect conflict is a known publication failure.', uncertain=True)
            activate_source(prepared)
            restore_directory(prepared, active=document_id)
            if stage and observed['stage']['file'] is not None:
                # A false/warning copy that wrote data has no independent native
                # readback. Its file cannot be adopted as a verified artifact.
                if (not _normal(copy, 'pending_copy') or copy.success is not True
                        or context.get('staged_file') is None or observed['stage']['file'] != context['staged_file']):
                    raise ExecutionFailure('first_save_copy_held', 'Unverified persisted copy remains retained.', uncertain=True)
                cleanup_stage(prepared)

        def restored(before, after):
            return (after['semantic'] == before['semantic'] and after['snapshots'] == before['snapshots']
                and after['original_files'] == before['semantic']['files'] and not after['pending']
                and not after['pending_release'] and not after['journal_failed']
                and (after['stage'] is None or (after['stage']['empty'] is True and after['stage']['file'] is None)))

        class Guard:
            def __enter__(self):
                self.stack = ExitStack()
                self.released = False
                try:
                    context['lease'] = self.stack.enter_context(self_files.lease_destination(context_before['destination']))
                    context['native_guard'] = self.stack.enter_context(self_adapter.native_first_save_guard(
                        tuple(entry.model for entry in context['entries'] if entry is not context['source']), document_id))
                except BaseException:
                    self.stack.close()
                    raise
                return self

            def __exit__(self, *args):
                result = self.stack.__exit__(*args)
                self.released = True
                return result

            @property
            def evidence(self):
                native = context.get('native_guard')
                return dict(scope='native_first_save_guard_v1', native_guard=deepcopy(native.evidence) if native else None,
                            destination_lease_released=self.released)

        self_files, self_adapter = self.files, self.adapter
        context_before = None
        def guard(prepared):
            nonlocal context_before
            context_before = prepared.before
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
