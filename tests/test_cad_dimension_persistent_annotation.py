"""Dual-interface annotation/dimension PID regressions with fake pointers only."""

from types import SimpleNamespace as NS

import pytest
import pythoncom

from solidworks_mcp import binding
from solidworks_mcp.cad_dimensions import CadDimensionsMixin, NativeDimension
from solidworks_mcp.cad_geometry import CadGeometryMixin
from solidworks_mcp.jobs import ExecutionFailure


NO_INTERFACE = -2147467262


class Pointer:
    def __init__(self, payload, supported):
        self.payload, self.supported = payload, set(supported)
        self.queries = []
        self.query_error = None

    def QueryInterface(self, interface_iid, wrapper_iid):
        self.queries.append((interface_iid, wrapper_iid))
        assert wrapper_iid == pythoncom.IID_IDispatch
        if self.query_error is not None:
            raise self.query_error
        if interface_iid not in self.supported:
            raise pythoncom.com_error(NO_INTERFACE, 'Fake unsupported dual interface', None, None)
        return self


class Dispatch:
    def __init__(self, payload, *supported):
        self._oleobj_ = Pointer(payload, supported)

    def __getattr__(self, name):
        return getattr(self._oleobj_.payload, name)


class Wrapper:
    CLSID = 'base'

    def __init__(self, pointer):
        assert isinstance(pointer, Pointer)
        self._oleobj_ = pointer

    def __getattr__(self, name):
        return getattr(self._oleobj_.payload, name)


class Display(Wrapper):
    CLSID = 'fake-IDisplayDimension'


class Annotation(Wrapper):
    CLSID = 'fake-IAnnotation'


class Dimension(Wrapper):
    CLSID = 'fake-IDimension'


class Feature(Wrapper):
    CLSID = 'fake-IFeature'


class RefPlane(Wrapper):
    CLSID = 'fake-IRefPlane'


class Adapter(CadDimensionsMixin, CadGeometryMixin):
    _module = NS(IDisplayDimension=Display, IAnnotation=Annotation, IDimension=Dimension,
                 IFeature=Feature, IRefPlane=RefPlane)

    def __init__(self, refs):
        self.refs = refs
        self.lookups = []
        self.pid_reads = []
        self.members = [binding.wrap(refs[b'owner'], Feature)]
        self.statuses = {}
        self.feature_reads = []
        self.same_calls = []
        self._sw = NS(IsSame=self.native_same)

    def _extension(self, model):
        return self

    @staticmethod
    def _persistent_variant(token):
        return bytes(token)

    def GetObjectByPersistReference3(self, token):
        self.lookups.append(token)
        return self.refs.get(token), self.statuses.get(token, 0)

    def features(self, model):
        self.feature_reads.append(model)
        return list(self.members)

    def native_same(self, left, right):
        self.same_calls.append((left, right))
        return 1 if left.native_plane is right.native_plane else 0

    @staticmethod
    def identity(obj):
        return obj.canonical

    def GetPersistReference3(self, obj):
        self.pid_reads.append(obj)
        return obj.pid


def fixture(*, annotation_pid=True):
    owner_data = NS(canonical=object(), pid=b'owner')
    owner = Dispatch(owner_data, Feature.CLSID)
    dimension_data = NS(canonical=object(), pid=b'', GetFeatureOwner=lambda: owner)
    dimension = Dispatch(dimension_data, Dimension.CLSID)
    annotation_data = NS(canonical=object(), pid=b'display', GetType=lambda: 4)
    annotation = Dispatch(annotation_data, Annotation.CLSID)
    display_data = NS(canonical=object(), pid=b'display', GetType=lambda: 1,
                      GetDimension2=lambda slot: dimension if slot == 0 else None,
                      GetAnnotation=lambda: annotation)
    display = Dispatch(display_data, Display.CLSID)
    annotation_data.GetSpecificAnnotation = lambda: display
    adapter = Adapter({b'display': annotation if annotation_pid else display, b'owner': owner})
    anchor = dict(strategy='display_dimension_v1', display_pid_hex=b'display'.hex(),
                  dimension_index=0, display_type=1, owner_pid_hex=b'owner'.hex())
    record = NativeDimension(binding.wrap(dimension, Dimension), binding.wrap(owner, Feature),
        displays=[binding.wrap(display, Display)], display_slots=[(binding.wrap(display, Display), 0)],
        owner_tree_identity=owner_data.canonical)
    return NS(a=adapter, anchor=anchor, record=record, owner=owner, dimension=dimension,
              display=display, annotation=annotation, display_data=display_data,
              annotation_data=annotation_data, dimension_data=dimension_data, owner_data=owner_data)


