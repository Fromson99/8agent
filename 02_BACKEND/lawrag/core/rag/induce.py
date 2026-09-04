"""귀납 — 승인 사례(edge_rules.json redirect 행)를 일반 규칙 후보로.

    python -m lawrag.core.rag.induce [--no-llm] [--dry-run]

흐름(RULE_LOOP.md §4): 군집화(결정적) → 일반화 → replay 검증 → 잠정 등재
→ (RAG_RULES_AUTOPROMOTE=on 이면) 잠정→규칙 자동 승격.

일반화는 두 갈래다:
  기계  특징 서명이 이미 술어 어휘와 1:1 인 군집 — 사슬하강처럼 특징화가
        곧 규칙인 모양. LLM 없이 조립한다.
  LLM   서명이 안 잡힌 잔여 사례 — 닫힌 술어 어휘로만 when 을 쓰게 하고,
        위반이면 사유를 되돌려 1회 재시도(structure custom.validate 규율).
        어느 쪽이든 replay 가 최종 관문이다 — LLM 산출도 특별 대우 없음.

여기서 규칙이 발동되는 일은 없다 — 등재는 잠정까지고, 발동은 rules.mode()
와 상태 사다리의 몫이다. 유도 자체를 끄려면 RAG_RULES_INDUCE=off.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from typing import Optional

from lawrag.core.rag import refs
from lawrag.core.rag import replay as replay_mod
from lawrag.core.rag import rules as rules_mod

HOLDOUT_RATIO = 0.3     # 사례가 4건 이상일 때 최신 30% 는 일반화에 안 보여준다

INDUCE_SYSTEM = (
    "너는 규칙 귀납기다. 사람이 승인한 착지 재지정 사례들을 받아, 사례들에"
    " 공통인 **문서 무관** 조건을 닫힌 술어 어휘로만 쓴다.\n"
    "  - when 의 키는 반드시 주어진 술어 목록에서, 값은 그 술어의 허용 인자"
    " 중에서 고른다. 다른 키·값 금지.\n"
    "  - 특정 문서·좌표(doc_id, 노드 번호)에만 참인 조건은 규칙이 아니다 —"
    " 그런 군집이면 rule 을 null 로 둔다.\n"
    "  - rationale 은 한 문장."
)

INDUCE_SCHEMA = {
    "type": "object",
    "properties": {"rule": {"type": ["object", "null"], "properties": {
        "when": {"type": "object"},
        "then": {"type": "object"},
        "rationale": {"type": "string"}},
        "required": ["when", "then", "rationale"],
        "additionalProperties": False}},
    "required": ["rule"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- 특징화·군집
def featurize(index, row: dict) -> Optional[tuple]:
    """사례 하나의 특징 서명 — 색인 조회만으로 계산한다(결정적).
    지금 아는 모양은 하나: 표면 사슬을 내리면 정확히 new_dst 에 닿는 재지정."""
    view = index.docs.get(row.get("dst_doc"))
    if view is None:
        return None
    dst = view.by_id.get(row.get("dst"))
    if dst is None:
        return None
    rs = refs.find(row.get("surface") or "")
    if not rs or not rs[0].chain:
        return None
    unit = None
    for label in (dst.get("surface"), dst.get("title")):
        k = refs.label_key(label or "")
        if k:
            unit = k[0]
            break
    if unit is None:
        return None
    node, depth = refs._descend(view, refs._children(view), dst.get("id"),
                                rs[0].chain)
    if depth == len(rs[0].chain) and node == row.get("new_dst"):
        return ("표면사슬하강", unit)
    return None


def clusters(index) -> tuple[dict, list, int]:
    """redirect 행 전체 → (서명별 군집, 서명 없는 잔여, 제외 수).

    출처가 규칙인 행은 표본에서 뺀다 — 규칙의 산출 위에서 태어난 사례를
    귀납의 증거로 쓰면 규칙이 저 자신을 확증한다. 귀납의 표본은 규칙의
    결과와 독립이어야 한다."""
    grouped: dict[tuple, list] = {}
    rest: list[dict] = []
    excluded = 0
    for row in replay_mod._redirect_rows():
        if (row.get("출처") or {}).get("rule"):
            excluded += 1
            continue
        sig = featurize(index, row)
        if sig is None:
            rest.append(row)
        else:
            grouped.setdefault(sig, []).append(row)
    return grouped, rest, excluded


# ---------------------------------------------------------------- 일반화
def _evidence(rows: list[dict]) -> dict:
    rows = sorted(rows, key=lambda r: r.get("created", ""))
    holdout = []
    if len(rows) >= 4:
        n = max(1, math.ceil(len(rows) * HOLDOUT_RATIO))
        holdout = [replay_mod.instance_key(r) for r in rows[-n:]]
    qids = [q for r in rows for q in (r.get("evidence_qids") or [])]
    return {"instances": [replay_mod.instance_key(r) for r in rows],
            "holdout": holdout, "qids": qids[:40]}


def propose_mechanical(sig: tuple, rows: list[dict]) -> Optional[dict]:
    if sig[0] != "표면사슬하강":
        return None
    return {"kind": "redirect", "tier": "core", "status": "잠정",
            "when": {"간선.표면사슬": "있음", "간선.도착단위": sig[1],
                     "도착.사슬하강": "완전"},
            "then": {"redirect": "표면사슬_하강"},
            "falsify_when": "규칙이 내린 착지를 부검이 뒤집으면(원장 뒤집힘)",
            "rationale": f"표면이 {sig[1]} 아래 사슬까지 말한 참조는 실존하는 "
                         "가장 깊은 자손이 착지다",
            "evidence": _evidence(rows), "resolved_by": "귀납(기계)"}


def propose_llm(llm, rows: list[dict]) -> Optional[dict]:
    """서명이 안 잡힌 사례들 — LLM 이 닫힌 어휘로 일반화를 시도한다.
    위반이면 사유를 되돌려 1회 재시도. 실패는 조용히 None — 다음 유도 때
    사례가 더 쌓이면 다시 본다."""
    if llm is None or not rows:
        return None
    shown = rows if len(rows) < 4 else \
        sorted(rows, key=lambda r: r.get("created", ""))[
            :len(rows) - max(1, math.ceil(len(rows) * HOLDOUT_RATIO))]
    vocab = {k: sorted(v) for k, v in rules_mod.PRED_ARGS.items()}
    sample = [{k: r.get(k) for k in ("surface", "src_path", "dst_path",
                                     "new_dst_path", "이유")} for r in shown[:12]]
    user = (f"[술어 어휘]\n{json.dumps(vocab, ensure_ascii=False)}\n"
            f"[행동 어휘]\n{sorted(rules_mod.ACTIONS)}\n"
            f"[승인 사례]\n{json.dumps(sample, ensure_ascii=False)}")
    why = None
    for _ in range(2):
        ask = user if why is None else \
            f"{user}\n[이전 시도 거부 사유]\n{why} — 고쳐서 다시."
        out = llm.structured("rag.rules.induce", INDUCE_SYSTEM, ask,
                             INDUCE_SCHEMA, max_tokens=1000, effort="medium")
        if out is None or out.get("rule") is None:
            return None
        cand = {"kind": "redirect", "tier": "core", "status": "잠정",
                "when": out["rule"].get("when"), "then": out["rule"].get("then"),
                "falsify_when": "규칙이 내린 착지를 부검이 뒤집으면",
                "rationale": out["rule"].get("rationale", ""),
                "evidence": _evidence(rows), "resolved_by": "귀납(LLM)"}
        why = rules_mod.validate({**cand, "id": "gr-후보"})
        if why is None:
            return cand
    return None


# ---------------------------------------------------------------- 실행
def run(index=None, llm=None) -> list[dict]:
    """한 바퀴 유도 — 군집마다 (후보, replay 성적, 등재 결과)를 보고한다."""
    if index is None:
        from lawrag.core.rag import index as index_mod
        index = index_mod.current()
    grouped, rest, excluded = clusters(index)
    candidates: list[tuple[dict, list]] = []
    for sig, rows in grouped.items():
        cand = propose_mechanical(sig, rows)
        if cand:
            candidates.append((cand, rows))
    llm_cand = propose_llm(llm, rest)
    if llm_cand:
        candidates.append((llm_cand, rest))

    auto = os.environ.get("RAG_RULES_AUTOPROMOTE", "off").strip().lower() == "on"
    report = []
    for cand, rows in candidates:
        res = replay_mod.verify(cand, index, instances=rows)
        item = {"후보": {k: cand[k] for k in
                         ("when", "then", "rationale", "resolved_by")},
                "사례": len(rows), "replay": res, "등재": None}
        if res["green"]:
            added = rules_mod.add_rule(cand)
            if added:
                item["등재"] = added["id"]
                if auto and len(rows) >= rules_mod.MIN_EVIDENCE:
                    rules_mod.set_status(added["id"], "규칙", by="자동(replay)",
                                         note=f"재현 {res['reproduced']}/"
                                              f"{res['total']} · 충돌 0")
                    item["승격"] = "규칙"
        report.append(item)
    # 조용한 실패 금지 — 다루지 못한 표본도 보고에 남는다. "안 보였다"와
    # "안 다뤘다"가 구별돼야 어휘 개정 신호(§8)를 읽을 수 있다.
    if rest and llm is None:
        report.append({"잔여": len(rest), "등재": None,
                       "사유": "특징 서명 없음 — LLM 미가동이라 어휘 안 일반화 미탐색"})
    if excluded:
        report.append({"제외": excluded, "등재": None,
                       "사유": "규칙 산출 유래 사례 — 자기확증 방지로 표본 제외"})
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="승인 사례 → 일반 규칙 귀납")
    ap.add_argument("--no-llm", action="store_true",
                    help="기계 일반화만 — 서명 없는 잔여는 건너뛴다")
    args = ap.parse_args()
    if os.environ.get("RAG_RULES_INDUCE", "on").strip().lower() == "off":
        print("RAG_RULES_INDUCE=off — 유도를 건너뜁니다")
        return
    llm = None
    if not args.no_llm:
        from lawrag.core import llm as llm_mod
        if llm_mod.available():
            llm = llm_mod.LLM()
    print(json.dumps(run(llm=llm), ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
