"""Guarded, single-file part export; publication is not a CAD/FS transaction.

No public tools are registered here. The runtime supplies a durable mutating job
and an approved, local output directory owned by the server/operator. Export
revisions cover complete supported analytical boundaries and export settings; they are
not feature-rename revisions or assertions about every add-in's metadata.
"""

from dataclasses import asdict, dataclass
from copy import deepcopy
import hashlib
import math
import os
from pathlib import Path
import re
import stat
import struct
import uuid

from .documents import rejected
from .jobs import ExecutionFailure, _json
from .mutations import MutationCoordinator, PreparedMutation
from .step_units import MAX_STEP_UNIT_BYTES, declared_step_length_unit


SCOPE = 'part_solid_brep_export_v1'
EXTENSIONS = {'stl': '.stl', 'step': '.step', 'parasolid': '.x_t'}
MAX_FILE_BYTES = 1024 * 1024 * 1024


@dataclass(frozen=True)
class ExportOptions:
    format: str
    filename: str
    units: str = ''

    def checked(self):
        if self.format not in EXTENSIONS:
            raise rejected('unsupported_export_format', 'Supported formats: stl, step, parasolid.')
        if (not isinstance(self.filename, str) or not 1 <= len(self.filename) <= 160
                or self.filename != self.filename.strip() or self.filename.endswith(('.', ' '))
                or re.search(r'[\x00-\x1f\x7f\\/:*?"<>|]', self.filename)
                or self.filename in ('.', '..') or self.filename.startswith('.')):
            raise rejected('invalid_export_filename', 'Use one plain filename, without directories or reserved characters.')
        stem = self.filename.split('.', 1)[0].upper()
        if stem in {'CON', 'PRN', 'AUX', 'NUL'} or re.fullmatch(r'(COM|LPT)[1-9]', stem):
            raise rejected('invalid_export_filename', 'Reserved Windows device filename.')
        if Path(self.filename).suffix.lower() != EXTENSIONS[self.format]:
            raise rejected('export_extension_mismatch', 'Filename extension must match the explicit format.')
        if self.format == 'stl' and self.units not in ('mm', 'm', 'in'):
            raise rejected('explicit_stl_units_required', 'STL has no unit metadata: specify mm, m or in.')
        if self.format != 'stl' and self.units != '':
            raise rejected('unsupported_export_units', 'Neutral-format unit overrides are not implemented.')
        return self


@dataclass(frozen=True)
class ExportManifest:
    operation_id: str
    document_id: str
    configuration: str
    source_revision: str
    revision_scope: str
    path: str
    format: str
    bytes: int
    sha256: str
    coordinate_frame: str
    units: str | None
    units_embedded: bool | None
    unit_evidence: str
    native_errors: int
    native_warnings: int
    source_unchanged: bool
    preferences_restored: bool
    publication: str
    file_validation: dict
    export_settings: dict
    geometry_roundtrip_verified: bool = False


def _identity(path):
    value = path.lstat()
    return value.st_dev, value.st_ino


def _is_reparse(path):
    # pathlib.Path.is_junction only exists in Python 3.12+, while this project
    # supports 3.11. Windows reparse points include junctions and other redirects.
    return (path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0)
        & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)))


def _plain_directory(path):
    # Approved root is a server-owned trust boundary, not a client path. Reject
    # junctions/symlinks in its ancestry; revalidate its identity before I/O.
    for ancestor in (path, *path.parents):
        if _is_reparse(ancestor):
            raise rejected('unsafe_export_directory', 'Export directories must not use symlinks or junctions.')
    if not path.is_dir():
        raise rejected('export_directory_missing', 'Approved export directory must already exist.')


