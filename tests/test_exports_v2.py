"""Export source/preference guards, owned-file cleanup and durable publication."""

from concurrent.futures import Future
from contextlib import nullcontext
from copy import deepcopy
import importlib.util
import math
import os
from pathlib import Path
import struct
import sys
from types import ModuleType, SimpleNamespace

import pytest

from solidworks_mcp.documents import DocumentCatalog, rejected
from solidworks_mcp.exports_v2 import (ExportCatalog, ExportOptions, _plain_directory,
    validate_export_file)
from solidworks_mcp.jobs import ExecutionFailure, JobRunner, JobStore
from test_document_catalog_v2 import Adapter as DocumentsAdapter, model


def binary_stl(*, invalid_number=False):
    # Negative-space geometry catches accidental 'translate to positive' claims
    # in the structural manifest; actual native frame equivalence is separate.
    return b'fixture'.ljust(80, b'\0') + struct.pack('<I', 1) + struct.pack('<12fH',
        0, 0, 1, -2, 0, 0, -1, 1, 0, math.nan if invalid_number else -1, 0, 0, 0)


class Watch:
    def __init__(self):
        self.sequence = 0
    def poll(self):
        return self.sequence
    def close(self):
        pass


class Adapter(DocumentsAdapter):
    def __init__(self):
        super().__init__()
        self.config_identity = object()
        self.geometry = {'fingerprint': 'complete-native-body-fixture'}
        self.preferences = {'coordinate_system': 'Система координат', 'unit': 3}
        self.watch = Watch()
        self.active = True
        self.selection = 0
        self.pending = False
        self.writes = 0
        self.fault = None
        self.write_hook = None
    def watch_part(self, wrapper):
        return self.watch
    def configuration_identity(self, wrapper, configuration):
        return self.config_identity
    def export_document_is_active(self, wrapper):
        return self.active
    def export_source_snapshot(self, wrapper):
        if self.selection:
            raise rejected('export_selection_not_empty', 'Nonempty fixture selection.')
        if self.pending:
            raise rejected('document_needs_rebuild', 'Fixture needs rebuild.')
        return {'document': self.snapshot(wrapper), 'geometry': deepcopy(self.geometry)}
    def export_preferences(self, options):
        return deepcopy(self.preferences)
    def export_profile(self, options):
        return {'format': options.format, 'stl_quality': 'fixture_reproducible', 'warnings_accepted': 0}
    def export_part_to_file(self, wrapper, path, options, before):
        self.writes += 1
        assert before == self.preferences
        self.preferences.update(coordinate_system='', unit=0)
        try:
            if options.format == 'stl':
                path.write_bytes(binary_stl(invalid_number=self.fault == 'nan'))
            elif options.format == 'step':
                unit = 'SI_UNIT(.MILLI.,.METRE.)' if self.fault != 'unit' else 'SI_UNIT($,.FOOT.)'
                path.write_text('ISO-10303-21;\nDATA;#1=(LENGTH_UNIT()NAMED_UNIT(*)' + unit +
                    ');#2=GLOBAL_UNIT_ASSIGNED_CONTEXT((#1));\nENDSEC;\nEND-ISO-10303-21;', encoding='ascii')
            else:
                path.write_bytes(b'**PARASOLID TRANSMIT FILE\n**fixture\n')
            if self.write_hook:
                self.write_hook(path)
            if self.fault == 'exception':
                raise RuntimeError('Injected native export exception.')
            if self.fault == 'sidecar':
                (path.parent / 'unexpected.txt').write_text('foreign file', encoding='utf8')
            if self.fault == 'source':
                self.geometry['fingerprint'] = 'concurrent-edit'
            self.watch.sequence += 1  # Native SaveNotify is expected, not a geometry edit.
            return {'success': self.fault != 'false', 'errors': 256 if self.fault == 'false' else 0,
                    'warnings': 1 if self.fault == 'warning' else 0}
        finally:
            if self.fault != 'restore':
                self.preferences = deepcopy(before)


