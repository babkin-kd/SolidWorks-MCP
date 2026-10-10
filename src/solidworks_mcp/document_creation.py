"""Explicit template references and durable new-part creation, owned by one STA.

The application revision covers the declared open-document metadata/view scope,
not arbitrary add-in memory or a generic rollback of the CAD session. Existing
models are never closed or saved by this operation.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
import uuid

from .documents import rejected
from .features import russian_name
from .jobs import _json
from .jobs import ExecutionFailure
from .mutations import MutationCoordinator, PreparedMutation


SCOPE = 'new_empty_part_document_v1'
MAX_TEMPLATE_BYTES = 128 * 1024 * 1024


def template_signature(filename):
    """Fingerprint the exact readable file without loading CAD or writing it."""
    path = Path(filename).resolve(strict=True)
    if path.suffix.lower() != '.prtdot' or not path.is_file():
        raise rejected('invalid_part_template', 'An existing native .prtdot template is required.')
    before = path.stat()
    if not 0 < before.st_size <= MAX_TEMPLATE_BYTES:
        raise rejected('invalid_part_template', 'Template size exceeds the bounded readable-file scope.')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        count = 0
        while chunk := source.read(1024 * 1024):
            count += len(chunk)
            if count > MAX_TEMPLATE_BYTES:
                raise rejected('template_changed_during_read', 'Template exceeded the size bound while reading.')
            digest.update(chunk)
    after = path.stat()
    token = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    if token(before) != token(after) or count != before.st_size:
        raise rejected('template_changed_during_read', 'Template changed while its fingerprint was collected.')
    return {'path': str(path), 'size': count, 'sha256': digest.hexdigest(),
            'file_identity': list(token(after))}


@dataclass
class TemplateReference:
    object_id: str
    signature: dict


class DocumentCreationCatalog:
    """Internal candidate; publish only after installed native acceptance."""

    def __init__(self, documents, store, connection_epoch):
        self.documents, self.store = documents, store
        self.adapter = documents.adapter
        self.connection_epoch = connection_epoch
        self.application_id = 'app_' + uuid.uuid4().hex
        self.coordinator = MutationCoordinator(store, connection_epoch)
        self.references = {}
        self.receipts = {}  # Exact native ownership survives an unknown result on this connection.

    def list_templates(self):
        filename = self.adapter.default_part_template()
        if not filename:
            raise rejected('part_template_not_configured', 'Configure the SolidWorks default part template; no fallback creation.')
        try:
            signature = template_signature(filename)
        except (OSError, ValueError) as exc:
            raise rejected('part_template_unavailable', 'The configured native part template cannot be fingerprinted.') from exc
        ref = next((ref for ref in self.references.values() if ref.signature == signature), None)
        if ref is None:
            if len(self.references) >= 128:
                raise rejected('template_reference_budget_exceeded', 'Template references exhausted on this connection.')
            ref = TemplateReference('template_' + uuid.uuid4().hex, signature)
            self.references[ref.object_id] = ref
        return {'application_id': self.application_id, 'templates': [{'template_id': ref.object_id,
                'document_type': 'part', 'source': 'solidworks_configured_default',
                'filename': Path(signature['path']).name, 'signature': signature}],
                'native_creation_available': False}

    def _template(self, template_id):
        reference = self.references.get(template_id)
        if reference is None:
            raise rejected('template_reference_not_found', 'Use a template_id returned on this connection.')
        current = self.list_templates()['templates'][0]
        if current['template_id'] != template_id or current['signature'] != reference.signature:
            raise rejected('template_reference_stale', 'Configured template or its file changed; prepare a new request.')
        return reference

    def _capture(self):
        def capture():
            self.documents._refresh()
            entries = tuple(self.documents._entries)
            rows = []
            for entry in entries:
                observed = self.documents._observe(entry)
                if observed['document_type'] != 'part':
                    raise rejected('unsupported_open_document', 'Initial creation baseline supports existing parts only; assembly/drawing edit modes are not yet accepted.')
                if self.adapter.document_editing_sketch(entry.model):
                    raise rejected('existing_sketch_edit_active', 'Finish existing sketch editing before document creation.')
                rows.append({**observed, 'view': self.adapter.document_view_snapshot(entry.model)})
            active = self.adapter.active_document()
            token = self.adapter.identity(active) if active is not None else None
            active_entry = next((entry for entry in entries if entry.identity == token), None) if token is not None else None
            if token is not None and active_entry is None:
                raise rejected('application_changed_during_read', 'Active document is outside the enumerated baseline.')
            semantic = {'documents': sorted(rows, key=lambda row: row['document_id']), 'active_document_id': active_entry.document_id if active_entry else None,
                        'visible': self.adapter.application_visible()}
            return entries, semantic
        first, before = capture()
        second, after = capture()
        if ([entry.identity for entry in first] != [entry.identity for entry in second] or before != after):
            raise rejected('application_changed_during_read', 'Application documents or views changed during preparation.')
        _json(before)
        return first, before

    def prepare_create_part(self, template_id, name, configuration_name='Основная'):
        name, configuration_name = russian_name(name), russian_name(configuration_name)
        ref = self._template(template_id)
        if self.adapter.application_busy():
            raise rejected('application_busy', 'An existing CAD command is active; its flag is not borrowed.')
        entries, semantic = self._capture()
        if any(row['title'].casefold() == name.casefold() for row in semantic['documents']):
            raise rejected('document_title_conflict', 'The requested Russian document title already exists.')
        payload = {'scope': SCOPE, 'application_id': self.application_id, 'connection_epoch': self.connection_epoch,
                   'template_id': template_id, 'template': ref.signature, 'name': name,
                   'configuration_name': configuration_name, 'semantic': semantic}
        revision = 'rev_' + hashlib.sha256(_json(payload).encode('utf8')).hexdigest()
        return {'application_id': self.application_id, 'revision': revision, 'revision_scope': SCOPE,
                'template_id': template_id, 'name': name, 'configuration_name': configuration_name,
                'template': ref.signature, 'baseline': semantic, 'native_creation_available': False}

    @staticmethod
    def _same_existing(before, after, *, created_id=None):
        current = [row for row in after['documents'] if row['document_id'] != created_id]
        return current == before['documents'] and after['visible'] == before['visible']

    def create_part(self, operation_id, document_id, configuration, expected_revision,
                    template_id, name, configuration_name='Основная'):
        # document_id is the server-returned application token, not a model/name.
        if document_id != self.application_id or configuration != '':
            raise rejected('application_reference_mismatch', 'Use the exact prepared application target.')
        name, configuration_name = russian_name(name), russian_name(configuration_name)
        target = {}
        def prepare():
            public = self.prepare_create_part(template_id, name, configuration_name)
            entries, semantic = self._capture()
            if semantic != public['baseline']:
                raise rejected('application_changed_during_read', 'Baseline changed after template preparation.')
            if len(self.receipts) >= 1000:
                raise rejected('document_receipt_budget_exceeded', 'Native ownership receipts exhausted on this connection.')
            receipt = self.adapter.new_document_receipt(tuple(entry.model for entry in entries))
            self.receipts[operation_id] = receipt
            target.update(public=public, entries=entries, receipt=receipt)
            return PreparedMutation(public['revision'], {'scope': SCOPE, 'semantic': semantic,
                'template': public['template'], 'name': name, 'configuration_name': configuration_name}, effect_scope='application')
        def validate(prepared):
            # The guard owns CommandInProgress now; use the same baseline proof
            # without treating our own acknowledged flag as a foreign command.
            ref = self._template(template_id)
            _, semantic = self._capture()
            return ref.signature == target['public']['template'] and semantic == prepared.before['semantic']
        def apply(prepared):
            self.adapter.create_empty_part_document(target['receipt'], prepared.before['template']['path'], name, configuration_name)
            return {'name': name, 'configuration_name': configuration_name}
        def inspect(prepared):
            _, semantic = self._capture()
            receipt = target['receipt']
            evidence = self.adapter.created_document_evidence(receipt)
            created_id = None
            if evidence['complete']:
                created_id = next((entry.document_id for entry in self.documents._entries
                                   if entry.identity == self.adapter.created_document_identity(receipt)), None)
                if created_id is None:
                    raise rejected('created_document_not_current', 'Exact returned document is not in the application catalog.')
            return {'semantic': semantic, 'created_document_id': created_id, 'created': evidence}
        def verify(before, after, value):
            evidence, new_id = after['created'], after['created_document_id']
            return (evidence['complete'] is True and evidence['title'] == name and evidence['configuration'] == configuration_name
                    and evidence['empty_part'] is True and new_id is not None
                    and self._same_existing(before['semantic'], after['semantic'], created_id=new_id)
                    and after['semantic']['active_document_id'] == new_id)
        def restore(before, prepared):
            self.adapter.restore_created_document(target['receipt'])
        try:
            result = self.coordinator.execute(operation_id, document_id=document_id, configuration='',
                expected_revision=expected_revision, prepare=prepare, validate=validate, apply=apply,
                inspect=inspect, verify=verify, restore=restore,
                verify_restored=lambda before, after: before['semantic'] == after['semantic'] and after['created']['restored'] is True,
                guard=lambda prepared: self.adapter.document_creation_guard(tuple(entry.model for entry in target['entries'])))
        except ExecutionFailure as exc:
            if not exc.uncertain:
                self.receipts.pop(operation_id, None)
            raise
        if result['verified']:
            self.receipts.pop(operation_id, None)
        return result
