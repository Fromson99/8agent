"""법제처 법령지식 API 8기능의 비활성·비밀제거 데모 영수증 생성기."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import time

from lawrag.sources.common import HttpClient, make_session
from lawrag.sources.moleg_knowledge import MolegKnowledgeClient


CASES = (
    ("legal_terms", {"query": "계약"}, 2),
    ("legal_term_detail", {"trmSeqs": "5521597"}, 100),
    ("knowledge_terms", {"query": "계약"}, 2),
    ("everyday_terms", {"query": "계약"}, 2),
    ("legal_term_relations", {"MST": "48269"}, 100),
    ("everyday_term_relations", {"MST": "355021"}, 100),
    ("term_articles", {"MST": "48269"}, 100),
    ("article_terms", {"ID": "000285", "JO": "001500"}, 100),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logger = logging.getLogger("moleg-knowledge-demo")
    logger.addHandler(logging.NullHandler())
    client = MolegKnowledgeClient(
        HttpClient(make_session(), logger, min_interval=1.0), "test"
    )
    results = []
    for endpoint, parameters, display in CASES:
        started = time.monotonic()
        xml, page = client.fetch(endpoint, parameters, display=display)
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        results.append({
            "endpoint": endpoint,
            "parameters": parameters,
            "http_and_xml": "passed",
            "oc_exposed": "OC=test" in xml,
            "source_total": page.total_count,
            "normalized_count": len(page.records),
            "examples": list(page.records[:2]),
            "latency_ms": elapsed_ms,
        })
    receipt = {
        "schema_version": "moleg-knowledge-api-demo-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "credential": "public-test-credential-not-persisted-in-responses",
        "request_count": len(results),
        "llm_calls": 0,
        "passed": all(
            row["http_and_xml"] == "passed"
            and row["oc_exposed"] is False
            and row["normalized_count"] > 0
            for row in results
        ),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