def validate_export_file(path, options):
    """Structural verification and hashing, not a BREP round-trip assertion."""
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_FILE_BYTES:
        raise rejected('invalid_export_file', 'Export must be a nonempty, bounded regular file.')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
        stream.seek(0)
        if options.format == 'stl':
            header = stream.read(84)
            count = struct.unpack('<I', header[80:84])[0] if len(header) == 84 else 0
            if count == 0 or info.st_size != 84 + count * 50:
                raise rejected('invalid_export_file', 'Binary STL triangle count/length mismatch.')
            low, high = [math.inf] * 3, [-math.inf] * 3
            for _ in range(count):
                values = struct.unpack('<12fH', stream.read(50))
                if not all(math.isfinite(number) for number in values[:12]):
                    raise rejected('invalid_export_file', 'STL contains nonfinite normals or coordinates.')
                for start in (3, 6, 9):
                    for axis in range(3):
                        low[axis] = min(low[axis], values[start + axis])
                        high[axis] = max(high[axis], values[start + axis])
            facts = {'kind': 'binary_stl_structure', 'triangle_count': count,
                     'bounding_box': {'min': low, 'max': high, 'units': options.units},
                     'units': options.units, 'units_embedded': False,
                     'unit_evidence': 'Explicit request plus verified native swExportStlUnits; STL stores no units.'}
        elif options.format == 'step':
            # Inspect the complete bounded file: a prefix cannot establish that
            # later representation contexts use the same length unit.
            if info.st_size > MAX_STEP_UNIT_BYTES:
                raise rejected('step_unit_validation_limit', 'STEP unit validation supports files up to 4 MiB.')
            # Unit syntax is ASCII. Preserve every byte one-to-one while the
            # metadata parser discards opaque quoted names/comments: native
            # SW files can contain non-ASCII labels in those fields.
            prefix = stream.read(info.st_size).decode('latin1')
            stream.seek(max(0, info.st_size - 4096))
            suffix = stream.read().decode('ascii', errors='replace')
            if 'ISO-10303-21;' not in prefix[:256] or 'END-ISO-10303-21;' not in suffix:
                raise rejected('invalid_export_file', 'STEP exchange-file envelope is missing.')
            try:
                unit = declared_step_length_unit(prefix)
            except ValueError:
                raise rejected('unsupported_export_unit_declaration', 'No single supported STEP SI length context was verified.') from None
            facts = {'kind': 'step_exchange_envelope', 'units': unit,
                     'units_embedded': True,
                     'unit_evidence': 'GLOBAL_UNIT_ASSIGNED_CONTEXT references a supported SI LENGTH_UNIT declaration.'}
        else:
            prefix = stream.read(4096)
            if not prefix.startswith(b'**') or b'PARASOLID' not in prefix.upper():
                raise rejected('invalid_export_file', 'Parasolid text transmit header was not identified.')
            facts = {'kind': 'parasolid_text_header', 'units': None, 'units_embedded': None,
                     'unit_evidence': 'Native Parasolid output; coordinate units are not independently verified by this validator.'}
    after = path.lstat()
    if ((after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)):
        raise rejected('export_file_changed', 'Staged file changed during verification.')
    return {'bytes': info.st_size, 'sha256': digest.hexdigest(), 'validation': facts,
            'identity': [info.st_dev, info.st_ino]}


