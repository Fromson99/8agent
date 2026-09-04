"""법률 질문의 지배조문 후보를 범위·쟁점문언·참조관계로 나눠 선정한다.

단일 유사도 1등을 지배규범으로 확정하지 않는다. 법령/시장 범위, 실제 질문
문언을 담은 조항, 명시적 법률 참조는 서로 다른 법적 기능이므로 세 채널의 닫힌
후보 패널로 보존한다. 운영 배선 전 shadow 실험용이다.
"""

from __future__ import annotations

import re
from typing import Any

from lawrag.core.rag.experiments.typed_evidence_connections import _title_alignment


_ARTICLE = re.compile(r"제\s*\d+(?:\s*-\s*\d+)?\s*조(?:의\s*\d+)?")
_WORD = re.compile(r"[가-힣A-Za-z0-9]+")
_STOP = frozenset({
    "업무", "문맥", "관련", "어떻게", "무엇", "어떤", "하는가", "되는가",
    "있는가", "경우", "기준", "규정", "요구", "근거", "해당", "여부",
})
_PARTICLES = (
    "으로부터", "에서부터", "에게서", "으로써", "으로서", "이라면", "라면",
    "에서는", "에게", "께서", "에서", "부터", "까지", "보다", "처럼", "으로",
    "로서", "로써", "와의", "과의", "에는", "에도", "의", "은", "는", "이",
    "가", "을", "를", "에", "와", "과", "도", "만",
)
_QUESTION_ENDINGS = ("하는가", "되는가", "있는가", "없는가", "인가")
_ORIGIN_SCORE = {
    "exact-structural": 8.0,
    "assertion-tree": 6.0,
    "normative-reference-verifier": 4.0,
    "keyword-bm25": 0.0,
    "supplemental-closure": -6.0,
}
_BRIDGE_SCORE = {
    "direct_typed_companion": 30.0,
    "direct_untyped_reference": 24.0,
    "indirect_reference_context": 12.0,
    "seed_governing_candidate": 8.0,
    "question_explicit_target": 30.0,
    "selected_pair_typed_context": 22.0,
    "selected_pair_reference_context": 14.0,
    "supplemental_context": -10.0,
    "parallel_search_context": 0.0,
}


def _packed(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(value or "")).casefold()


def _article_mentions(value: str) -> set[str]:
    return {_packed(match.group(0)) for match in _ARTICLE.finditer(str(value or ""))}


def issue_terms(question: str) -> set[str]:
    """업무 문맥 앞의 실제 질문에서 조사와 상투어를 제거한다."""
    main = str(question or "").split("(업무 문맥:", 1)[0]
    out = set()
    for raw in _WORD.findall(main):
        token = raw.casefold()
        for ending in _QUESTION_ENDINGS:
            if len(token) > len(ending) + 1 and token.endswith(ending):
                token = token[:-len(ending)]
                break
        for particle in _PARTICLES:
            if len(token) > len(particle) + 1 and token.endswith(particle):
                token = token[:-len(particle)]
                break
        if len(token) >= 2 and token not in _STOP and not _ARTICLE.fullmatch(token):
            out.add(token)
    return out


def _market_scope_score(question: str, document: str) -> tuple[float, list[str]]:
    question_packed = _packed(question)
    document_packed = _packed(document)
    score = 0.0
    reasons = []
    if "코스닥" in question_packed:
        if "코스닥" in document_packed:
            score += 20
            reasons.append("kosdaq_scope_match")
        elif "유가증권시장" in document_packed:
            score -= 25
            reasons.append("kosdaq_scope_conflict")
    if "유가증권시장" in question_packed or "코스피" in question_packed:
        if "유가증권시장" in document_packed:
            score += 20
            reasons.append("kospi_scope_match")
        elif "코스닥" in document_packed:
            score -= 25
            reasons.append("kospi_scope_conflict")
    return score, reasons


