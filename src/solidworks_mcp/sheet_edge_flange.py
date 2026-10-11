"""Explicit read-only preparation for one edge flange on a proven folded L sheet.

Internal preparation only; no new MCP tool is registered.
"""

import math
import re
from dataclasses import asdict

from .documents import rejected
from .features import russian_name
from .geometry import GeometryCatalog
from .part_creation import _positive_length
from .sheet_parameters import SheetParameterCatalog
from .sheet_edge_flange_definition import EdgeFlangeOnL,SCOPE,flange_revision,l_flange_edge_points


def flange_request(base_object_id,edge_id,flange_length_mm,bend_radius_mm,k_factor,
        sketch_name='Эскиз отбортовки',feature_name='Отбортовка'):
    SheetParameterCatalog._arguments(base_object_id,False)
    if type(edge_id) is not str or re.fullmatch(r'obj_[0-9a-f]{32}',edge_id) is None:
        raise rejected('invalid_sheet_flange_edge','An explicit opaque current edge reference is required.')
    length=_positive_length(flange_length_mm,'flange_length_mm')
    radius=_positive_length(bend_radius_mm,'bend_radius_mm')
    if max(length,radius)>10000000.:
        raise rejected('sheet_parameter_out_of_range','Flange parameters exceed the bounded native capture.')
    if type(k_factor) not in (float,int) or not math.isfinite(k_factor) or not 0.<=k_factor<=1.:
        raise rejected('invalid_sheet_k_factor','An explicit finite second-bend K-factor between zero and one is required.')
    names=[russian_name(sketch_name),russian_name(feature_name),'Сгиб отбортовки','Развёртка сгиба отбортовки']
    if len({name.casefold() for name in names})!=4:
        raise rejected('sheet_name_collision','All four created nodes must have distinct Russian names.')
    return dict(base_object_id=base_object_id,edge_id=edge_id,flange_length_mm=length,
        bend_radius_mm=radius,k_factor=float(k_factor),sketch_name=names[0],feature_name=names[1])


class SheetEdgeFlangeCatalog(SheetParameterCatalog):
    def __init__(self,dimensions):
        super().__init__(dimensions)
        self.geometry=GeometryCatalog(dimensions.documents)

    def _prepare_edge_flange(self,document_id,configuration,*,retained=None,**arguments):
        request=flange_request(**arguments)
        captured=self._capture(document_id,configuration,request['base_object_id'],retained)
        capture,target,state,_,source,_,_=captured
        if state['evidence']['flattened'] is not False:
            raise rejected('sheet_flange_source_flat','Fold the explicitly targeted L sheet before creating an edge flange.')
        definition=EdgeFlangeOnL.validate(source,request['flange_length_mm'],request['bend_radius_mm'],request['k_factor'],
            request['sketch_name'],request['feature_name'])
        names={row['name'].casefold() for row in state['semantic']['tree']['features']}
        if any(name.casefold() in names for name in (definition.sketch_name,definition.feature_name,
                'Сгиб отбортовки','Развёртка сгиба отбортовки')):
            raise rejected('sheet_name_collision','A requested new Russian node name already exists in the model.')
        entry,identity=capture.state[:2]
        edge,reference=self.geometry._resolve(entry,request['edge_id'],configuration,identity,'edge')
        body=self.adapter.resolve_persistent_id(entry.model,target.body_pid,'body')
        if reference.body_id is None or self.adapter.identity(self.adapter.owner_body(edge,'edge'))!=self.adapter.identity(body):
            raise rejected('sheet_flange_edge_membership','The explicit edge must bind the same retained sole source body.')
        points=self.adapter.pattern_edge_points(edge)
        frame=state['evidence']['plane_transform'];controls=state['evidence']['controls']
        if not l_flange_edge_points(points,source,frame):
            raise rejected('sheet_flange_edge_unsupported','Select the full longitudinal free edge on the inner face of the vertical leg.')
        revision=flange_revision(state,definition,document_id=document_id,configuration=configuration,
            base_object_id=request['base_object_id'],edge_pid_hex=reference.persistent_id.hex(),points=points,controls=controls)
        self.dimensions._close_native_proof(entry,capture.event_sequence)
        available=callable(getattr(self,'create_edge_flange',None)) and all(callable(getattr(self.adapter,name,None)) for name in (
            'new_sheet_flange_receipt','create_sheet_edge_flange','sheet_flange_bundle','sheet_flange_preserve_names',
            'sheet_edge_flange_evidence','restore_sheet_edge_flange'))
        public=dict(document_id=document_id,configuration=configuration,**request,revision_scope=SCOPE,revision=revision,
            source_parameters=asdict(source),expected_geometry=definition.expected_geometry(frame),
            expected_volume_mm3=definition.volume_mm3,expected_area_mm2=definition.surface_area_mm2,
            native_change_available=available)
        return public,captured,definition,edge,reference

    def prepare_edge_flange(self,document_id,configuration,**arguments):
        return self._prepare_edge_flange(document_id,configuration,**arguments)[0]