def plane_fixture(*, annotation_pid=True):
    x = fixture(annotation_pid=annotation_pid)
    native_plane = object()
    raw = Dispatch(NS(canonical=object(), pid=b'owner', native_plane=native_plane), RefPlane.CLSID)
    specific = Dispatch(NS(canonical=object(), pid=b'owner', native_plane=native_plane), RefPlane.CLSID)
    x.owner_data.GetTypeName2 = lambda: 'RefPlane'
    x.owner_data.GetSpecificFeature2 = lambda: specific
    x.a.refs[b'owner'] = raw
    # A separate current member proves resolution is not a traversal ordinal.
    neighbor = Dispatch(NS(canonical=object(), pid=b'neighbor'), Feature.CLSID)
    x.a.members.insert(0, binding.wrap(neighbor, Feature))
    x.raw_plane, x.specific_plane = raw, specific
    return x


def test_actual_queried_helper_requests_class_iid_and_dispatch_wrapper_iid():
    raw = Dispatch(NS(canonical=object()), Display.CLSID)
    result = binding.queried(raw, Display)
    assert type(result) is Display and result._oleobj_ is raw._oleobj_
    assert raw._oleobj_.queries == [(Display.CLSID, pythoncom.IID_IDispatch)]
    # Even an exact generated-wrapper type must perform actual native QI.
    second = binding.queried(result, Display)
    assert type(second) is Display and len(raw._oleobj_.queries) == 2
    assert binding.queried(None, Display) is None


def test_queried_helper_accepts_pointer_and_propagates_native_query_failure():
    raw = Dispatch(NS(), Annotation.CLSID)
    result = binding.queried(raw._oleobj_, Annotation)
    assert type(result) is Annotation and result._oleobj_ is raw._oleobj_
    with pytest.raises(pythoncom.com_error) as exc:
        binding.queried(raw, Display)
    assert exc.value.hresult == NO_INTERFACE


def test_normal_display_pid_uses_actual_display_query_without_annotation_fallback():
    x = fixture(annotation_pid=False)
    dimension, display = x.a._dimension_anchor_parts(object(), x.anchor)
    assert x.a.identity(dimension) == x.dimension.canonical
    assert x.a.identity(display) == x.display.canonical
    assert x.display._oleobj_.queries == [(Display.CLSID, pythoncom.IID_IDispatch)]
    assert not x.annotation._oleobj_.queries
    assert x.a.dimension_reference_is_current(object(), x.record, x.anchor) is True


def test_annotation_pid_roundtrips_to_exact_display_dimension_owner_and_slot():
    x = fixture()
    dimension, display = x.a._dimension_anchor_parts(object(), x.anchor)
    assert x.a.identity(dimension) == x.dimension.canonical
    assert x.a.identity(display) == x.display.canonical
    assert x.annotation._oleobj_.queries == [
        (Display.CLSID, pythoncom.IID_IDispatch), (Annotation.CLSID, pythoncom.IID_IDispatch),
        (Annotation.CLSID, pythoncom.IID_IDispatch)]
    assert x.display._oleobj_.queries == [(Display.CLSID, pythoncom.IID_IDispatch)]
    assert x.a.dimension_persistent_id(object(), x.record) == x.anchor
    assert x.a.dimension_reference_is_current(object(), x.record, x.anchor) is True


