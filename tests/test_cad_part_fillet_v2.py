"""Native access boundary regressions; artificial COM, not CAD acceptance."""

import pytest

from solidworks_mcp.cad_part_fillet import CadPartFilletMixin
from solidworks_mcp.jobs import ExecutionFailure
from test_cad_part_pattern_v2 import setup as pattern_setup


@pytest.fixture
def setup(pattern_setup):
    adapter,receipt,replacement,data=pattern_setup
    class Adapter(CadPartFilletMixin,adapter.__class__):pass
    adapter.__class__=Adapter
    adapter._module.ISimpleFilletFeatureData2=object
    receipt.fillet=receipt.pattern;receipt.fillet_identity=receipt.pattern_identity;receipt.edge_pid=b'edge'
    data.Edges=[data.D1Axis]
    data.Type=0;data.DefaultRadius=.002;data.FilletItemsCount=-1
    data.GetEdgeCount=lambda:1;data.GetFeatureCount=lambda:0;data.GetLoopCount=lambda:0;data.GetHoldLineCount=lambda:0
    data.IsMultipleRadius=data.PropagateToTangentFaces=data.EnablePartialEdgeParameters=False
    data.AsymmetricFillet=data.CurvatureContinuous=False;data.ConicTypeForCrossSectionProfile=0
    return adapter,receipt,replacement,data


def test_native_rollback_replaced_body_requires_persistent_round_trip(setup):
    adapter,receipt,replacement,_=setup
    old=receipt.body_identity
    evidence=adapter.edge_fillet_evidence(object(),receipt)
    assert evidence['complete'] is True and evidence['parameters']['edge_matches'] is True
    assert receipt.body is replacement and receipt.body_identity!=old
    assert evidence['volume_mm3']==1e9


def test_same_mass_name_cannot_authorize_foreign_body(setup):
    adapter,receipt,replacement,_=setup;replacement.pid=b'foreign'
    with pytest.raises(ExecutionFailure,match='Persistent resulting body'):adapter.edge_fillet_evidence(object(),receipt)
    assert receipt.body is not replacement


def test_scalar_confirmation_never_accesses_rollback(setup):
    adapter,receipt,_,_=setup
    scalars=adapter.edge_fillet_parameters(object(),receipt)
    assert scalars['radius_m']==.002 and adapter.accessed is False


def test_access_false_holds_unknown_without_attempted_deletion(setup):
    adapter,receipt,_,data=setup;data.AccessSelections=lambda *args:False
    with pytest.raises(ExecutionFailure) as error:adapter.edge_fillet_evidence(object(),receipt)
    assert error.value.uncertain is True and receipt.selection_uncertain is True


def test_definition_read_exception_releases_native_access_before_propagating(setup):
    adapter,receipt,replacement,data=setup
    data.GetEdgeCount=lambda:(_ for _ in ()).throw(RuntimeError('Read failed.'))
    with pytest.raises(RuntimeError):adapter.edge_fillet_evidence(object(),receipt)
    assert adapter.current is replacement and receipt.selection_uncertain is False


def test_release_failure_marks_access_unknown(setup):
    adapter,receipt,_,data=setup
    data.ReleaseSelectionAccess=lambda:(_ for _ in ()).throw(RuntimeError('Release failed.'))
    with pytest.raises(RuntimeError):adapter.edge_fillet_evidence(object(),receipt)
    assert receipt.selection_uncertain is True
