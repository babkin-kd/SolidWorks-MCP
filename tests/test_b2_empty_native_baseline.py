"""Composite native baseline shape, without claiming any actual CAD result."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

scripts=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(scripts))
try:
    from verify_b2_impact_native import empty_native_baseline
finally:
    sys.path.remove(str(scripts))


BASELINE=[["31.2.1",True,None,[]],[[],None,False,True],[]]


def test_complete_empty_composite_accepts_native_tuple_and_serialized_list():
    assert empty_native_baseline(BASELINE)
    assert empty_native_baseline((tuple(BASELINE[0]),tuple(BASELINE[1]),()))


@pytest.mark.parametrize('value',[[],None,[[],[],[]],BASELINE[:2]])
def test_missing_complete_observation_is_not_an_empty_session(value):
    assert not empty_native_baseline(value)


@pytest.mark.parametrize('section,field,value',[
    (0,0,''),(0,1,1),(0,2,'active'),(0,3,['document']),
    (1,0,['document']),(1,1,'active'),(1,2,True),(1,2,0),
    (1,3,False),(1,3,1),
])
def test_live_scope_guard_or_mismatched_visibility_refuses(section,field,value):
    current=deepcopy(BASELINE)
    current[section][field]=value
    assert not empty_native_baseline(current)


def test_window_census_must_also_be_empty():
    current=deepcopy(BASELINE);current[2]=[{'hwnd':123}]
    assert not empty_native_baseline(current)
