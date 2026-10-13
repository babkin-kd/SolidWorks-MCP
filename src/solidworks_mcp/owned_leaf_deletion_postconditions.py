"""Finite full BASE→SKETCH leaf deletion proof; no native ownership authority."""
import re

from .jobs import _json
from .rectangle_construction import BlindRectangleExtrusion
from .rectangle_extrusion_postconditions import verified_rectangle_extrusion
from .rectangle_postconditions import same_unmodified_session
from .rectangle_snapshot import BASE, SKETCH, validated_rectangle_snapshot


MAX_LEAF_DOCUMENTS = 32


def validated_leaf_session(state, document_id, configuration, profile):
    """Return detached full supported session or raise a concrete data gate.

Native census completeness/canonical identity and ownership remain the trusted
producer's obligations. This validates the declared finite data profile.
"""
    def require(condition, field):
        if not condition: raise ValueError(field)
    require(type(state) is dict and set(state) == {'semantic','snapshots'}, 'complete_session')
    semantic = state['semantic']
    require(type(semantic) is dict and {'documents','windows','application','active_document_id',
        'reference_graph','files'} == set(semantic), 'complete_semantic_inventory')
    rows = semantic['documents']
    require(type(rows) is list and 0 < len(rows) <= MAX_LEAF_DOCUMENTS, 'bounded_complete_document_census')
    ids = [row['document_id'] for row in rows]
    require(all(type(key) is str and key.strip() for key in ids)
        and len(set(ids)) == len(ids) and set(state['snapshots']) == set(ids), 'exact_snapshot_roster')
    require(semantic['active_document_id'] == document_id and ids.count(document_id) == 1,
            'active_explicit_target')
    require(semantic['reference_graph'] == [], 'no_session_reference_graph')
    require(type(semantic['files']) is list, 'complete_file_inventory')
    app=semantic['application']
    require(type(app) is dict and set(app)=={'user_control','visible','current_directory','search_folders'}
        and type(app['user_control']) is bool and type(app['visible']) is bool
        and type(app['current_directory']) is str and type(app['search_folders']) is str,
        'complete_native_application_context')
    require(type(semantic['windows']) is list
        and all(type(row) is dict and set(row)=={'document_id','hwnd','title'}
            and row['document_id'] in ids and type(row['hwnd']) is int and row['hwnd']>0
            and type(row['title']) is str for row in semantic['windows'])
        and len({row['hwnd'] for row in semantic['windows']})==len(semantic['windows'])
        and sum(row['document_id'] == document_id for row in semantic['windows']) == 1,
        'one_target_window')
    for row in rows:
        require({'document_id','title','path','document_type','active_configuration','configurations',
            'needs_save','update_stamp','observation_sequence','observation_revision','view','visible',
            'dependencies','dependency_files','mode','file'} <= set(row), 'complete_native_document_context')
        require(row['document_type'] == 'part' and row['visible'] is True and row['dependencies'] == [],
                'complete_supported_part_neighbors')
        require(type(row['view']) is dict and bool(row['view']) and row['dependency_files']==[],
                'full_native_view_and_dependencies')
        mode=row['mode']
        require(type(mode) is dict and set(mode)=={'blocking_state','read_only_state',
            'editing_sketch','editing_component','view_only','drawing_state'}
            and type(mode['blocking_state']) is int and mode['blocking_state']==0
            and type(mode['read_only_state']) is int and mode['read_only_state'] in (0,1)
            and mode['editing_sketch'] is False and mode['editing_component'] is False
            and mode['view_only'] is False and mode['drawing_state'] is None,
            'complete_native_part_edit_mode')
        snapshot = validated_rectangle_snapshot(state['snapshots'][row['document_id']])
        require(snapshot['configuration'] == row['active_configuration']
            and snapshot['configurations'] == row['configurations'], 'exact_configuration_membership')
        require(snapshot['clone_state']['profile'] == (profile if row['document_id'] == document_id else BASE),
                'exact_current_profile')
        if row['document_id'] == document_id:
            require(row['path'] == '' and row['active_configuration'] == configuration
                and row['configurations'] == [configuration] and row['needs_save'] is True
                and type(row['update_stamp']) is int and type(row['observation_sequence']) is int
                and type(row['observation_revision']) is str and bool(row['observation_revision'])
                and type(row['mode']['read_only_state']) is int and row['mode']['read_only_state'] == 0
                and row['file'] is None and snapshot['selection_count'] == 0,
                'unsaved_dirty_editable_one_configuration_target')
    import json
    return json.loads(_json(state))


def validated_leaf_target(state, *, document_id, configuration, object_id,
                          feature_native_id, feature_pid_hex):
    """Bind the exact observed BASE feature role to the retained owner's data.

An opaque object ID is validated as scope data; its ownership is independently
established by the server registry, never by a JSON field or this predicate.
"""
    if (type(object_id) is not str or re.fullmatch(r'feat_[0-9a-f]{32}',object_id) is None
            or type(feature_native_id) is not int or type(feature_pid_hex) is not str):
        raise ValueError('exact_owned_feature_scope')
    pid = bytes.fromhex(feature_pid_hex)
    if not pid or pid.hex() != feature_pid_hex: raise ValueError('exact_feature_PID_bytes')
    checked = validated_leaf_session(state,document_id,configuration,BASE)
    snapshot = checked['snapshots'][document_id]
    matches = [(index,row) for index,row in enumerate(snapshot['clone_state']['features'])
               if row['native_id'] == feature_native_id]
    if (len(matches) != 1 or matches[0][1]['feature_type'] not in ('Boss','Extrusion')
            or matches[0][1]['owner_native_id'] is not None or matches[0][1]['suppressed'] is not False):
        raise ValueError('exact_standalone_extrusion_role')
    references = [row for row in snapshot['references'] if row['kind']=='feature'
                  and row['role']=='feature:'+str(matches[0][0])]
    if len(references) != 1 or references[0]['token'] != feature_pid_hex:
        raise ValueError('exact_native_feature_role_PID')
    return checked


def verified_owned_leaf_deletion(before_base, after_sketch, *, document_id, configuration,
                                 object_id, feature_native_id, feature_pid_hex, current_definition):
    """Verify only finite snapshot delta, preserving the absorbed original sketch.

Use actual current depth/names. The reverse construction proof alone checks
the BASE target's volatile fields, so a forward session proof is mandatory to
validate the actual SKETCH after-state. Neither proof authorizes native calls.
"""
    try:
        if type(current_definition) is not BlindRectangleExtrusion: return False
        before = validated_leaf_target(before_base,document_id=document_id,configuration=configuration,
            object_id=object_id,feature_native_id=feature_native_id,feature_pid_hex=feature_pid_hex)
        after = validated_leaf_session(after_sketch,document_id,configuration,SKETCH)
        snapshot = after['snapshots'][document_id]
        if (any(row['native_id']==feature_native_id for row in snapshot['clone_state']['features'])
                or any(row['kind']=='feature' and row['token']==feature_pid_hex for row in snapshot['references'])):
            return False
        return (same_unmodified_session(before,after,document_id)
            and verified_rectangle_extrusion(after,before,document_id,current_definition,feature_native_id))
    except Exception:
        return False
