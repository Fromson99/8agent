"""격리 실험 모듈과 저장된 평가 산출물의 읽기 전용 카탈로그.

``var/eval/e2e``에는 공통 manifest, 구형 실험 결과, raw와 비교표가 함께 있다. 모두를
하나의 스키마로 억지 변환하면 과거 증거가 사라지므로 원형은 보존하고 화면에 필요한
공통 표지만 파생한다. 행 전체는 목록 응답에 싣지 않는다.
"""

from __future__ import annotations

import importlib.util
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from lawrag.core.rag import experiments
from lawrag.platform.paths import repository_root
from lawrag.platform.stored_paths import resolve_stored_path


ROOT = repository_root()
# These files are immutable pre-v2 experiment evidence.  Follow the migration
# receipt instead of treating them as new runtime output.
EVAL_ROOT = resolve_stored_path(ROOT, "var/eval/e2e")


def _kind(path: Path) -> str:
    name = path.name
    if name.endswith(".manifest.json"):
        return "manifest"
    if name.endswith(".raw.json"):
        return "raw"
    if name.endswith(".compare.json"):
        return "comparison"
    if "ablation" in name:
        return "ablation"
    if "portfolio" in name:
        return "portfolio"
    return "result"


def _scalar_summary(value: Any, prefix: str = "", depth: int = 0) -> list[dict]:
    """서로 다른 세대의 summary에서 화면용 숫자·판정만 보수적으로 뽑는다."""
    if depth > 2:
        return []
    rows: list[dict] = []
    if isinstance(value, dict):
        for key, item in value.items():
            label = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, (str, int, float, bool)) or item is None:
                if len(str(item)) <= 100:
                    rows.append({"key": label, "value": item})
            elif isinstance(item, dict):
                rows.extend(_scalar_summary(item, label, depth + 1))
    return rows


_PRIORITY = (
    "cases", "completed", "gold", "passed", "pass_rate", "semantic_accuracy",
    "selected_hits", "selected_recall", "candidate_recall", "article_recall",
    "basis_recall", "calls", "input_tokens", "duration_ms", "wall_ms_p50",
    "wall_ms_p95", "regression", "decision", "release_ready",
)


def _metrics(summary: Any) -> list[dict]:
    rows = _scalar_summary(summary)
    priority = {key: pos for pos, key in enumerate(_PRIORITY)}
    rows.sort(key=lambda row: (
        min((priority[key] for key in priority
             if row["key"] == key or row["key"].endswith(f".{key}")), default=999),
        row["key"],
    ))
    return rows[:18]


def _module_key(text: str) -> str:
    lowered = text.lower()
    for spec in experiments.specs():
        if any(pattern.lower() in lowered for pattern in spec["artifact_patterns"]):
            return spec["key"]
    return ""


def _mapping(value: Any) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _read_stub(path: Path) -> dict:
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "path": str(path.relative_to(ROOT)), "name": path.name,
            "kind": _kind(path), "error": f"{type(exc).__name__}: {exc}",
            "size": path.stat().st_size, "updated_at": path.stat().st_mtime,
        }
    experiment = str(blob.get("experiment") or "")
    run = _mapping(blob.get("run"))
    suite = _mapping(blob.get("suite"))
    label = experiment or str(run.get("label") or blob.get("name") or path.stem)
    summary = blob.get("summary") or {}
    rows = blob.get("rows")
    if rows is None:
        rows = blob.get("results")
    return {
        "path": str(path.relative_to(ROOT)), "name": path.name,
        "kind": _kind(path), "experiment": label,
        "module_key": _module_key(f"{path.name} {experiment}"),
        "created_at": str(blob.get("created_at") or ""),
        "updated_at": path.stat().st_mtime, "size": path.stat().st_size,
        "case_count": len(rows) if isinstance(rows, list) else int(
            suite.get("case_count") or (summary.get("cases") if isinstance(summary, dict) else 0) or 0),
        "run": run, "suite": {
            key: suite.get(key) for key in
            ("name", "version", "role", "case_count", "sha256") if key in suite
        },
        "variant": _mapping(blob.get("variant")),
        "metrics": _metrics(summary),
    }


def _signature() -> tuple:
    paths = sorted(EVAL_ROOT.glob("*.json")) if EVAL_ROOT.is_dir() else []
    return tuple((path.name, path.stat().st_mtime_ns, path.stat().st_size)
                 for path in paths)


@lru_cache(maxsize=2)
def _catalog_cached(signature: tuple) -> dict:
    artifacts = [_read_stub(EVAL_ROOT / name) for name, _, _ in signature]
    registered = {row["key"]: row for row in experiments.specs()}
    module_dir = Path(experiments.__file__).parent
    modules = []
    for path in sorted(module_dir.glob("*.py")):
        if path.name == "__init__.py":
            continue
        key = path.stem
        spec = dict(registered.get(key) or {
            "key": key, "title": key, "status": "미등재", "decision": "확인 필요",
            "purpose": "레지스트리에 설명이 없는 격리 실험 모듈",
            "module": f"lawrag.core.rag.experiments.{key}", "runner": "",
            "document": "", "artifact_patterns": [],
        })
        spec["importable"] = importlib.util.find_spec(spec["module"]) is not None
        spec["artifact_count"] = sum(row.get("module_key") == key for row in artifacts)
        modules.append(spec)
    groups: dict[str, dict] = {}
    for artifact in artifacts:
        key = artifact.get("experiment") or artifact["name"]
        group = groups.setdefault(key, {
            "key": key, "artifacts": 0, "latest": 0.0,
            "kinds": {}, "module_key": artifact.get("module_key") or "",
        })
        group["artifacts"] += 1
        group["latest"] = max(group["latest"], float(artifact.get("updated_at") or 0))
        kind = artifact.get("kind") or "result"
        group["kinds"][kind] = group["kinds"].get(kind, 0) + 1
        if not group["module_key"] and artifact.get("module_key"):
            group["module_key"] = artifact["module_key"]
    return {
        "modules": modules, "module_count": len(modules),
        "experiments": sorted(groups.values(), key=lambda row: (-row["latest"], row["key"])),
        "experiment_count": len(groups),
        "artifacts": sorted(artifacts, key=lambda row: (-row["updated_at"], row["name"])),
        "artifact_count": len(artifacts), "root": str(EVAL_ROOT),
    }


def catalog() -> dict:
    return _catalog_cached(_signature())


def _compact(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "…"
    if isinstance(value, dict):
        return {str(key): _compact(item, depth + 1)
                for key, item in list(value.items())[:60]}
    if isinstance(value, list):
        return [_compact(item, depth + 1) for item in value[:20]]
    if isinstance(value, str):
        return value[:1500]
    return value


def detail(relative_path: str) -> dict:
    path = (ROOT / relative_path).resolve()
    root = EVAL_ROOT.resolve()
    if path.parent != root or path.suffix != ".json" or not path.is_file():
        raise FileNotFoundError(relative_path)
    blob = json.loads(path.read_text(encoding="utf-8"))
    rows = blob.get("rows")
    if rows is None:
        rows = blob.get("results")
    return {
        "artifact": _read_stub(path),
        "configuration": _compact({
            key: blob.get(key) for key in
            ("experiment", "source", "model", "cap", "baseline", "contract",
             "run", "suite", "variant", "controls", "engine") if key in blob
        }),
        "summary": _compact(blob.get("summary") or {}),
        "rows_preview": _compact(rows[:12] if isinstance(rows, list) else []),
    }