@pytest.mark.parametrize('annotation_pid', [False, True])
def test_plane_specific_owner_pid_uses_exact_current_feature_resolver_before_owner_comparison(annotation_pid):
    x = plane_fixture(annotation_pid=annotation_pid)
    model = object()
    # Blindly rewrapping the plane-specific pointer preserves the wrong canonical
    # identity, the precise failure addressed by the shared feature resolver.
    assert x.a.identity(binding.wrap(x.raw_plane, Feature)) != x.record.owner_tree_identity
    resolved = x.a._resolve_dimension_anchor_object(model, b'owner'.hex(), Feature)
    assert resolved is x.a.members[1] and x.a.identity(resolved) == x.record.owner_tree_identity
    assert x.a.feature_reads == [model] and x.a.lookups == [b'owner']
    assert x.a.same_calls[0][0] is x.raw_plane
    assert x.a.same_calls[0][1]._oleobj_ is x.specific_plane._oleobj_
    assert x.a.resolve_dimension_id(model, x.anchor).canonical == x.dimension.canonical
    assert x.a.dimension_persistent_id(model, x.record) == x.anchor
    assert x.a.dimension_reference_is_current(model, x.record, x.anchor) is True


@pytest.mark.parametrize('status,code', [(4, 'object_deleted'), (2, 'object_suppressed'), (1, 'object_reference_invalid')])
def test_plane_owner_pid_unavailable_state_never_adopts_a_current_member(status, code):
    x = plane_fixture();x.a.statuses[b'owner'] = status
    with pytest.raises(ExecutionFailure) as exc:
        x.a.resolve_dimension_id(object(), x.anchor)
    assert exc.value.code == code
    assert not x.a.feature_reads and not x.a.same_calls


@pytest.mark.parametrize('fault', ['stale_member', 'foreign_raw', 'duplicate_pid', 'specific_pid',
                                  'missing_specific', 'nonplane_member', 'wrong_owner', 'missing_owner'])
def test_plane_specific_owner_anchor_keeps_exact_pid_membership_native_and_dimension_owner_checks(fault):
    x = plane_fixture()
    if fault == 'stale_member':
        x.a.members.pop()
    elif fault == 'foreign_raw':
        x.raw_plane._oleobj_.payload.native_plane = object()
    elif fault == 'duplicate_pid':
        x.a.members.append(binding.wrap(Dispatch(NS(canonical=object(), pid=b'owner'), Feature.CLSID), Feature))
    elif fault == 'specific_pid':
        x.specific_plane._oleobj_.payload.pid = b'foreign'
    elif fault == 'missing_specific':
        x.owner_data.GetSpecificFeature2 = lambda: None
    elif fault == 'nonplane_member':
        x.owner_data.GetTypeName2 = lambda: 'Boss'
    elif fault == 'wrong_owner':
        x.dimension_data.GetFeatureOwner = lambda: Dispatch(NS(canonical=object()), Feature.CLSID)
    else:
        x.dimension_data.GetFeatureOwner = lambda: None
    with pytest.raises(ExecutionFailure) as exc:
        x.a.resolve_dimension_id(object(), x.anchor)
    assert exc.value.code == 'persistent_reference_mismatch'
    if fault in ('stale_member', 'duplicate_pid', 'specific_pid', 'missing_specific', 'nonplane_member'):
        assert not x.a.same_calls


@pytest.mark.parametrize('same', [0, 2, True, False, 1.0, '1', None])
def test_plane_owner_native_same_requires_exact_supported_integer_result(same):
    x = plane_fixture();x.a._sw.IsSame = lambda left, right: same
    with pytest.raises(ExecutionFailure) as exc:
        x.a.dimension_persistent_id(object(), x.record)
    assert exc.value.code == 'persistent_reference_mismatch'


def test_direct_dimension_pid_keeps_direct_resolution_without_owner_feature_enumeration():
    x = fixture();x.dimension_data.pid = b'dimension';x.a.refs[b'dimension'] = x.dimension
    anchor = dict(strategy='direct_dimension_v1', dimension_pid_hex=b'dimension'.hex())
    assert x.a.dimension_persistent_id(object(), x.record) == anchor
    assert x.a.dimension_reference_is_current(object(), x.record, anchor) is True
    assert x.a.lookups == [b'dimension', b'dimension']
    assert not x.a.feature_reads and not x.a.same_calls


