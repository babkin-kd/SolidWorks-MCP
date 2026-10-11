"""One-shot CWD memento bridge: fake native calls, no SolidWorks."""
from types import SimpleNamespace
import threading

import pytest

from solidworks_mcp.cad_native_document_open import CadNativeDocumentOpenMixin
from solidworks_mcp.jobs import ExecutionFailure


class Adapter(CadNativeDocumentOpenMixin):
    def __init__(self, original, current, result=True, error=None):
        self.original, self.current, self.result, self.error = str(original), str(current), result, error
        self.calls = []
        self._sw = SimpleNamespace(GetCurrentWorkingDirectory=lambda: self.current,
                                   SetCurrentWorkingDirectory=self.setter)

    def setter(self, value):
        self.calls.append(value)
        if self.error:
            raise self.error
        if self.result is True:
            self.current = value
        return self.result


@pytest.fixture
def adapter(tmp_path):
    original, current = tmp_path / 'original', tmp_path / 'opened'
    original.mkdir()
    current.mkdir()
    return Adapter(original, current)


def receipt(adapter):
    return adapter.new_native_directory_restore_receipt(adapter.original, adapter.current)


def test_normal_setter_is_once_and_receipt_retains_ack_without_final_baseline_claim(adapter):
    r = receipt(adapter)
    value = adapter.restore_native_open_directory(r)
    assert value == dict(native_call_attempted=True, native_call_returned=True, pending_directory=False,
                         acknowledgement_valid=True, setter_succeeded=True)
    assert r.raw_return is True and adapter.calls == [adapter.original]
    with pytest.raises(ExecutionFailure) as error:
        adapter.restore_native_open_directory(r)
    assert error.value.code == 'native_open_directory_receipt_reused' and len(adapter.calls) == 1


@pytest.mark.parametrize('value', [None, '', ' ', False, 1, 'relative', 'bad\x00path',
    pytest.param('x' * 32768, id='too_long')])
def test_untyped_unbounded_or_relative_directory_refused_before_native(adapter, value):
    with pytest.raises(ExecutionFailure):
        adapter.new_native_directory_restore_receipt(value, adapter.current)
    with pytest.raises(ExecutionFailure):
        adapter.new_native_directory_restore_receipt(adapter.original, value)
    assert not adapter.calls


def test_same_or_missing_original_directory_refused_before_native(adapter, tmp_path):
    for target, current in ((adapter.original, adapter.original), (str(tmp_path / 'missing'), adapter.current)):
        with pytest.raises(ExecutionFailure):
            adapter.new_native_directory_restore_receipt(target, current)
    assert not adapter.calls


def test_foreign_current_directory_prevents_setter(adapter):
    r = receipt(adapter)
    adapter.current = adapter.original
    with pytest.raises(ExecutionFailure) as error:
        adapter.restore_native_open_directory(r)
    assert error.value.code == 'native_open_directory_changed'
    assert not r.native_call_attempted and not r.pending_directory and not adapter.calls


def test_removed_target_directory_prevents_setter(adapter):
    r = receipt(adapter)
    from pathlib import Path
    Path(adapter.original).rmdir()
    with pytest.raises(ExecutionFailure):
        adapter.restore_native_open_directory(r)
    assert not r.native_call_attempted and not adapter.calls


def test_foreign_sta_and_wrong_receipt_do_not_call_native(adapter):
    r = receipt(adapter)
    r.thread = threading.get_ident() + 1
    with pytest.raises(ExecutionFailure):
        adapter.restore_native_open_directory(r)
    with pytest.raises(ExecutionFailure):
        adapter.restore_native_open_directory(object())
    assert not adapter.calls


def test_throwing_setter_stays_pending_and_cannot_be_repeated(adapter):
    r = receipt(adapter)
    adapter.error = RuntimeError('native setter outcome unknown')
    with pytest.raises(RuntimeError):
        adapter.restore_native_open_directory(r)
    assert r.native_call_attempted and r.pending_directory and not r.native_call_returned
    with pytest.raises(ExecutionFailure):
        adapter.restore_native_open_directory(r)
    assert len(adapter.calls) == 1


@pytest.mark.parametrize('result', [False, None, 1, 'True', (True,)])
def test_normal_false_or_malformed_ack_retained_once_without_claiming_restore(adapter, result):
    r = receipt(adapter)
    adapter.result = result
    with pytest.raises(ExecutionFailure) as error:
        adapter.restore_native_open_directory(r)
    assert error.value.uncertain is True
    assert r.raw_return == result and r.native_call_returned and not r.pending_directory
    assert r.acknowledgement_valid is (type(result) is bool) and r.setter_succeeded is False
    with pytest.raises(ExecutionFailure):
        adapter.restore_native_open_directory(r)
    assert len(adapter.calls) == 1
