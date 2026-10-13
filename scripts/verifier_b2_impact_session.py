"""Finite N5 passive session census around the retained current target reader.

No COM connection, guard acquisition, mutation, retry or cleanup. The native
owner must retain an event envelope across the refused request itself and bind
its durable journal separately. This reader cannot confer native acceptance.
"""
import hashlib
import json
from pathlib import Path
import stat

from solidworks_mcp.jobs import _json
from solidworks_mcp.native_document_open import NativeDocumentOpenCatalog
from solidworks_mcp.rectangle_snapshot import BASE, validated_rectangle_snapshot
from verifier_b2_impact_fixture import require


SCOPE = 'b2_impact_current_session_v1'


def equation_file_facts(binding):
    """Fingerprint only the exact private fixture file explicitly bound by owner."""
    from solidworks_mcp.exports_v2 import _is_reparse
    require(type(binding) is dict and set(binding) == {'path', 'sha256'}, 'Exact fixture file binding required.')
    path = Path(binding['path'])
    require(path.is_absolute() and path.suffix.lower() == '.txt'
            and path.resolve(strict=True).is_relative_to((Path.cwd() / 'work').resolve())
            and not any(_is_reparse(item) for item in (path, *path.parents)),
            'Only an absolute private nonredirected equation fixture is supported.')
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 16384, 'Bounded regular fixture file required.')
    raw = path.read_bytes()
    after = path.lstat()
    signature = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    digest = hashlib.sha256(raw).hexdigest()
    require(signature(before) == signature(after) and len(raw) == before.st_size
            and type(binding['sha256']) is str and digest == binding['sha256'],
            'Owned equation file changed during or since fixture preparation.')
    return dict(path=str(path), bytes=len(raw), sha256=digest,
                identity=[before.st_dev, before.st_ino], mtime_ns=before.st_mtime_ns, ctime_ns=before.st_ctime_ns)


class B2ImpactSession:
    def __init__(self, target, neighbor_entry, neighbor_before, *, equation_file=None):
        self.target = target
        self.documents = target.fixture.ownership.documents
        self.adapter = self.documents.adapter
        self.neighbor = neighbor_entry
        self.neighbor_identity = neighbor_entry.identity
        self.before = validated_rectangle_snapshot(neighbor_before)
        self.equation_file = None if equation_file is None else json.loads(_json(equation_file))
        require(self.before['clone_state']['profile'] == BASE
                and neighbor_entry.document_id != target.binding.document_id
                and self.adapter.identity(neighbor_entry.model) == self.neighbor_identity,
                'Exact retained neighbor and its complete original BASE required.')
        self.sessions = NativeDocumentOpenCatalog(self.documents, None, target.binding.connection_epoch)

    def capture(self, guarded_ids=()):
        file_before = None if self.equation_file is None else equation_file_facts(self.equation_file)
        entries, semantic = self.sessions._capture_session(guarded_ids)
        binding = self.target.binding
        expected = {binding.document_id: binding.model_identity,
                    self.neighbor.document_id: self.neighbor_identity}
        require(len(entries) == 2 and {entry.document_id for entry in entries} == set(expected)
                and all(entry.identity == expected[entry.document_id] for entry in entries),
                'Only the two original current model incarnations are supported.')
        row = next(row for row in semantic['documents'] if row['document_id'] == self.neighbor.document_id)
        require(row['document_type'] == 'part' and row['active_configuration'] == self.before['configuration']
                and row['configurations'] == self.before['configurations'], 'Original neighbor configuration changed.')
        target = self.target.capture()
        properties = target['deletion_context']['native_context']['equations']['properties']
        require(type(properties['linked_to_file']) is bool
                and properties['linked_to_file'] is (file_before is not None)
                and (properties['file_path'] == '' if file_before is None else
                     Path(properties['file_path']).resolve() == Path(file_before['path']).resolve()),
                'Actual equation link must match its exact owner-bound file; omitted files are not empty.')
        first = validated_rectangle_snapshot(self.adapter.rectangle_construction_snapshot(self.neighbor.model))
        second = validated_rectangle_snapshot(self.adapter.rectangle_construction_snapshot(self.neighbor.model))
        require(_json(first) == _json(second) == _json(self.before),
                'Complete neighbor data changed or became unavailable.')
        closing_entries, closing = self.sessions._capture_session(guarded_ids)
        file_after = None if self.equation_file is None else equation_file_facts(self.equation_file)
        require(_json(semantic) == _json(closing)
                and _json(file_before) == _json(file_after)
                and [(entry.document_id, entry.identity) for entry in entries]
                    == [(entry.document_id, entry.identity) for entry in closing_entries],
                'Session metadata/windows/files/UI/references/incarnations changed during capture.')
        return json.loads(_json(dict(scope=SCOPE, semantic=closing, target=target, neighbor=second,
                                    equation_file=file_after,
                                    accepted=False, native_b2_accepted=False, cleanup_authorized=False,
                                    full_refusal_context_available=False,
                                    open_gates=['event_envelope_across_refused_request',
                                                'bound_actual_refusal_job_and_replay',
                                                'terminal_fixture_journal_and_own_cleanup'])))


def same_refused_session(before, after):
    """Exact two returned observations; only a comparison, never permission."""
    fields = {'scope', 'semantic', 'target', 'neighbor', 'equation_file', 'accepted', 'native_b2_accepted',
              'cleanup_authorized', 'full_refusal_context_available', 'open_gates'}
    require(all(type(value) is dict and set(value) == fields and value['scope'] == SCOPE
                and all(value[key] is False for key in ('accepted', 'native_b2_accepted',
                    'cleanup_authorized', 'full_refusal_context_available')) for value in (before, after)),
            'Complete returned passive session observations required.')
    require(_json(before) == _json(after), 'Refused request changed a declared current observation.')
    return True
