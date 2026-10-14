"""One-shot modern native Copy bridge for bounded first-save orchestration.

No tool or atomic SaveAs is implemented here. The domain owns the filesystem
lease/stage, full CAD checkpoint, reader/publication/replacement and restoration.
"""
from dataclasses import dataclass, field
import os
from pathlib import Path
import threading

from . import binding
from .application_close_guard import ApplicationCloseGuard
from .cad_selection_scope import preserved_selection
from .documents import rejected
from .jobs import ExecutionFailure
from .timings_v2 import timed_call


@dataclass
class NativeFirstSaveCopyReceipt:
    model: object
    identity: object
    filename: str
    configuration: str
    source_snapshot: dict
    thread: int = field(default_factory=threading.get_ident)
    native_call_attempted: bool = False
    pending_copy: bool = False
    native_call_returned: bool = False
    raw_return: object = None
    acknowledgement_valid: bool = False
    success: object = None
    errors: object = None
    warnings: object = None


@dataclass
class NativeFirstSaveCloseReceipt:
    model: object
    identity: object
    native_name: str
    thread: int = field(default_factory=threading.get_ident)
    native_call_attempted: bool = False
    pending_close: bool = False
    native_call_returned: bool = False
    acknowledgement_valid: bool = False
    raw_return: object = None


