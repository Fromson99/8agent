"""결정론 게이트 — 등재의 유일한 문 (ontology_kg §3.4 마지막 단).

LLM 이 무엇을 판정했든 여기서 세 검사를 통과해야 등재된다:

    비공허성    이 용어로 실제 도달되는 청크가 존재하는가 (출현 앵커 ≥ 1)
    변별력      청크 구분에 기여하는가 — 전체 블록의 일정 비율 이상에 나오는
               어휘("규정"·"관리")는 어디에나 있어서 아무 데도 못 데려간다
    충돌        기존 케노니컬과 표면형이 모순 병합되지 않는가

등재는 glossary.json 에 status=잠정 으로 들어간다 — 활성은 사람 검수 또는
사용 실적(Phase 3 승격)이 정한다. transcribe.register 와 같은 파일·같은
충돌 규칙을 쓴다(등재의 문이 둘이면 규칙이 갈린다).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.rag.index import terms_path
from core.terms.candidates import HarvestResult
from core.terms.judge import Verdict
from core.terms.stats import Scored
from core.terms.transcribe import _load_terms, _save_terms, norm

# 변별력 컷 — 전체 블록의 이 비율 이상에 나오면 저변별 어휘다.
LIFT_MAX_BLOCK_RATIO = 0.15
# 짧은 키(≤2자)는 컷이 훨씬 엄격하다 — "상품"·"가입" 같은 2글자 일반어가
# 잠정으로 등재되면 검색 사다리의 **정확 단을 선점**해서 벡터 단까지 내려가지
# 못하게 막는다 (하이브리드 실측에서 발견). 진짜 2글자 용어(PSV·법 등)는
# 출현이 몰려 있어 이 컷을 통과한다.
LIFT_SHORT_LEN = 2
LIFT_SHORT_RATIO = 0.05
OCC_CAP = 50            # 용어당 저장할 출현 좌표 상한 (파일 비대 방지)


def _lift_cut(key: str) -> float:
    return LIFT_SHORT_RATIO if len(key) <= LIFT_SHORT_LEN else LIFT_MAX_BLOCK_RATIO


def register(h: HarvestResult, rows: list[Scored],
             groups: list[list[str]],
             verdicts: dict[int, Verdict],
             terms_file: Optional[Path] = None) -> dict:
    """게이트를 통과시켜 **표면형별 개별 용어**로 등재한다.

    결정 변경 (2026-08-10, 사용자): 군집을 케노니컬로 **병합하지 않는다** —
    추출은 추출이다. 병합(과병합의 괴물: 투자업자↔투자자 실증)은 값이 비싸고,
    별칭 검색의 몫은 이제 벡터 기본 모드가 하므로, 케노니컬은 사람 검수와
    질의 루프 증거(Phase 3 별칭 공리)가 **벌어서** 만든다.

    군집(groups)은 판정 비용 절감용 배치 단위로만 남는다 — 판정(is_term)은
    군집이 공유하되, 등재는 구성 key 마다 따로다. verdicts 가 비어 있으면
    (무 LLM) 전부 무판정 잠정 등재 — 검수 큐가 받는다.
    """
    terms_file = terms_file or terms_path()
    existing = _load_terms(terms_file)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # key → 군집 판정 (군집이 기각이면 구성원 전부 기각 — 같은 개념 후보다)
    vmap: dict[str, Verdict] = {}
    for gi, member_keys in enumerate(groups):
        v = verdicts.get(gi)
        if v is not None:
            for k in member_keys:
                vmap[k] = v

    surface_owner: dict[str, str] = {}
    for key, t in existing.items():
        for sfc in t.get("surfaces", []):
            surface_owner.setdefault(norm(sfc), key)

    n_blocks = max(h.n_blocks, 1)
    added, updated, rejected = [], [], []

    for r in rows:
        key = r.key
        v = vmap.get(key)
        if v is not None and not v.is_term:
            rejected.append({"군집": r.surface, "이유": f"판정 기각: {v.reason[:60]}"})
            continue
        mentions = h.mentions.get(key, [])

        # ── 비공허성: 도달 가능한 앵커가 있어야 용어다
        if not mentions:
            rejected.append({"군집": r.surface, "이유": "비공허성: 출현 앵커 없음"})
            continue

        # ── 변별력(lift): 어디에나 있는 어휘는 구분에 기여하지 못한다
        blocks = {(m.doc_id, m.block) for m in mentions}
        ratio = len(blocks) / n_blocks
        cut = _lift_cut(key)
        if ratio > cut:
            rejected.append({"군집": r.surface,
                             "이유": f"변별력: 블록 {ratio:.0%} 출현 (컷 {cut:.0%})"})
            continue

        # ── 충돌: 이 표면형이 이미 다른 용어의 것이면 새 용어를 만들지 않는다
        owner = surface_owner.get(key)
        if owner is not None and owner != key:
            rejected.append({"군집": r.surface,
                             "이유": f"충돌: 표면형이 기존 용어 '{owner}' 의 것"})
            continue

        row = existing.get(key)
        if row is None:
            conf = ("high" if v and v.confidence >= 0.9
                    else "medium" if v else "medium")
            row = {"term": r.surface, "key": key, "surfaces": [r.surface],
                   "note": (f"[{v.type}] {v.reason}"[:160] if v else ""),
                   "source": "통계", "status": "잠정", "confidence": conf,
                   "created": now, "hits": 0, "misses": 0, "occurrences": []}
            existing[key] = row
            surface_owner[key] = key
            added.append(r.surface)
        else:
            updated.append(r.surface)

        have = {(o.get("doc_id"), o.get("block")) for o in row["occurrences"]}
        for m in mentions:
            if len(row["occurrences"]) >= OCC_CAP:
                break
            if (m.doc_id, m.block) in have:
                continue
            have.add((m.doc_id, m.block))
            row["occurrences"].append({
                "doc_id": m.doc_id, "doc": m.doc, "node": m.node,
                "surface": m.surface, "page": m.page, "block": m.block,
                "text": m.text[:120], "via": "통계"})
        row["scope"] = {"docs": sorted({o.get("doc_id")
                                        for o in row["occurrences"]
                                        if o.get("doc_id")})}

    _save_terms(terms_file, existing)
    return {"added": added, "updated": updated, "rejected": rejected,
            "total": len(existing), "store": str(terms_file)}


def sweep(h: HarvestResult, terms_file: Optional[Path] = None) -> dict:
    """소급 적용 — 이미 등재된 **통계 유래** 용어에 현재 lift 컷을 다시 건다.

    컷이 강화되면 과거 등재분도 같은 잣대를 받아야 한다(§5.5 소급 적용의
    게이트판). 강등은 tombstone — 검수 큐에서 사람이 되살릴 수 있고,
    tombstone 은 재등재에 끈끈해서(register 가 상태를 안 건드린다) 다음
    빌드가 같은 것을 도로 살리지 않는다. 수기·tier1 은 건드리지 않는다 —
    사람이 넣었거나 저자가 선언한 것이다."""
    terms_file = terms_file or terms_path()
    existing = _load_terms(terms_file)
    n_blocks = max(h.n_blocks, 1)
    demoted = []
    for key, row in existing.items():
        if row.get("source") != "통계" or row.get("status") != "잠정":
            continue
        mentions = h.mentions.get(key, [])
        if not mentions:
            continue                        # 이번 코퍼스에 없다 — 판단 보류
        ratio = len({(m.doc_id, m.block) for m in mentions}) / n_blocks
        cut = _lift_cut(key)
        if ratio > cut:
            row["status"] = "tombstone"
            row["note"] = (f"[소급 강등] 변별력: 블록 {ratio:.0%} 출현 (컷 {cut:.0%}) — "
                           + (row.get("note") or ""))[:200]
            demoted.append(row["term"])
    if demoted:
        _save_terms(terms_file, existing)
    return {"demoted": demoted}


def coverage(h: HarvestResult, views, terms_file: Optional[Path] = None) -> dict:
    """커버리지 공백 지도 — 구역마다 앵커된 용어가 몇 개인가 (ontology_kg
    Phase 1 검증 실험). 공백 구역의 크기가 곧 탐험 루프가 감당할 몫이다."""
    terms_file = terms_file or terms_path()
    anchored: dict[tuple, set] = {}
    try:
        rows = json.loads(Path(terms_file).read_text(encoding="utf-8")).get("terms", [])
    except Exception:
        rows = []
    for t in rows:
        if t.get("status") == "tombstone":
            continue
        for o in t.get("occurrences", []):
            if o.get("node") is not None:
                anchored.setdefault((o["doc_id"], o["node"]), set()).add(t["key"])

    docs = []
    for v in views:
        per_node = [{"node": n.get("id"), "path": v.path(n.get("id")),
                     "terms": len(anchored.get((v.doc_id, n.get("id")), ()))}
                    for n in v.nodes]
        gaps = [p for p in per_node if p["terms"] == 0]
        docs.append({"doc_id": v.doc_id, "doc": v.name,
                     "nodes": len(per_node), "gaps": len(gaps),
                     "gap_nodes": gaps[:30],
                     "avg_terms": round(sum(p["terms"] for p in per_node)
                                        / max(len(per_node), 1), 2)})
    total_nodes = sum(d["nodes"] for d in docs)
    total_gaps = sum(d["gaps"] for d in docs)
    return {"docs": docs,
            "total": {"nodes": total_nodes, "gaps": total_gaps,
                      "gap_ratio": round(total_gaps / max(total_nodes, 1), 3)}}
