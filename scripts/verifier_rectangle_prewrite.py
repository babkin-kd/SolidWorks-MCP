"""Bounded prewrite protocol admission; independently unchanged CAD is required."""
from solidworks_mcp.jobs import _json


OPERATIONS=frozenset({'sketch.create_rectangle','part.extrude_rectangle'})
CODES=frozenset({'stale_revision','object_reference_not_found','object_configuration_mismatch',
    'invalid_plane_reference','invalid_sketch_reference','feature_name_conflict',
    'rectangle_target_unsupported','rectangle_baseline_unsupported','unsupported_creation_ui'})


def verified_rectangle_prewrite(job,*,expected_code,expected_arguments):
    """Only explicit trusted pre-checkpoint refusals, never a rollback/unknown.

    This gate binds the durable request but does not observe CAD. The caller
    must separately prove zero dispatch and unchanged complete supported state.
    """
    try:
        _json(job);_json(expected_arguments)
        if (expected_code not in CODES or job['operation'] not in OPERATIONS
                or job['status']!='failed' or job['result'] is not None
                or job['payload']['mutates'] is not True
                or job['payload']['arguments']!=expected_arguments
                or job['error']['code']!=expected_code
                or job['error']['requires_reconciliation'] is not False):return False
        # Any checkpoint requires its own guarded no-effect/rollback proof.
        # Never admit an unfinished or not_started mutation through this path.
        return job.get('mutation') is None
    except Exception:return False
