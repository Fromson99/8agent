#!/usr/bin/env python3
"""현행성 감사가 찾은 신설 조문만 Frame 재추출 대상으로 연다.

이 단계는 canonical을 자동 승인하지 않는다. 결과는 ``data/frames`` 파생층에 쓰며,
이후 graph build → stage-frame-concepts → 승인 → stage-frame-knowledge 순서로 올린다.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lawrag.core.domain_graph.freshness import audit  # noqa: E402
from lawrag.core.domain_graph.tier1 import Tier1Registry  # noqa: E402
from lawrag.core.rag import frames, index as index_mod  # noqa: E402
from lawrag.core.rag import conceptfirst  # noqa: E402
from scripts import review_golden as review  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--document", action="append", default=[])
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    index = index_mod.current()
    registry = Tier1Registry.load(conceptfirst.registry_path())
    report = audit(index, registry, detail_limit=max(0, args.limit))
    wanted_documents = set(args.document)
    targets = [row for row in report["refresh_targets"]
               if not wanted_documents or row["document"] in wanted_documents]
    grouped: dict[str, set[object]] = defaultdict(set)
    for row in targets:
        grouped[row["doc_id"]].add(row["node"])

    result = {"audit": {key: value for key, value in report.items()
                        if key not in {"refresh_targets", "missing_sample"}},
              "targets": targets, "extractions": [], "dry_run": args.dry_run}
    if args.dry_run:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    if review._llm() is None:
        raise SystemExit("LLM 설정이 없습니다")
    for doc_id, nodes in grouped.items():
        view = index.docs[doc_id]
        extracted = frames.extract_doc(
            view, review._llm, workers=max(1, args.workers),
            only_missing=not args.force, article_ids=nodes)
        result["extractions"].append({"doc_id": doc_id, **extracted})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