class ExportCatalog:
    def __init__(self, documents, store, connection_epoch, approved_output_root, *, adapter=None, mutation_guard=None):
        self.documents = documents
        self.adapter = adapter or documents.adapter
        self.store = store
        self.connection_epoch = connection_epoch
        self.coordinator = MutationCoordinator(store, connection_epoch)
        self.mutation_guard = mutation_guard
        path = Path(approved_output_root).absolute()
        _plain_directory(path)
        self.root = path.resolve(strict=True)
        self.root_identity = _identity(self.root)

    def _check_root(self):
        _plain_directory(self.root)
        if _identity(self.root) != self.root_identity:
            raise rejected('export_directory_changed', 'Approved output directory identity changed.')

    def _destination(self, options):
        self._check_root()
        destination = self.root / options.filename
        if os.path.lexists(destination):
            raise rejected('export_file_exists', 'Destination exists; overwriting is not supported.')
        return destination

    def _state(self, document_id, configuration, options):
        entry, observed = self.documents.resolve(document_id, configuration)
        if observed['document_type'] != 'part':
            raise rejected('unsupported_document_type', 'Initial export supports solid parts only.')
        if observed['active_configuration'] != configuration:
            raise rejected('configuration_not_active', 'Export requires the explicit configuration already active.')
        if not self.adapter.export_document_is_active(entry.model):
            raise rejected('document_not_active', 'Export requires the explicit document already active.')
        watch = entry.features.get('watch')
        if watch is None:
            watch = self.adapter.watch_part(entry.model)
            entry.features['watch'] = watch
        sequence = watch.poll()
        configuration_identity = self.adapter.configuration_identity(entry.model, configuration)
        configurations = entry.features.setdefault('export_configurations', {})
        cached = configurations.get(configuration)
        if cached is None or cached[0] != configuration_identity:
            cached = configuration_identity, 'cfg_' + uuid.uuid4().hex
            configurations[configuration] = cached
        semantic = self.adapter.export_source_snapshot(entry.model)
        semantic = {**semantic, 'export_profile': self.adapter.export_profile(options)}
        preferences = self.adapter.export_preferences(options)
        current, after = self.documents.resolve(document_id, configuration)
        if current is not entry or after != observed:
            raise rejected('document_changed_during_read', 'Export source changed during collection.')
        # Both getters and canonical PyIUnknown equality can perform native
        # work. Complete them before the final notification poll.
        closing_identity = self.adapter.configuration_identity(entry.model, configuration)
        closing_active = self.adapter.export_document_is_active(entry.model)
        same_identity = closing_identity == configuration_identity
        closing_sequence = watch.poll()
        if (not same_identity or not closing_active
                or closing_sequence != sequence):
            raise rejected('document_changed_during_read', 'Export source changed during collection.')
        payload = {'scope': SCOPE, 'connection_epoch': self.connection_epoch, 'document_id': document_id,
                   'configuration': configuration, 'configuration_epoch': cached[1],
                   'observed': observed, 'semantic': semantic, 'preferences': preferences,
                   'options': asdict(options), 'event_sequence': sequence, 'solidworks_revision': self.adapter.revision}
        revision = 'export_rev_' + hashlib.sha256(_json(payload).encode('utf-8')).hexdigest()
        return entry, revision, semantic, preferences

    def prepare(self, document_id, configuration, format, filename, units=''):
        options = ExportOptions(format, filename, units).checked()
        destination = self._destination(options)
        entry, revision, semantic, _ = self._state(document_id, configuration, options)
        # Full supported analytical boundary and native metadata must remain
        # stable. Native Copy/Save byte streams are not canonical geometry.
        if self._state(document_id, configuration, options)[1] != revision:
            raise rejected('export_revision_unstable', 'Export source serialization is not repeatable; no write is allowed.')
        return {'document_id': document_id, 'configuration': configuration, 'revision': revision,
                'revision_scope': SCOPE, 'options': asdict(options), 'path': str(destination),
                'source': deepcopy(semantic), 'geometry_roundtrip_verified': False}

    def execute(self, operation_id, document_id, configuration, expected_revision, format, filename, units=''):
        options = ExportOptions(format, filename, units).checked()
        if self.mutation_guard is None:
            raise rejected('mutation_guard_unavailable', 'Export requires an owning-STA native UI guard.')
        destination = self._destination(options)
        # Server-generated, unrelated to request/path input. No filesystem write
        # occurs until MutationCoordinator has committed the durable checkpoint.
        staging = self.root / ('.mcp-export-' + uuid.uuid4().hex)
        temporary = staging / ('model' + EXTENSIONS[format])
        context = {'staging_created': False, 'published': False,
                   'publication_uncertain': False, 'facts': None}

        def prepare():
            entry, revision, semantic, preferences = self._state(document_id, configuration, options)
            context['entry'] = entry
            return PreparedMutation(revision, {'scope': SCOPE, 'source': semantic, 'preferences': preferences,
                'options': asdict(options), 'destination': str(destination), 'destination_was_absent': True,
                'staging_directory': str(staging), 'temporary_path': str(temporary)}, effect_scope='application')

        def validate(prepared):
            self._destination(options)
            entry, revision, _, _ = self._state(document_id, configuration, options)
            return entry is context['entry'] and revision == prepared.revision

        def source_state():
            entry, _, semantic, preferences = self._state(document_id, configuration, options)
            if entry is not context['entry']:
                raise rejected('document_identity_changed', 'Export source native identity changed.')
            return {'source': semantic, 'preferences': preferences}

        def clean_staging():
            if not context['staging_created']:
                return
            if _identity(staging) != context['staging_identity'] or _is_reparse(staging):
                raise RuntimeError('Owned staging directory identity changed; no cleanup attempted.')
            if os.path.lexists(temporary):
                # SaveAs runs exclusively inside this freshly created directory.
                # Refuse links/unknown identities rather than deleting targets.
                info = temporary.lstat()
                if not stat.S_ISREG(info.st_mode):
                    raise RuntimeError('Unexpected staged file type; no cleanup attempted.')
                if context.get('temporary_identity') and _identity(temporary) != context['temporary_identity']:
                    raise RuntimeError('Staged file identity changed; no cleanup attempted.')
                temporary.unlink()
            staging.rmdir()  # Never recursively delete unexpected sidecars/files.
            context['staging_created'] = False

        def apply(prepared):
            self._check_root()
            staging.mkdir(mode=0o700)
            context['staging_created'] = True
            context['staging_identity'] = _identity(staging)
            native = self.adapter.export_part_to_file(context['entry'].model, temporary, options,
                prepared.before['preferences'])
            if not isinstance(native, dict) or native.get('success') is not True or native.get('errors') != 0:
                raise rejected('native_export_failed', f'Native SaveAs3 did not confirm success: {native}.')
            if native.get('warnings') != 0:
                raise rejected('native_export_warning', f'Export warnings require review before publication: {native}.')
            context['temporary_identity'] = _identity(temporary)
            facts = validate_export_file(temporary, options)
            context['facts'] = facts
            current = source_state()
            if current != {'source': prepared.before['source'], 'preferences': prepared.before['preferences']}:
                raise rejected('export_source_changed', 'Source/preference preservation was not verified; output will not be published.')
            if _identity(staging) != context['staging_identity'] or _is_reparse(staging):
                raise rejected('export_directory_changed', 'Owned staging directory identity changed.')
            entries = list(staging.iterdir())
            if len(entries) != 1:
                raise rejected('unexpected_export_files', 'Unexpected sidecars appeared; no output will be published.')
            # SolidWorks can change extension casing (model.stl -> model.STL)
            # on Windows. Establish the one actual file by native filesystem
            # identity, not a case-sensitive comparison of directory names.
            # A second entry is always a sidecar, even if it is a hard link to
            # the same file. Do not normalize or guess an alternative path.
            entry = entries[0]
            if (_is_reparse(entry) or not stat.S_ISREG(entry.lstat().st_mode)
                    or _identity(entry) != context['temporary_identity']
                    or _identity(temporary) != context['temporary_identity']):
                raise rejected('export_file_changed', 'Staged directory entry differs from the verified export file.')
            # Windows FlushFileBuffers (os.fsync) needs a writable handle;
            # this is our verified staging file, never an existing user file.
            with temporary.open('r+b') as stream:
                os.fsync(stream.fileno())
            self._destination(options)
            # Same filesystem hard-link insertion is atomic and fails if any
            # destination exists. os.replace/rename-overwrite is never used.
            # A filesystem call may apply a side effect before losing its
            # acknowledgement. Never infer "not published" from an exception.
            context['publication_uncertain'] = True
            try:
                os.link(temporary, destination, follow_symlinks=False)
            except FileExistsError:
                try:
                    if os.path.lexists(destination) and _identity(destination) != tuple(facts['identity']):
                        context['publication_uncertain'] = False  # Confirmed foreign-file conflict.
                except OSError:
                    pass  # Unknown destination identity keeps the conservative hold.
                raise
            context['published'] = True
            context['publication_uncertain'] = False
            published = validate_export_file(destination, options)
            if published != facts:
                raise RuntimeError('Published file identity/content differs from the verified staging file.')
            clean_staging()
            validation = facts['validation']
            return asdict(ExportManifest(operation_id, document_id, configuration, expected_revision, SCOPE,
                str(destination), format, facts['bytes'], facts['sha256'], 'part_model',
                validation['units'], validation['units_embedded'], validation['unit_evidence'],
                0, 0, True, True, 'atomic_no_overwrite_link', validation,
                prepared.before['source']['export_profile']))

        def inspect(prepared):
            result = source_state()
            result['published'] = context['published']
            result['publication_uncertain'] = context['publication_uncertain']
            result['staging_clean'] = not context['staging_created']
            result['file'] = validate_export_file(destination, options) if context['published'] else None
            return result

        def verify(before, after, value):
            return (after['source'] == before['source'] and after['preferences'] == before['preferences']
                and after['published'] is True and after['staging_clean'] is True
                and after['file'] == context['facts'] and value['sha256'] == after['file']['sha256'])

        def restore(before, prepared):
            # A published output is never deleted by a generic exception handler.
            # Journal or source uncertainty after publication requires inspection.
            clean_staging()
            if context['published'] or context['publication_uncertain']:
                raise RuntimeError('Output publication was confirmed or remains uncertain; inspect its recorded path instead of replay or deletion.')

        def verify_restored(before, restored):
            return (restored['source'] == before['source'] and restored['preferences'] == before['preferences']
                and restored['published'] is False and restored['publication_uncertain'] is False
                and restored['staging_clean'] is True)

        return self.coordinator.execute(operation_id, document_id=document_id, configuration=configuration,
            expected_revision=expected_revision, prepare=prepare, validate=validate, apply=apply,
            inspect=inspect, verify=verify, restore=restore, verify_restored=verify_restored,
            guard=lambda prepared: self.mutation_guard(context['entry'].model))
