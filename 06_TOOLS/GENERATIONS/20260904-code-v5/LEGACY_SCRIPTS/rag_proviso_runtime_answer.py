#!/usr/bin/env python3
"""One frozen Haiku product-role probe for ADR-0149 CM-003."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time


ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
sys.path.insert(0, str(ROOT / "02_BACKEND"))

from lawrag.core import llm as llm_mod  # noqa: E402
from lawrag.core.rag.index import Index  # noqa: E402


MODEL = "claude-haiku-4-5-20251001"
SYSTEM = """당신은 법률 RAG의 단서 실행기다. 제공된 원문만 사용한다.

반드시 다음 순서로 판단한다.
1. 질문 사실과 직접 맞는 본문 호를 고른다.
2. 그 호의 단서를 독립적으로 읽고, 연결된 시행세칙의 정확한 항·호를 찾아 단서 적용 여부를 판단한다.
3. 단서가 본문 호를 제외하면 거기서 최종 보유기간을 만들지 말고, 같은 부모 조문의 다른 독립 호 중 질문 사실과 맞을 가능성이 있는 호를 후보로 다시 검토한다.
4. 후보 호의 결합요건을 각각 독립 slot으로 쪼갠다. 각 slot은 true/false/unknown 중 하나다.
5. exact 원문 근거 또는 명시적 정의·의제·대체 관계가 없으면 서로 다른 요건을 동일시하지 않는다. 특히 '제3자 배정'만으로 '모집이나 매출이 아닌 방법'을 true로 만들지 말고, '재무적투자자'만으로 법문상 '벤처금융 또는 전문투자자'를 true로 만들지 않는다.
6. 모든 결합요건이 true가 아니면 단정적 기간 대신 조건부 결론과 추가 확인사항을 쓴다.

좌표, 적용한 단서 문면, 독립 slot과 evidence를 구조화해 반환한다."""

SCHEMA = {
    "type": "object",
    "properties": {
        "initial_rule_coordinate": {"type": "string"},
        "initial_rule_reason": {"type": "string"},
        "proviso_coordinate": {"type": "string"},
        "proviso_match": {"type": "string", "enum": ["true", "false", "unknown"]},
        "proviso_reason": {"type": "string"},
        "next_rule_coordinate": {"type": "string"},
        "slots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "slot": {"type": "string"},
                    "value": {"type": "string", "enum": ["true", "false", "unknown"]},
                    "evidence": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["slot", "value", "evidence", "reason"],
                "additionalProperties": False,
            },
        },
        "answer": {"type": "string"},
        "additional_checks": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "initial_rule_coordinate", "initial_rule_reason", "proviso_coordinate",
        "proviso_match", "proviso_reason", "next_rule_coordinate", "slots",
        "answer", "additional_checks",
    ],
    "additionalProperties": False,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-lock", type=Path, required=True)
    parser.add_argument("--relation-run", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    lock = json.loads(args.input_lock.read_text("utf-8"))
    run = json.loads(args.relation_run.read_text("utf-8"))
    index = Index.load(ROOT / "01_DATA/structure", ROOT / "01_DATA/glossary.json",
                       ROOT / "01_DATA/links.json")
    source_doc, source_node = lock["known_case"]["source_article"]
    detail_doc, detail_node = lock["known_case"]["direct_detail_article"]
    source_view, detail_view = index.docs[source_doc], index.docs[detail_doc]
    source_text = source_view.section_outline(source_view.by_id[source_node], cap=16000)
    detail_text = detail_view.section_outline(detail_view.by_id[detail_node], cap=16000)
    relationship = {
        "source": [source_doc, source_node],
        "target": [detail_doc, detail_node],
        "kind": "FOLLOW_RECEPTION",
        "plane": "SEARCH_ROUTING",
        "legal_effect_inferred": False,
        "direct_detail_routed": run["cm003"]["direct_detail_routed"],
    }
    user = "\n\n".join((
        "[질문]\n" + lock["known_case"]["question"],
        "[관계 메타데이터]\n" + json.dumps(relationship, ensure_ascii=False),
        "[원문 A: 코스닥시장 상장규정]\n" + source_text,
        "[원문 B: 코스닥시장 상장규정 시행세칙 — 연결 대상 조문 전체]\n" + detail_text,
    ))
    started = time.perf_counter()
    client = llm_mod.LLM(model=MODEL)
    output = client.structured(
        "adr0149.proviso_package_answer", SYSTEM, user, SCHEMA,
        max_tokens=5000, model=MODEL)
    exchange = client.log[-1].dump()
    result = {
        "schema_version": "proviso-runtime-answer-v1",
        "adr_id": "ADR-0149", "experiment_id": "ADR-0149-experiment-v1",
        "run_id": "run-003", "role": "proviso_package_answer",
        "class": "product", "model": MODEL,
        "input_lock_sha256": sha256(args.input_lock),
        "relation_run_sha256": sha256(args.relation_run),
        "relationship": relationship, "output": output,
        "receipt": exchange,
        "usage": exchange.get("usage") or {},
        "latency_ms": exchange.get("dur_ms") or round(
            (time.perf_counter() - started) * 1000, 3),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
