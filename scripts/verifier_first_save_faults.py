"""Controlled verifier faults; these never impersonate actual COM failures.

The CAD delegate is called once before response injection. Its original normal
receipt is detached separately. No rollback, retry, cleanup or hold release is
performed here. The race producer uses exclusive creation inside private work.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path


COPY_FAULTS = ('false_after_copy', 'warning_after_copy', 'throw_after_copy', 'incomplete_after_copy')
_COPY_FIELDS = ('filename', 'configuration', 'native_call_attempted', 'pending_copy',
                'native_call_returned', 'acknowledgement_valid', 'success', 'errors', 'warnings', 'raw_return')


class CopyResponseFault:
    def __init__(self, delegate, fault):
        if fault not in COPY_FAULTS:
            raise ValueError('Only a named controlled after-copy fault is supported.')
        self.delegate, self.fault = delegate, fault
        self.copy_calls = 0
        self.original_receipt = None
        self.injection_applied = False

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def save_native_first_save_copy(self, receipt):
        if self.copy_calls:
            raise AssertionError('A controlled case must never repeat native Copy.')
        self.copy_calls += 1
        self.delegate.save_native_first_save_copy(receipt)
        self.original_receipt = json.loads(json.dumps(
            {name: getattr(receipt, name) for name in _COPY_FIELDS}, allow_nan=False))
        original = self.original_receipt
        if (original['native_call_attempted'] is not True or original['pending_copy'] is not False
                or original['native_call_returned'] is not True
                or original['acknowledgement_valid'] is not True or original['success'] is not True
                or any(type(original[key]) is not int or original[key] != 0 for key in ('errors', 'warnings'))):
            raise AssertionError('Injection requires an independently recorded normal successful Copy receipt.')
        self.injection_applied = True
        if self.fault == 'throw_after_copy':
            raise RuntimeError('Controlled bridge exception AFTER normal native Copy; not a COM throw.')
        if self.fault == 'false_after_copy':
            receipt.success, receipt.errors = False, 1
            receipt.raw_return = (False, 1, 0)
        elif self.fault == 'warning_after_copy':
            receipt.warnings = 1
            receipt.raw_return = (True, 0, 1)
        else:
            receipt.native_call_returned = receipt.acknowledgement_valid = False
            receipt.success = receipt.errors = receipt.warnings = receipt.raw_return = None


def file_witness(path):
    path = Path(path)
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if any(getattr(before, key) != getattr(after, key) for key in fields):
        raise AssertionError('File changed while observing controlled race witness.')
    return dict(identity=[after.st_dev, after.st_ino], size=after.st_size,
                mtime_ns=after.st_mtime_ns, ctime_ns=after.st_ctime_ns,
                sha256=hashlib.sha256(data).hexdigest())


class DestinationRace:
    def __init__(self, delegate, private_root):
        self.delegate = delegate
        self.private_root = Path(private_root).resolve(strict=True)
        self.publication_calls = 0
        self.foreign_file = None
        self.foreign_witness = None

    def __getattr__(self, name):
        return getattr(self.delegate, name)

    def publish(self, stage, lease):
        if self.publication_calls:
            raise AssertionError('A controlled case must never repeat publication.')
        target = Path(lease.token['destination'])
        if (not target.is_absolute() or not target.resolve().is_relative_to(self.private_root)
                or target.suffix.lower() != '.sldprt'):
            raise ValueError('Controlled race writes must remain inside the exact private test root.')
        self.publication_calls += 1
        with target.open('xb') as stream:
            stream.write(b'Controlled foreign destination: never overwrite.')
        self.foreign_file = str(target)
        self.foreign_witness = file_witness(target)
        return self.delegate.publish(stage, lease)

    def preserved_foreign_file(self):
        return (self.foreign_file is not None
                and file_witness(self.foreign_file) == deepcopy(self.foreign_witness))
