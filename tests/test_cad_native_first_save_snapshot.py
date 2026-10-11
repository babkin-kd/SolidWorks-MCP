"""Passive oracle components with native-shaped fakes, not CAD acceptance."""
from copy import deepcopy
from types import SimpleNamespace as NS
import random

import pytest

from solidworks_mcp import binding
from solidworks_mcp import cad_native_first_save_snapshot as native
from solidworks_mcp.jobs import ExecutionFailure
from test_planar_brep_v2 import make_body, snapshot


@pytest.fixture(autouse=True)
def typed_wrappers(monkeypatch):
    monkeypatch.setattr(binding, 'wrap', lambda raw, cls: raw)


class Adapter:
    _module = NS(IVertex=object, IEdge=object, ICustomPropertyManager=object)
    def __init__(self, body=None):
        self.body = body or make_body()
        self.objects = [self.body, *self.body.edges, *self.body.faces]
        self.tokens = {id(item): str(index).encode() for index,item in enumerate(self.objects)}
        self.target = None
    def topology(self, body, kind): return body.edges[:] if kind=='edge' else body.faces[:]
    def identity(self, obj): return id(obj)
    def owner_body(self, obj, kind): return obj.body
    def persistent_id(self, model, obj): return self.tokens[id(obj)]
    def resolve_persistent_id(self, model, token, kind):
        return self.target or next(item for item in self.objects if self.tokens[id(item)] == token)


def test_complete_boundary_roles_are_independent_of_native_enumeration_order():
    adapter = Adapter()
    boundary = snapshot(adapter.body)
    first = []
    native._topology(adapter, object(), adapter.body, boundary, first)
    assert len(first)==18 and {row['kind'] for row in first}=={'face','edge'}
    random.Random(42).shuffle(adapter.body.faces)
    random.Random(9).shuffle(adapter.body.edges)
    second = []
    native._topology(adapter, object(), adapter.body, boundary, second)
    assert sorted(first,key=lambda row:(row['kind'],row['role'])) == sorted(second,key=lambda row:(row['kind'],row['role']))


@pytest.mark.parametrize('fault', ['foreign_owner','duplicate_edge','duplicate_face','missing_edge','missing_face','replaced_reference','wrong_geometry'])
def test_complete_boundary_rejects_foreign_incomplete_alias_and_changed_incidence(fault):
    adapter = Adapter()
    boundary = snapshot(adapter.body)
    if fault=='foreign_owner': adapter.body.edges[0].body=make_body()
    elif fault=='duplicate_edge': adapter.body.edges[-1]=adapter.body.edges[0]
    elif fault=='duplicate_face': adapter.body.faces[-1]=adapter.body.faces[0]
    elif fault=='missing_edge': adapter.body.edges.pop()
    elif fault=='missing_face': adapter.body.faces.pop()
    elif fault=='replaced_reference': adapter.target=make_body()
    else: adapter.body.vertices[0].point=(99.,0.,0.)
    with pytest.raises(ExecutionFailure) as exc:
        native._topology(adapter, object(), adapter.body, boundary, [])
    assert exc.value.code=='first_save_snapshot_unsupported'


@pytest.mark.parametrize('fault', ['empty','duplicate_role','duplicate_token','wrong_native_identity'])
def test_reference_inventory_requires_exact_bijective_roundtrip(fault):
    adapter=Adapter()
    rows=[]
    if fault=='empty': adapter.tokens[id(adapter.body)]=b''
    elif fault=='wrong_native_identity': adapter.target=make_body()
    else:
        native._pid(adapter,object(),adapter.body,'body','body:0',rows)
        if fault=='duplicate_role': adapter.tokens[id(adapter.body)]=b'new'
    with pytest.raises(ExecutionFailure):
        native._pid(adapter,object(),adapter.body,'body','body:0' if fault!='duplicate_token' else 'body:1',rows)


class Properties:
    Count=1
    def __init__(self): self.outputs=(2,'Сталь','Сталь',True,False); self.calls=[]
    def GetNames(self): return ['Материал']
    def Get6(self,name,cached): self.calls.append((name,cached)); return self.outputs
    def GetType2(self,name): return 30


def test_property_reader_uses_cached_only_and_preserves_all_outputs():
    manager=Properties()
    adapter=NS(_module=Adapter._module,_extension=lambda model:NS(CustomPropertyManager=lambda cfg:manager))
    result=native._properties(adapter,object(),'Основная')
    assert result[''][0]==dict(name='Материал',type=30,value='Сталь',resolved='Сталь',was_resolved=True,linked=False,cached_result=2)
    assert manager.calls==[('Материал',True),('Материал',True)]


@pytest.mark.parametrize('outputs', [(2,'x','y',True,False),(2,'x','x',True,True),(True,'x','x',True,False),(2,'x','x',1,False),(2,'x','x',True,0),(2,'x','x',True)])
def test_linked_evaluated_malformed_property_data_is_not_silently_dropped(outputs):
    manager=Properties(); manager.outputs=outputs
    adapter=NS(_module=Adapter._module,_extension=lambda model:NS(CustomPropertyManager=lambda cfg:manager))
    with pytest.raises(ExecutionFailure):native._properties(adapter,object(),'Основная')


@pytest.mark.parametrize('value',[True,float('nan'),float('inf'),'1',None])
def test_exact_geometry_numbers_never_coerce_invalid_data(value):
    with pytest.raises(ExecutionFailure):native._number(value)


def test_equal_real_numbers_have_exact_hex_encoding():
    assert native._number(1)==native._number(1.)=='0x1.0000000000000p+0'


