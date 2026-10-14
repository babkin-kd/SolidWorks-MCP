"""Pure validation of actual engineering input; no native creation is claimed."""

from dataclasses import FrozenInstanceError
import pytest

from solidworks_mcp.jobs import ExecutionFailure
from solidworks_mcp.part_creation import BaseRectangle
from solidworks_mcp.part_creation import validated_plane_transform


IDENTITY = (1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0., 1., 0., 0., 0.)


def definition(**changes):
    return BaseRectangle.validate(**{'plane_object_id': 'feat_' + 'a' * 32,
                                    'width_mm': 40., 'height_mm': 20., 'depth_mm': 10., **changes})


def test_plate_has_known_geometry_in_plane_coordinates_and_native_units():
    item = definition()
    assert item.profile_m == ((0., 0.), (.04, 0.), (.04, .02), (0., .02))
    assert item.depth_m == .01
    assert item.volume_mm3 == 8000. and item.surface_area_mm2 == 2800.
    assert definition(depth_mm=12.).volume_mm3 == 9600.
    assert (item.sketch_name, item.feature_name, item.body_name) == (
        'Эскиз основания', 'Основание', 'Тело основания')
    with pytest.raises(FrozenInstanceError): item.depth_mm = 12.


@pytest.mark.parametrize('value', [True, False, None, '10', 0, -1, 0.0009,
                                 float('nan'), float('inf'), -float('inf'), 10 ** 400])
@pytest.mark.parametrize('parameter', ['width_mm', 'height_mm', 'depth_mm'])
def test_invalid_lengths_are_rejected_before_any_native_builder(value, parameter):
    with pytest.raises(ExecutionFailure) as error:
        definition(**{parameter: value})
    assert error.value.code == 'invalid_part_length' and error.value.uncertain is False


@pytest.mark.parametrize('value', ['Front Plane', '#1', '1', '', None, 'feat_' + 'a' * 31])
def test_plane_names_and_indices_are_not_accepted_as_references(value):
    with pytest.raises(ExecutionFailure) as error: definition(plane_object_id=value)
    assert error.value.code == 'invalid_plane_reference'


@pytest.mark.parametrize('parameter', ['sketch_name', 'feature_name', 'body_name'])
def test_created_entities_require_valid_russian_names(parameter):
    with pytest.raises(ExecutionFailure) as error: definition(**{parameter: 'Base'})
    assert error.value.code == 'invalid_russian_name'


def test_feature_names_cannot_be_autosuffixed_to_hide_a_collision():
    with pytest.raises(ExecutionFailure) as error:
        definition(sketch_name='Основание', feature_name='основание')
    assert error.value.code == 'part_name_collision'


def test_analytical_measurement_overflow_is_rejected():
    with pytest.raises(ExecutionFailure) as error:
        definition(width_mm=1e200, height_mm=1e200)
    assert error.value.code == 'part_measurement_overflow'


def test_plane_frame_is_native_rigid_transform_not_a_plane_name():
    assert validated_plane_transform(IDENTITY) == IDENTITY
    rotated = (0., 1., 0., -1., 0., 0., 0., 0., 1., *IDENTITY[9:])
    assert validated_plane_transform(rotated) == rotated


@pytest.mark.parametrize('index,value,code', [
    (0, float('nan'), 'invalid_plane_transform'), (0, True, 'invalid_plane_transform'),
    (0, 10 ** 400, 'invalid_plane_transform'), (0, 2., 'unsupported_plane_transform'),
    (0, 1e308, 'unsupported_plane_transform'),
    (8, -1., 'unsupported_plane_transform'), (12, 2., 'unsupported_plane_transform'),
    (9, .01, 'unsupported_offset_plane')])
def test_unusable_plane_transform_is_rejected(index, value, code):
    data = list(IDENTITY)
    data[index] = value
    with pytest.raises(ExecutionFailure) as error: validated_plane_transform(data)
    assert error.value.code == code


@pytest.mark.parametrize('value', [None, [], list(IDENTITY)[:12], 'Передняя'])
def test_incomplete_plane_transform_is_rejected(value):
    with pytest.raises(ExecutionFailure) as error: validated_plane_transform(value)
    assert error.value.code == 'invalid_plane_transform'
