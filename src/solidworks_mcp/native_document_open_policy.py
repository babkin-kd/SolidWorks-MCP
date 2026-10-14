"""Pure argument policy shared by native-open preparation and its COM bridge."""

from pathlib import Path

from .documents import rejected
from .native_document_save import EXTENSIONS


DOCUMENT_TYPES = {'part': 1, 'assembly': 2, 'drawing': 3}


def validate_native_open_arguments(filename, document_type, configuration, read_only):
    if (type(filename) is not str or not filename or type(document_type) is not str
            or document_type not in DOCUMENT_TYPES or not Path(filename).is_absolute()
            or Path(filename).suffix.lower() != EXTENSIONS[document_type]):
        raise rejected('native_document_path_required', 'Use an absolute native path matching the explicit document type.')
    if type(read_only) is not bool:
        raise rejected('native_open_policy_invalid', 'Read-only policy must be an explicit Boolean.')
    if (type(configuration) is not str or '\x00' in configuration
            or (document_type == 'drawing' and configuration != '')
            or (document_type != 'drawing' and not configuration.strip())):
        raise rejected('native_open_configuration_required', 'Part/assembly require an exact nonempty configuration; drawing requires an empty configuration.')
    if '\x00' in filename:
        raise rejected('native_document_path_required', 'Native paths cannot contain a null character.')
