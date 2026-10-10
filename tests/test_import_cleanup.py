"""Synthetic import failures exercise ownership and error preservation, never CAD."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
import pythoncom

from solidworks_mcp import binding
from solidworks_mcp.constants import SW_TOGGLE_3D_INTERCONNECT
from solidworks_mcp.errors import SolidWorksError
from solidworks_mcp.import_cleanup import ImportDocumentCleanup
from solidworks_mcp.session import SolidWorksSession


class Document:
    def __init__(self, title, kind=1, token=None):
        self.title, self.kind = title, kind
        self.token = [title] if token is None else token  # Canonical COM identities are unhashable.
        self.path = ''
        self.stamp = 10
        self.modified = True
        self._oleobj_ = SimpleNamespace(QueryInterface=lambda iid: self.token)
        self.bodies = [object()]
        self.children = []
    def GetTitle(self): return self.title
    def GetPathName(self): return self.path
    def GetType(self): return self.kind
    def GetUpdateStamp(self): return self.stamp
    def GetSaveFlag(self): return self.modified
    def GetBodies2(self, *args): return self.bodies
    def GetComponents(self, top_only):
        assert top_only is True
        return [SimpleNamespace(GetModelDoc2=lambda child=child: child) for child in self.children]


class Application:
    def __init__(self, documents=(), guarded=True):
        self.documents = list(documents)
        self.CommandInProgress = guarded
        self.interconnect = True
        self.closes = []
        self.sets = []
        self.close_hook = None
        self.setter_hook = None
    def CloseDoc(self, title):
        self.closes.append(title)
        if self.close_hook:
            return self.close_hook(title)
        self.documents[:] = [d for d in self.documents if d.title != title]
    def GetUserPreferenceToggle(self, setting):
        assert setting == SW_TOGGLE_3D_INTERCONNECT
        return self.interconnect
    def SetUserPreferenceToggle(self, setting, value):
        assert setting == SW_TOGGLE_3D_INTERCONNECT
        self.sets.append(value)
        self.interconnect = value
        return self.setter_hook(value) if self.setter_hook else None  # Native VT_VOID.


def scope(app):
    return ImportDocumentCleanup(app, lambda: list(app.documents), lambda d: d.token, lambda: True, lambda d: d.children)


def session(app, original, monkeypatch):
    result = SolidWorksSession()
    result._sw = app
    result._owns_command_in_progress = True
    result._model = original
    result._mod = SimpleNamespace(IModelDoc2=object(), IPartDoc=object(), IAssemblyDoc=object(), IComponent2=object())
    result._ensure = lambda: app
    result._open_documents = lambda: list(app.documents)
    result._native_or_neutral = lambda *args: ('supplier.step', True)
    result.get_mass_properties = lambda: {'mass_properties': {'volume_mm3': 100}}
    result._require_assembly = lambda: result._model
    result._components = lambda model: []
    monkeypatch.setattr(binding, 'wrap', lambda raw, cls: raw)
    return result


def test_import_closes_assembly_first_without_closing_preexisting_components():
    original = Document('Рабочая деталь')
    app = Application([original])
    cleanup = scope(app)
    app.documents.extend([Document('Импортированный компонент'), Document('Импортированная сборка', 2)])
    cleanup.cleanup()
    assert app.documents == [original]
    assert app.closes == ['Импортированная сборка', 'Импортированный компонент']


def test_preexisting_document_rename_cannot_turn_it_into_an_owned_import():
    original = Document('Рабочая деталь')
    app = Application([original])
    cleanup = scope(app)
    original.title = 'Новое имя пользователя'
    app.documents.append(Document('Временная деталь'))
    with pytest.raises(RuntimeError, match='pre-existing document changed'):
        cleanup.cleanup()
    assert app.closes == []


def test_replacement_with_the_same_title_is_not_mistaken_for_the_original():
    original = Document('Рабочая деталь', token=['original'])
    app = Application([original])
    cleanup = scope(app)
    app.documents[:] = [Document('Рабочая деталь', token=['replacement'])]
    with pytest.raises(RuntimeError, match='pre-existing document changed'):
        cleanup.cleanup()
    assert app.closes == []


def test_duplicate_titles_are_never_passed_to_close_doc():
    app = Application()
    cleanup = scope(app)
    app.documents.extend([Document('Одинаковое имя', token=[1]), Document('Одинаковое имя', token=[2])])
    with pytest.raises(RuntimeError, match='Ambiguous document title'):
        cleanup.cleanup()
    assert app.closes == []


@pytest.mark.parametrize('guarded_at_start,guarded_at_cleanup', [(False, True), (True, False)])
def test_cleanup_cannot_borrow_an_unrelated_automation_interval(guarded_at_start, guarded_at_cleanup):
    app = Application(guarded=guarded_at_start)
    cleanup = scope(app)
    app.CommandInProgress = guarded_at_cleanup
    app.documents.append(Document('Временная деталь'))
    with pytest.raises(RuntimeError, match='exclusive automation interval'):
        cleanup.cleanup()
    assert app.closes == []


def test_throwing_close_is_not_retried_even_if_it_took_effect():
    app = Application()
    cleanup = scope(app)
    app.documents.extend([Document('Первая'), Document('Вторая')])
    error = pythoncom.com_error(-2147467259, 'Close returned an error', None, None)
    def close(title):
        app.documents.pop(0)
        raise error
    app.close_hook = close
    with pytest.raises(pythoncom.com_error) as caught:
        cleanup.cleanup()
    assert caught.value is error
    assert app.closes == ['Первая']
    assert len(app.documents) == 1


def test_void_close_without_observed_effect_is_not_repeated():
    app = Application()
    cleanup = scope(app)
    app.documents.append(Document('Временная'))
    app.close_hook = lambda title: None
    with pytest.raises(RuntimeError, match='not confirmed'):
        cleanup.cleanup()
    assert app.closes == ['Временная']


def test_assembly_close_may_also_release_its_new_component():
    original = Document('Рабочая')
    app = Application([original])
    cleanup = scope(app)
    app.documents.extend([Document('Компонент'), Document('Сборка', 2)])
    app.close_hook = lambda title: app.documents.__setitem__(slice(None), [original])
    cleanup.cleanup()
    assert app.closes == ['Сборка']


@pytest.mark.parametrize('failure', ['load-com', 'body-com', 'mass-com', 'surface-only', 'wrong-type', 'no-document'])
def test_part_import_cleans_all_its_new_documents_for_load_and_validation_errors(monkeypatch, failure):
    original = Document('Рабочая')
    app = Application([original])
    result = session(app, original, monkeypatch)
    imported = Document('Импортированная', 2 if failure == 'wrong-type' else 1)
    com_error = pythoncom.com_error(-2147467259, 'Controlled fake COM rejection', None, None)
    def load(*args):
        app.documents.append(imported)
        if failure == 'load-com': raise com_error
        if failure == 'no-document': return None, 1
        return imported, 0
    result._load_file = load
    if failure == 'body-com':
        imported.GetBodies2 = lambda *args: (_ for _ in ()).throw(com_error)
    if failure == 'mass-com':
        result.get_mass_properties = lambda: (_ for _ in ()).throw(com_error)
    if failure == 'surface-only': imported.bodies = []
    with pytest.raises((pythoncom.com_error, SolidWorksError)) as caught:
        result.open_part('supplier.step')
    if failure.endswith('com'): assert caught.value is com_error
    assert app.documents == [original]
    assert app.closes == ['Импортированная']
    assert result._model is original
    assert app.interconnect is True and app.sets == []


@pytest.mark.parametrize('failure', ['load-com', 'component-com', 'wrong-type'])
def test_assembly_import_restores_preference_and_cleans_validation_failures(monkeypatch, failure):
    original = Document('Рабочая')
    app = Application([original])
    result = session(app, original, monkeypatch)
    imported = Document('Импортированная', 1 if failure == 'wrong-type' else 2)
    error = pythoncom.com_error(-2147467259, 'Controlled assembly COM rejection', None, None)
    def load(*args):
        assert app.interconnect is False
        app.documents.append(imported)
        if failure == 'load-com': raise error
        return imported, 0
    result._load_file = load
    if failure == 'component-com':
        result._components = lambda model: (_ for _ in ()).throw(error)
    with pytest.raises((pythoncom.com_error, SolidWorksError)):
        result.open_assembly('supplier.step')
    assert app.documents == [original] and app.closes == ['Импортированная']
    assert result._model is original
    assert app.sets == [False, True] and app.interconnect is True


def test_throwing_preference_setter_is_restored_without_calling_the_importer(monkeypatch):
    original = Document('Рабочая')
    app = Application([original])
    result = session(app, original, monkeypatch)
    error = pythoncom.com_error(-2147467259, 'Setter changed state and then failed', None, None)
    app.setter_hook = lambda value: (_ for _ in ()).throw(error) if not value else True
    result._load_file = lambda *args: pytest.fail('Import must not run after a failed preference setter.')
    with pytest.raises(pythoncom.com_error) as caught:
        result.open_assembly('supplier.step')
    assert caught.value is error
    assert app.interconnect is True and app.sets == [False, True]
    assert app.documents == [original] and app.closes == []


def test_restoration_and_cleanup_failures_do_not_hide_the_primary_com_error(monkeypatch):
    original = Document('Рабочая')
    app = Application([original])
    result = session(app, original, monkeypatch)
    error = pythoncom.com_error(-2147467259, 'Primary load failure', None, None)
    app.setter_hook = lambda value: setattr(app, 'interconnect', False) if value else None
    def load(*args):
        app.documents.append(Document('Временная'))
        raise error
    result._load_file = load
    app.close_hook = lambda title: (_ for _ in ()).throw(RuntimeError('Controlled close failure'))
    with pytest.raises(pythoncom.com_error) as caught:
        result.open_assembly('supplier.step')
    assert caught.value is error
    assert len(error.__notes__) == 2
    assert 'Interconnect restoration is unconfirmed' in error.__notes__[0]
    assert 'Import cleanup is unconfirmed' in error.__notes__[1]
    assert result._model is original and app.closes == ['Временная']


@pytest.mark.parametrize('kind', ['part', 'assembly'])
def test_successful_import_keeps_the_result_and_restores_preferences(monkeypatch, kind):
    original = Document('Рабочая')
    app = Application([original])
    result = session(app, original, monkeypatch)
    imported = Document('Импортированная', 1 if kind == 'part' else 2)
    def load(*args):
        app.documents.append(imported)
        return imported, 0
    result._load_file = load
    answer = getattr(result, 'open_' + kind)('supplier.step')
    assert answer['ok'] and answer['imported']
    assert result._model is imported and app.documents == [original, imported]
    assert app.closes == [] and app.interconnect is True


def test_primary_error_notes_are_visible_in_legacy_result_without_starting_a_server():
    path = Path(__file__).resolve().parents[1] / 'src/solidworks_mcp/server.py'
    tree = ast.parse(path.read_text(encoding='utf8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_failure')
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
    error = RuntimeError('Primary error')
    assert namespace['_failure'](str(error), error) == {'ok': False, 'error': 'Primary error'}
    error.add_note('Import cleanup is unconfirmed; reconcile state.')
    assert namespace['_failure'](str(error), error) == {'ok': False, 'error': 'Primary error', 'diagnostics': error.__notes__}

def test_existing_guard_from_another_session_is_not_borrowed(monkeypatch):
    original = Document('Рабочая')
    app = Application([original])
    result = session(app, original, monkeypatch)
    result._owns_command_in_progress = False
    result._load_file = lambda *args: pytest.fail('No import may start under a foreign guard.')
    with pytest.raises(SolidWorksError, match='Cannot borrow'):
        result.open_part('supplier.step')
    assert app.documents == [original] and app.closes == [] and app.CommandInProgress is True


def test_direct_import_owns_and_releases_its_own_guard(monkeypatch):
    original = Document('Рабочая')
    app = Application([original], guarded=False)
    result = session(app, original, monkeypatch)
    result._owns_command_in_progress = False
    imported = Document('Импортированная')
    def load(*args):
        assert app.CommandInProgress is True and result._owns_command_in_progress is True
        app.documents.append(imported)
        return imported, 0
    result._load_file = load
    assert result.open_part('supplier.step')['ok']
    assert app.CommandInProgress is False and result._owns_command_in_progress is False


def test_unconfirmed_cleanup_blocks_another_import_before_any_com_change(monkeypatch):
    original = Document('Рабочая')
    app = Application([original])
    result = session(app, original, monkeypatch)
    def load(*args):
        app.documents.append(Document('Временная'))
        raise RuntimeError('Primary import failure')
    result._load_file = load
    app.close_hook = lambda title: None
    with pytest.raises(RuntimeError, match='Primary import failure'):
        result.open_part('supplier.step')
    assert result._import_reconciliation_required is True
    result._load_file = lambda *args: pytest.fail('No automatic retry may occur.')
    with pytest.raises(SolidWorksError, match='previous import'):
        result.open_part('supplier.step')
    assert app.closes == ['Временная']


def test_guard_presence_does_not_substitute_for_ownership():
    app = Application()
    cleanup = ImportDocumentCleanup(app, lambda: list(app.documents), lambda d: d.token, lambda: False)
    app.documents.append(Document('Временная'))
    with pytest.raises(RuntimeError, match='exclusive automation interval'):
        cleanup.cleanup()
    assert app.closes == []


def test_restoration_failure_after_success_still_blocks_next_import(monkeypatch):
    original = Document('Рабочая')
    app = Application([original])
    result = session(app, original, monkeypatch)
    imported = Document('Сборка', 2)
    def load(*args):
        app.documents.append(imported)
        return imported, 0
    result._load_file = load
    app.setter_hook = lambda value: setattr(app, 'interconnect', False) if value else None
    with pytest.raises(SolidWorksError, match='restoration was not confirmed'):
        result.open_assembly('supplier.step')
    assert result._import_reconciliation_required is True
    assert app.documents == [original] and result._model is original
    with pytest.raises(SolidWorksError, match='previous import'):
        result.open_assembly('supplier.step')


def test_guard_acquisition_failure_is_not_blindly_restored_or_retried(monkeypatch):
    original = Document('Рабочая')
    app = Application([original], guarded=False)
    result = session(app, original, monkeypatch)
    result._owns_command_in_progress = False
    error = RuntimeError('Controlled guard readback failure')
    calls = []
    def guard(value):
        calls.append(value)
        app.CommandInProgress = True
        raise error
    result._command_in_progress = guard
    result._load_file = lambda *args: pytest.fail('LoadFile4 must not run after uncertain acquisition.')
    with pytest.raises(RuntimeError) as caught:
        result.open_part('supplier.step')
    assert caught.value is error and calls == [True]
    assert result._import_reconciliation_required is True and app.closes == []
    with pytest.raises(SolidWorksError, match='previous import'):
        result.open_part('supplier.step')
    assert calls == [True]


def test_void_preference_setter_without_effect_is_rejected_by_readback(monkeypatch):
    original = Document('Рабочая')
    app = Application([original])
    result = session(app, original, monkeypatch)
    app.setter_hook = lambda value: setattr(app, 'interconnect', True) if not value else None
    result._load_file = lambda *args: pytest.fail('Load must not run if disabling had no observed effect.')
    with pytest.raises(SolidWorksError, match='Could not disable'):
        result.open_assembly('supplier.step')
    assert app.interconnect is True and app.sets == [False, True]
    assert app.closes == [] and result._import_reconciliation_required is False


def test_nested_interconnect_assemblies_close_parent_before_held_child():
    original = Document('Рабочая')
    app = Application([original])
    cleanup = scope(app)
    part = Document('Деталь')
    inner = Document('Вложенная сборка', 2)
    outer = Document('Внешняя сборка', 2)
    inner.children = [part]
    outer.children = [inner]
    # Native inventory reports a child before its parent; grouping by type
    # alone tries an ineffective close of the held inner assembly.
    app.documents.extend([part, inner, outer])
    def close(title):
        target = next(d for d in app.documents if d.title == title)
        if any(target in d.children for d in app.documents if d is not target):
            return None
        app.documents.remove(target)
    app.close_hook = close
    cleanup.cleanup()
    assert app.closes == ['Внешняя сборка', 'Вложенная сборка', 'Деталь']
    assert app.documents == [original]


def test_shared_subassembly_is_closed_only_after_both_new_parents():
    app = Application()
    cleanup = scope(app)
    shared = Document('Общая подсборка', 2)
    a, b = Document('Первый родитель', 2), Document('Второй родитель', 2)
    a.children = [shared, shared]  # Multiple instances are one document edge.
    b.children = [shared]
    app.documents[:] = [shared, a, b]
    cleanup.cleanup()
    assert app.closes == ['Первый родитель', 'Второй родитель', 'Общая подсборка']


def test_preexisting_reused_component_is_excluded_from_dependency_cleanup():
    original = Document('Библиотечная деталь')
    app = Application([original])
    cleanup = scope(app)
    root = Document('Импортированная сборка', 2)
    root.children = [original]
    app.documents.append(root)
    cleanup.cleanup()
    assert app.documents == [original] and app.closes == ['Импортированная сборка']


def test_dependency_cycle_is_rejected_before_any_close():
    app = Application()
    cleanup = scope(app)
    a, b = Document('Первая сборка', 2), Document('Вторая сборка', 2)
    a.children, b.children = [b], [a]
    app.documents[:] = [a, b]
    with pytest.raises(RuntimeError, match='Cyclic'):
        cleanup.cleanup()
    assert app.closes == []


def test_untracked_dependency_is_not_implicitly_adopted():
    app = Application()
    cleanup = scope(app)
    root = Document('Сборка', 2)
    root.children = [Document('Неучтённый документ')]
    app.documents.append(root)
    with pytest.raises(RuntimeError, match='outside the captured'):
        cleanup.cleanup()
    assert app.closes == []