@pytest.fixture
def setup(tmp_path):
    adapter = Adapter()
    adapter.models = [model()]
    documents = DocumentCatalog(adapter)
    document_id = documents.list()['documents'][0]['document_id']
    store = JobStore(tmp_path / 'jobs.sqlite')
    output = tmp_path / 'exports'
    output.mkdir()
    exports = ExportCatalog(documents, store, 'connection_1', output, mutation_guard=lambda model: nullcontext())
    yield adapter, documents, exports, store, document_id, output
    documents.close()
    store.close()


class InlineWorker:
    def submit(self, fn):
        future = Future()
        try:
            future.set_result(fn())
        except BaseException as exc:
            future.set_exception(exc)
        return future


def export(setup, *, request='export', revision=None, format='stl', filename='Кронштейн.stl', units=None):
    adapter, documents, exports, store, document_id, output = setup
    if units is None:
        units = 'mm' if format == 'stl' else ''
    if revision is None:
        revision = exports.prepare(document_id, 'Основная', format, filename, units)['revision']
    context = {'document_id': document_id, 'configuration': 'Основная', 'expected_revision': revision}
    arguments = {**context, 'format': format, 'filename': filename, 'units': units}
    return JobRunner(store, InlineWorker()).submit(request, 'document.export', arguments,
        lambda operation_id: exports.execute(operation_id, **arguments), context=context,
        mutates=True, pass_operation_id=True, verify=lambda result: result['verified'] is True)


def test_export_checkpoint_precedes_native_write_and_preserves_source(setup):
    adapter, documents, exports, store, document_id, output = setup
    before = deepcopy(adapter.models[0].state), deepcopy(adapter.preferences)
    def verify_checkpoint(path):
        job = store.list()['items'][0]
        assert job['mutation']['phase'] == 'prepared'
        checkpoint = job['mutation']['before_state']
        assert checkpoint['_mutation_effect_scope'] == 'application'
        assert checkpoint['temporary_path'] == str(path)
        assert not (output / 'Кронштейн.stl').exists()
    adapter.write_hook = verify_checkpoint
    job = export(setup)
    assert job['status'] == 'succeeded', job
    assert job['mutation']['phase'] == 'committed'
    manifest = job['result']['value']
    assert manifest['units'] == 'mm' and manifest['units_embedded'] is False
    assert manifest['file_validation']['bounding_box']['min'][0] == -2
    assert manifest['source_unchanged'] is True and manifest['preferences_restored'] is True
    assert manifest['geometry_roundtrip_verified'] is False
    assert [path.name for path in output.iterdir()] == ['Кронштейн.stl']
    assert (adapter.models[0].state, adapter.preferences) == before


def test_duplicate_request_returns_historical_output_without_second_write(setup):
    adapter, _, exports, _, document_id, _ = setup
    revision = exports.prepare(document_id, 'Основная', 'stl', 'Кронштейн.stl', 'mm')['revision']
    first = export(setup, revision=revision)
    retry = export(setup, revision=revision)
    assert first['status'] == 'succeeded', first
    assert first['operation_id'] == retry['operation_id']
    assert first['result'] == retry['result'] and adapter.writes == 1


@pytest.mark.skipif(os.name != 'nt', reason='Case-equivalent native export paths require Windows.')
@pytest.mark.parametrize('format,extension', [('stl', '.stl'), ('step', '.step'), ('parasolid', '.x_t')])
def test_native_uppercase_extension_publishes_same_verified_file(setup, format, extension):
    adapter, _, _, _, _, output = setup
    observed = []
    def uppercase_native_extension(path):
        identity = (path.stat().st_dev, path.stat().st_ino)
        actual = path.with_suffix(extension.upper())
        path.rename(actual)
        entries = list(path.parent.iterdir())
        assert len(entries) == 1 and entries[0].name == actual.name
        assert path.exists() and (path.stat().st_dev, path.stat().st_ino) == identity
        observed.append(identity)
    adapter.write_hook = uppercase_native_extension
    filename = 'Контрольная деталь' + extension
    job = export(setup, format=format, filename=filename)
    assert job['status'] == 'succeeded', job
    assert job['mutation']['phase'] == 'committed'
    manifest = job['result']['value']
    published = (output / filename).stat()
    assert (published.st_dev, published.st_ino) == observed[0]
    assert manifest['source_unchanged'] is True and manifest['preferences_restored'] is True
    assert [entry.name for entry in output.iterdir()] == [filename]


