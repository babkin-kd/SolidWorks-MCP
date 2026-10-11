"""One clean CloseDoc with full window/file census; no retained-data unload claim."""

import hashlib
from pathlib import Path

from .documents import rejected
from .jobs import ExecutionFailure, _json
from .mutations import MutationCoordinator, PreparedMutation
from .native_document_save import EXTENSIONS, MAX_OPEN_DOCUMENTS, MAX_TOTAL_BYTES, native_file_facts


SCOPE = 'native_document_close_clean_v1'


class NativeDocumentCloseCatalog:
    def __init__(self, documents, store, connection_epoch):
        self.documents, self.adapter = documents, documents.adapter
        self.connection_epoch = connection_epoch
        self.coordinator = MutationCoordinator(store, connection_epoch)

    @staticmethod
    def _invalid(message):
        return rejected('native_close_census_invalid', message)

    def _capture_once(self, guarded_ids=()):
        self.documents._refresh()
        entries = tuple(self.documents._entries)
        if len(entries) > MAX_OPEN_DOCUMENTS:
            raise rejected('native_session_budget_exceeded', 'Complete close census exceeds 5000 models.')
        rows, files, spellings, total = [], {}, {}, 0

        def fingerprint(filename, document_type):
            nonlocal total
            spelling = (filename.casefold(), document_type)
            if spelling in spellings:
                return spellings[spelling]
            # Fingerprint the original spelling first: resolving a symlink
            # must never erase the file/ancestry redirect rejection.
            facts = native_file_facts(filename, document_type)
            canonical = str(Path(filename).resolve(strict=True))
            key = canonical.casefold()
            facts['path'] = canonical
            if key not in files:
                files[key] = dict(document_type=document_type, file=facts)
                total += facts['bytes']
                if total > MAX_TOTAL_BYTES:
                    raise rejected('native_session_file_budget_exceeded', 'Full close file checkpoint exceeds 2 GiB.')
            elif files[key] != dict(document_type=document_type, file=facts):
                raise rejected('native_session_changed_during_read', 'A repeated native path changed within the complete census.')
            spellings[spelling] = files[key]['file']
            return spellings[spelling]

        for entry in entries:
            observed = self.documents._observe(entry)
            if observed['document_type'] not in EXTENSIONS:
                raise rejected('unsupported_document_type', 'Only native part/assembly/drawing documents can enter this close scope.')
            context = self.adapter.native_close_model_context(entry.model)
            if (not isinstance(context, dict) or type(context.get('visible')) is not bool
                    or type(context.get('dependencies')) is not list or not isinstance(context.get('mode'), dict)):
                raise self._invalid('Visibility, complete dependency list and edit modes must be typed.')
            dependencies = context['dependencies']
            if any(not isinstance(path, str) or not path or not Path(path).is_absolute() for path in dependencies):
                raise self._invalid('Every dependency must resolve to an absolute saved path.')
            mode = dict(context['mode'])
            if (type(mode.get('blocking_state')) is not int or type(mode.get('read_only_state')) is not int
                    or any(type(mode.get(key)) is not bool for key in ('editing_sketch', 'editing_component', 'view_only'))):
                raise self._invalid('Native mode flags require strict integer/Boolean values.')
            allowed_blocks = (0, 2) if entry.document_id in guarded_ids else (0,)
            if (mode['blocking_state'] not in allowed_blocks or mode['editing_sketch']
                    or mode['editing_component'] or mode['view_only']):
                raise rejected('native_document_edit_mode', 'Finish active editing/commands before closing; no foreign UI lock is borrowed.')
            # Only survivor locks owned by this execution may differ from baseline.
            if entry.document_id in guarded_ids:
                mode['blocking_state'] = 0
            facts = None
            if observed['path']:
                facts = fingerprint(observed['path'], observed['document_type'])
            dependency_files = []
            for dependency in sorted(set(dependencies), key=str.casefold):
                kind = next((kind for kind, extension in EXTENSIONS.items() if Path(dependency).suffix.lower() == extension), None)
                if kind is None:
                    raise rejected('native_close_dependency_unsupported', 'Every saved dependency must be a native part/assembly/drawing file.')
                dependency_files.append(fingerprint(dependency, kind))
            rows.append({**observed, 'view': self.adapter.document_view_snapshot(entry.model),
                         'visible': context['visible'], 'dependencies': sorted(set(dependencies), key=str.casefold),
                         'dependency_files': dependency_files, 'mode': mode, 'file': facts})
        windows = []
        handles = set()
        for raw, details in self.adapter.native_close_windows():
            identity = self.adapter.identity(raw)
            entry = next((entry for entry in entries if entry.identity == identity), None)
            if (entry is None or not isinstance(details, dict) or set(details) != {'hwnd', 'title'}
                    or type(details['hwnd']) is not int or not 0 < details['hwnd'] < 2 ** 63
                    or not isinstance(details['title'], str) or details['hwnd'] in handles):
                raise self._invalid('Every unique native window must map to the complete canonical model census.')
            handles.add(details['hwnd'])
            windows.append(dict(document_id=entry.document_id, **details))
        for row in rows:
            if row['visible'] != any(window['document_id'] == row['document_id'] for window in windows):
                raise self._invalid('Document visibility and its enumerated windows disagree.')
        active = self.adapter.active_document()
        token = self.adapter.identity(active) if active is not None else None
        current = next((entry for entry in entries if entry.identity == token), None)
        if token is not None and current is None:
            raise self._invalid('Active native model is outside the complete census.')
        application = self.adapter.native_close_application_context()
        if (not isinstance(application, dict) or set(application) != {'user_control', 'visible', 'current_directory', 'search_folders'}
                or type(application['user_control']) is not bool or type(application['visible']) is not bool
                or any(not isinstance(application[key], str) for key in ('current_directory', 'search_folders'))):
            raise self._invalid('Application ownership/visibility and search settings must be typed.')
        semantic = dict(documents=sorted(rows, key=lambda row: row['document_id']),
                        windows=sorted(windows, key=lambda row: row['hwnd']),
                        files=[files[key] for key in sorted(files)], application=dict(application),
                        active_document_id=current.document_id if current else None)
        _json(semantic)
        return entries, semantic

    def _capture(self, guarded_ids=()):
        first, before = self._capture_once(guarded_ids)
        second, after = self._capture_once(guarded_ids)
        if [entry.identity for entry in first] != [entry.identity for entry in second] or before != after:
            raise rejected('native_session_changed_during_read', 'Full close census changed between consecutive observations.')
        return second, after

    def _state(self, document_id, configuration, active_after_document_id, allowed_hidden_document_ids, guarded_ids=()):
        if (not isinstance(active_after_document_id, str) or type(allowed_hidden_document_ids) is not list
                or any(not isinstance(value, str) or not value for value in allowed_hidden_document_ids)
                or len(set(allowed_hidden_document_ids)) != len(allowed_hidden_document_ids)):
            raise rejected('native_close_policy_invalid', 'Use one explicit survivor ID and a unique exact list of allowed hidden document IDs.')
        entries, semantic = self._capture(guarded_ids)
        entry = next((entry for entry in entries if entry.document_id == document_id), None)
        if entry is None:
            raise rejected('document_not_open', 'The exact target is no longer open; list documents again.')
        target = next(row for row in semantic['documents'] if row['document_id'] == document_id)
        if (configuration != target['active_configuration']
                or (target['configurations'] and configuration not in target['configurations'])):
            raise rejected('configuration_not_active', 'Close requires the explicit active configuration; it never switches configurations.')
        native_name = target['title']
        if (not isinstance(native_name, str) or not native_name.strip()
                or sum(isinstance(row['title'], str) and row['title'].casefold() == native_name.casefold()
                       for row in semantic['documents']) != 1):
            raise rejected('native_close_name_ambiguous', 'The prepared native title must be nonempty and unique across all open models.')
        active_id = semantic['active_document_id']
        hidden = sorted(row['document_id'] for row in semantic['documents']
                        if row['document_id'] != document_id and row['document_id'] != active_id and not row['visible'])
        if set(hidden) != set(allowed_hidden_document_ids):
            raise rejected('native_close_hidden_impact_not_allowed', 'The exact complete nonactive hidden collateral list must be explicitly allowed.')
        retiring_ids = sorted([document_id, *hidden])
        closing = [row for row in semantic['documents'] if row['document_id'] in retiring_ids]
        if any(row['needs_save'] is not False for row in closing):
            raise rejected('native_close_dirty_document', 'Require-clean never discards dirty target or hidden collateral changes.')
        survivors = [row for row in semantic['documents'] if row['document_id'] not in retiring_ids]
        closing_paths = {row['file']['path'].casefold() for row in closing if row['file']}
        closing_identities = {tuple(row['file']['identity']) for row in closing if row['file']}
        def references_closing(facts):
            return facts is not None and (facts['path'].casefold() in closing_paths or tuple(facts['identity']) in closing_identities)
        if any(references_closing(row['file']) or any(references_closing(facts) for facts in row['dependency_files']) for row in survivors):
            raise rejected('native_close_referenced_data_unsupported', 'A surviving model references closing data; retained-reference close is a separate scope.')
        surviving_windows = [window for window in semantic['windows'] if window['document_id'] not in retiring_ids]
        if (not survivors or not surviving_windows) and semantic['application']['user_control'] is False:
            raise rejected('native_close_background_quit_risk', 'Closing the final document/window with UserControl=false is prohibited.')
        if active_id == document_id:
            if surviving_windows:
                chosen = next((row for row in survivors if row['document_id'] == active_after_document_id), None)
                if chosen is None or not chosen['visible']:
                    raise rejected('native_close_active_survivor_required', 'An active target requires an explicit visible surviving document.')
                expected_active = active_after_document_id
            else:
                if active_after_document_id:
                    raise rejected('native_close_active_survivor_invalid', 'No surviving window is available for the requested active document.')
                expected_active = None
        else:
            if active_after_document_id:
                raise rejected('native_close_active_survivor_invalid', 'Closing an inactive target preserves the original active document; use an empty survivor argument.')
            expected_active = active_id
        impact = dict(target_document_id=document_id, native_name=native_name,
                      retiring_document_ids=retiring_ids, hidden_document_ids=hidden,
                      survivor_document_ids=sorted(row['document_id'] for row in survivors),
                      retiring_window_handles=sorted(window['hwnd'] for window in semantic['windows'] if window['document_id'] in retiring_ids),
                      active_after_document_id=expected_active, policy='require_clean', data_unload_claimed=False)
        payload = dict(scope=SCOPE, connection_epoch=self.connection_epoch, document_id=document_id,
                       configuration=configuration, allowed_hidden_document_ids=sorted(allowed_hidden_document_ids),
                       active_after_document_id=active_after_document_id, semantic=semantic, impact=impact)
        revision = 'rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
        return entry, entries, semantic, impact, revision

    def prepare_close(self, document_id, configuration, active_after_document_id='', allowed_hidden_document_ids=None):
        if self.adapter.application_busy():
            raise rejected('application_busy', 'An existing command flag is never borrowed.')
        allowed = [] if allowed_hidden_document_ids is None else allowed_hidden_document_ids
        _, _, semantic, impact, revision = self._state(document_id, configuration, active_after_document_id, allowed)
        return dict(document_id=document_id, configuration=configuration, revision=revision, revision_scope=SCOPE,
                    baseline=semantic, impact=impact, native_operation='ISldWorks.CloseDoc', dirty_discard_supported=False)

    @staticmethod
    def _effect_matches(before, after):
        semantic, impact = before['semantic'], before['impact']
        retiring = set(impact['retiring_document_ids'])
        return (after['semantic']['documents'] == [row for row in semantic['documents'] if row['document_id'] not in retiring]
                and after['semantic']['windows'] == [row for row in semantic['windows'] if row['document_id'] not in retiring]
                and after['semantic']['application'] == semantic['application']
                and after['original_files'] == semantic['files'])

    @staticmethod
    def _disk_files(semantic):
        files = []
        for item in semantic['files']:
            files.append(dict(document_type=item['document_type'],
                              file=native_file_facts(item['file']['path'], item['document_type'])))
        return files

    def close(self, operation_id, document_id, configuration, expected_revision,
              active_after_document_id='', allowed_hidden_document_ids=None):
        allowed = [] if allowed_hidden_document_ids is None else allowed_hidden_document_ids
        context = dict(pending_native_call=False, pending_activation=False, native=None, guarded_ids=())

        def prepare():
            if self.adapter.application_busy():
                raise rejected('application_busy', 'An existing command flag is never borrowed.')
            entry, entries, semantic, impact, revision = self._state(document_id, configuration, active_after_document_id, allowed)
            context.update(entry=entry, entries=entries, impact=impact,
                           guarded_ids=tuple(impact['survivor_document_ids']))
            return PreparedMutation(revision, dict(scope=SCOPE, semantic=semantic, impact=impact), effect_scope='application')

        def validate(prepared):
            entry, _, _, _, revision = self._state(document_id, configuration, active_after_document_id,
                                                   allowed, context['guarded_ids'])
            return entry is context['entry'] and revision == prepared.revision

        def inspect(prepared):
            _, semantic = self._capture(context['guarded_ids'])
            return dict(semantic=semantic, original_files=self._disk_files(prepared.before['semantic']),
                        native=context['native'], pending_native_call=context['pending_native_call'],
                        pending_activation=context['pending_activation'])

        def apply(prepared):
            context['pending_native_call'] = True
            native = self.adapter.close_native_document(context['entry'].model, prepared.before['impact']['native_name'])
            context['native'] = native
            context['pending_native_call'] = False
            if not isinstance(native, dict) or native.get('native_call_returned') is not True:
                raise rejected('native_close_not_acknowledged', 'CloseDoc must normally return once; its absence of error is not retirement proof.')
            # Census only live models. Never activate before the exact retirement,
            # survivor and file effects have been independently established.
            observed = inspect(prepared)
            if not self._effect_matches(prepared.before, observed):
                raise rejected('native_close_effect_not_verified', 'Native retirement/window delta or unchanged survivors/files were not confirmed.')
            active_after = prepared.before['impact']['active_after_document_id']
            if active_after is not None and observed['semantic']['active_document_id'] != active_after:
                survivor = next(entry for entry in self.documents._entries if entry.document_id == active_after)
                context['pending_activation'] = True
                self.adapter.activate_native_close_survivor(survivor.model)
                context['pending_activation'] = False
            return dict(document_id=document_id, retiring_document_ids=prepared.before['impact']['retiring_document_ids'],
                        ui_closed=True, data_unload_claimed=False, policy='require_clean', native=native)

        def verify(before, after, value):
            return (self._effect_matches(before, after)
                    and after['semantic']['active_document_id'] == before['impact']['active_after_document_id']
                    and not after['pending_native_call'] and not after['pending_activation']
                    and after['native'] == value['native'])

        def restore(before, prepared):
            if context['pending_native_call'] or context['pending_activation']:
                raise ExecutionFailure('native_close_outcome_unknown', 'Throwing native close/activation is never replayed or replaced by observation.', uncertain=True)
            observed = inspect(prepared)
            if observed['semantic'] != before['semantic'] or observed['original_files'] != before['semantic']['files']:
                raise ExecutionFailure('native_close_restore_unsupported', 'A lost model/window or changed survivor/file is never reopened, undone or rewritten as rollback.', uncertain=True)

        def restored(before, after):
            return (after['semantic'] == before['semantic'] and after['original_files'] == before['semantic']['files']
                    and not after['pending_native_call'] and not after['pending_activation'])

        return self.coordinator.execute(operation_id, document_id=document_id, configuration=configuration,
            expected_revision=expected_revision, prepare=prepare, validate=validate, apply=apply,
            inspect=inspect, verify=verify, restore=restore, verify_restored=restored,
            guard=lambda prepared: self.adapter.native_close_guard(
                tuple(entry.model for entry in context['entries'] if entry.document_id in context['guarded_ids']),
                tuple(context['impact']['retiring_document_ids'])))