class CadNativeFirstSaveMixin:
    @staticmethod
    def _first_save_stage_path(filename):
        if (type(filename) is not str or not filename.strip() or len(filename) > 32767
                or '\x00' in filename):
            raise rejected('native_first_save_stage_invalid', 'A bounded exact native staging filename is required.')
        path = Path(filename)
        if (not path.is_absolute() or path.suffix.lower() != '.sldprt'
                or not path.parent.is_dir() or os.path.lexists(path)):
            raise rejected('native_first_save_stage_invalid', 'Use a new .SLDPRT in the operation-owned leased stage.')
        # The filesystem collaborator holds ancestry/stage leases. This path
        # check alone is deliberately not advertised as race-safe publication.
        return filename

    def _first_save_copy_source(self, model, configuration):
        if (type(configuration) is not str or not configuration.strip()
                or len(configuration) > 1024 or '\x00' in configuration):
            raise rejected('native_first_save_configuration_invalid', 'An exact bounded configuration is required.')
        active = self.active_document()
        if active is None or self.identity(active) != self.identity(model):
            raise rejected('native_first_save_source_not_active', 'Native Copy requires the exact explicitly active source.')
        kind, filename = model.GetType(), model.GetPathName()
        if type(kind) is not int or kind != 1 or type(filename) is not str or filename != '':
            raise rejected('native_first_save_source_unsupported', 'Only an exact unsaved native part is supported.')
        snapshot = self.snapshot(model)
        if (snapshot['configurations'] != [configuration]
                or snapshot['active_configuration'] != configuration):
            raise rejected('native_first_save_configuration_unsupported', 'One exact active configuration is required.')
        mode = self.native_save_context(model)
        if (type(mode.get('read_only_state')) is not int or mode['read_only_state'] != 0
                or mode.get('view_only') is not False
                or mode.get('editing_sketch') is not False or mode.get('editing_component') is not False
                or type(mode.get('blocking_state')) is not int or mode['blocking_state'] not in (0, 2)):
            raise rejected('native_first_save_source_edit_mode', 'No editing/read-only/view-only or unowned lock is supported.')
        manager = binding.wrap(model.SelectionManager, self._module.ISelectionMgr)
        count = manager.GetSelectedObjectCount2(-1)
        if type(count) is not int or count != 0:
            raise rejected('native_first_save_selection_not_empty', 'The explicit source selection must be empty.')
        if self.pending_rebuild(model) is not False:
            raise rejected('native_first_save_source_needs_rebuild', 'Rebuild the source explicitly before first save.')
        return snapshot

    def new_native_first_save_copy_receipt(self, model, filename, configuration):
        filename = self._first_save_stage_path(filename)
        snapshot = self._first_save_copy_source(model, configuration)
        return NativeFirstSaveCopyReceipt(model, self.identity(model), filename, configuration, snapshot)

    @staticmethod
    def native_first_save_copy_evidence(receipt):
        return dict(native_call_attempted=receipt.native_call_attempted,
                    pending_copy=receipt.pending_copy, native_call_returned=receipt.native_call_returned,
                    acknowledgement_valid=receipt.acknowledgement_valid,
                    success=receipt.success if type(receipt.success) is bool else None,
                    errors=receipt.errors if type(receipt.errors) is int else None,
                    warnings=receipt.warnings if type(receipt.warnings) is int else None)

    def save_native_first_save_copy(self, receipt):
        if type(receipt) is not NativeFirstSaveCopyReceipt or receipt.thread != threading.get_ident():
            raise rejected('native_first_save_receipt_invalid', 'The exact receipt belongs to its original STA.')
        if receipt.native_call_attempted or receipt.pending_copy or receipt.native_call_returned:
            raise ExecutionFailure('native_first_save_receipt_reused', 'Native Copy is never repeated.', uncertain=True)
        if self.identity(receipt.model) != receipt.identity:
            raise rejected('native_first_save_source_replaced', 'The exact native source identity changed.')
        self._first_save_stage_path(receipt.filename)
        if self._first_save_copy_source(receipt.model, receipt.configuration) != receipt.source_snapshot:
            raise rejected('native_first_save_source_changed', 'The receipt-bound source changed before native Copy.')
        extension = self._extension(receipt.model)
        receipt.native_call_attempted = True
        receipt.pending_copy = True
        raw = timed_call('com', extension.SaveAs3, receipt.filename, 0, 3, None, None, 0, 0)
        receipt.raw_return = raw  # Retain before interpreting any acknowledgement.
        receipt.native_call_returned = True
        receipt.pending_copy = False
        if type(raw) is tuple and len(raw) == 3:
            receipt.success, receipt.errors, receipt.warnings = raw
            receipt.acknowledgement_valid = (type(raw[0]) is bool
                and type(raw[1]) is int and type(raw[2]) is int)
        # False/warnings/malformed returns are evidence for the full domain
        # oracle, never a known no-effect failure inferred by this bridge.
        return self.native_first_save_copy_evidence(receipt)

    def native_first_save_guard(self, survivor_models, source_document_id):
        # A closing source is intentionally never retained by a guard which
        # would query it on exit. The domain proves source/reader preservation
        # and owns all exact retirement and phase transitions under this CIP.
        return ApplicationCloseGuard(self._sw, survivor_models,
            lambda model, state: preserved_selection(self, model, state=state, label='native_first_save'),
            [source_document_id])

    def new_native_first_save_close_receipt(self, model, native_name):
        if (type(native_name) is not str or not native_name.strip()
                or len(native_name) > 32767 or '\x00' in native_name or model.GetTitle() != native_name):
            raise rejected('native_first_save_close_name_invalid', 'The exact current native title is required.')
        current = self.documents()
        identity = self.identity(model)
        if (sum(self.identity(item) == identity for item in current) != 1
                or sum(item.GetTitle().casefold() == native_name.casefold() for item in current) != 1):
            raise rejected('native_first_save_close_target_ambiguous', 'Exact live identity and unique native title required.')
        return NativeFirstSaveCloseReceipt(model, identity, native_name)

    def close_native_first_save_document(self, receipt):
        if type(receipt) is not NativeFirstSaveCloseReceipt or receipt.thread != threading.get_ident():
            raise rejected('native_first_save_close_receipt_invalid', 'Exact close receipt belongs to its original STA.')
        if receipt.native_call_attempted or receipt.pending_close or receipt.native_call_returned:
            raise ExecutionFailure('native_first_save_close_repeated', 'Native close is never repeated.', uncertain=True)
        current = self.documents()
        if (sum(self.identity(item) == receipt.identity for item in current) != 1
                or self.identity(receipt.model) != receipt.identity
                or receipt.model.GetTitle() != receipt.native_name
                or sum(item.GetTitle().casefold() == receipt.native_name.casefold() for item in current) != 1):
            raise rejected('native_first_save_close_target_changed', 'Exact live close target/title changed before CloseDoc.')
        receipt.native_call_attempted = receipt.pending_close = True
        raw = timed_call('com', self._sw.CloseDoc, receipt.native_name)
        receipt.raw_return = raw
        receipt.native_call_returned = True
        receipt.pending_close = False
        receipt.acknowledgement_valid = raw is None  # Registered CloseDoc is void.
        # No getter on the retired model. A void ACK is not retirement proof;
        # the domain compares a fresh live-only full census and file baseline.
        return dict(native_call_attempted=True, pending_close=False, native_call_returned=True,
                    acknowledgement_valid=receipt.acknowledgement_valid)