def test_second_staging_entry_is_rejected_even_when_same_file_identity(setup):
    adapter, _, _, store, document_id, output = setup
    def add_hardlink_sidecar(path):
        os.link(path, path.parent / 'second.stl')
    adapter.write_hook = add_hardlink_sidecar
    job = export(setup)
    assert job['status'] == 'unknown' and job['mutation']['phase'] == 'unresolved', job
    assert store.mutation_blockers('connection_1', document_id)
    assert not (output / 'Кронштейн.stl').exists()
    sidecar = next(output.glob('.mcp-export-*/second.stl'))
    assert sidecar.read_bytes() == binary_stl()


def test_one_foreign_directory_entry_cannot_replace_verified_file(setup, tmp_path, monkeypatch):
    _, _, _, store, document_id, output = setup
    foreign = tmp_path / 'foreign.stl'
    foreign.write_bytes(b'foreign file must remain untouched')
    original_iterdir = Path.iterdir
    def changed_directory_listing(path):
        if path.name.startswith('.mcp-export-'):
            return iter([foreign])
        return original_iterdir(path)
    monkeypatch.setattr(Path, 'iterdir', changed_directory_listing)
    job = export(setup)
    assert job['status'] == 'failed' and job['error']['code'] == 'export_file_changed', job
    assert job['mutation']['phase'] == 'rolled_back'
    assert not store.mutation_blockers('connection_1', document_id)
    assert foreign.read_bytes() == b'foreign file must remain untouched'
    assert not list(output.iterdir())


@pytest.mark.parametrize('change', ['geometry', 'preferences', 'configuration_identity', 'event'])
def test_stale_export_revision_blocks_write_without_using_feature_revision(setup, change):
    adapter, _, exports, _, document_id, output = setup
    revision = exports.prepare(document_id, 'Основная', 'stl', 'Кронштейн.stl', 'mm')['revision']
    if change == 'geometry':
        adapter.geometry['fingerprint'] = 'edited-without-stamp-change'
    elif change == 'preferences':
        adapter.preferences['unit'] = 2
    elif change == 'configuration_identity':
        adapter.config_identity = object()
    else:
        adapter.watch.sequence += 1
    job = export(setup, revision=revision)
    assert job['status'] == 'failed' and job['error']['code'] == 'stale_revision'
    assert adapter.writes == 0 and not list(output.iterdir())


@pytest.mark.parametrize('fault,code', [('exception', 'mutation_failed'), ('false', 'native_export_failed'),
    ('warning', 'native_export_warning'), ('nan', 'invalid_export_file')])
def test_native_failure_warning_or_invalid_file_restores_and_cleans_owned_file(setup, fault, code):
    adapter, _, _, store, document_id, output = setup
    adapter.fault = fault
    job = export(setup)
    assert job['status'] == 'failed' and job['error']['code'] == code, job
    assert job['mutation']['phase'] == 'rolled_back'
    assert not list(output.iterdir())
    assert not store.mutation_blockers('connection_1', document_id)


@pytest.mark.parametrize('fault', ['restore', 'source', 'sidecar'])
def test_unconfirmed_global_state_or_foreign_sidecar_creates_uncertainty_hold(setup, fault):
    adapter, _, _, store, document_id, output = setup
    adapter.fault = fault
    job = export(setup)
    assert job['status'] == 'unknown' and job['mutation']['phase'] == 'unresolved', job
    assert store.mutation_blockers('connection_1', 'another_document')
    assert not (output / 'Кронштейн.stl').exists()
    if fault == 'sidecar':
        assert list(output.glob('.mcp-export-*/unexpected.txt'))[0].read_text() == 'foreign file'


def test_existing_output_never_overwritten(setup):
    adapter, _, exports, _, document_id, output = setup
    existing = output / 'Кронштейн.stl'
    existing.write_bytes(b'user-content')
    with pytest.raises(ExecutionFailure) as failure:
        exports.prepare(document_id, 'Основная', 'stl', existing.name, 'mm')
    assert failure.value.code == 'export_file_exists' and adapter.writes == 0
    assert existing.read_bytes() == b'user-content'


