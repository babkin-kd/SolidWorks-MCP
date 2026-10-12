"""Complete detached observations for the finite three-stage rectangle workflow."""
import json

from .documents import rejected
from .jobs import _json
from .native_first_save import SNAPSHOT_KEYS, SNAPSHOT_SCOPE, validated_part_snapshot
from .rectangle_inventory import feature_relations, empty_feature_external_inventory
from .rectangle_annotation_views import validated_view_bindings


SCOPE = 'native_rectangle_construction_snapshot_v1'
EMPTY = 'empty_native_part_v1'
SKETCH = 'closed_rectangular_sketch_v1'
BASE = 'single_rectangular_blind_base_v1'
DATA_KEYS = {'profile', 'features', 'dependencies', 'geometry', 'dimensions', 'sketch',
    'parameters', 'controls', 'equation_reference_inventory', 'feature_external_reference_inventory',
    'planes', 'properties', 'units', 'annotations', 'configuration_state', 'auxiliary_data',
    'display_data', 'material', 'creation_controls', 'origin'}
CONTROL_KEYS = {'add_to_db', 'auto_solve', 'display_when_added', 'dimension_input'}
BASELINE_TYPES = frozenset(('CommentsFolder', 'FavoriteFolder', 'HistoryFolder',
    'SelectionSetFolder', 'SensorFolder', 'DocsFolder', 'DetailCabinet',
    'SurfaceBodyFolder', 'SolidBodyFolder', 'EnvFolder', 'InkMarkupFolder',
    'EqnFolder', 'MaterialFolder', 'NotesAreaFtrFolder', 'AmbientLight', 'DirectionLight',
    'RefPlane', 'OriginProfileFeature', 'ProfileFeature'))


