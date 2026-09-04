"""Evidence-grounded, accumulating checklists for legal answer verification.

The registry contains legal audit knowledge; this module only validates,
routes, renders, and deterministically aggregates item verdicts.  It never
repairs an answer and never treats checklist text as legal authority.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

import yaml
from lawrag.platform.paths import data_path, repository_root


ROOT = repository_root()
DEFAULT_ITEMS = data_path("legal_answer_checklists", "items")
ITEM_ID_RE = re.compile(r"^LC-\d{3}$")
VERDICTS = frozenset({"PASS", "FAIL", "UNCLEAR", "NOT_APPLICABLE"})
FINAL_VERDICTS = frozenset({"ACCEPT", "REJECT", "UNCLEAR"})


class ChecklistError(ValueError):
    """The checklist registry or a verifier result is invalid."""


@dataclass(frozen=True)
class Basis:
    path: str
    anchor: str
    note: str


@dataclass(frozen=True)
class ChecklistItem:
    id: str
    name: str
    scope: str
    severity: str
    status: str
    triggers: tuple[str, ...]
    basis: tuple[Basis, ...]
    operational_definition: str
    pass_examples: tuple[str, ...]
    fail_examples: tuple[str, ...]
    unclear_examples: tuple[str, ...]
    learned_from: tuple[str, ...]

    def prompt_card(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "severity": self.severity,
            "operational_definition": self.operational_definition,
            "pass_examples": list(self.pass_examples),
            "fail_examples": list(self.fail_examples),
            "unclear_examples": list(self.unclear_examples),
        }


@dataclass(frozen=True)
class AggregatedVerdict:
    verdict: str
    item_rows: tuple[dict[str, Any], ...]
    guard_errors: tuple[str, ...]


def _strings(value: Any, field: str, path: Path) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(row, str) for row in value):
        raise ChecklistError(f"{path}: {field} must be a list of strings")
    return tuple(row.strip() for row in value if row.strip())


def _basis(value: Any, path: Path, root: Path) -> tuple[Basis, ...]:
    if not isinstance(value, list) or not value:
        raise ChecklistError(f"{path}: basis must be a non-empty list")
    result = []
    for index, row in enumerate(value, 1):
        if not isinstance(row, dict):
            raise ChecklistError(f"{path}: basis[{index}] must be an object")
        stored = str(row.get("path") or "").strip()
        anchor = str(row.get("anchor") or "").strip()
        note = str(row.get("note") or "").strip()
        if not stored or Path(stored).is_absolute() or ".." in Path(stored).parts:
            raise ChecklistError(f"{path}: invalid repository-relative basis path: {stored}")
        target = root / stored
        if not target.is_file():
            raise ChecklistError(f"{path}: basis file does not exist: {stored}")
        if anchor and anchor not in target.read_text("utf-8"):
            raise ChecklistError(f"{path}: basis anchor not found in {stored}: {anchor}")
        result.append(Basis(stored, anchor, note))
    return tuple(result)


def load_item(path: str | Path, *, root: Path = ROOT) -> ChecklistItem:
    source = Path(path)
    try:
        raw = yaml.safe_load(source.read_text("utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ChecklistError(f"{source}: cannot read YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ChecklistError(f"{source}: item must be an object")
    item_id = str(raw.get("id") or "")
    if not ITEM_ID_RE.fullmatch(item_id) or source.stem != item_id:
        raise ChecklistError(f"{source}: id and filename must match LC-NNN")
    scope = str(raw.get("scope") or "")
    severity = str(raw.get("severity") or "")
    status = str(raw.get("status") or "")
    if scope not in {"core", "routed"}:
        raise ChecklistError(f"{source}: scope must be core or routed")
    if severity not in {"blocker", "warning"}:
        raise ChecklistError(f"{source}: severity must be blocker or warning")
    if status not in {"trial", "active", "retired"}:
        raise ChecklistError(f"{source}: status must be trial, active, or retired")
    triggers = _strings(raw.get("triggers"), "triggers", source)
    if scope == "core" and triggers:
        raise ChecklistError(f"{source}: core items cannot have triggers")
    if scope == "routed" and not triggers:
        raise ChecklistError(f"{source}: routed items need triggers")
    definition = str(raw.get("operational_definition") or "").strip()
    if len(definition) < 120:
        raise ChecklistError(f"{source}: operational_definition is too thin")
    examples = raw.get("examples") or {}
    if not isinstance(examples, dict):
        raise ChecklistError(f"{source}: examples must be an object")
    item = ChecklistItem(
        id=item_id,
        name=str(raw.get("name") or "").strip(),
        scope=scope,
        severity=severity,
        status=status,
        triggers=triggers,
        basis=_basis(raw.get("basis"), source, root),
        operational_definition=definition,
        pass_examples=_strings(examples.get("pass"), "examples.pass", source),
        fail_examples=_strings(examples.get("fail"), "examples.fail", source),
        unclear_examples=_strings(examples.get("unclear"), "examples.unclear", source),
        learned_from=_strings(raw.get("learned_from"), "learned_from", source),
    )
    if not item.name:
        raise ChecklistError(f"{source}: name is empty")
    if not item.pass_examples or not item.fail_examples or not item.unclear_examples:
        raise ChecklistError(f"{source}: PASS, FAIL, and UNCLEAR examples are all required")
    if not item.learned_from:
        raise ChecklistError(f"{source}: learned_from is required")
    return item


def load_items(directory: str | Path = DEFAULT_ITEMS, *, root: Path = ROOT,
               include_retired: bool = False) -> list[ChecklistItem]:
    base = Path(directory)
    if not base.is_dir():
        raise ChecklistError(f"checklist directory does not exist: {base}")
    paths = sorted(base.glob("LC-*.yaml"))
    if not paths:
        raise ChecklistError(f"no checklist items: {base}")
    items = [load_item(path, root=root) for path in paths]
    ids = [item.id for item in items]
    if len(ids) != len(set(ids)):
        raise ChecklistError("duplicate checklist ids")
    return [item for item in items if include_retired or item.status != "retired"]


def checklist_version(directory: str | Path = DEFAULT_ITEMS) -> str:
    base = Path(directory)
    digest = hashlib.sha256()
    count = 0
    for path in sorted(base.glob("LC-*.yaml")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
        count += 1
    return f"legal-answer-items{count}-{digest.hexdigest()[:12]}"


def route_items(question: str, evidence: Iterable[dict[str, Any]],
                items: Iterable[ChecklistItem]) -> list[ChecklistItem]:
    evidence_text = " ".join(
        " ".join(str(row.get(key) or "") for key in
                 ("document", "path", "role", "original_text"))
        for row in evidence
    )
    haystack = f"{question} {evidence_text}".casefold()
    routed = []
    for item in items:
        if item.scope == "core" or any(trigger.casefold() in haystack
                                        for trigger in item.triggers):
            routed.append(item)
    return sorted(routed, key=lambda item: item.id)


def render_cards(items: Iterable[ChecklistItem]) -> str:
    return json.dumps([item.prompt_card() for item in items],
                      ensure_ascii=False, indent=2)


def verifier_schema(item_ids: Iterable[str]) -> dict[str, Any]:
    ids = list(item_ids)
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "enum": ids},
                        "verdict": {"type": "string", "enum": sorted(VERDICTS)},
                        "answer_quote": {"type": "string"},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                        "reason": {"type": "string"},
                    },
                    "required": ["id", "verdict", "answer_quote", "evidence_ids", "reason"],
                    "additionalProperties": False,
                },
            },
            "recommended_verdict": {"type": "string", "enum": sorted(FINAL_VERDICTS)},
            "summary": {"type": "string"},
        },
        "required": ["items", "recommended_verdict", "summary"],
        "additionalProperties": False,
    }


def aggregate_verdict(items: Iterable[ChecklistItem], raw: dict[str, Any] | None,
                      *, answer: str, evidence_ids: Iterable[str]) -> AggregatedVerdict:
    required = {item.id: item for item in items}
    valid_evidence = set(evidence_ids)
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    if not isinstance(raw, dict):
        return AggregatedVerdict("UNCLEAR", (), ("verifier_output_missing",))
    seen: set[str] = set()
    raw_rows = raw.get("items")
    if not isinstance(raw_rows, list):
        return AggregatedVerdict("UNCLEAR", (), ("item_rows_missing",))
    for index, value in enumerate(raw_rows):
        if not isinstance(value, dict):
            errors.append(f"item_{index}_not_object")
            continue
        item_id = str(value.get("id") or "")
        verdict = str(value.get("verdict") or "")
        quote = str(value.get("answer_quote") or "").strip()
        cited = [str(eid) for eid in value.get("evidence_ids") or []]
        if item_id not in required:
            errors.append(f"unknown_item:{item_id}")
            continue
        if item_id in seen:
            errors.append(f"duplicate_item:{item_id}")
            continue
        seen.add(item_id)
        if verdict not in VERDICTS:
            errors.append(f"invalid_verdict:{item_id}")
            verdict = "UNCLEAR"
        if quote and quote not in answer:
            errors.append(f"answer_quote_not_found:{item_id}")
            verdict = "UNCLEAR"
        if any(eid not in valid_evidence for eid in cited):
            errors.append(f"invalid_evidence_id:{item_id}")
            verdict = "UNCLEAR"
            cited = [eid for eid in cited if eid in valid_evidence]
        rows.append({**value, "id": item_id, "verdict": verdict,
                     "evidence_ids": list(dict.fromkeys(cited))})
    missing = sorted(set(required) - seen)
    errors.extend(f"missing_item:{item_id}" for item_id in missing)
    if errors:
        return AggregatedVerdict("UNCLEAR", tuple(rows), tuple(errors))
    by_id = {row["id"]: row for row in rows}
    blockers = [(item, by_id[item.id]["verdict"]) for item in required.values()
                if item.severity == "blocker"]
    if any(verdict == "FAIL" for _, verdict in blockers):
        final = "REJECT"
    elif any(verdict == "UNCLEAR" for _, verdict in blockers):
        final = "UNCLEAR"
    else:
        final = "ACCEPT"
    return AggregatedVerdict(final, tuple(rows), ())
