"""Independent all-leaf/count/location/witness native acceptance oracle."""
import copy
import importlib.util
from pathlib import Path
import sys
import pytest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('aggregate_probe_verifier',SCRIPTS/'verify_component_aggregate_probes.py')
verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)


def value():
    return dict(measurement_scope='resolved_component_aggregate_point_distance_v1',coordinate_frame='assembly_model',
        leaf_component_count=2,leaf_component_ids=['leaf_a','leaf_b'],solid_leaf_component_count=2,evaluated_leaf_count=2,
        solid_body_count=2,nearest_component={'component_id':'leaf_b'},includes_hidden_components=True,
        includes_hidden_bodies=True,includes_surface_bodies=False,length_unit='mm',distance_mm=3.,
        distance_semantics='minimum_to_individual_solid_boundary',point_location='outside',inside=False,
        body_locations=[{'component_id':'leaf_a'},{'component_id':'leaf_b'}],point_mm=[199.,15.,0.],
        nearest_mm=[196.,15.,0.],point_assembly_mm=[199.,15.,0.],nearest_assembly_mm=[196.,15.,0.])


def test_complete_oracle_accepts_analytic_point_witness():
    verifier.check_probe(value(),'point',3.,location='outside')


@pytest.mark.parametrize('change',[{'evaluated_leaf_count':1},{'nearest_component':{'component_id':'foreign'}},
    {'distance_mm':0.},{'point_location':'inside'},{'nearest_mm':[195.,15.,0.]}])
def test_partial_or_foreign_or_inconsistent_result_is_not_accepted(change):
    wrong=value();wrong.update(change)
    with pytest.raises(AssertionError):verifier.check_probe(wrong,'point',3.,location='outside')


def test_missing_native_opt_in_before_wheel_or_cad(monkeypatch):
    monkeypatch.setattr(sys,'argv',['verify_component_aggregate_probes','--wheel','none.whl','--expected-version','dev','--expected-git-sha','sha','--state-dir','work/none'])
    monkeypatch.setattr(verifier,'validate_wheel',lambda *a,**kw:pytest.fail('wheel reached before opt-in'))
    with pytest.raises(SystemExit) as error:verifier.main()
    assert error.value.code==2
