"""사람 판정의 공통 receipt 원장.

기존 승인 저장소(edge_rules.json, candidates.json, glossary.json 등)는 각 기능의
정본이다. 이 모듈은 그것들을 대체하지 않고, 승인 한 번이 무엇을 고쳤고 다음
탐색에서 어느 축을 의심해야 하는지를 append-only 사건으로 겹쳐 기록한다.

쓰기 경로의 불변식:

* receipt 기록 실패가 이미 성립한 승인을 되돌리지 않는다(`safe_record`).
* 같은 대상을 다시 판정하면 옛 행을 고치지 않고 새 행을 append한다.
* 진화 뷰는 대상별 최신 판정만 세어 반복 클릭이 증거를 부풀리지 못하게 한다.
* 이 원장은 후보와 통계만 낸다. 정본 갱신은 계속 기존 사람 승인 API의 몫이다.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from lawrag.core.rag.index import store_path


log = logging.getLogger("lawrag.core.rag.approvals")

SCHEMA_VERSION = 1

# 실패 유형별로 바꿔 볼 수 있는 닫힌 탐색 축이다. receipt는 자유로운 코드를
# 생성하지 않고 이 목록 안의 후보만 진화 컨트롤러에 건넨다.
MUTATION_TARGETS = {
    "잘못된_참조": ("operator:reference.suppression",
                   "control:context.refs_per_section_max",
                   "control:expand.ref_depth_max"),
    "얕은_착지": ("operator:reference.landing_resolution",
                 "control:context.repair_refs_max",
                 "control:context.repair_children_max"),
    "과도한_참조확장": ("operator:reference.priority",
                     "control:context.refs_per_section_max",
                     "control:expand.ref_depth_max"),
    "검색_진입오염": ("operator:entry.channel_priority",
                   "control:entry.vector_cos_min",
                   "control:entry.vector_sections_max"),
    "구조화_오류": ("operator:structure.parser", "operator:structure.fitness_gate"),
    "질문기억_누락": ("control:entry.memory_cos_min",
                   "control:entry.memory_sections_max"),
    "질문기억_오염": ("control:entry.memory_cos_min", "operator:entry.memory_scope"),
    "용어_누락": ("operator:entry.keyword_alias",
                "control:entry.keyword_sections_max"),
    "용어_오염": ("operator:entry.keyword_filter",
                "control:context.term_sections_max"),
    "답변_오류": ("operator:retrieval.rescue_gate",
                "control:recover.confidence_min",
                "control:recover.fulltext_sections_max"),
    "규칙_반례": ("operator:rules.predicate_scope", "operator:rules.promotion_gate"),
}


def receipts_path() -> Path:
    root = Path(os.environ.get("RAG_LOG_DIR", store_path().parent / "rag"))
    return Path(os.environ.get("RAG_APPROVAL_RECEIPTS", root / "approval_receipts.jsonl"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _jsonable(value):
    """Pydantic/Path 같은 값이 섞여도 원장을 막지 않는 보수적 정규화."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    return str(value)


