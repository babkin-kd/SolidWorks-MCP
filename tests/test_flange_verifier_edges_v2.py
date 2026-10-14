"""Read-only candidate filtering must distinguish predicate rejection/errors."""

import importlib.util
from pathlib import Path

import pytest

from test_sheet_profile_definition_v2 import definition
from test_part_creation_v2 import IDENTITY

spec=importlib.util.spec_from_file_location('flange_edge_filter',Path(__file__).resolve().parents[1]/'scripts/verifier_sheet_edge_flange_edges.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


@pytest.mark.parametrize('start,end,kind,expected',[
    ([2.,20.,0.],[2.,20.,30.],'line',True),([2.,20.,30.],[2.,20.,0.],'line',True),
    ([0.,20.,0.],[0.,20.,30.],'line',False),([2.,20.,0.],[2.,20.,20.],'line',False),
    ([2.,20.,0.],[2.,20.,30.],'circle',False)])
def test_full_line_filter_only_rejects_geometrically_unsuitable_edges(start,end,kind,expected):
    assert module.flange_edge_candidate(dict(curve_type=kind,start_mm=start,end_mm=end),definition(),IDENTITY) is expected


def test_missing_candidate_data_is_not_hidden_as_geometric_mismatch():
    with pytest.raises(KeyError):module.flange_edge_candidate(dict(curve_type='line'),definition(),IDENTITY)
