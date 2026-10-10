"""Own-circle through cut over the shared native handle/selection/restore path."""

from . import binding
from .documents import rejected


class CadPartHoleMixin:
    def hole_edit_controls(self, model):
        bodies = self.bodies(model, 'all')
        if len(bodies) != 1 or bodies[0].GetType() != 0:
            raise rejected('hole_edit_body_scope', 'One exact solid body is required.')
        return {'body_name': str(bodies[0].Name), 'sketch_controls': self.part_creation_controls(model)}

    def new_through_hole_receipt(self, model, features, controls):
        return self.new_corner_cut_receipt(model,features,controls)

    def create_through_hole(self, model, plane, definition, receipt):
        from .session import SolidWorksSession
        def draw(manager):
            raw = SolidWorksSession._draw_circle(manager,definition.centre_x_mm/1000.,
                definition.centre_y_mm/1000.,definition.diameter_mm/2000.)
            return binding.wrap(raw,self._module.ISketchSegment)
        def define(definer, circle):
            names = {('x',0):'Центр X',('y',0):'Центр Y',('diameter',0):'Диаметр'}
            return definer.define(circles=[circle],names=names,origin_mm=(0.,0.))
        return self._create_through_cut(model,plane,definition,receipt,draw,define)

    def through_hole_evidence(self, model, receipt):
        return self._through_cut_evidence(model,receipt,self.circular_sketch_snapshot)

    def restore_through_hole(self, model, receipt):
        return self.restore_corner_cut(model,receipt)
