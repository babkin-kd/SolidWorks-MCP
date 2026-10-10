"""Typed MCP facade for the bounded single circular through-hole candidate."""

import sqlite3

from .contracts import ResponseEnvelope
from .jobs import JobError
from .part_cut_tools_v2 import Length,Wait


def register_part_hole_tools(app, runtime, response, failure):
    async def dispatch(request_id, operation, arguments, timeout_s, *, mutates=False):
        try:
            job=await (runtime.mutate if mutates else runtime.read)(request_id,operation,arguments,timeout_s=timeout_s)
            return response(status=job['status'],operation_id=job['operation_id'],
                context=job['payload']['context'],data=job['result'],error=job['error'])
        except (JobError,sqlite3.Error) as exc:
            return failure(exc)

    @app.tool()
    async def part_prepare_through_hole(request_id:str,document_id:str,configuration:str,
            object_id:str,plane_object_id:str,centre_x_mm:Length,centre_y_mm:Length,diameter_mm:Length,
            sketch_name:str='Эскиз отверстия',feature_name:str='Сквозное отверстие',timeout_s:Wait=10)->ResponseEnvelope:
        """Prepare one circular through hole in the explicit rectangular base.

        Read only; object_id is the BASE sketch and plane_object_id its exact current
        reference plane. Requires one supported positive blind rectangular base in
        an active writable single-config part. Positive centre X/Y and diameter are
        millimetres in the base plane frame. The full circle must leave >=0.001 mm
        material at all four sides. New sketch/cut names must be distinct Russian
        names. Returns single_base_circular_through_hole_v1 revision bound to full
        original constraints/dimensions/BREP, native references, controls and input.
        Waiting timeout does not cancel COM; poll the returned operation_id.
        """
        return await dispatch(request_id,'part.prepare_through_hole',{
            'document_id':document_id,'configuration':configuration,'object_id':object_id,
            'plane_object_id':plane_object_id,'centre_x_mm':centre_x_mm,'centre_y_mm':centre_y_mm,
            'diameter_mm':diameter_mm,'sketch_name':sketch_name,'feature_name':feature_name},timeout_s)

    @app.tool()
    async def part_create_through_hole(request_id:str,document_id:str,configuration:str,expected_revision:str,
            object_id:str,plane_object_id:str,centre_x_mm:Length,centre_y_mm:Length,diameter_mm:Length,
            sketch_name:str='Эскиз отверстия',feature_name:str='Сквозное отверстие',timeout_s:Wait=10)->ResponseEnvelope:
        """Create the prepared circle sketch and through-all cut by revision.

        Use identical explicit targets/input from part_prepare_through_hole. Durable
        checkpoint precedes CAD/UI writes. The circle is defined by own X/Y/diameter
        drivers. Checks retained native objects, complete original base and new
        circle constraints, full planar/cylindrical BREP, rebuild, independent mass
        facts, original body name and selection/marks. Known failure deletes only
        proved own cut/sketch; unknown/foreign effects hold the application and
        are never replayed. Reusing request_id returns the same job. Waiting timeout
        is not COM cancellation. This scope excludes blind/oblique/counterbore/tapped
        holes, arbitrary imported parts and editing the base after adding a hole.
        """
        return await dispatch(request_id,'part.create_through_hole',{
            'document_id':document_id,'configuration':configuration,'expected_revision':expected_revision,
            'object_id':object_id,'plane_object_id':plane_object_id,'centre_x_mm':centre_x_mm,
            'centre_y_mm':centre_y_mm,'diameter_mm':diameter_mm,'sketch_name':sketch_name,
            'feature_name':feature_name},timeout_s,mutates=True)

    @app.tool()
    async def part_prepare_hole_dimension_change(request_id:str,document_id:str,configuration:str,
            base_object_id:str,object_id:str,dimension_id:str,value_mm:Length,timeout_s:Wait=10)->ResponseEnvelope:
        """Prepare an existing through-hole X/Y or diameter edit, in millimetres.

        Explicit base_object_id is the rectangular BASE sketch; object_id is the
        existing circular sketch; dimension_id comes from dimension_list and must
        be its exact independent centre X, centre Y or diameter driver. Read only.
        One base/one through-hole, fully defined single-config part, >=0.001 mm
        material on every side. Returns input-bound revision and complete expected
        shape. No implicit document, selection, name lookup or configuration.
        """
        return await dispatch(request_id,'part.prepare_hole_dimension_change',{
            'document_id':document_id,'configuration':configuration,'base_object_id':base_object_id,
            'object_id':object_id,'dimension_id':dimension_id,'value_mm':value_mm},timeout_s)

    @app.tool()
    async def part_set_hole_dimension(request_id:str,document_id:str,configuration:str,expected_revision:str,
            base_object_id:str,object_id:str,dimension_id:str,value_mm:Length,timeout_s:Wait=10)->ResponseEnvelope:
        """Set the prepared own hole driver and prove full constraints/body after rebuild.

        Uses identical explicit targets/input and revision from preparation.
        Checkpoint before CAD/UI writes; verifies unchanged base, other dimensions,
        constraints, controls/body name, full BREP and independent native measures.
        Known attributable failure restores only the exact own scalar; foreign or
        unreadable effects hold the application and are never replayed. Reusing
        request_id returns the same job. Waiting timeout does not cancel COM.
        Excludes multiple/blind/oblique/tapped holes and arbitrary imported parts.
        """
        return await dispatch(request_id,'part.set_hole_dimension',{
            'document_id':document_id,'configuration':configuration,'expected_revision':expected_revision,
            'base_object_id':base_object_id,'object_id':object_id,'dimension_id':dimension_id,
            'value_mm':value_mm},timeout_s,mutates=True)
