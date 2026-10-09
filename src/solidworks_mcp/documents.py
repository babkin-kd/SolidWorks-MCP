"""STA-owned document identities and observed-state tokens; no implicit target.

The adapter supplies COM identity objects, which need equality, not hashing.
Never persist those objects or pass them out of the apartment. These observation
tokens cover document metadata and update stamps, not arbitrary CAD properties;
they are not yet the complete mutation revision gate required by the plan.
"""

from dataclasses import dataclass, field
from copy import deepcopy
import hashlib
import json
import threading
import uuid

from .jobs import ExecutionFailure


def rejected(code, message):
    return ExecutionFailure(code, message, uncertain=False)


@dataclass
class _Entry:
    document_id: str
    identity: object
    model: object
    observed: dict | None = None
    sequence: int = 0
    geometry: dict = field(default_factory=dict)


class DocumentCatalog:
    """A catalog belongs to one connection/apartment, never to a file path."""

    def __init__(self, adapter):
        self.adapter = adapter
        self._thread = threading.get_ident()
        self._entries = []

    def _check_thread(self):
        if threading.get_ident() != self._thread:
            raise rejected('wrong_apartment', 'Document access must run on its owning STA thread.')

    def _refresh(self):
        self._check_thread()
        # Replace the catalog only after enumeration completes. An interrupted
        # COM call must not invalidate a partially enumerated set of documents.
        live = []
        for model in self.adapter.documents():
            identity = self.adapter.identity(model)
            entry = next((old for old in self._entries if old.identity == identity), None)
            if entry is None:
                entry = _Entry('doc_' + uuid.uuid4().hex, identity, model)
            else:
                entry.model = model
            if not any(old.document_id == entry.document_id for old in live):
                live.append(entry)
        self._entries = live  # Closed documents release their COM references here.

    def _observe(self, entry):
        snapshot = self.adapter.snapshot(entry.model)
        if snapshot != entry.observed:
            entry.sequence += 1
            entry.observed = deepcopy(snapshot)
        encoded = json.dumps({'document_id': entry.document_id, 'sequence': entry.sequence,
                              'snapshot': snapshot}, ensure_ascii=False, sort_keys=True,
                             separators=(',', ':'), allow_nan=False)
        return {**deepcopy(snapshot), 'document_id': entry.document_id,
                'observation_revision': 'obs_' + hashlib.sha256(encoded.encode('utf-8')).hexdigest(),
                'observation_sequence': entry.sequence}

    def list(self):
        self._refresh()
        return {'documents': [self._observe(entry) for entry in self._entries],
                'solidworks_revision': self.adapter.revision,
                'revision_scope': 'update_stamp_and_document_metadata'}

    def resolve(self, document_id: str, configuration: str):
        """Internal STA-only target resolution; callers must never export entry.model."""
        self._refresh()
        entry = next((entry for entry in self._entries if entry.document_id == document_id), None)
        if entry is None:
            raise rejected('document_not_open', 'Unknown or closed document_id; list open documents again.')
        observed = self._observe(entry)
        configurations = observed['configurations']
        if configuration not in configurations and not (not configurations and configuration == ''):
            raise rejected('configuration_not_found', 'The explicit configuration does not exist in this document.')
        return entry, observed

    def get(self, document_id: str, configuration: str):
        entry, observed = self.resolve(document_id, configuration)
        # Metadata can be read without activating either the document or the
        # configuration. This tool makes no promise of inactive geometry access.
        return {**observed, 'configuration': configuration,
                'configuration_is_active': configuration == observed['active_configuration'],
                'revision_scope': 'update_stamp_and_document_metadata'}

    def close(self):
        self._check_thread()
        self._entries.clear()
        self.adapter.close()