@pytest.mark.parametrize('annotation_type', [1, 3, True, False, '4', 4.0, None])
def test_wrong_annotation_type_including_bool_cannot_become_dimension(annotation_type):
    x = fixture();x.annotation_data.GetType = lambda: annotation_type
    with pytest.raises(ExecutionFailure) as exc:
        x.a._dimension_anchor_parts(object(), x.anchor)
    assert exc.value.code == 'object_reference_invalid'
    assert not x.display._oleobj_.queries


@pytest.mark.parametrize('fault', ['no_specific', 'wrong_annotation', 'no_annotation', 'wrong_display_pid'])
def test_fallback_requires_exact_underlying_display_annotation_and_persistent_id(fault):
    x = fixture()
    if fault == 'no_specific':
        x.annotation_data.GetSpecificAnnotation = lambda: None
    elif fault == 'wrong_annotation':
        foreign = Dispatch(NS(canonical=object()), Annotation.CLSID)
        x.display_data.GetAnnotation = lambda: foreign
    elif fault == 'no_annotation':
        x.display_data.GetAnnotation = lambda: None
    else:
        x.display_data.pid = b'foreign-pid'
    with pytest.raises(ExecutionFailure) as exc:
        x.a._dimension_anchor_parts(object(), x.anchor)
    assert exc.value.code == ('object_reference_invalid' if fault == 'no_specific' else 'persistent_reference_mismatch')


@pytest.mark.parametrize('hresult', [-2147467259, -2147417848, -2147023170])
def test_general_native_query_error_never_enters_annotation_fallback(hresult):
    x = fixture()
    x.annotation._oleobj_.query_error = pythoncom.com_error(hresult, 'Fake native failure', None, None)
    with pytest.raises(pythoncom.com_error) as exc:
        x.a._dimension_anchor_parts(object(), x.anchor)
    assert exc.value.hresult == hresult
    assert x.annotation._oleobj_.queries == [(Display.CLSID, pythoncom.IID_IDispatch)]
    assert not x.display._oleobj_.queries and not x.a.pid_reads


@pytest.mark.parametrize('fault', ['wrong_owner', 'missing_owner', 'no_dimension', 'wrong_slot', 'wrong_type'])
def test_annotation_fallback_does_not_relax_existing_dimension_owner_type_slot_checks(fault):
    x = fixture()
    if fault == 'wrong_owner':
        foreign = Dispatch(NS(canonical=object()), Feature.CLSID)
        x.dimension_data.GetFeatureOwner = lambda: foreign
    elif fault == 'missing_owner':
        x.dimension_data.GetFeatureOwner = lambda: None
    elif fault == 'no_dimension':
        x.display_data.GetDimension2 = lambda slot: None
    elif fault == 'wrong_slot':
        x.anchor['dimension_index'] = 1
    else:
        x.display_data.GetType = lambda: 10
    with pytest.raises(ExecutionFailure):
        x.a._dimension_anchor_parts(object(), x.anchor)


@pytest.mark.parametrize('fault', ['dimension', 'display_membership', 'slot_membership', 'owner_tree'])
def test_resolved_annotation_still_requires_exact_current_record_membership(fault):
    x = fixture()
    if fault == 'dimension':
        foreign = Dispatch(NS(canonical=object(), pid=b''), Dimension.CLSID)
        x.record.dimension = binding.wrap(foreign, Dimension)
    elif fault == 'display_membership':
        foreign = Dispatch(NS(canonical=object()), Display.CLSID)
        x.record.display_slots = [(binding.wrap(foreign, Display), 0)]
    elif fault == 'slot_membership':
        x.record.display_slots = [(binding.wrap(x.display, Display), 1)]
    else:
        x.record.owner_tree_identity = object()
    assert x.a.dimension_reference_is_current(object(), x.record, x.anchor) is False