def annotation_fixture():
    annotation=NS(GetPosition=lambda:[0.,1.,2.],GetName=lambda:'Размер толщины',
                  GetType=lambda:4,Visible=1)
    display=NS(GetAnnotation=lambda:annotation,GetTextFormat=lambda:NS(GetAllValues=lambda:['Arial',.003,False]),
               Type2=2,GetText=lambda which:'12',GetUseDocTextFormat=lambda:True)
    roster=[annotation]
    extension=NS(GetAnnotationCount=lambda:len(roster),GetAnnotations=lambda:roster[:],
        GetObjectByPersistReference3=lambda token:(annotation,0))
    adapter=NS(_extension=lambda model:extension,_module=NS(IAnnotation=object,ITextFormat=object),
        identity=lambda obj:id(obj),persistent_id=lambda model,obj:b'annotation',_persistent_variant=lambda pid:pid)
    return adapter,annotation,display,roster


def test_complete_own_dimension_annotation_is_bound_and_preserved():
    adapter,_,display,_=annotation_fixture()
    references=[]
    rows=native._annotations(adapter,object(),[NS(displays=[display])],references)
    assert rows==[dict(role='annotation:Размер толщины',type=4,visible=1,
        position=[float(value).hex() for value in (0.,1.,2.)],display_type=2,text='12',
        use_document_format=True,text_format=['Arial',.003,False])]
    assert references==[dict(kind='annotation',role='annotation:Размер толщины',token=b'annotation'.hex())]


@pytest.mark.parametrize('fault',['foreign_note','duplicate_annotation','missing','bad_position','bad_format','wrong_reference','wrong_visible'])
def test_annotation_inventory_rejects_unobserved_or_replaced_data(fault):
    adapter,annotation,display,roster=annotation_fixture()
    if fault=='foreign_note':roster.append(object())
    elif fault=='duplicate_annotation':roster.append(annotation)
    elif fault=='missing':roster.clear()
    elif fault=='bad_position':annotation.GetPosition=lambda:[0.,1.]
    elif fault=='bad_format':display.GetTextFormat=lambda:NS(GetAllValues=lambda:[object()])
    elif fault=='wrong_reference':adapter._extension(None).GetObjectByPersistReference3=lambda token:(object(),0)
    else:annotation.Visible=True
    with pytest.raises(ExecutionFailure):
        native._annotations(adapter,object(),[NS(displays=[display])],[])


def configuration_fixture():
    config=NS(Name='Основная',Description='Основание',Comment='',AlternateName='',
        BOMPartNoSource=0,Type=0,Lock=False,UseAlternateNameInBOM=False,UseDescriptionInBOM=False,
        SuppressNewFeatures=False,HideNewComponentModels=False,SuppressNewComponentModels=False,
        RepresentationShared=True,GetParameterCount=lambda:1,GetParameters=lambda:(['Толщина'],[.012]),
        GetDisplayStates=lambda:['Состояние отображения'],GetDisplayStatesCount=lambda:1,
        GetChildrenCount=lambda:0)
    adapter=NS(_module=NS(IConfiguration=object),identity=lambda value:id(value))
    model=NS(GetConfigurationByName=lambda name:config)
    return adapter,model,config


def test_configuration_parameters_labels_and_display_membership_are_preserved():
    adapter,model,_=configuration_fixture()
    result=native._configuration(adapter,model,'Основная')
    assert result['parameters']==[('Толщина',.012)]
    assert result['display_states']==['Состояние отображения']
    assert result['Description']=='Основание' and result['RepresentationShared'] is True


@pytest.mark.parametrize('fault',['bad_scalar','incomplete_parameters','duplicate_parameters','bad_value',
    'bad_display_count','duplicate_display','derived','replacement'])
def test_configuration_capture_rejects_partial_or_replaced_membership(fault):
    adapter,model,config=configuration_fixture()
    if fault=='bad_scalar':config.Lock=0
    elif fault=='incomplete_parameters':config.GetParameters=lambda:(['Толщина'],[])
    elif fault=='duplicate_parameters':
        config.GetParameterCount=lambda:2;config.GetParameters=lambda:(['Толщина','Толщина'],[1.,2.])
    elif fault=='bad_value':config.GetParameters=lambda:(['Толщина'],[object()])
    elif fault=='bad_display_count':config.GetDisplayStatesCount=lambda:2
    elif fault=='duplicate_display':
        config.GetDisplayStates=lambda:['Один','Один'];config.GetDisplayStatesCount=lambda:2
    elif fault=='derived':config.GetChildrenCount=lambda:1
    else:
        calls=[]
        def getter(name):
            calls.append(name);return config if len(calls)==1 else object()
        model.GetConfigurationByName=getter
    with pytest.raises(ExecutionFailure):native._configuration(adapter,model,'Основная')


@pytest.mark.parametrize('fault',['attachment','comment','selection_set'])
def test_unobserved_embedded_data_is_rejected_before_copy(fault):
    comments=NS(GetCommentCount=lambda:0,GetComments=lambda:[])
    selections=NS(GetSelectionSets=lambda:[])
    extension=NS(GetAttachmentCount=lambda:0,GetAttachments=lambda:[])
    if fault=='attachment':extension.GetAttachmentCount=lambda:1
    elif fault=='comment':comments.GetCommentCount=lambda:1
    else:selections.GetSelectionSets=lambda:[object()]
    features=[NS(GetSpecificFeature2=lambda:comments),NS(GetSpecificFeature2=lambda:selections)]
    rows=[dict(feature_type='CommentsFolder'),dict(feature_type='SelectionSetFolder')]
    adapter=NS(_extension=lambda model:extension,_module=NS(ICommentFolder=object,ISelectionSetFolder=object))
    with pytest.raises(ExecutionFailure):native._empty_auxiliary_data(adapter,object(),features,rows)
