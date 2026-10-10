"""Read native equation/reference inventories, without solving or opening files.

Indexes and reference names describe native rows; they never resolve a writable
feature. This inventory is part of deletion-impact work, not deletion authority.
"""

from .documents import rejected

SCOPE = 'native_feature_deletion_context_v1'
MAX_ROWS = 5000
MAX_TEXT = 16384
MAX_TEXT_TOTAL = 2097152
EXTERNAL_FIELDS = ('model_path', 'component_path', 'feature_name', 'data_type',
                   'status', 'reference_entity', 'feature_component', 'configuration_option',
                   'configuration_name')


def _count(value):
    if type(value) is not int or not 0 <= value <= MAX_ROWS:
        raise rejected('feature_context_capture_invalid', 'Native inventory count is invalid or exceeds budget.')
    return value


def _text(value):
    if type(value) is not str or len(value) > MAX_TEXT:
        raise rejected('feature_context_capture_invalid', 'Native inventory requires bounded strings.')
    return value


def _boolean(value):
    if type(value) is not bool:
        raise rejected('feature_context_capture_invalid', 'Native inventory requires exact booleans.')
    return value


def _integer(value):
    if type(value) is not int or not -(2 ** 31) <= value < 2 ** 31:
        raise rejected('feature_context_capture_invalid', 'Native inventory requires exact integers.')
    return value


def _columns(value, count, validators):
    if type(value) not in (tuple, list) or len(value) != len(validators):
        raise rejected('feature_context_capture_invalid', 'Native reference outputs have an unexpected shape.')
    columns = []
    for column, validator in zip(value, validators):
        if column is None and count == 0:
            column = []
        if type(column) not in (tuple, list) or len(column) != count:
            raise rejected('feature_context_capture_invalid', 'Reference counts and parallel arrays disagree.')
        columns.append([validator(item) for item in column])
    return columns


class CadDeletionContextMixin:
    def _wrap_equation_manager(self, raw):
        from . import binding
        return binding.wrap(raw, self._module.IEquationMgr)

    def feature_deletion_context(self, model):
        manager = self._wrap_equation_manager(model.GetEquationMgr())
        if manager is None:
            raise rejected('feature_context_capture_invalid', 'Native equation manager was not returned.')
        text_work = 0
        def read_text(value):
            nonlocal text_work
            value = _text(value)
            text_work += len(value)
            if text_work > MAX_TEXT_TOTAL:
                raise rejected('feature_context_budget_exceeded', 'Equation/reference text budget exceeded.')
            return value
        count = _count(manager.GetCount())
        disabled = _count(manager.GetDisabledEquationCount())
        properties = {'linked_to_file': _boolean(manager.LinkToFile), 'file_path': read_text(manager.FilePath),
                      'automatic_rebuild': _boolean(manager.AutomaticRebuild),
                      'automatic_solve_order': _boolean(manager.AutomaticSolveOrder),
                      'angular_equation_units': _integer(manager.AngularEquationUnits)}
        rows = [{'row_index': index, 'expression': read_text(manager.Equation(index)),
                 'disabled': _boolean(manager.Disabled(index)),
                 'global_variable': _boolean(manager.GlobalVariable(index)),
                 'configuration_option': _integer(manager.GetConfigurationOption(index))}
                for index in range(count)]
        if (_count(manager.GetCount()) != count or _count(manager.GetDisabledEquationCount()) != disabled
                or sum(row['disabled'] for row in rows) != disabled):
            raise rejected('document_changed_during_read', 'Equation inventory count/disabled coverage changed.')
        extension = self._extension(model)
        external_count = _count(extension.ListExternalFileReferencesCount())
        validators = (read_text, read_text, read_text, read_text, _integer, read_text, read_text, _integer, read_text)
        external = _columns(extension.ListExternalFileReferences2(), external_count, validators)
        if _count(extension.ListExternalFileReferencesCount()) != external_count:
            raise rejected('document_changed_during_read', 'External reference count changed during capture.')
        auxiliary_count = _count(model.ListAuxiliaryExternalFileReferencesCount())
        auxiliary = _columns(model.ListAuxiliaryExternalFileReferences(), auxiliary_count, (read_text, read_text))
        if _count(model.ListAuxiliaryExternalFileReferencesCount()) != auxiliary_count:
            raise rejected('document_changed_during_read', 'Auxiliary reference count changed during capture.')
        result = {'scope': SCOPE, 'equations': {'count': count, 'disabled_count': disabled,
                    'properties': properties, 'rows': rows},
                  'external_references': {'count': external_count, 'rows': [
                    {'row_index': index, **dict(zip(EXTERNAL_FIELDS, values))}
                    for index, values in enumerate(zip(*external))]},
                  'auxiliary_references': {'count': auxiliary_count, 'rows': [
                    {'row_index': index, 'feature_name': values[0], 'file_path': values[1]}
                    for index, values in enumerate(zip(*auxiliary))]}}
        return result