def test_destination_created_during_native_export_wins_without_overwrite(setup):
    adapter, _, _, _, _, output = setup
    adapter.write_hook = lambda path: (output / 'Кронштейн.stl').write_bytes(b'concurrent-user-file')
    job = export(setup)
    assert job['status'] == 'failed' and job['error']['code'] == 'export_file_exists', job
    assert job['mutation']['phase'] == 'rolled_back'
    assert (output / 'Кронштейн.stl').read_bytes() == b'concurrent-user-file'
    assert len(list(output.iterdir())) == 1


def test_atomic_link_existence_race_never_overwrites(setup, monkeypatch):
    import solidworks_mcp.exports_v2 as module
    adapter, _, _, _, _, output = setup
    original = module.os.link
    def race(source, destination, **kwargs):
        Path(destination).write_bytes(b'concurrent-file-before-link')
        return original(source, destination, **kwargs)
    monkeypatch.setattr(module.os, 'link', race)
    job = export(setup)
    assert job['status'] == 'failed' and job['mutation']['phase'] == 'rolled_back', job
    assert (output / 'Кронштейн.stl').read_bytes() == b'concurrent-file-before-link'


def test_failure_after_publication_keeps_file_and_requires_reconciliation(setup, monkeypatch):
    import solidworks_mcp.exports_v2 as module
    adapter, _, _, store, _, output = setup
    original = module.validate_export_file
    def fail_after_publish(path, options):
        if path.parent == output:
            raise RuntimeError('Injected post-publication inspection error.')
        return original(path, options)
    monkeypatch.setattr(module, 'validate_export_file', fail_after_publish)
    job = export(setup)
    assert job['status'] == 'unknown' and job['mutation']['phase'] == 'unresolved', job
    assert (output / 'Кронштейн.stl').read_bytes() == binary_stl()
    assert store.mutation_blockers('connection_1', 'another_document')


@pytest.mark.parametrize('options', [
    ('stl', '../outside.stl', 'mm'), ('stl', 'C:\\outside.stl', 'mm'),
    ('stl', 'file.stl:secret', 'mm'), ('stl', 'CON.stl', 'mm'),
    ('stl', 'NUL.stl', 'mm'), ('stl', 'COM1.stl', 'mm'),
    ('stl', 'file.step', 'mm'), ('stl', 'file.stl', ''),
    ('step', 'file.step', 'mm'), ('3mf', 'file.3mf', ''),
    ('stl', '.hidden.stl', 'mm'), ('stl', ' trailing.stl', 'mm')])
def test_paths_formats_and_units_reject_before_writes(options):
    with pytest.raises(ExecutionFailure):
        ExportOptions(*options).checked()


@pytest.mark.parametrize('state,code', [('active', 'document_not_active'),
    ('selection', 'export_selection_not_empty'), ('pending', 'document_needs_rebuild')])
def test_unavailable_native_context_rejected_before_checkpoint(setup, state, code):
    adapter, _, exports, _, document_id, output = setup
    setattr(adapter, state, False if state == 'active' else True)
    with pytest.raises(ExecutionFailure) as failure:
        exports.prepare(document_id, 'Основная', 'stl', 'file.stl', 'mm')
    assert failure.value.code == code and adapter.writes == 0 and not list(output.iterdir())


def test_step_detects_declared_length_units_without_inference_from_cad_ui(setup):
    job = export(setup, format='step', filename='Деталь.step')
    assert job['status'] == 'succeeded', job
    manifest = job['result']['value']
    assert manifest['units'] == 'mm' and manifest['units_embedded'] is True


def test_step_unsupported_unit_declaration_is_not_published(setup):
    setup[0].fault = 'unit'
    job = export(setup, format='step', filename='Деталь.step')
    assert job['status'] == 'failed' and job['error']['code'] == 'unsupported_export_unit_declaration', job
    assert not list(setup[-1].iterdir())


def test_parasolid_manifest_does_not_invent_verified_file_units(setup):
    job = export(setup, format='parasolid', filename='Деталь.x_t')
    assert job['status'] == 'succeeded', job
    assert job['result']['value']['units'] is None
    assert job['result']['value']['units_embedded'] is None
    assert job['result']['value']['geometry_roundtrip_verified'] is False


