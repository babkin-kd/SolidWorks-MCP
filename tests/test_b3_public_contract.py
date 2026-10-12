"""Pure B3 public facade -> runtime payload tests; no worker or CAD execution."""
import asyncio
from copy import deepcopy
import inspect
import json
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError
from mcp.server.fastmcp.exceptions import ToolError

from solidworks_mcp.runtime_v2 import Runtime, MUTATING_OPERATIONS, READ_OPERATIONS
from solidworks_mcp.server_v2 import create_app

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
try:
    from verifier_b3_public_contract import SPECS, B3ToolSpec
finally:
    sys.path.remove(str(SCRIPTS))


EXPECTED_OPERATIONS = {
    'document_list': 'document.list', 'document_get': 'document.get',
    'feature_list': 'feature.list', 'feature_get': 'feature.get',
    'dimension_list': 'dimension.list', 'dimension_get': 'dimension.get', 'sketch_get': 'sketch.get',
    'body_list': 'geometry.list', 'face_list': 'geometry.list', 'edge_list': 'geometry.list',
    'geometry_get': 'geometry.get', 'component_list': 'component.list', 'component_get': 'component.get',
    'component_body_list': 'component.bodies', 'component_body_get': 'component.bodies',
    'component_face_list': 'component.topology_list', 'component_edge_list': 'component.topology_list',
    'component_topology_get': 'component.topology_get', 'measurement_prepare_mass': 'measurement.prepare_mass',
    'measurement_get_mass': 'measurement.mass', 'measurement_get_bounds': 'measurement.bounds',
    **{'measurement_get_component_' + suffix: 'measurement.component_' + suffix for suffix in
       ('distance', 'point_distance', 'axis_distance', 'aggregate_distance', 'aggregate_point_distance', 'aggregate_axis_distance')},
}

FRAME = {'origin_mm': [7, -4, 2], 'axes_in_model': [[0, 1, 0], [-1, 0, 0], [0, 0, 1]]}
INPUTS = {'request_id': 'b3-read', 'document_id': 'doc_explicit', 'configuration': 'Основная',
    'expected_observation_revision': 'obs_exact', 'expected_revision': 'rev_mass',
    'object_id': 'obj_explicit', 'body_id': 'body_explicit', 'component_id': 'component_explicit',
    'component_a_id': 'component_a', 'component_b_id': 'component_b',
    'point_mm': [1, -2, 3], 'axis_origin_mm': [4, 5, 6], 'axis_direction': [0, 3, 4]}


class CapturingRunner:
    """Record actual Runtime._dispatch submissions, never execute their callbacks."""
    def __init__(self):
        self.calls = []

    def submit(self, request_id, operation, arguments, execute, **kwargs):
        job = dict(operation_id='operation_b3', status='succeeded', error=None, result={},
            payload=dict(arguments=arguments, context=kwargs['context'], mutates=kwargs['mutates']))
        self.calls.append(dict(request_id=request_id, operation=operation, job=job, **kwargs))
        return job

    async def wait(self, operation_id, *, timeout_s):
        self.calls[-1]['timeout_s'] = timeout_s
        assert operation_id == 'operation_b3'
        return self.calls[-1]['job']


@pytest.fixture
def app_and_runner():
    def forbidden():
        pytest.fail('No worker, catalog, COM, or CAD execution is permitted.')
    runtime = Runtime(None, worker_factory=forbidden, catalog_factory=forbidden)
    runner = CapturingRunner()
    runtime._runner = runner
    return create_app(None, runtime), runner


def required_arguments(app, tool):
    parameters = inspect.signature(app._tool_manager.get_tool(tool).fn).parameters
    return {key: deepcopy(INPUTS[key]) for key, value in parameters.items() if value.default is inspect.Parameter.empty}


def assert_actual_payload(app, runner, tool, arguments):
    original = deepcopy(arguments)
    asyncio.run(app.call_tool(tool, arguments))
    actual = runner.calls[-1]
    spec = SPECS[tool]
    assert actual['operation'] == spec.operation
    # JSON bytes distinguish 1 from 1.0, unlike Python equality.
    assert json.dumps(actual['job']['payload'], sort_keys=True, ensure_ascii=False) == json.dumps(
        spec.payload(arguments), sort_keys=True, ensure_ascii=False)
    assert actual['request_id'] == arguments['request_id']
    assert actual['timeout_s'] == arguments.get('timeout_s', 10)
    assert actual['pass_operation_id'] is spec.mutates
    assert (actual['verify'] is not None) is spec.mutates
    assert arguments == original


def test_exact_finite_inventory_and_mutation_classification():
    assert len(SPECS) == 27
    assert {name: spec.operation for name, spec in SPECS.items()} == EXPECTED_OPERATIONS
    assert {name for name, spec in SPECS.items() if spec.mutates} == {'measurement_get_mass'}
    assert 'job_get' not in SPECS
    for spec in SPECS.values():
        assert spec.operation in (MUTATING_OPERATIONS if spec.mutates else READ_OPERATIONS)
        assert spec.argument_map == {} and spec.float_arguments == frozenset()
        assert spec.prewrite_failure_codes == spec.preenqueue_error_codes == frozenset()


