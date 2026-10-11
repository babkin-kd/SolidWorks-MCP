"""Validate the source-backed registry and render its Markdown views. No CAD calls."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "engineering" / "practices"
SHARDS = ("sketches.json", "features.json", "assemblies.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_catalog(shards, schema):
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    sources, practices = {}, {}
    for shard in shards:
        validator.validate(shard)
        for source in shard["sources"]:
            require(source["id"] not in sources, f"Duplicate source: {source['id']}")
            require(urlparse(source["url"]).hostname is not None, "Source has no hostname")
            sources[source["id"]] = source
        for practice in shard["practices"]:
            require(practice["id"] not in practices, f"Duplicate practice: {practice['id']}")
            practices[practice["id"]] = practice
    urls = [source["url"] for source in sources.values()]
    require(len(urls) == len(set(urls)), "Same source URL registered under multiple IDs")
    for practice in practices.values():
        for claim in practice["source_claims"]:
            require(claim["source_id"] in sources, f"Unknown source: {claim['source_id']}")
            if practice["verification"]["source"] == "confirmed":
                source = sources[claim["source_id"]]
                require(source["access_status"] == "read" and source["claims"],
                        f"Unconfirmed subject text: {source['id']}")
        checks = practice["checks"]
        check_ids = [check["id"] for check in checks]
        require(len(check_ids) == len(set(check_ids)), f"Duplicate check in {practice['id']}")
        evidence = practice["verification"]["evidence"]
        for check in checks:
            if check["outcome"] == "passed":
                require(any(item.get("check_id") == check["id"] and
                            item["kind"] == check["kind"] and item["outcome"] == "passed"
                            for item in evidence), f"Passed without evidence: {check['id']}")
        if practice["lifecycle"] == "approved":
            require(practice["verification"]["methodology"] == "accepted",
                    f"Approved without methodology review: {practice['id']}")
        if practice["verification"]["implementation"] == "native_accepted":
            accepted = [item for item in evidence if item["kind"] == "native" and
                        item["outcome"] == "passed" and any(
                            check["id"] == item.get("check_id") and
                            check["kind"] == "native" and check["outcome"] == "passed"
                            for check in checks)]
            require(accepted, f"Native acceptance has no exact-wheel evidence: {practice['id']}")
    return sources, practices


def bullets(items):
    return "\n".join(f"- {item}" for item in items)


def render_views(sources, practices):
    outputs = {}
    source_lines = ["# Источники лучших практик SolidWorks", "",
                    "Предметные разделы прочитаны 11.10.2026. Эта страница создаётся из",
                    "`engineering/practices/*.json`; изменения вносятся в канонические записи.",
                    "Подтверждение источником не является приёмкой нашего MCP.", ""]
    for source in sorted(sources.values(), key=lambda item: item["id"]):
        source_lines.extend([
            f"## {source['id']} {source['title']}", "",
            f"[Первоисточник]({source['url']})", "",
            f"Издатель: {source['publisher']}. Продукт: {source['product']}.",
            f"Редакция: {source['edition']}. Дата публикации: {source['published_on'] or 'не установлена'}.",
            f"Дата доступа: {source['accessed_on']}. Прочитано: {source['locator']}.",
            f"Состояние доступа: `{source['access_status']}`.", "",
            "Извлечённые положения:", "", bullets(source["claims"]), "",
            "Границы источника:", "", bullets(source["limits"]), ""
        ])
    outputs["Docs/BEST_PRACTICES_SOURCES.md"] = "\n".join(source_lines).rstrip() + "\n"
    index = ["# Карточки лучших практик SolidWorks", "",
             "Представление создаётся из канонического JSON-реестра. Статусы источника,",
             "инженерной методики и реализации независимы; черновики не являются CAD-приёмкой.", "",
             "| Практика | Версия | Жизненный цикл | Источник | Методика | Реализация | Стадия |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for practice in sorted(practices.values(), key=lambda item: item["id"]):
        pid = practice["id"]
        verification = practice["verification"]
        index.append(f"| [{pid}: {practice['title']}](practices/{pid}.md) | {practice['version']} | "
                     f"{practice['lifecycle']} | {verification['source']} | {verification['methodology']} | "
                     f"{verification['implementation']} | {practice['target_stage']} |")
        lines = [f"# {practice['title']}", "",
                 f"ID: `{pid}`. Версия: `{practice['version']}`. Ответственный: {practice['owner']}.",
                 f"Жизненный цикл: `{practice['lifecycle']}`. Сила: `{practice['rule_strength']}`.",
                 f"Стадия PLAN.md: `{practice['target_stage']}`.", "",
                 "Канонический реестр: [engineering/practices](../../engineering/practices).",
                 "Представление генерируется; его текст отдельно не редактируется.", "",
                 "## Основание", ""]
        for claim in practice["source_claims"]:
            source = sources[claim["source_id"]]
            lines.append(f"- [{source['id']}]({source['url']}), {claim['locator']}: {claim['statement']}")
        lines.extend(["", "## Наша интерпретация", "", practice["interpretation"], ""])
        fields = (("applicability", "Применимость"), ("exceptions", "Исключения"),
                  ("parameters", "Входные параметры и базы"), ("invariants", "Сохраняемые условия"),
                  ("method", "Предлагаемый метод"), ("requires_capabilities", "Необходимые возможности"))
        for key, title in fields:
            lines.extend([f"## {title}", "", bullets(practice[key]), ""])
        lines.extend(["## Наши проверочные сценарии", ""])
        for check in practice["checks"]:
            lines.extend([f"- `{check['id']}` — {check['kind']}, `{check['outcome']}`.",
                          f"  Процедура: {check['procedure']}", f"  Ожидается: {check['expected']}"])
        lines.extend(["", "## Состояние доказательств", "",
                      f"Источник: `{verification['source']}`; методика: `{verification['methodology']}`;",
                      f"реализация: `{verification['implementation']}`.", ""])
        if verification["evidence"]:
            for item in verification["evidence"]:
                lines.append(f"- {item['kind']}: `{item['outcome']}`, {item['date']}, "
                             f"{item['artifact']}; область: {item['scope']}.")
        else:
            lines.append("Свидетельств выполнения сценариев пока нет.")
        lines.extend(["", "## Ограничения", "", bullets(practice["limitations"]), ""])
        outputs[f"Docs/practices/{pid}.md"] = "\n".join(lines).rstrip() + "\n"
    outputs["Docs/BEST_PRACTICES_INDEX.md"] = "\n".join(index) + "\n"
    return outputs


def load_catalog(root=ROOT):
    registry = root / "engineering" / "practices"
    return validate_catalog([read_json(registry / name) for name in SHARDS],
                            read_json(registry / "schema.json"))


def registered_tool_names(root=ROOT):
    """Read statically registered v2 tools without importing a server or COM."""
    package = root / "src/solidworks_mcp"
    tree = ast.parse((package / "server_v2.py").read_text(encoding="utf-8"))
    paths = {package / "server_v2.py"}
    registrations = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Name) and node.func.id.startswith("register_")}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and any(
                item.name in registrations for item in node.names):
            paths.add(package / (node.module.rsplit(".", 1)[-1] + ".py"))
    names = set()
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                        and decorator.func.attr == "tool" and
                        isinstance(decorator.func.value, ast.Name) and
                        decorator.func.value.id == "app"):
                    explicit = next((item.value.value for item in decorator.keywords
                                     if item.arg == "name" and isinstance(item.value, ast.Constant)), None)
                    names.add(explicit or node.name)
    return names


def validate_capabilities(mapping, practices, tool_names, root=ROOT):
    require(mapping["schema_version"] == "1.0", "Unsupported capability-map schema")
    rows = mapping["practices"]
    ids = [row["practice_id"] for row in rows]
    require(len(ids) == len(set(ids)) and set(ids) == set(practices),
            "Capability map does not cover the registry exactly once")
    for row in rows:
        pid = row["practice_id"]
        require(row["practice_version"] == practices[pid]["version"],
                f"Capability map version differs: {pid}")
        require(row["status"] in {"guidance_only", "partial", "unsupported"},
                f"Invalid capability status: {pid}")
        require(set(row["tools"]) <= tool_names, f"Unregistered public tool in {pid}")
        require(row["scope"] and row["missing"] and row["source_refs"],
                f"Capability map has no scope or limitation: {pid}")
        require(row["stage"] == practices[pid]["target_stage"], f"Stage differs: {pid}")
        for reference in row["source_refs"]:
            require((root / reference).is_file(), f"Missing contract reference: {reference}")
    return mapping


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-docs", action="store_true", help="Render maintained Markdown views")
    args = parser.parse_args()
    sources, practices = load_catalog()
    validate_capabilities(read_json(REGISTRY / "capabilities.json"), practices,
                          registered_tool_names())
    outputs = render_views(sources, practices)
    for relative, content in outputs.items():
        path = ROOT / relative
        if args.write_docs:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        else:
            require(path.is_file() and path.read_text(encoding="utf-8") == content,
                    f"Stale or missing generated view: {relative}; use --write-docs")
    digest = hashlib.sha256(json.dumps({"sources": sources, "practices": practices},
                                      ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    print(json.dumps({"sources": len(sources), "practices": len(practices),
                      "registry_sha256": digest, "cad_called": False,
                      "views_written": args.write_docs}, ensure_ascii=False))


if __name__ == "__main__":
    main()