def subject_key(kind: str, subject: dict) -> str:
    body = json.dumps([kind, _jsonable(subject)], ensure_ascii=False,
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(body.encode("utf-8")).hexdigest()[:20]


def record(*, kind: str, decision: str, effect: str, subject: dict,
           failure: str = "", before=None, after=None, note: str = "",
           actor: str = "human", qids: Optional[Iterable[str]] = None,
           source: Optional[dict] = None,
           mutation_targets: Optional[Iterable[str]] = None) -> dict:
    """정본 판정 하나를 append하고 저장한 receipt를 돌려준다."""
    normalized_subject = _jsonable(subject or {})
    ts = _now()
    rec = {
        "schema_version": SCHEMA_VERSION,
        "receipt_id": f"apr-{ts[:10].replace('-', '')}-{uuid.uuid4().hex[:12]}",
        "ts": ts,
        "kind": str(kind),
        "decision": str(decision),
        "effect": str(effect),
        "failure": str(failure),
        "subject_key": subject_key(str(kind), normalized_subject),
        "subject": normalized_subject,
        "before": _jsonable(before),
        "after": _jsonable(after),
        "note": str(note or "")[:1000],
        "actor": str(actor or "human"),
        "qids": sorted({str(q) for q in (qids or []) if q}),
        "source": _jsonable(source or {}),
        "mutation_targets": list(mutation_targets or MUTATION_TARGETS.get(failure, ())),
    }
    path = receipts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def safe_record(**kwargs) -> Optional[dict]:
    """승인이 먼저다. 부가 원장 오류는 기록하되 정본 전이를 실패시키지 않는다."""
    try:
        return record(**kwargs)
    except Exception:  # pragma: no cover - 파일시스템 장애에서도 승인 계약을 지킨다.
        log.exception("approval receipt 기록 실패 — 정본 승인은 유지")
        return None


def read(limit: Optional[int] = None) -> list[dict]:
    path = receipts_path()
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            rows.append(rec)
    return rows[-limit:] if limit is not None else rows


def current() -> list[dict]:
    """대상별 최신 판정. 재승인·판정 번복은 한 표로만 센다."""
    latest: dict[str, dict] = {}
    order: list[str] = []
    for rec in read():
        key = rec.get("subject_key") or subject_key(
            str(rec.get("kind") or ""), rec.get("subject") or {})
        if key not in latest:
            order.append(key)
        latest[key] = rec
    return [latest[key] for key in order if key in latest]


def _docs(value) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"doc_id", "src_doc", "dst_doc"} and item:
                found.add(str(item))
            else:
                found.update(_docs(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_docs(item))
    return found


def evolution_summary(min_evidence: int = 2) -> dict:
    """최신 사람 판정을 실패×효과로 묶은 읽기 전용 진화 후보표.

    여기서 `탐색후보`가 되어도 자동 변경은 없다. 외부 탐색기가 이 표를 보고
    닫힌 control 후보를 만들고, replay/holdout/shadow 뒤 기존 승인 문으로
    되돌려야 한다.
    """
    min_evidence = max(1, int(min_evidence))
    rows = current()
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for rec in rows:
        failure, effect = str(rec.get("failure") or ""), str(rec.get("effect") or "")
        # 일반 규칙이 만든 착지를 사람이 다시 고친 사건은 그 규칙의 반례이지,
        # 새 규칙/탐색기의 양성 학습 표본이 아니다. rule_hits 쪽 반증만 센다.
        if (rec.get("source") or {}).get("derived_from_rule"):
            continue
        # 보류·정상·기각은 중요한 음성 증거지만 변이 후보의 양성 근거로 세지 않는다.
        if not failure or effect in {"none", "pending", "rejected", "confirmed"}:
            continue
        groups[(failure, effect)].append(rec)

    candidates = []
    for (failure, effect), evidence in groups.items():
        qids = sorted({q for rec in evidence for q in rec.get("qids") or []})
        docs = sorted({d for rec in evidence for d in _docs(rec.get("subject"))})
        targets = sorted({target for rec in evidence
                          for target in rec.get("mutation_targets") or []})
        candidates.append({
            "failure": failure,
            "effect": effect,
            "evidence": len(evidence),
            "unique_qids": len(qids),
            "documents": len(docs),
            "qids": qids[:20],
            "doc_ids": docs[:20],
            "mutation_targets": targets,
            "last": max((rec.get("ts") or "") for rec in evidence),
            "status": "탐색후보" if len(evidence) >= min_evidence else "관측중",
            "receipt_ids": [rec.get("receipt_id") for rec in evidence[-20:]],
        })
    candidates.sort(key=lambda row: (-row["evidence"], row["failure"], row["effect"]))
    return {
        "receipts": len(read()),
        "current_subjects": len(rows),
        "by_kind": dict(Counter(str(row.get("kind") or "") for row in rows)),
        "by_decision": dict(Counter(str(row.get("decision") or "") for row in rows)),
        "min_evidence": min_evidence,
        "candidates": candidates,
    }