@pytest.mark.parametrize('tool', sorted(SPECS))
def test_declared_defaults_match_actual_public_signature(app_and_runner, tool):
    app, _ = app_and_runner
    params = inspect.signature(app._tool_manager.get_tool(tool).fn).parameters
    actual_defaults = {key: value.default for key, value in params.items()
        if key not in ('request_id', 'timeout_s') and value.default is not inspect.Parameter.empty}
    assert SPECS[tool].argument_defaults == actual_defaults


@pytest.mark.parametrize('tool', sorted(SPECS))
def test_minimal_inputs_match_real_facade_and_runtime_normalization(app_and_runner, tool):
    app, runner = app_and_runner
    assert_actual_payload(app, runner, tool, required_arguments(app, tool))


@pytest.mark.parametrize('tool', sorted(SPECS))
def test_explicit_optional_inputs_match_runtime_without_default_leakage(app_and_runner, tool):
    app, runner = app_and_runner
    args = required_arguments(app, tool)
    overrides = dict(limit=2, cursor='opaque_cursor', body_type='surface', body_id='body_selected',
        frame=FRAME, coordinate_frame=FRAME, timeout_s=0)
    params = inspect.signature(app._tool_manager.get_tool(tool).fn).parameters
    args.update({key: deepcopy(value) for key, value in overrides.items() if key in params})
    assert_actual_payload(app, runner, tool, args)


@pytest.mark.parametrize('tool,kind', [('body_list', 'body'), ('face_list', 'face'), ('edge_list', 'edge'),
    ('component_face_list', 'face'), ('component_edge_list', 'edge')])
def test_server_owned_kind_cannot_be_overridden(tool, kind):
    assert SPECS[tool].constant_args == {'kind': kind}
    with pytest.raises(ValueError, match='server-owned constants'):
        SPECS[tool].payload({'request_id': 'r', 'kind': 'other'})


VECTOR_TOOLS = [name for name, spec in SPECS.items() if isinstance(spec, B3ToolSpec) and spec.vector_arguments]
FRAME_TOOLS = [name for name, spec in SPECS.items() if isinstance(spec, B3ToolSpec) and spec.frame_arguments]


@pytest.mark.parametrize('tool', VECTOR_TOOLS)
@pytest.mark.parametrize('bad', [True, '1', None])
def test_vectors_reject_non_numeric_coercions_as_real_facade_does(app_and_runner, tool, bad):
    app, runner = app_and_runner
    args = required_arguments(app, tool)
    key = next(iter(SPECS[tool].vector_arguments))
    args[key] = [bad, 2, 3]
    with pytest.raises(ValidationError):
        SPECS[tool].payload(args)
    with pytest.raises(ToolError):
        asyncio.run(app.call_tool(tool, args))
    assert runner.calls == []


@pytest.mark.parametrize('tool', FRAME_TOOLS)
@pytest.mark.parametrize('fault', ['reflection', 'scale', 'extra', 'boolean', 'nan'])
def test_frames_reject_unsupported_inputs_before_dispatch(app_and_runner, tool, fault):
    app, runner = app_and_runner
    args = required_arguments(app, tool)
    frame = deepcopy(FRAME)
    if fault == 'reflection': frame['axes_in_model'][2][2] = -1
    elif fault == 'scale': frame['axes_in_model'][0][1] = 2
    elif fault == 'extra': frame['name'] = 'hidden_native_frame'
    elif fault == 'boolean': frame['origin_mm'][0] = True
    else: frame['origin_mm'][0] = float('nan')
    args[next(iter(SPECS[tool].frame_arguments))] = frame
    with pytest.raises(ValidationError):
        SPECS[tool].payload(args)
    with pytest.raises(ToolError):
        asyncio.run(app.call_tool(tool, args))
    assert runner.calls == []


def test_part_pair_distance_has_no_frame_and_component_body_get_has_no_list_defaults():
    assert SPECS['measurement_get_component_distance'].argument_defaults == {}
    assert SPECS['component_body_get'].argument_defaults == {}
    assert SPECS['component_body_list'].argument_defaults == {'body_type': 'all'}


def test_mass_nullable_target_and_context_are_preserved():
    payload = SPECS['measurement_get_mass'].payload(dict(request_id='mass', timeout_s=0,
        document_id='doc', configuration='Основная', expected_revision='mass_rev',
        expected_observation_revision='obs'))
    assert payload == dict(arguments=dict(document_id='doc', configuration='Основная',
        expected_revision='mass_rev', expected_observation_revision='obs', body_id=None),
        context=dict(document_id='doc', configuration='Основная', expected_revision='mass_rev',
            expected_observation_revision='obs', body_id=None), mutates=True)