@pytest.mark.parametrize('create_output,error_type', [(True, OSError), (True, FileExistsError), (False, OSError)])
def test_link_acknowledgement_failure_never_claims_verified_rollback(setup, monkeypatch, create_output, error_type):
    import os
    _, _, _, store, _, output = setup
    original_link = os.link

    def uncertain_link(source, destination, **kwargs):
        if create_output:
            original_link(source, destination, **kwargs)
        raise error_type('Simulated lost filesystem acknowledgement.')

    monkeypatch.setattr(os, 'link', uncertain_link)
    job = export(setup)
    assert job['status'] == 'unknown' and job['mutation']['phase'] == 'unresolved'
    assert store.mutation_blockers('connection_1', 'unrelated_document')
    destination = output / 'Кронштейн.stl'
    assert destination.exists() == create_output
    if create_output:
        assert destination.read_bytes() == binary_stl()
    assert not list(output.glob('.mcp-export-*'))


def test_windows_reparse_detection_is_compatible_with_python_311(tmp_path, monkeypatch):
    original = Path.lstat
    def with_reparse(path, *args, **kwargs):
        result = original(path, *args, **kwargs)
        if path == tmp_path:
            return SimpleNamespace(st_mode=result.st_mode, st_file_attributes=0x400)
        return result
    monkeypatch.setattr(Path, 'lstat', with_reparse)
    with pytest.raises(ExecutionFailure) as failure:
        _plain_directory(tmp_path)
    assert failure.value.code == 'unsafe_export_directory'


def test_inplace_same_size_file_change_during_hash_is_rejected(tmp_path, monkeypatch):
    import os
    path = tmp_path / 'owned.stl'
    path.write_bytes(binary_stl())
    original_open = Path.open
    replaced = False
    class EditingReader:
        def __init__(self, stream):
            self.stream = stream
        def __enter__(self):
            self.stream.__enter__()
            return self
        def __exit__(self, *args):
            return self.stream.__exit__(*args)
        def read(self, size=-1):
            nonlocal replaced
            value = self.stream.read(size)
            if not replaced:
                replaced = True
                previous = path.stat()
                # Same inode and size, explicit mtime change after hash reading
                # starts. A size/inode-only guard would miss this change.
                with original_open(path, 'r+b') as writer:
                    writer.write(b'changed')
                os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns + 10000000))
            return value
        def seek(self, *args):
            return self.stream.seek(*args)
    def opened(target, mode='r', *args, **kwargs):
        stream = original_open(target, mode, *args, **kwargs)
        return EditingReader(stream) if target == path and mode == 'rb' else stream
    monkeypatch.setattr(Path, 'open', opened)
    with pytest.raises(ExecutionFailure) as failure:
        validate_export_file(path, ExportOptions('stl', path.name, 'mm'))
    assert failure.value.code == 'export_file_changed'


