"""무타입 관계(PROTO_REL) — §5.8(a)(b) 의 그릇과 집계.

관계의 **타이핑**은 수요(질의 문형)가 확인된 뒤의 일이고, 지금 하는 것은
흔적 수집이다: 문장 공기 증거를 적재하고, 쌍마다 집계를 갱신한다.

    증거(rel_evidence.jsonl)  후보 생성 패스의 부산물 — 문장 좌표·연결 패턴
    집계(proto_rel.json)      쌍별 n_cooccur·n_docs·top_patterns·G²·status

승격 임계(§5.8a 초기값): proto→candidate 는
    n_cooccur ≥ 5  AND  n_docs ≥ 2  AND  G² ≥ 10.83 (p<0.001)

graph DB 는 없다 — links.json 과 같은 규약으로 파일이 정본이다. 컴파일
패스가 코퍼스에서 재생성하는 산출물이므로 var/out/terms/ 에 둔다 (질의 유래
공활성 증거(§5.8c)는 Phase 2 에서 data 쪽 append 로 합류한다).
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from lawrag.core.terms.candidates import Cooccur, HarvestResult
from lawrag.core.terms.stats import _g2_pair

# §5.8a 초기 임계 — p<0.001 의 G² 컷과 재현 요건
PROMOTE_COOCCUR = 5
PROMOTE_DOCS = 2
PROMOTE_G2 = 10.83


def write_evidence(cooccurs: list[Cooccur], out_path: Path,
                   parser_version: str = "") -> int:
    """증거 원본 적재 — 감사·재집계용. 나열(enum)은 ⑥ 형제 증거이므로
    proto-rel 집계에서 빠지지만 원본에는 남는다(분기 라우팅의 기록)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for c in cooccurs:
            f.write(json.dumps({
                "kind": c.kind, "a": c.a, "b": c.b, "pattern": c.pattern,
                "anchor": {"doc_id": c.doc_id, "block": c.block, "sent": c.sent},
                "parser_version": parser_version or None,
            }, ensure_ascii=False) + "\n")
    return len(cooccurs)


def aggregate(h: HarvestResult, keep_keys: set) -> list[dict]:
    """쌍별 PROTO_REL 집계. keep_keys(생존 후보)에 든 용어끼리만 —
    컷오프에서 떨어진 후보의 관계는 노이즈다."""
    pairs: dict[tuple, dict] = {}
    for c in h.cooccurs:
        if c.kind != "cooccur" or c.a not in keep_keys or c.b not in keep_keys:
            continue
        row = pairs.setdefault((c.a, c.b), {
            "a": c.a, "b": c.b, "n_cooccur": 0, "docs": set(), "patterns": {}})
        row["n_cooccur"] += 1
        row["docs"].add(c.doc_id)
        if c.pattern:
            row["patterns"][c.pattern] = row["patterns"].get(c.pattern, 0) + 1

    # 문장 수준 G² — "함께 나온 것이 우연 대비 얼마나 놀라운가"
    n_sents = max(h.n_sents, 1)
    sent_count: dict[str, int] = {}
    for terms in h.sent_terms.values():
        for k in terms:
            if k in keep_keys:
                sent_count[k] = sent_count.get(k, 0) + 1

    out = []
    for (a, b), row in pairs.items():
        g2 = _g2_pair(row["n_cooccur"], sent_count.get(a, 0),
                      sent_count.get(b, 0), n_sents)
        n_docs = len(row["docs"])
        # G² 는 양측 검정이다 — "서로 피해 다니는" 쌍도 유의로 나온다.
        # 관계 승격은 **양의 연관**(관측 > 기대)일 때만.
        expected = sent_count.get(a, 0) * sent_count.get(b, 0) / n_sents
        status = ("candidate"
                  if (row["n_cooccur"] >= PROMOTE_COOCCUR
                      and n_docs >= PROMOTE_DOCS and g2 >= PROMOTE_G2
                      and row["n_cooccur"] > expected)
                  else "proto")
        top = sorted(row["patterns"].items(), key=lambda kv: -kv[1])[:3]
        out.append({"a": a, "b": b, "n_cooccur": row["n_cooccur"],
                    "n_docs": n_docs, "g2": round(g2, 2),
                    "top_patterns": [{"pattern": p, "n": n} for p, n in top],
                    "type": None, "status": status})
    out.sort(key=lambda r: (-r["n_cooccur"], -r["g2"]))
    return out


def save(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"proto_rel": rows,
         "thresholds": {"n_cooccur": PROMOTE_COOCCUR, "n_docs": PROMOTE_DOCS,
                        "g2": PROMOTE_G2}},
        ensure_ascii=False, indent=2), encoding="utf-8")
