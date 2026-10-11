"""Artificial own projection profile; not native CAD acceptance."""
from copy import deepcopy
from types import SimpleNamespace as NS

import pytest

from solidworks_mcp.edge_flange_sketch import EdgeFlangeSketchReader,edge_flange_sketch_matches,edge_flange_profile_preserved
from solidworks_mcp.sheet_edge_flange_definition import EdgeFlangeOnL
from solidworks_mcp.jobs import ExecutionFailure
from test_linear_sketch_v2 import Sketch,Line,Relation
from test_sheet_profile_definition_v2 import definition
from test_part_creation_v2 import IDENTITY


@pytest.fixture
def profile():
    d=EdgeFlangeOnL.validate(definition(),15.,2.5,.38)
    sk=Sketch(width=d.source.length_mm/1000.,height=d.profile_height_mm/1000.)
    ghost=Line(sk,9,sk.points[0],sk.points[1]);edge=object()
    dimension=NS(FullName='Вылет от внутреннего ребра@Эскиз отбортовки@Контрольная деталь.Part')
    display=NS(Type2=12,GetDimension2=lambda slot:dimension,IsLinked=False,GetLinkedText=lambda:'')
    sk.relations=[Relation(32,[3,3],[ghost,sk.lines[0]],[edge,sk.lines[0]]),
        Relation(5,[3],[sk.lines[1]]),Relation(5,[3],[sk.lines[3]]),Relation(4,[3],[sk.lines[2]]),
        Relation(1,[2,2],[sk.points[2],sk.points[1]],display=display)]
    return sk,ghost,edge,d


def capture(profile,phase='before_factory'):
    sk,ghost,edge,d=profile
    if phase=='after_factory':sk.relations[0].definitions=[ghost,sk.lines[0]]
    snapshot,members=EdgeFlangeSketchReader(sk,wrap=lambda raw,name:raw,identity=id,phase=phase,
        source_definition=lambda raw:id(edge) if raw is edge else None).read()
    snapshot['model_to_sketch']=[float(v).hex() for v in (0,1,0,0,0,1,1,0,0,0,-.002,-.02,1,0,0,0)]
    return snapshot,members


@pytest.mark.parametrize('phase',['before_factory','after_factory'])
def test_complete_rectangle_projection_network_with_phase_specific_definitions(profile,phase):
    snapshot,members=capture(profile,phase)
    assert edge_flange_sketch_matches(snapshot,profile[3],IDENTITY)
    assert len(snapshot['points'])==4 and len(snapshot['segments'])==5
    assert sum(line['projection_internal'] for line in snapshot['segments'])==1
    assert ('prepared_source_edge' in dict(members))==(phase=='before_factory')
    assert 'model_origin' not in dict(members)


def test_factory_projection_migration_and_full_name_change_preserve_exact_entities(profile):
    before,before_members=capture(profile)
    profile[0].relations[-1].display.GetDimension2(0).FullName='Вылет от внутреннего ребра@Эскиз9@Контрольная деталь.Part'
    after,after_members=capture(profile,'after_factory')
    assert edge_flange_profile_preserved(before,after,before_members,after_members)
    changed=list(after_members);key,token=next((key,token) for key,token in changed if key.startswith('dimension:'))
    changed[changed.index((key,token))]=(key,object())
    assert not edge_flange_profile_preserved(before,after,before_members,changed)
    after['points'][0]['coordinates_si'][0]=float(.0001).hex()
    assert not edge_flange_profile_preserved(before,after,before_members,after_members)


@pytest.mark.parametrize('defect',['foreign_edge','foreign_ghost','ghost_new_points','extra_ghost','unsupported_kind','missing_definition'])
def test_partial_or_foreign_projection_does_not_create_a_complete_capture(profile,defect):
    sk,ghost,edge,d=profile
    if defect=='foreign_edge':sk.relations[0].definitions[0]=object()
    elif defect=='foreign_ghost':ghost.owner=object()
    elif defect=='ghost_new_points':ghost.end=deepcopy(ghost.end);ghost.end.owner=sk;ghost.end.number=77
    elif defect=='extra_ghost':sk.relations.append(Relation(5,[3],[Line(sk,10,sk.points[0],sk.points[1])]))
    elif defect=='unsupported_kind':sk.relations[0].types=[2,3]
    else:sk.relations[0].definitions=[]
    with pytest.raises(ExecutionFailure):capture(profile)


@pytest.mark.parametrize('defect',['scale','reflection','offset','wrong_side','point_status','curve','construction',
    'underdefined','projection_definition','duplicate_vertical','wrong_horizontal','wrong_dimension_points',
    'wrong_display_type','suppressed','extra_relation','wrong_phase','extra_point'])
def test_status_or_same_rectangle_bounds_do_not_hide_wrong_frame_or_constraints(profile,defect):
    snapshot,_=capture(profile);definition=profile[3]
    projection=next(r for r in snapshot['relations'] if r['type']==32)
    vertical=[r for r in snapshot['relations'] if r['type']==5]
    horizontal=next(r for r in snapshot['relations'] if r['type']==4)
    dim=next(r for r in snapshot['relations'] if r['type']==1)
    if defect=='scale':snapshot['model_to_sketch'][12]=float(2).hex()
    elif defect=='reflection':snapshot['model_to_sketch'][8]=float(-1).hex()
    elif defect=='offset':snapshot['model_to_sketch'][11]=float(-.021).hex()
    elif defect=='wrong_side':snapshot['model_to_sketch'][1]=float(-1).hex()
    elif defect=='point_status':snapshot['points'][0]['constraint_status']=1
    elif defect=='curve':snapshot['segments'][0]['kind']='arc'
    elif defect=='construction':snapshot['segments'][0]['construction']=True
    elif defect=='underdefined':snapshot['constraint_status']=2
    elif defect=='projection_definition':projection['definitions']=['foreign_edge',projection['entities'][1]]
    elif defect=='duplicate_vertical':vertical[1]['entities']=vertical[0]['entities'];vertical[1]['definitions']=vertical[0]['definitions']
    elif defect=='wrong_horizontal':horizontal['entities']=vertical[0]['entities'];horizontal['definitions']=vertical[0]['definitions']
    elif defect=='wrong_dimension_points':dim['entities']=list(reversed(dim['entities']));dim['definitions']=dim['entities']
    elif defect=='wrong_display_type':dim['display_type']=11
    elif defect=='suppressed':projection['suppressed']=True
    elif defect=='extra_relation':snapshot['relations'].append(deepcopy(projection))
    elif defect=='wrong_phase':snapshot['factory_phase']='unknown'
    else:snapshot['points'].append(deepcopy(snapshot['points'][0]))
    assert not edge_flange_sketch_matches(snapshot,definition,IDENTITY)
