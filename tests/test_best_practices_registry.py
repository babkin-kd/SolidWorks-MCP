"""Registry integrity checks: no SolidWorks, installed package or COM access."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest
from jsonschema import ValidationError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("practice_registry_verifier", ROOT / "scripts/verify_best_practices.py")
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


@pytest.fixture
def registry():
    folder = ROOT / "engineering/practices"
    return ([json.loads((folder / name).read_text(encoding="utf-8")) for name in VERIFIER.SHARDS],
            json.loads((folder / "schema.json").read_text(encoding="utf-8")))


def test_registered_claims_are_resolved_to_read_primary_sources(registry):
    sources, practices = VERIFIER.validate_catalog(*registry)
    assert sources and practices
    assert all(claim["source_id"] in sources for practice in practices.values()
               for claim in practice["source_claims"])


@pytest.mark.parametrize("access_status", ["partial", "unread", "unavailable"])
def test_confirmed_claim_cannot_use_a_search_snippet_or_unread_page(registry, access_status):
    shards, schema = copy.deepcopy(registry)
    shards[0]["sources"][0]["access_status"] = access_status
    with pytest.raises(ValueError, match="Unconfirmed subject text"):
        VERIFIER.validate_catalog(shards, schema)


def test_deleted_or_mistyped_source_reference_is_rejected(registry):
    shards, schema = copy.deepcopy(registry)
    shards[0]["practices"][0]["source_claims"][0]["source_id"] = "SRC-ZZ-99"
    with pytest.raises(ValueError, match="Unknown source"):
        VERIFIER.validate_catalog(shards, schema)


def test_duplicate_practice_or_source_is_rejected(registry):
    shards, schema = copy.deepcopy(registry)
    shards[1]["practices"].append(copy.deepcopy(shards[0]["practices"][0]))
    with pytest.raises(ValueError, match="Duplicate practice"):
        VERIFIER.validate_catalog(shards, schema)


def test_same_url_is_not_counted_as_two_independent_sources(registry):
    shards, schema = copy.deepcopy(registry)
    shards[1]["sources"][0]["url"] = shards[0]["sources"][0]["url"]
    with pytest.raises(ValueError, match="Same source URL"):
        VERIFIER.validate_catalog(shards, schema)


def test_passed_case_without_matching_execution_evidence_is_rejected(registry):
    shards, schema = copy.deepcopy(registry)
    practice = shards[0]["practices"][0]
    practice["checks"][0]["outcome"] = "passed"
    check_id = practice["checks"][0]["id"]
    practice["verification"]["evidence"] = [item for item in practice["verification"]["evidence"]
                                             if item.get("check_id") != check_id]
    with pytest.raises(ValueError, match="Passed without evidence"):
        VERIFIER.validate_catalog(shards, schema)


def test_native_acceptance_cannot_be_inferred_from_confirmed_source(registry):
    shards, schema = copy.deepcopy(registry)
    shards[0]["practices"][0]["verification"]["implementation"] = "native_accepted"
    with pytest.raises(ValueError, match="Native acceptance has no exact-wheel evidence"):
        VERIFIER.validate_catalog(shards, schema)


@pytest.mark.parametrize("outcome", ["skipped", "not_run", "unknown", "failed"])
def test_nonpassed_native_evidence_is_not_acceptance(registry, outcome):
    shards, schema = copy.deepcopy(registry)
    practice = shards[0]["practices"][0]
    practice["verification"]["implementation"] = "native_accepted"
    practice["verification"]["evidence"].append({
        "kind": "native", "outcome": outcome, "artifact": "work/example/report.json",
        "date": "2026-10-11", "scope": "illustrative_native_scope",
        "limitations": ["Synthetic test record, not CAD evidence"],
        "package_version": "2.0.0.dev87", "wheel_sha256": "a" * 64,
        "source_digest": "b" * 64, "git_sha": "c" * 40,
        "solidworks_version": "2023 SP2.1"
    })
    with pytest.raises(ValueError, match="Native acceptance has no exact-wheel evidence"):
        VERIFIER.validate_catalog(shards, schema)


def test_exact_installed_wheel_identity_is_required_for_native_evidence(registry):
    shards, schema = copy.deepcopy(registry)
    shards[0]["practices"][0]["verification"]["evidence"] = [{
        "kind": "native", "outcome": "passed", "artifact": "work/example/report.json",
        "date": "2026-10-11", "scope": "illustrative_native_scope", "limitations": [],
        "solidworks_version": "2023 SP2.1"
    }]
    with pytest.raises(ValidationError):
        VERIFIER.validate_catalog(shards, schema)


def test_native_report_without_a_matching_passed_case_is_not_acceptance(registry):
    shards, schema = copy.deepcopy(registry)
    practice = shards[0]["practices"][0]
    practice["verification"]["implementation"] = "native_accepted"
    practice["verification"]["evidence"].append({
        "kind": "native", "outcome": "passed", "artifact": "work/example/report.json",
        "date": "2026-10-11", "scope": "illustrative_native_scope",
        "limitations": ["Synthetic test record, not CAD evidence"],
        "package_version": "2.0.0.dev87", "wheel_sha256": "a" * 64,
        "source_digest": "b" * 64, "git_sha": "c" * 40,
        "solidworks_version": "2023 SP2.1", "check_id": "unrelated-case"
    })
    with pytest.raises(ValueError, match="Native acceptance has no exact-wheel evidence"):
        VERIFIER.validate_catalog(shards, schema)


def test_methodology_approval_is_separate_from_source_confirmation(registry):
    shards, schema = copy.deepcopy(registry)
    shards[0]["practices"][0]["lifecycle"] = "approved"
    with pytest.raises(ValueError, match="Approved without methodology review"):
        VERIFIER.validate_catalog(shards, schema)


@pytest.mark.parametrize("defect", ["tool", "version", "duplicate", "missing_reference"])
def test_capability_map_cannot_advertise_unknown_tools_or_stale_cards(registry, defect):
    _, practices = VERIFIER.validate_catalog(*registry)
    mapping = json.loads((ROOT / "engineering/practices/capabilities.json").read_text(encoding="utf-8"))
    row = mapping["practices"][0]
    if defect == "tool":
        row["tools"].append("part_create_general_symmetry")
    elif defect == "version":
        row["practice_version"] = "9.9.9"
    elif defect == "duplicate":
        mapping["practices"].append(copy.deepcopy(row))
    else:
        row["source_refs"].append("Docs/MISSING_CONTRACT.md")
    with pytest.raises(ValueError):
        VERIFIER.validate_capabilities(mapping, practices, VERIFIER.registered_tool_names())


@pytest.fixture
def skill_builder(monkeypatch):
    monkeypatch.setitem(sys.modules, "verify_best_practices", VERIFIER)
    spec = importlib.util.spec_from_file_location("practice_skill_builder", ROOT / "scripts/build_best_practices_skill.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    return builder


@pytest.fixture
def deployable_skill(tmp_path, skill_builder):
    source = tmp_path / skill_builder.SKILL / "SKILL.md"
    source.parent.mkdir(parents=True)
    source.write_text("Owned source fixture\n", encoding="utf-8")
    files = {"SKILL.md": skill_builder.sha256(source.read_text(encoding="utf-8")),
             "references/card.md": skill_builder.sha256("Owned card fixture\n")}
    manifest = {"generator": "scripts/build_best_practices_skill.py", "files": files}
    outputs = {"references/card.md": "Owned card fixture\n",
               "references/manifest.json": skill_builder.encode(manifest)}
    target = skill_builder.deploy(tmp_path, outputs, manifest)
    return tmp_path, target, outputs, manifest


@pytest.mark.parametrize("defect", ["local_change", "extra_file", "unknown_owner"])
def test_skill_deployment_preserves_local_changes_and_unknown_files(skill_builder, deployable_skill, defect):
    root, target, outputs, manifest = deployable_skill
    if defect == "local_change":
        (target / "references/card.md").write_text("User edit\n", encoding="utf-8")
    elif defect == "extra_file":
        (target / "personal.md").write_text("User file\n", encoding="utf-8")
    else:
        (target / "references/manifest.json").write_text('{"generator":"another-owner"}', encoding="utf-8")
    before = {path.relative_to(target): path.read_bytes() for path in target.rglob("*") if path.is_file()}
    with pytest.raises(ValueError):
        skill_builder.deploy(root, outputs, manifest)
    after = {path.relative_to(target): path.read_bytes() for path in target.rglob("*") if path.is_file()}
    assert after == before
