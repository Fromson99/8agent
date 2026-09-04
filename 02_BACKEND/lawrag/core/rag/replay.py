"""후보 규칙의 replay 검증 — 승격의 결정적 근거.

튜플이 프롬프트 원본과 좌표까지 남기는 덕에, 후보 규칙을 켜고 과거를 다시
돌릴 수 있다. 세 가지를 센다:

    재현    근거가 된 승인 사례(redirect 행)들을 규칙이 재현하는가 —
            홀드아웃(LLM 에게 안 보여준 사례) 포함 전부.
    소실    사례의 문서·마디가 사라져 검사 불능 — 실패가 아니라 표본 제외.
    충돌    현재 색인의 **모든** 간선에 규칙을 돌려서,
              억제재생  옮긴 착지가 사람이 억제한 간선을 되살린다
              사례상충  사람이 그 간선에 직접 확정한 재지정과 다른 곳으로 보낸다
              정답피드백 정답 피드백이 확인한 착지를 흔든다

green(재현 전부 + 충돌 0)일 때만 induce 가 잠정 등재한다. 여기엔 LLM 이 없다.
"""

from __future__ import annotations

import json
from typing import Optional

from lawrag.core.rag import rules as rules_mod
from lawrag.core.rag import verdicts as verdicts_mod


def _redirect_rows() -> list[dict]:
    p = verdicts_mod.rules_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("redirect", [])
    except Exception:
        return []


def instance_key(row: dict) -> str:
    return (f"{row.get('src_doc')}:{row.get('src')}"
            f"→{row.get('dst_doc')}:{row.get('dst')}⤷{row.get('new_dst')}")


def _confirmed_landings() -> set:
    """정답 피드백이 확인한 좌표 — 그 튜플이 실제로 인용한 refs 의 (doc, node).
    규칙이 이 좌표로 오는 간선을 옮기면 사람이 옳다고 한 것을 흔드는 것이다."""
    try:
        from lawrag.core.rag import tuples as tuples_mod
        rows = tuples_mod.read(limit=10_000)
    except Exception:
        return set()
    out = set()
    for row in rows:
        fb = row.get("피드백") or {}
        if fb.get("판정") != "정답":
            continue
        for r in row.get("refs") or []:
            if r.get("doc_id") is not None and r.get("node") is not None:
                out.add((r["doc_id"], r["node"]))
    return out


def verify(rule: dict, index, instances: Optional[list[dict]] = None) -> dict:
    """후보 규칙 하나의 성적표. instances 를 안 주면 rule.evidence.instances
    의 키로 edge_rules.json redirect 행을 찾는다."""
    if instances is None:
        want = set((rule.get("evidence") or {}).get("instances") or [])
        instances = [r for r in _redirect_rows() if instance_key(r) in want]

    reproduced, lost, missed = 0, 0, []
    for row in instances:
        view = index.docs.get(row.get("dst_doc"))
        if (row.get("src_doc") not in index.docs or view is None
                or view.by_id.get(row.get("dst")) is None):
            lost += 1
            continue
        edge = {k: row.get(k) for k in
                ("src_doc", "src", "dst_doc", "dst", "surface")}
        hit = rules_mod.evaluate(index, edge, only=rule)
        if hit is not None and hit[1] == row.get("new_dst"):
            reproduced += 1
        else:
            missed.append(instance_key(row))

    conflicts: list[dict] = []
    confirmed = _confirmed_landings()
    edges, _ = index.cross_refs()
    for e in edges:
        hit = rules_mod.evaluate(index, e, only=rule)
        if hit is None:
            continue
        new_dst = hit[1]
        coord = (e["src_doc"], e["src"], e.get("dst_doc"), e["dst"])
        if verdicts_mod.is_suppressed(e["src_doc"], e["src"],
                                      e.get("dst_doc", ""), new_dst):
            conflicts.append({"종류": "억제재생", "간선": coord, "이동": new_dst})
        if (e.get("dst_doc"), e["dst"]) in confirmed:
            conflicts.append({"종류": "정답피드백", "간선": coord, "이동": new_dst})
    # 사례상충 — 사람이 그 간선에 직접 확정한 재지정과 규칙이 다른 곳을
    # 가리키는가. 런타임에서는 인스턴스가 먼저 적용돼 규칙이 원간선을 못
    # 보지만(우선순위), 후보 검증은 역사 전체와의 모순을 세야 한다 — 그래서
    # 규칙 사전(redirect_map)의 **원좌표**를 직접 평가한다.
    for coord, inst in verdicts_mod.redirect_map().items():
        row = {"src_doc": coord[0], "src": coord[1],
               "dst_doc": coord[2], "dst": coord[3],
               "surface": inst.get("surface", "")}
        hit = rules_mod.evaluate(index, row, only=rule)
        if hit is not None and hit[1] != inst.get("new_dst"):
            conflicts.append({"종류": "사례상충", "간선": coord,
                              "이동": hit[1], "사례": inst.get("new_dst")})

    checked = len(instances) - lost
    return {"total": len(instances), "reproduced": reproduced, "소실": lost,
            "미재현": missed, "충돌": conflicts,
            "green": checked >= 1 and reproduced == checked and not conflicts}
