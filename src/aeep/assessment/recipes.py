"""Deterministic synthetic recipes. Ground truth is constructed before rendering inputs."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import re
import string
from itertools import islice
from pathlib import Path
from typing import Any

from ..artifact_store import _read_stable_file, _safe_local_path
from ..benchmarking import BenchmarkCase, BenchmarkSplit
from ..errors import ConfigurationError
from ..models import ActionRequest, ValidationKind, ValidationSpec
from .models import RecipeDefinition

VARIATIONS = {
    "csv": ["plain", "quoted", "unicode", "empty", "reordered", "semicolon", "malformed"],
    "text": ["plain", "optional", "repeated", "reordered", "distractor", "unicode", "invalid"],
    "search": ["present", "absent", "duplicate", "nested", "unicode", "escape"],
}


def faulty_outputs(correct: dict[str, Any]) -> list[Any]:
    """Fault injections catch constant, missing-field and wrong-value graders."""
    if not correct:
        return [None, {"unexpected_field": True}]
    changed = json.loads(json.dumps(correct))
    key = next(iter(changed))
    changed[key] = {"corrupted": True}
    faults = [None, {}, {"wrong": True}, changed, {**correct, "unexpected_field": True}]
    payload = correct[key]
    if isinstance(payload, list) and payload:
        faults.append({key: payload[:-1]})
        if len(payload) > 1 and payload != list(reversed(payload)):
            faults.append({key: list(reversed(payload))})
    elif isinstance(payload, dict) and payload:
        faults.append({key: dict(list(payload.items())[1:])})
    if "error" in correct:
        faults.extend([{"records": []}, {"fields": {"id": "duplicate"}}, {"matches": [{"path": "../secret", "line": 1, "text": "escaped"}]}])
    return faults


def independent_cases(family: str, root: Path) -> list[BenchmarkCase]:
    """Reviewed literals, independent of the randomized generator and reference code."""
    fixtures: list[tuple[dict[str, Any], dict[str, Any]]]
    if family == "csv":
        fixtures = [
            ({"text": 'id,note\n1,"hello, world"\n2,"two\nlines"\n', "delimiter": ","}, {"records": [{"id": "1", "note": "hello, world"}, {"id": "2", "note": "two\nlines"}]}),
            ({"text": 'note;id\n"hello, world";1\n"two\nlines";2\n', "delimiter": ";"}, {"records": [{"id": "1", "note": "hello, world"}, {"id": "2", "note": "two\nlines"}]}),
            ({"text": "a,a\n1,2\n", "delimiter": ","}, {"error": "invalid_input"}),
        ]
    elif family == "text":
        fixtures = [
            ({"text": "note: ignored\nname: Zoë\nid: 42", "fields": ["id", "name", "missing"]}, {"fields": {"id": "42", "name": "Zoë"}}),
            ({"text": "id: 42\nname: Zoë", "fields": ["name", "id"]}, {"fields": {"id": "42", "name": "Zoë"}}),
            ({"text": "id: 42\nid: 43", "fields": ["id"]}, {"error": "invalid_input"}),
        ]
    elif family == "search":
        root.mkdir(parents=True, exist_ok=True)
        (root / "a.txt").write_text("miss\nneedle\n", encoding="utf-8")
        (root / "b.txt").write_text("needle\n", encoding="utf-8")
        fixtures = [
            ({"root": str(root), "path": ".", "query": "needle"}, {"matches": [{"path": "a.txt", "line": 2, "text": "needle"}, {"path": "b.txt", "line": 1, "text": "needle"}]}),
            ({"root": str(root), "path": ".", "query": "absent"}, {"matches": []}),
            ({"root": str(root), "path": "../", "query": "needle"}, {"error": "invalid_input"}),
        ]
    else:
        return []
    return [BenchmarkCase(case_id=f"independent-{index}", split=BenchmarkSplit.QUALIFICATION, action=ActionRequest(capability=f"assessment.{family}@1", input=value), validators=[ValidationSpec(kind=ValidationKind.EXACT_MATCH, config={"expected": expected})]) for index, (value, expected) in enumerate(fixtures)]


def generate_reviewed_case(
    recipe: RecipeDefinition, index: int, seed: int, split: BenchmarkSplit
) -> BenchmarkCase:
    """Small declarative generator for reviewed new labeled-record families."""
    if recipe.generator != "record_template:1" or recipe.grader != "exact_match:1":
        raise ConfigurationError("a controlled generator adapter is required for this definition")
    config = recipe.generator_config
    fields = config.get("fields")
    templates = config.get("templates")
    if (
        not isinstance(fields, list)
        or not 1 <= len(fields) <= 100
        or not all(isinstance(field, str) and field.isidentifier() for field in fields)
        or len(fields) != len(set(fields))
    ):
        raise ConfigurationError("reviewed record fields must be unique identifiers")
    if not isinstance(templates, dict) or set(templates) != set(recipe.variations):
        raise ConfigurationError("every reviewed variation requires a literal template")
    variation = recipe.variations[index % len(recipe.variations)]
    template = templates[variation]
    if not isinstance(template, str) or len(template) > 10000:
        raise ConfigurationError("reviewed template exceeds its format limit")
    for _literal, field, format_spec, conversion in string.Formatter().parse(template):
        if field is not None and (field not in fields or format_spec or conversion):
            raise ConfigurationError("templates support literal field replacement only")
    rng = random.Random(f"{seed}:{split.value}:{index}")
    record = {field: f"value-{rng.getrandbits(96):024x}" for field in fields}
    return BenchmarkCase(
        case_id=f"{split.value}-{variation}-{index}",
        variation=variation,
        template_family=f"{recipe.recipe_id}:{variation}",
        split=split,
        action=ActionRequest(
            capability=recipe.capability, input={"text": template.format_map(record)}
        ),
        validators=[
            ValidationSpec(kind=ValidationKind.EXACT_MATCH, config={"expected": {"record": record}})
        ],
    )


def recipe_features(
    recipe: RecipeDefinition, value: dict[str, Any]
) -> dict[str, str | int | bool] | None:
    if recipe.extension is not None:
        from .extensions import structural_features
        return structural_features(recipe, value)
    if recipe.generator != "record_template:1":
        return features(recipe.generator.split(":")[1], value)
    observed = features("record_template", value)
    if observed is None:
        return None
    for variation, template in recipe.generator_config["templates"].items():
        pattern = "".join(
            re.escape(literal) + (r"value-[a-f0-9]{24}" if field is not None else "")
            for literal, field, _format, _conversion in string.Formatter().parse(template)
        )
        if re.fullmatch(pattern, value["text"]):
            return {**observed, "variation": variation}
    return None


def reviewed_record_fixtures(recipe: RecipeDefinition) -> list[BenchmarkCase]:
    fixtures = recipe.generator_config.get("independent_fixtures")
    if not isinstance(fixtures, list) or not 2 <= len(fixtures) <= 100:
        raise ConfigurationError("reviewed recipes require at least two independent literal grader fixtures")
    return [BenchmarkCase(case_id=f"reviewed-literal-{index}", split=BenchmarkSplit.QUALIFICATION,
                          action=ActionRequest(capability=recipe.capability, input=item["input"]),
                          validators=[ValidationSpec(kind=ValidationKind.EXACT_MATCH, config={"expected": item["output"]})])
            for index, item in enumerate(fixtures)]


def reference_record_template(recipe: RecipeDefinition, text: str) -> dict[str, Any]:
    """Independent recognition of the reviewed record language; no generator answers."""
    for template in recipe.generator_config["templates"].values():
        seen: set[str] = set()
        pattern = ""
        for literal, field, _format, _conversion in string.Formatter().parse(template):
            pattern += re.escape(literal)
            if field is not None:
                pattern += f"(?P={field})" if field in seen else f"(?P<{field}>value-[a-f0-9]{{24}})"
                seen.add(field)
        match = re.fullmatch(pattern, text)
        if match:
            return {"record": match.groupdict()}
    return {"error": "invalid_input"}


def reference_csv(text: str, delimiter: str = ",") -> dict[str, Any]:
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        headers = next(reader)
        if not headers or len(headers) != len(set(headers)) or any(not key for key in headers):
            return {"error": "invalid_input"}
        rows = list(reader)
        if any(len(row) != len(headers) for row in rows):
            return {"error": "invalid_input"}
        return {"records": [dict(zip(headers, row, strict=True)) for row in rows]}
    except (csv.Error, StopIteration, ValueError):
        return {"error": "invalid_input"}


def reference_text(text: str, fields: list[str]) -> dict[str, Any]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        label, separator, value = line.partition(":")
        if label in fields:
            if not separator or label in result:
                return {"error": "invalid_input"}
            result[label] = value.lstrip(" ")
    return {"fields": result}


def search_files(root: str, path: str = ".") -> list[dict[str, str]]:
    """Read at most 1000 entries and 100 KB beneath the selected root."""
    base = Path(root).resolve(strict=True)
    from .identity import protected_directory
    if protected_directory(base):
        raise ConfigurationError("search roots cannot expose home or Codex state")
    target = base / path
    if Path(path).is_absolute() or ".." in Path(path).parts or target.is_symlink():
        raise ConfigurationError("search path escapes its root")
    target = target.resolve()
    if not target.is_relative_to(base):
        raise ConfigurationError("search path escapes its root")
    paths = sorted(islice(target.rglob("*"), 1001)) if target.is_dir() else [target]
    if len(paths) > 1000:
        raise ConfigurationError("search tree exceeds its entry limit")
    files = []
    remaining = 100000
    for file in paths:
        if file.is_symlink() or not file.resolve().is_relative_to(base):
            raise ConfigurationError("search tree contains an unsafe path")
        if not file.is_file():
            continue
        if file.name in {"auth.json", ".env", "credentials.json"} or protected_directory(file):
            raise ConfigurationError("search excludes authentication and credential files")
        relative = file.relative_to(base).as_posix()
        data = _read_stable_file(_safe_local_path(base, relative), remaining)
        remaining -= len(data)
        files.append({"path": relative, "text": data.decode("utf-8")})
    return files


def reference_search(root: str, query: str, path: str = ".") -> dict[str, Any]:
    try:
        files = search_files(root, path)
    except (ConfigurationError, OSError, UnicodeError, ValueError):
        return {"error": "invalid_input"}
    matches = []
    for file in files:
        for number, line in enumerate(file["text"].splitlines(), 1):
            if query in line:
                matches.append(
                    {"path": file["path"], "line": number, "text": line}
                )
    return {"matches": matches}


def shipped_recipe(family: str) -> RecipeDefinition:
    if family not in VARIATIONS:
        raise ConfigurationError("unknown recipe family; a reviewed definition is required")
    properties: dict[str, Any]
    if family == "csv":
        properties = {
            "text": {"type": "string", "maxLength": 100000},
            "delimiter": {"enum": [",", ";", "\t"]},
        }
        required = ["text", "delimiter"]
    elif family == "text":
        properties = {
            "text": {"type": "string", "maxLength": 100000},
            "fields": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 100,
                "uniqueItems": True,
            },
        }
        required = ["text", "fields"]
    else:
        properties = {
            "root": {"type": "string"},
            "query": {"type": "string", "minLength": 1},
            "path": {"type": "string"},
        }
        required = ["root", "query", "path"]
    result_name = {"csv": "records", "text": "fields", "search": "matches"}[family]
    result_schema: dict[str, Any] = {
        "csv": {"type": "array", "items": {"type": "object", "additionalProperties": {"type": "string"}}},
        "text": {"type": "object", "additionalProperties": {"type": "string"}},
        "search": {"type": "array", "items": {"type": "object", "properties": {"path": {"type": "string"}, "line": {"type": "integer", "minimum": 1}, "text": {"type": "string"}}, "required": ["path", "line", "text"], "additionalProperties": False}},
    }[family]
    return RecipeDefinition(
        recipe_id=f"{family}.v2",
        capability=f"assessment.{family}@1",
        description={
            "csv": "CSV to string-valued records with strict row widths and unique headers.",
            "text": "Extract exact labeled fields; omit absent fields and reject duplicate requested labels.",
            "search": "Find literal matches in UTF-8 files beneath an approved root, returning sorted paths and line numbers.",
        }[family],
        input_schema={
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
        output_schema={"type": "object", "oneOf": [
            {"properties": {result_name: result_schema}, "required": [result_name], "additionalProperties": False},
            {"properties": {"error": {"const": "invalid_input"}}, "required": ["error"], "additionalProperties": False},
        ]},
        generator=f"builtin:{family}:2",
        grader="exact_match:1",
        extractor=f"builtin:{family}:3",
        variations=VARIATIONS[family],
        exclusions=["Inputs outside the reviewed limits", "Unreviewed formats and encodings"],
        dependencies={"recipes.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
    )


def features(family: str, value: dict[str, Any]) -> dict[str, str | int | bool] | None:
    if family not in {*VARIATIONS, "record_template"}:
        return None
    try:
        encoded = json.dumps(value, ensure_ascii=False).encode()
        if len(encoded) > 100000:
            return None
        result: dict[str, str | int | bool] = {
            "family": family,
            "size": "small" if len(encoded) <= 4096 else "large",
        }
        if family == "record_template":
            return result if isinstance(value.get("text"), str) and set(value) == {"text"} else None
        if family == "csv":
            text = value["text"]
            delimiter = value["delimiter"]
            if not isinstance(text, str) or delimiter not in {",", ";", "\t"}:
                return None
            headers = next(csv.reader(io.StringIO(text), delimiter=delimiter, strict=True))
            if len(headers) > 100:
                return None
            count, invalid, embedded, empty = 0, len(headers) != len(set(headers)) or any(not key for key in headers), False, False
            reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
            next(reader)
            try:
                for row in reader:
                    count += 1
                    if count > 1000 or len(row) > 100:
                        return None
                    invalid |= len(row) != len(headers)
                    embedded |= any("\n" in cell or "\r" in cell for cell in row)
                    empty |= any(cell == "" for cell in row)
            except csv.Error:
                invalid = True
            result["structure"] = json.dumps([count, len(headers), invalid, "\"" in text, embedded, empty, headers == sorted(headers)])
            result.update(
                delimiter=delimiter,
                unicode=not text.isascii(),
                columns=json.dumps(sorted(headers)),
                unicode_characters="".join(
                    sorted({character for character in text if not character.isascii()})
                ),
            )
        elif family == "text":
            if not isinstance(value["text"], str) or not isinstance(value["fields"], list):
                return None
            if not all(isinstance(field, str) for field in value["fields"]):
                return None
            lines = value["text"].splitlines()
            if len(lines) > 1000 or len(value["fields"]) > 100:
                return None
            labels = [line.partition(":")[0] for line in lines]
            requested = set(value["fields"])
            selected = [label for label in labels if label in requested]
            invalid = len(selected) != len(set(selected)) or any(":" not in line and line in requested for line in lines)
            result["structure"] = json.dumps([sorted(set(selected)), invalid, len(labels), len(labels) != len(set(labels)), any(label not in requested for label in labels), labels == sorted(labels)])
            result.update(
                unicode=not value["text"].isascii(),
                fields=json.dumps(sorted(value["fields"])),
                unicode_characters="".join(
                    sorted({character for character in value["text"] if not character.isascii()})
                ),
            )
        else:
            if not all(isinstance(value[key], str) for key in ("root", "query", "path")):
                return None
            root, path = Path(value["root"]), Path(value["path"])
            if not root.is_absolute() or path.is_absolute() or ".." in path.parts:
                return None
            from .identity import protected_directory
            base = root.resolve(strict=True)
            target = base / path
            if protected_directory(base) or target.is_symlink() or not target.resolve().is_relative_to(base):
                return None
            entries = list(islice(target.rglob("*"), 1001)) if target.is_dir() else [target]
            if len(entries) > 1000:
                return None
            sizes, depths = [], []
            for entry in entries:
                if entry.is_symlink() or not entry.resolve().is_relative_to(base) or protected_directory(entry) or entry.name in {"auth.json", ".env", "credentials.json"}:
                    return None
                if entry.is_file():
                    sizes.append(entry.stat().st_size)
                    depths.append(len(entry.relative_to(base).parts))
                elif not entry.is_dir():
                    return None
            if sum(sizes) > 100000:
                return None
            result["structure"] = json.dumps([len(sizes), max(depths, default=0), max(sizes, default=0), sum(sizes)])
            result.update(root=str(root.resolve()), unicode=not value["query"].isascii())
        return result
    except (ConfigurationError, KeyError, TypeError, ValueError, OSError, StopIteration, csv.Error):
        return None


def generate_case(
    family: str, index: int, seed: int, split: BenchmarkSplit, *, fixture_root: Path | None = None
) -> tuple[BenchmarkCase, str]:
    recipe = shipped_recipe(family)
    variation = recipe.variations[index % len(recipe.variations)]
    rng = random.Random(f"{seed}:{split.value}:{index}")
    marker = f"item-{rng.getrandbits(96):024x}"
    value: dict[str, Any]
    shape = (index // len(recipe.variations)) % 4
    if family == "csv":
        delimiter = ";" if variation == "semicolon" else ","
        headers = ["id", "name", "note"]
        record = {
            "id": marker,
            "name": "東京" if variation == "unicode" else "Ada",
            "note": 'line 1\n"quoted", value'
            if variation == "quoted"
            else ""
            if variation == "empty"
            else "example",
        }
        if shape == 1:
            headers.append("extra")
            record["extra"] = "extra value"
        elif shape == 2:
            headers.remove("name")
            record.pop("name")
        if variation == "reordered":
            headers.reverse()
        stream = io.StringIO(newline="")
        writer = csv.writer(stream, delimiter=delimiter)
        writer.writerow(headers)
        records = [{**record, "id": f"{marker}-{row}"} for row in range((1, 2, 5, 12)[shape])]
        for row in records:
            writer.writerow([row[key] for key in headers])
        text = stream.getvalue()
        expected: dict[str, Any] = {"records": records}
        if variation == "malformed":
            text += '"unterminated'
            expected = {"error": "invalid_input"}
        value = {"text": text, "delimiter": delimiter}
    elif family == "text":
        record = {"id": marker, "name": "Zoë" if variation == "unicode" else "Ada"}
        if variation != "optional":
            record["note"] = "example"
        fields = ["id", "name", "note"]
        if shape == 1:
            fields.append("extra")
            record["extra"] = "extra value"
        elif shape == 2:
            fields.remove("name")
            record.pop("name")
        elif shape == 3:
            fields.append("missing")
        lines = [f"{key}: {value}" for key, value in record.items()]
        if variation == "reordered":
            lines.reverse()
        if variation == "distractor":
            lines.insert(0, "unrequested: ignore this")
        expected = {"fields": record}
        if variation in {"repeated", "invalid"}:
            lines.append("id: duplicate" if variation == "repeated" else "id")
            expected = {"error": "invalid_input"}
        value = {"text": "\n".join(lines), "fields": fields}
    else:
        if fixture_root is None:
            raise ConfigurationError("search recipes require a disposable fixture root")
        root = fixture_root / f"{split.value}-{index}"
        root.mkdir(parents=True, exist_ok=True)
        filename = ("nested/" * (shape + 1) if variation == "nested" else "") + "answer.txt"
        file = root / filename
        file.parent.mkdir(parents=True, exist_ok=True)
        line = f"東京 {marker}" if variation == "unicode" else marker
        prefix = "distractor\n" * (shape + 1)
        file.write_text(f"{prefix}{line}\n", encoding="utf-8")
        for number in range(shape):
            (root / f"other-{number}.txt").write_text("no match\n", encoding="utf-8")
        query = "absent-value" if variation == "absent" else marker
        matches = [] if variation == "absent" else [{"path": filename, "line": shape + 2, "text": line}]
        if variation == "duplicate":
            (root / "copy.txt").write_text(line, encoding="utf-8")
            matches.append({"path": "copy.txt", "line": 1, "text": line})
        expected = {
            "matches": sorted(matches, key=lambda match: (str(match["path"]), int(match["line"])))
        }
        value = {
            "root": str(root.resolve()),
            "query": query,
            "path": "../" if variation == "escape" else ".",
        }
        if variation == "escape":
            expected = {"error": "invalid_input"}
    return BenchmarkCase(
        case_id=f"{split.value}-{variation}-{index}",
        variation=variation,
        template_family=f"{recipe.recipe_id}:{variation}:shape-{shape}",
        fixture_files={item["path"]: hashlib.sha256(item["text"].encode()).hexdigest() for item in search_files(value["root"])} if family == "search" else None,
        split=split,
        action=ActionRequest(capability=recipe.capability, input=value),
        validators=[ValidationSpec(kind=ValidationKind.EXACT_MATCH, config={"expected": expected})],
    ), variation
