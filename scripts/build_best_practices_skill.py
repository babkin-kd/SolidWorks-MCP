"""Build/check a self-contained skill snapshot from the canonical registry; no CAD."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from verify_best_practices import (load_catalog, read_json, render_views, require,
                                  registered_tool_names, validate_capabilities)

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path("skills/solidworks-part-design")
DEPLOYED = Path(".agents/skills/solidworks-part-design")


def sha256(content):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def build_outputs(root=ROOT):
    sources, practices = load_catalog(root)
    capability_map = read_json(root / "engineering/practices/capabilities.json")
    validate_capabilities(capability_map, practices, registered_tool_names(root), root)
    part_ids = sorted(pid for pid in practices if pid.startswith("SW-PART-"))
    mappings = {row["practice_id"]: row for row in capability_map["practices"]}
    require(set(mappings) == set(practices), "Capability map does not cover the registry")
    for pid, row in mappings.items():
        require(row["practice_version"] == practices[pid]["version"],
                f"Capability map version differs: {pid}")
    digest = sha256(json.dumps({"sources": sources, "practices": practices},
                              ensure_ascii=False, sort_keys=True))
    views = render_views(sources, practices)
    outputs = {}
    for pid in part_ids:
        content = views[f"Docs/practices/{pid}.md"]
        content = content.replace(
            "Канонический реестр: [engineering/practices](../../engineering/practices).\n"
            "Представление генерируется; его текст отдельно не редактируется.",
            "Генерируемый снимок канонического реестра engineering/practices.\n"
            f"Digest всего реестра: `{digest}`.\n"
            "Состав снимка: [manifest.json](manifest.json).")
        outputs[f"references/{pid}.md"] = content
    selected = {key: value for key, value in capability_map.items() if key != "practices"}
    selected["practices"] = [mappings[pid] for pid in part_ids]
    outputs["references/capabilities.json"] = encode(selected)
    skill_content = (root / SKILL / "SKILL.md").read_text(encoding="utf-8")
    manifest = {
        "schema_version": "1.0", "skill_version": "1.0.0",
        "generator": "scripts/build_best_practices_skill.py", "registry_sha256": digest,
        "capabilities_sha256": sha256(encode(capability_map)),
        "practices": [{"id": pid, "version": practices[pid]["version"]} for pid in part_ids],
        "files": {"SKILL.md": sha256(skill_content), **{
            path: sha256(content) for path, content in sorted(outputs.items())}},
        "cad_called": False,
        "acceptance_scope": "Registry snapshot integrity only; not native CAD acceptance",
    }
    outputs["references/manifest.json"] = encode(manifest)
    return outputs, manifest


def deploy(root, outputs, manifest):
    target = root / DEPLOYED
    content = {"SKILL.md": (root / SKILL / "SKILL.md").read_text(encoding="utf-8"), **outputs}
    if target.exists():
        previous = read_json(target / "references/manifest.json")
        require(previous.get("generator") == manifest["generator"],
                "Existing skill was not created by this generator")
        expected = set(previous["files"]) | {"references/manifest.json"}
        actual = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
        require(actual == expected, "Existing installation has extra or missing files; preserve it")
        for relative, digest in previous["files"].items():
            require(sha256((target / relative).read_text(encoding="utf-8")) == digest,
                    f"Installed skill has local changes; preserve {relative}")
        require(expected <= set(content), "Removing old skill resources requires a reviewed migration")
    for relative, value in content.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8", newline="\n")
    return target


def verify_deployed(root, outputs):
    target = root / DEPLOYED
    require(target.is_dir(), "Skill has not been deployed to .agents/skills")
    content = {"SKILL.md": (root / SKILL / "SKILL.md").read_text(encoding="utf-8"), **outputs}
    actual = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
    require(actual == set(content), "Deployed skill has extra or missing files")
    for relative, value in content.items():
        require((target / relative).read_text(encoding="utf-8") == value,
                f"Deployed skill differs: {relative}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Refresh the skill references")
    parser.add_argument("--deploy", action="store_true", help="Install the verified snapshot in repository .agents/skills")
    parser.add_argument("--check-deployed", action="store_true", help="Verify deployed bytes and file set")
    args = parser.parse_args()
    outputs, manifest = build_outputs()
    for relative, content in outputs.items():
        path = ROOT / SKILL / relative
        if args.write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        else:
            require(path.is_file() and path.read_text(encoding="utf-8") == content,
                    f"Stale or missing skill snapshot: {relative}; use --write")
    actual = {str(path.relative_to(ROOT / SKILL)).replace("\\", "/")
              for path in (ROOT / SKILL / "references").rglob("*") if path.is_file()}
    require(actual == set(outputs), "Skill references contain extra or outdated files")
    if args.deploy:
        deploy(ROOT, outputs, manifest)
    if args.check_deployed:
        verify_deployed(ROOT, outputs)
    print(json.dumps({"practices": len(manifest["practices"]),
                      "registry_sha256": manifest["registry_sha256"],
                      "cad_called": False, "snapshot_written": args.write,
                      "deployed": args.deploy, "deployment_checked": args.check_deployed}))


if __name__ == "__main__":
    main()