@pytest.fixture
def native_adapter_module(monkeypatch):
    # Load native adapter with pure Python stand-ins; no pythoncom/COM calls.
    import solidworks_mcp
    binding = ModuleType('solidworks_mcp.binding')
    binding.wrap = lambda obj, cls: obj
    monkeypatch.setitem(sys.modules, 'pythoncom', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'solidworks_mcp.binding', binding)
    monkeypatch.setattr(solidworks_mcp, 'binding', binding, raising=False)
    spec = importlib.util.spec_from_file_location('solidworks_mcp._cad_export_unit',
        Path(__file__).parents[1] / 'src/solidworks_mcp/cad_exports_v2.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_native_setter_partial_failure_attempts_all_restore_and_readback(native_adapter_module):
    module = native_adapter_module
    adapter = module.CadExportsAdapter(SimpleNamespace())
    options = ExportOptions('stl', 'fixture.stl', 'mm')
    desired = module.desired_preferences(options)
    before = {name: (value + 1 if type(value) is int else not value if type(value) is bool
        else value + 0.5 if type(value) is float else 'Другая система') for name, value in desired.items()}
    before.update(stl_quality=3, stl_deviation_m=9.15190966989661e-7, stl_angle_rad=.0174532925199433)
    state = before.copy()
    calls = []
    adapter._preflight = lambda model: None
    adapter.snapshot = lambda model: {'state': 'unchanged'}
    adapter._get_preference = lambda name: state[name]
    def setter(name, value):
        calls.append((name, value))
        state[name] = value  # Applied even though setter then throws.
        if name == 'stl_units' and value == desired[name]:
            raise RuntimeError('Injected setter exception after native write.')
    adapter._set_preference = setter
    with pytest.raises(RuntimeError):
        adapter.export_part_to_file(object(), Path('owned.stl'), options, before)
    assert state == before
    assert calls[-2:] == [('stl_units', before['stl_units']), ('coordinate_system', before['coordinate_system'])]


def test_native_restore_refuses_external_preference_third_value(native_adapter_module):
    module = native_adapter_module
    adapter = module.CadExportsAdapter(SimpleNamespace())
    options = ExportOptions('parasolid', 'fixture.x_t')
    before = {'coordinate_system': 'Старая система', 'parasolid_version': 5}
    state = before.copy()
    adapter._preflight = lambda model: None
    adapter.snapshot = lambda model: {'state': 'unchanged'}
    adapter._get_preference = lambda name: state[name]
    adapter._set_preference = lambda name, value: state.__setitem__(name, value)
    def native_save(*args):
        state['coordinate_system'] = 'Чужое изменение'
        return True, 0, 0
    adapter._extension = lambda model: SimpleNamespace(SaveAs3=native_save)
    with pytest.raises(ExecutionFailure) as failure:
        adapter.export_part_to_file(object(), Path('owned.x_t'), options, before)
    assert failure.value.code == 'export_preferences_restore_unconfirmed'
    assert state == {'coordinate_system': 'Чужое изменение', 'parasolid_version': 5}


def test_native_next_preference_changed_during_prior_setter_is_never_overwritten(native_adapter_module):
    module = native_adapter_module
    adapter = module.CadExportsAdapter(SimpleNamespace())
    options = ExportOptions('parasolid', 'fixture.x_t')
    before = {'coordinate_system': 'Старая система', 'parasolid_version': 5}
    state, calls = before.copy(), []
    adapter._preflight = lambda model: None
    adapter.snapshot = lambda model: {'state': 'unchanged'}
    adapter._get_preference = lambda name: state[name]

    def setter(name, value):
        calls.append((name, value))
        state[name] = value
        if name == 'coordinate_system' and value == '':
            state['parasolid_version'] = 77  # External write during the earlier COM call.

    adapter._set_preference = setter
    adapter._extension = lambda model: pytest.fail('SaveAs3 must not start after the conflict.')
    with pytest.raises(ExecutionFailure) as error:
        adapter.export_part_to_file(object(), Path('owned.x_t'), options, before)
    assert error.value.code == 'stale_export_preferences'
    assert state == {'coordinate_system': 'Старая система', 'parasolid_version': 77}
    assert all(name != 'parasolid_version' for name, value in calls)


def test_native_saveas3_returns_bitmasks_and_restores_preferences(native_adapter_module):
    module = native_adapter_module
    adapter = module.CadExportsAdapter(SimpleNamespace())
    options = ExportOptions('parasolid', 'fixture.x_t')
    before = {'coordinate_system': 'Старая система', 'parasolid_version': 5}
    state = before.copy()
    adapter._preflight = lambda model: None
    adapter.snapshot = lambda model: {'state': 'unchanged'}
    adapter._get_preference = lambda name: state[name]
    adapter._set_preference = lambda name, value: state.__setitem__(name, value)
    calls = []
    def native_save(*args):
        calls.append(args)
        assert state == {'coordinate_system': '', 'parasolid_version': 0}
        return False, 256, 2
    adapter._extension = lambda model: SimpleNamespace(SaveAs3=native_save)
    result = adapter.export_part_to_file(object(), Path('owned.x_t'), options, before)
    assert calls == [('owned.x_t', 0, 3, None, None, 0, 0)]
    assert result['success'] is False and result['errors'] == 256 and result['warnings'] == 2
    assert state == before
