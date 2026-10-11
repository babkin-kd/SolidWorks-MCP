"""Passive bounded native file closure, not a resolved CAD-load acceptance.

The domain must pair this manifest with a fresh complete application census,
and revalidate both under its durable execution guard. File inventories do not
establish referenced configuration resolution or ownership of loaded models.
"""

from pathlib import Path

from .native_document_open_policy import validate_native_open_arguments
from .documents import rejected
from .native_document_save import EXTENSIONS, MAX_OPEN_DOCUMENTS, MAX_TOTAL_BYTES, native_file_facts


def _physical_key(facts):
    return tuple(facts['identity'])


class NativeOpenFileManifest:
    def __init__(self, adapter):
        self.adapter = adapter

    def _once(self, filename, document_type, configuration, baseline_entries, baseline_semantic):
        source_key = str(Path(filename).resolve(strict=True)).casefold()
        loaded_rows = baseline_semantic['documents']
        entry_by_id = {entry.document_id: entry for entry in baseline_entries}
        if (len(loaded_rows) != len(entry_by_id) or len(loaded_rows) > MAX_OPEN_DOCUMENTS
                or {row['document_id'] for row in loaded_rows} != set(entry_by_id)):
            raise rejected('native_open_census_invalid', 'A complete fresh baseline catalog is required for file ownership classification.')
        queue = {filename.casefold(): (filename, document_type)}
        visited, spellings, physical_files, total = {}, set(), {}, 0
        for item in baseline_semantic['files']:
            facts = item['file']
            physical = _physical_key(facts)
            value = (item['document_type'], facts['sha256'], facts['bytes'])
            if physical in physical_files and physical_files[physical] != value:
                raise rejected('native_open_census_invalid', 'Baseline file aliases disagree in type or content.')
            if physical not in physical_files:
                physical_files[physical] = value
                total += facts['bytes']
        if total > MAX_TOTAL_BYTES:
            raise rejected('native_session_file_budget_exceeded', 'Existing files already exceed the full-session byte budget.')
        while queue:
            spelling, (path, kind) = queue.popitem()
            spellings.add(spelling)
            # Fingerprint the original spelling before resolve: never erase a
            # redirect/junction by resolving it prior to ancestry validation.
            facts = native_file_facts(path, kind)
            canonical = str(Path(path).resolve(strict=True))
            key = canonical.casefold()
            facts['path'] = canonical
            if key in visited:
                if visited[key]['file'] != facts or visited[key]['document_type'] != kind:
                    raise rejected('native_session_changed_during_read', 'A repeated dependency changed within the file manifest.')
                continue
            if len(visited) >= MAX_OPEN_DOCUMENTS:
                raise rejected('native_open_dependency_budget_exceeded', 'Native source and dependency closure exceed 5000 files.')
            physical = _physical_key(facts)
            prior = physical_files.get(physical)
            if prior is None:
                physical_files[physical] = (kind, facts['sha256'], facts['bytes'])
                total += facts['bytes']
                if total > MAX_TOTAL_BYTES:
                    raise rejected('native_session_file_budget_exceeded', 'Unique native source/dependency files exceed 2 GiB.')
            elif prior != (kind, facts['sha256'], facts['bytes']):
                raise rejected('native_session_changed_during_read', 'Aliases of a native file disagree in type or content.')
            borrowed = [row for row in loaded_rows if row['file'] is not None
                        and (row['file']['path'].casefold() == key or _physical_key(row['file']) == physical)]
            if len(borrowed) > 1:
                raise rejected('native_open_loaded_alias_ambiguous', 'Multiple preexisting models identify the same source/dependency file.')
            resident = self.adapter.native_open_loaded_identity(canonical)
            if resident is not None:
                matched = [entry for entry in baseline_entries if entry.identity == resident]
                if len(matched) != 1 or not borrowed or matched[0].document_id != borrowed[0]['document_id']:
                    raise rejected('native_open_census_invalid', 'Resident native data must identify one exact preexisting baseline model and file.')
            # A source hardlink is already loaded even if native path lookup
            # does not recognize the alias. Never acquire ownership by path.
            if key == source_key and (borrowed or resident is not None):
                raise rejected('native_document_already_loaded', 'Opening existing or referenced source data requires a separate explicit reuse contract.')
            inventory = self.adapter.native_open_file_inventory(canonical, kind)
            if (type(inventory) is not dict or set(inventory) != {'dependencies','configurations'}
                    or type(inventory['dependencies']) is not list or type(inventory['configurations']) is not list):
                raise rejected('native_open_inventory_invalid', 'Typed complete file configuration/dependency inventories are required.')
            names = inventory['configurations']
            if (any(type(name) is not str or not name.strip() or '\x00' in name for name in names)
                    or len(names) != len(set(names)) or len(names) > MAX_OPEN_DOCUMENTS
                    or (kind == 'drawing' and names) or (kind != 'drawing' and not names)):
                raise rejected('native_open_configurations_unavailable', 'Exact unique file configuration names are required.')
            if key == source_key and kind != 'drawing' and configuration not in names:
                raise rejected('native_open_configuration_not_found', 'The requested source configuration is absent; no last-saved fallback is allowed.')
            dependencies = []
            if len(inventory['dependencies']) > MAX_OPEN_DOCUMENTS:
                raise rejected('native_open_dependency_budget_exceeded', 'Dependency inventory exceeds the complete-manifest budget.')
            for dependency in inventory['dependencies']:
                if (type(dependency) is not dict or set(dependency) != {'name','path','document_type'}
                        or type(dependency['name']) is not str or not dependency['name']
                        or type(dependency['path']) is not str or '\x00' in dependency['path'] or not Path(dependency['path']).is_absolute()
                        or type(dependency['document_type']) is not str or dependency['document_type'] not in EXTENSIONS):
                    raise rejected('native_open_inventory_invalid', 'Every dependency requires one exact native name, absolute path and type.')
                dependencies.append(dict(dependency))
                child_key = dependency['path'].casefold()
                if child_key not in spellings and child_key not in queue:
                    if len(spellings) + len(queue) >= MAX_OPEN_DOCUMENTS:
                        raise rejected('native_open_dependency_budget_exceeded', 'Native manifest path spellings exceed the complete 5000-file budget.')
                    queue[child_key] = (dependency['path'], dependency['document_type'])
                elif child_key in queue and queue[child_key][1] != dependency['document_type']:
                    raise rejected('native_open_inventory_invalid', 'A queued native dependency has inconsistent document types.')
            # Re-read after native inventory calls, independently of the next
            # complete pass. No source bytes are written or refreshed here.
            after = native_file_facts(path, kind)
            after['path'] = canonical
            if after != facts:
                raise rejected('native_file_changed_during_read', 'Native file changed while querying its saved inventory.')
            visited[key] = dict(document_type=kind, file=facts, configurations=list(names),
                dependencies=sorted(dependencies, key=lambda row: (row['path'].casefold(),row['name'])),
                borrowed_document_id=borrowed[0]['document_id'] if borrowed else None)
        return dict(source_path=visited[source_key]['file']['path'], source_document_type=document_type,
                    configuration=configuration, files=[visited[key] for key in sorted(visited)], session_unique_bytes=total)

    def capture(self, filename, document_type, configuration, baseline_entries, baseline_semantic):
        validate_native_open_arguments(filename, document_type, configuration, False)
        # First reject missing/reparse source through the shared native facts
        # contract; resolve(strict=True) must not leak a raw missing-file error.
        native_file_facts(filename, document_type)
        entries = tuple(baseline_entries)
        before = self._once(filename, document_type, configuration, entries, baseline_semantic)
        after = self._once(filename, document_type, configuration, entries, baseline_semantic)
        if before != after:
            raise rejected('native_open_manifest_changed_during_read', 'Complete native file/dependency manifest changed between observations.')
        return after
