"""Failure oracles for legacy cleanup; no CAD connection."""
from types import SimpleNamespace
import pytest
from legacy_cad_safety import close_owned_part


class Model:
    def __init__(self, token='owned', blocked=0):
        self.token, self.blocked = token, blocked
    def GetBlockingState(self): return self.blocked
    def GetUpdateStamp(self): return 7
    def GetTitle(self): return 'Контрольная деталь'
    def GetPathName(self): return ''


def session(documents, close):
    return SimpleNamespace(_model=documents[0] if documents else None,
                           _open_documents=lambda: documents,
                           _sw=SimpleNamespace(CloseDoc=close))


def test_exact_owned_cleanup_checks_actual_empty_roster():
    owned = Model(); documents = [owned]; calls = []
    def close(title): calls.append(title); documents.clear()
    sw = session(documents, close)
    assert close_owned_part(sw, owned, lambda m:m.token)['closed']
    assert calls == ['Контрольная деталь'] and sw._model is None


@pytest.mark.parametrize('documents', [[Model('foreign')], [Model(),Model('foreign')], [Model(blocked=1)]])
def test_foreign_or_blocked_documents_are_retained(documents):
    calls = []; sw = session(documents, calls.append)
    with pytest.raises(RuntimeError, match='retained'):
        close_owned_part(sw, Model(), lambda m:m.token)
    assert calls == [] and documents


def test_silent_close_failure_is_not_successful_cleanup():
    owned = Model(); documents = [owned]
    with pytest.raises(RuntimeError, match='did not restore'):
        close_owned_part(session(documents, lambda title:None), owned, lambda m:m.token)
    assert documents == [owned]


def test_close_exception_is_not_suppressed():
    owned = Model(); documents = [owned]
    def fail(title): raise RuntimeError('native close failed')
    with pytest.raises(RuntimeError, match='native close failed'):
        close_owned_part(session(documents, fail), owned, lambda m:m.token)


def test_already_closed_owned_fixture_is_not_reclosed():
    calls=[]; sw=session([], calls.append)
    assert close_owned_part(sw, Model(), lambda m:m.token) == 'already_closed'
    assert calls == [] and sw._model is None