def anchor_scores(question: str, row: dict[str, Any], position: int) \
        -> dict[str, Any]:
    document = str(row.get("document") or "")
    path = str(row.get("path") or "")
    tail = path.split("▸")[-1]
    origin = str(row.get("role") or "")
    connection = dict(row.get("typed_connection") or {})
    question_packed = _packed(question)
    document_packed = _packed(document)
    reasons = []

    scope = 0.0
    if _article_mentions(question) & _article_mentions(path):
        scope += 40
        reasons.append("explicit_article_match")
    if document_packed and document_packed in question_packed:
        scope += 30
        reasons.append("explicit_document_match")
    market_score, market_reasons = _market_scope_score(question, document)
    scope += market_score
    reasons.extend(market_reasons)
    alignment = _title_alignment(question, path)
    scope += 20 * alignment
    if _ARTICLE.search(tail):
        scope += 6
    else:
        scope -= 8
        reasons.append("container_not_article")
    scope += _ORIGIN_SCORE.get(origin, 0.0)
    scope += max(0.0, 3.0 - position * 0.1)

    text_packed = _packed(str(row.get("original_text") or ""))
    hits = sorted(term for term in issue_terms(question) if _packed(term) in text_packed)
    issue = 20 * alignment + min(36, 12 * len(hits))
    issue += _ORIGIN_SCORE.get(origin, 0.0)
    issue += 6 if _ARTICLE.search(tail) else -8
    if hits:
        reasons.append("issue_terms:" + ",".join(hits))

    role = str(connection.get("connection_role") or "parallel_search_context")
    bridge = _BRIDGE_SCORE.get(role, 0.0) + _ORIGIN_SCORE.get(origin, 0.0)
    if connection.get("evidence_tier") == "C_context_only":
        bridge -= 3
    if connection.get("direct_relations"):
        reasons.append("typed_relations:" + ",".join(
            str(value) for value in connection.get("direct_relations") or []))

    return {
        "scope_score": round(scope, 4),
        "issue_score": round(issue, 4),
        "bridge_score": round(bridge, 4),
        "title_alignment": round(alignment, 4),
        "issue_terms": hits,
        "reasons": reasons,
    }


def governing_anchor_panel(question: str, evidence: list[dict[str, Any]], *,
                           max_candidates: int = 8) -> list[dict[str, Any]]:
    """세 채널을 round-robin하여 최대 ``max_candidates`` 후보를 반환한다."""
    scored = []
    for position, row in enumerate(evidence):
        scored.append({
            "evidence_id": str(row.get("id") or f"E{position + 1}"),
            "original_position": position + 1,
            **anchor_scores(question, row, position),
        })
    channels = {
        "scope": sorted(scored, key=lambda row: (
            -row["scope_score"], row["original_position"])),
        "issue": sorted(scored, key=lambda row: (
            -row["issue_score"], row["original_position"])),
        "bridge": sorted(scored, key=lambda row: (
            -row["bridge_score"], row["original_position"])),
    }
    cursors = {name: 0 for name in channels}
    selected: dict[str, dict[str, Any]] = {}
    order = ("scope", "issue", "bridge")
    while len(selected) < min(max_candidates, len(scored)):
        progressed = False
        for name in order:
            rows = channels[name]
            while cursors[name] < len(rows):
                candidate = rows[cursors[name]]
                cursors[name] += 1
                if candidate["evidence_id"] in selected:
                    continue
                selected[candidate["evidence_id"]] = {
                    **candidate, "selected_by": [name],
                }
                progressed = True
                break
            if len(selected) >= min(max_candidates, len(scored)):
                break
        if not progressed:
            break
    # 다른 채널에서도 상위권인 이유를 감사 artifact에 남긴다.
    top_ids = {name: {row["evidence_id"] for row in rows[:max_candidates]}
               for name, rows in channels.items()}
    for evidence_id, row in selected.items():
        row["selected_by"] = [name for name in order if evidence_id in top_ids[name]]
    return list(selected.values())
