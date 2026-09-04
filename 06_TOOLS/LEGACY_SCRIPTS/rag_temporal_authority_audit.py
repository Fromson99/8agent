#!/usr/bin/env python3
"""51문항과 현재 코퍼스의 시점·법원성 검증 가능 범위를 계측한다."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))
os.environ.setdefault("STRUCTURE_STORE", "01_DATA/structure")
os.environ.setdefault("GLOSSARY_STORE", "01_DATA/glossary.json")

from lawrag.core.rag import index as index_mod  # noqa: E402
from lawrag.core.rag.legal_validity import (  # noqa: E402
    authority,
    parse_as_of,
    validate_document,
)


def _has(value) -> bool:
    return bool(str(value or "").strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    cases = list(suite.get("cases") or suite.get("rows") or [])[:51]
    index = index_mod.current().scoped(None)

    authority_counts = Counter()
    metadata = Counter()
    series = defaultdict(list)
    for view in index.docs.values():
        authority_counts[authority(view)[0]] += 1
        for field in ("enforce", "revised", "status", "series", "version"):
            metadata[field] += _has(getattr(view, field, ""))
        if view.series:
            series[view.series].append(view.doc_id)
    explicit = []
    latencies = []
    statuses = Counter()
    for case in cases:
        question = str(case.get("question") or "")
        as_of = parse_as_of(question)
        started = time.perf_counter()
        if as_of:
            findings = [validate_document(view, as_of) for view in index.docs.values()]
            statuses.update(row.temporal_status for row in findings)
            explicit.append({"case_no": case.get("case_no"), "as_of": as_of.isoformat(),
                             "status_counts": dict(Counter(
                                 row.temporal_status for row in findings))})
        latencies.append((time.perf_counter() - started) * 1000)

    result = {
        "experiment": "temporal-authority-metadata-audit-v1",
        "contract": {
            "purpose": "evidence warning/gating, not automatic conflict resolution",
            "full_date_only": True,
            "historical_text_policy": "do not silently reuse current text",
        },
        "corpus": {
            "documents": len(index.docs),
            "authority_classes": dict(sorted(authority_counts.items())),
            "metadata_coverage": {
                key: {"count": metadata[key],
                      "rate": round(metadata[key] / len(index.docs), 4) if index.docs else 0}
                for key in ("enforce", "revised", "status", "series", "version")
            },
            "multi_version_series": sum(len(ids) > 1 for ids in series.values()),
            "series_count": len(series),
        },
        "suite": {
            "cases": len(cases),
            "explicit_full_date_cases": len(explicit),
            "rows": explicit,
            "all_document_statuses_for_explicit_dates": dict(statuses),
        },
        "latency_ms": {
            "median": round(statistics.median(latencies), 4) if latencies else 0,
            "max": round(max(latencies), 4) if latencies else 0,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