def validated_rectangle_snapshot(value):
    fail = lambda message: rejected('rectangle_snapshot_unsupported', message)
    if type(value) is not dict or set(value) != SNAPSHOT_KEYS or value['scope'] != SCOPE:
        raise fail('A complete typed rectangle construction observation is required.')
    if (type(value['configuration']) is not str or not value['configuration'].strip()
            or type(value['configurations']) is not list or value['configurations'] != [value['configuration']]
            or type(value['solid_body_count']) is not int or value['solid_body_count'] not in (0, 1)
            or type(value['selection_count']) is not int or not 0 <= value['selection_count'] <= 256
            or type(value['clone_state']) is not dict):
        raise fail('Exactly one observed part configuration and a complete selection/body census are required.')
    data = value['clone_state']
    controls = data.get('creation_controls')
    if (type(controls) is not dict or set(controls) != CONTROL_KEYS
            or any(type(x) is not bool for x in controls.values())):
        raise fail('Every native sketch creation control must be observed.')
    if value['solid_body_count'] == 1:
        if data.get('profile') != BASE:
            raise fail('The only supported body is one rectangular blind base.')
        original = {**value, 'scope': SNAPSHOT_SCOPE}
        original['native_observations']={k:v for k,v in value['native_observations'].items() if k!='annotation_view_bindings'}
        validated_part_snapshot(original)
        try:validated_view_bindings(data['display_data'],value['native_observations']['annotation_view_bindings'],{'width','height','depth'})
        except (KeyError,ValueError,TypeError) as exc:raise fail('Complete base annotation-view bindings required.') from exc
        return json.loads(_json(value))
    if set(data) != DATA_KEYS or data['profile'] not in (EMPTY, SKETCH):
        raise fail('Empty and closed-sketch profiles require the complete declared data inventory.')
    rows = data['features']
    if type(rows) is not list or not 4 <= len(rows) <= 64:
        raise fail('A complete bounded baseline feature tree is required.')
    ids = [row.get('native_id') for row in rows if type(row) is dict]
    if len(ids) != len(rows) or any(type(i) is not int for i in ids) or len(set(ids)) != len(ids):
        raise fail('Feature incarnations must be complete and unique.')
    kinds = [row.get('feature_type') for row in rows]
    expected_sketches = int(data['profile'] == SKETCH)
    if (kinds.count('RefPlane') != 3 or kinds.count('OriginProfileFeature') != 1
            or kinds.count('ProfileFeature') != expected_sketches
            or any(k not in BASELINE_TYPES for k in kinds)
            or any(row.get('suppressed') is not False or type(row.get('error_code')) is not int
                   or row['error_code'] != 0 for row in rows)):
        raise fail('Only the exact clean baseline and at most one rectangle sketch are supported.')
    if (data['geometry'] != {'representation': 'planar_polyhedral_brep_v1', 'bodies': []}
            or type(data['dimensions']) is not list or len(data['dimensions']) != expected_sketches * 2
            or type(data['planes']) is not list or len(data['planes']) != 3
            or type(data['units']) is not list or not data['units']
            or type(data['material']) is not list or len(data['material']) != 2
            or any(type(v) is not str for v in data['material'])):
        raise fail('The complete empty geometry, planes, units, material and dimension inventory are required.')
    if expected_sketches:
        if type(data['sketch']) is not dict or type(data['parameters']) is not dict:
            raise fail('A complete proven rectangle sketch and driving parameters are required.')
    elif data['sketch'] is not None or data['parameters'] is not None:
        raise fail('An empty part cannot contain hidden sketch data.')
    for key in ('dependencies', 'controls', 'equation_reference_inventory',
                'feature_external_reference_inventory', 'properties', 'configuration_state',
                'auxiliary_data', 'display_data'):
        if type(data[key]) is not dict or not data[key]:
            raise fail('Every declared data inventory must contain a complete observation.')
    if type(data['annotations']) is not list:
        raise fail('The complete native annotation inventory is required.')
    try:
        feature_relations(data)
        empty_feature_external_inventory(data)
    except (KeyError, ValueError, TypeError) as exc:
        raise fail('Complete typed feature relations and external inventories are required before construction.') from exc
    refs = value['references']
    if type(refs) is not list or not 4 <= len(refs) <= 5000:
        raise fail('Every structural reference needs a current native anchor.')
    roles, tokens = set(), set()
    for row in refs:
        if (type(row) is not dict or set(row) != {'kind', 'role', 'token'}
                or any(type(x) is not str or not x or '\0' in x or len(x) > 65536 for x in row.values())
                or (row['kind'], row['role']) in roles or row['token'] in tokens):
            raise fail('Reference roles and native anchors must be complete and bijective.')
        roles.add((row['kind'], row['role'])); tokens.add(row['token'])
    for i, row in enumerate(rows):
        if row['feature_type'] in ('RefPlane', 'OriginProfileFeature', 'ProfileFeature'):
            if ('feature', f'feature:{i}') not in roles:
                raise fail('Every plane/origin/sketch must bind its exact feature role.')
    observations = value['native_observations']
    if (type(observations) is not dict or set(observations) != {'document_dimension_namespace','annotation_view_bindings'}
            or type(observations['document_dimension_namespace']) is not str
            or not observations['document_dimension_namespace']):
        raise fail('The observed native document namespace is required.')
    try:validated_view_bindings(data['display_data'],observations['annotation_view_bindings'],{'width','height'} if expected_sketches else set())
    except (KeyError,ValueError,TypeError) as exc:raise fail('Complete sketch/empty annotation-view bindings required.') from exc
    origin = data['origin']
    if (type(origin) is not dict or set(origin) != {'feature_role', 'point_role', 'native_id',
            'point_type', 'constraint_status', 'coordinates_si'}
            or ('feature', origin.get('feature_role')) not in roles
            or ('sketch_point', origin.get('point_role')) not in roles
            or origin.get('feature_role') != f'feature:{kinds.index("OriginProfileFeature")}'
            or origin.get('point_role') != ('sketch:0/model_origin' if expected_sketches else 'origin:point')
            or type(origin.get('native_id')) is not list or len(origin['native_id']) != 2
            or any(type(v) is not int or not 0 <= v <= 2**31 - 1 for v in origin['native_id'])
            or type(origin.get('point_type')) is not int or origin['point_type'] != 1
            or type(origin.get('constraint_status')) is not int or origin['constraint_status'] != 2
            or type(origin.get('coordinates_si')) is not list or len(origin['coordinates_si']) != 3):
        raise fail('The fixed native model origin must bind its exact observed feature/point.')
    try:
        if any(type(v) is not str or float.fromhex(v) != 0. for v in origin['coordinates_si']):
            raise fail('The initial construction profile requires the exact native model origin.')
    except ValueError as exc:
        raise fail('The model origin coordinates must be complete native SI values.') from exc
    _json(value)
    return json.loads(_json(value))
