"""Pure revision regression; no CAD/installed-flat-state acceptance claim."""

from copy import deepcopy

import pytest

from solidworks_mcp.sheet_flat_state import flat_state_revision


def closed_capture():
    return dict(dimension_revision='rev_native',semantic=dict(geometry=dict(vertices=['0x1.0p-2']),
        tree=dict(features=[dict(native_id=34,suppressed=True)]),dimensions=[dict(value_si=.04)]),
        flat=dict(pid_hex='aa',suppressed=True),fixed_face=dict(pid_hex='bb'),
        sheet_parameters=dict(k_factor=.42,thickness=.002),base_parameters=dict(radius=.002),
        controls=dict(add_to_db=False),options=dict(MergeFace=True),sketch=dict(fully_defined=True),
        volume_mm3=3402.7433388230806,area_mm2=3749.5928947446205)


def test_redundant_mass_roundoff_does_not_false_reject_an_unchanged_native_capture():
    before=closed_capture();after=deepcopy(before);after['volume_mm3']=3402.743338823081
    after['area_mm2']+=1e-12
    assert flat_state_revision(before)==flat_state_revision(after)
    assert before==closed_capture()


@pytest.mark.parametrize('target',['dimension_revision','geometry','tree','dimension','flat','fixed_face','k','thickness','base','controls','options','sketch'])
def test_actual_native_state_changes_remain_in_the_exact_revision(target):
    before=closed_capture();after=deepcopy(before)
    if target=='dimension_revision':after[target]='rev_changed'
    elif target=='geometry':after['semantic']['geometry']['vertices'][0]='0x1.1p-2'
    elif target=='tree':after['semantic']['tree']['features'][0]['suppressed']=False
    elif target=='dimension':after['semantic']['dimensions'][0]['value_si']=.041
    elif target=='flat':after['flat']['suppressed']=False
    elif target=='fixed_face':after['fixed_face']['pid_hex']='cc'
    elif target=='k':after['sheet_parameters']['k_factor']=.43
    elif target=='thickness':after['sheet_parameters']['thickness']=.003
    elif target=='base':after['base_parameters']['radius']=.003
    elif target=='controls':after['controls']['add_to_db']=True
    elif target=='options':after['options']['MergeFace']=False
    elif target=='sketch':after['sketch']['fully_defined']=False
    assert flat_state_revision(before)!=flat_state_revision(after)
