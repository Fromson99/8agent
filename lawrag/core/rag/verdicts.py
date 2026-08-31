"""판정 지문 — 답변 시점 LLM 이 찍는 "잘못 끌려온 구역" 기록과 그 승격.

KG 는 완벽하지 않다. 참조 닫힘이 A→B 를 끌고 왔는데 B 가 엉뚱하면, 지금까지는
LLM 이 조용히 안 쓰고 버렸다 — 그 판단이 증발했다. 이제는 **지문으로 남는다**
(사용자 결정 2026-08-10):

    **사후 감사**(audit.py — 답을 보낸 뒤 백그라운드 1콜)의 판정
      → verdicts.jsonl 에 적재 (append-only — 후보일 뿐, 무반영)
      → 백로그 화면에서 사람이 승인/기각
      → 승인 = edge_rules.json 의 억제 간선 등재
      → 참조 닫힘(expand_refs)이 그 간선을 건너뛴다

판정은 네 갈래이고, **가는 곳이 다르다**:

    오참조     간선이 틀렸다      → 억제 후보(간선별로 묶어 승인/기각)
    참조무관   간선은 옳다        → 회수 신호(확장 규칙이 넓다) — 통계로만
    검색무관   진입 검색이 빗나감 → 회수 신호(벡터·용어 검색) — 통계로만
    구조화오류 계층이 원문과 다름 → 구역(문서·마디)별로 묶어 구조 재해석 후보

무관 계열을 간선 억제 후보로 올리면 안 된다 — 좌표가 맞는데 이번 질문에 안
맞았을 뿐이라, 지우면 옳은 법령 참조를 영영 잃는다(실측 2026-08-11).

제안자/검증자 분리는 그대로다: LLM 지문 몇 개가 쌓여도 간선은 살아 있고,
사람의 승인만이 규칙을 만든다. 기각도 기록된다 — 같은 간선의 지문이 다시
쌓이면 백로그에 다시 올라온다(반증 가능한 규칙, §5.5).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lawrag.core.rag.index import store_path


# 판정 갈래 — audit.KINDS 와 같아야 한다. 옛 기록의 "무관"은 참조무관·검색무관으로
# 갈리기 전 이름이라 함께 받는다(적재된 것을 다시 쓰지 않는다).
KINDS = ("오참조", "참조무관", "검색무관", "구조화오류", "무관")


def verdicts_path() -> Path:
    return Path(os.environ.get("RAG_LOG_DIR", store_path().parent / "rag")) \
        / "verdicts.jsonl"


def rules_path() -> Path:
    """간선 억제 규칙 — L3 장부 자리(data/rules/)의 첫 입주자다."""
    return Path(os.environ.get("RAG_RULES_DIR", store_path().parent / "rules")) \
        / "edge_rules.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _append(rec: dict) -> None:
    p = verdicts_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _edge_key(src_doc, src, dst_doc, dst) -> str:
    return f"{src_doc}:{src}→{dst_doc}:{dst}"


# ---------------------------------------------------------------- 적재
def log(qid: str, question: str, discards: list[dict]) -> int:
    """합성이 돌려준 판정 지문을 적재한다. 반영은 없다 — 기록이 전부다."""
    n = 0
    for d in discards:
        rec = {"kind": "지문", "qid": qid, "ts": _now(), "질의": question,
               "판정": d.get("kind"), "사유": d.get("reason", ""),
               "구역": d.get("section"), "경위": d.get("via"),
               "매칭": d.get("matched")}
        src = d.get("ref_src")
        if src and d.get("section"):
            rec["간선"] = {"src_doc": src["doc_id"], "src": src["node"],
                           "src_path": src.get("path", ""),
                           "surface": src.get("surface", ""),
                           "dst_doc": d["section"]["doc_id"],
                           "dst": d["section"]["node"],
                           "dst_path": d["section"].get("path", "")}
        _append(rec)
        n += 1
    return n


def resolve(edge: dict, action: str, note: str = "") -> dict:
    """백로그 처리 — 승인이면 억제 규칙 등재, 기각이면 기록만.

    승인은 곧 규칙이다: 이후 참조 닫힘이 이 간선을 건너뛴다. 증거(해당
    지문들의 qid)는 규칙에 함께 남는다 — 왜 억제됐는지 되짚을 수 있어야 한다.
    """
    key = _edge_key(edge["src_doc"], edge["src"], edge["dst_doc"], edge["dst"])
    _append({"kind": "처리", "ts": _now(), "edge_key": key,
             "action": action, "note": note})
    if action != "승인":
        from lawrag.core.rag import approvals
        approvals.safe_record(
            kind="reference_verdict", decision=action, effect="rejected",
            failure="잘못된_참조", subject={"edge_key": key,
                 "src_doc": edge.get("src_doc"), "dst_doc": edge.get("dst_doc")},
            after={"suppressed": False}, note=note, actor="human",
            source={"ledger": "verdicts"})
        return {"action": action, "edge_key": key}

    p = rules_path()
    data = {"suppress": []}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    qids = [r.get("qid") for r in _records()
            if r.get("kind") == "지문" and r.get("간선")
            and _edge_key(r["간선"]["src_doc"], r["간선"]["src"],
                          r["간선"]["dst_doc"], r["간선"]["dst"]) == key]
    if not any(_edge_key(r["src_doc"], r["src"], r["dst_doc"], r["dst"]) == key
               for r in data.get("suppress", [])):
        data.setdefault("suppress", []).append({
            "src_doc": edge["src_doc"], "src": edge["src"],
            "dst_doc": edge["dst_doc"], "dst": edge["dst"],
            "src_path": edge.get("src_path", ""),
            "dst_path": edge.get("dst_path", ""),
            "이유": note or "판정 백로그 승인",
            "evidence_qids": qids[:20], "created": _now()})
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    _rules_cache.clear()
    from lawrag.core.rag import approvals
    approvals.safe_record(
        kind="reference_verdict", decision=action, effect="suppress",
        failure="잘못된_참조", subject={"edge_key": key,
             "src_doc": edge.get("src_doc"), "dst_doc": edge.get("dst_doc")},
        before={"suppressed": False}, after={"suppressed": True}, note=note,
        actor="human", qids=qids, source={"ledger": "edge_rules"})
    return {"action": "승인", "edge_key": key, "suppressed": True}


# ---------------------------------------------------------------- 교정(재지정)
# 억제가 "이 간선은 틀렸다"라면, 교정은 "이 간선의 도착이 얕다 — 제2조가
# 아니라 제2조 제3항이다"다. 답변 시점 LLM 이 착지의 자손 중에서 옳은 구역을
# 고르면(닫힌 후보) 그 제안이 여기 쌓이고, 사람이 승인해야 재지정 규칙이 되어
# 색인의 간선 자체가 그 좌표로 옮겨 앉는다.
def log_fixes(qid: str, question: str, fixes: list[dict]) -> int:
    """착지 교정 제안을 적재한다. 반영은 없다 — 기록이 전부다."""
    n = 0
    for f in fixes:
        _append({"kind": "교정", "qid": qid, "ts": _now(), "질의": question,
                 "간선": {k: f.get(k) for k in
                          ("src_doc", "src", "src_path", "surface",
                           "dst_doc", "dst", "dst_path")},
                 "새_dst": f.get("new_dst"), "새_dst_path": f.get("new_dst_path", ""),
                 "사유": f.get("reason", "")})
        n += 1
    return n


def _fix_key(edge: dict, new_dst) -> str:
    return (_edge_key(edge["src_doc"], edge["src"], edge["dst_doc"], edge["dst"])
            + f"⤷{new_dst}")


def resolve_fix(fix: dict, action: str, note: str = "") -> dict:
    """교정 백로그 처리 — 승인이면 재지정 규칙 등재, 기각이면 기록만.

    재지정은 같은 문서 안의 자손으로만 간다(제안이 착지의 자손에서 나오므로) —
    다른 문서로 보내는 것은 교정이 아니라 링크 판정(links)의 몫이다.
    """
    key = _fix_key(fix, fix.get("new_dst"))
    _append({"kind": "교정처리", "ts": _now(), "fix_key": key,
             "action": action, "note": note})
    if action != "승인":
        from lawrag.core.rag import approvals
        approvals.safe_record(
            kind="landing_fix", decision=action, effect="rejected",
            failure="얕은_착지", subject={"fix_key": key,
                 "src_doc": fix.get("src_doc"), "dst_doc": fix.get("dst_doc")},
            after={"redirected": False}, note=note, actor="human",
            source={"ledger": "verdicts"})
        return {"action": action, "fix_key": key}

    p = rules_path()
    data = {"suppress": [], "redirect": []}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    rows = data.setdefault("redirect", [])
    qids = [r.get("qid") for r in _records()
            if r.get("kind") == "교정" and r.get("간선")
            and r.get("새_dst") == fix.get("new_dst")
            and _edge_key(r["간선"]["src_doc"], r["간선"]["src"],
                          r["간선"]["dst_doc"], r["간선"]["dst"])
            == _edge_key(fix["src_doc"], fix["src"],
                         fix["dst_doc"], fix["dst"])]
    if not any(_fix_key(r, r.get("new_dst")) == key for r in rows):
        rows.append({
            "src_doc": fix["src_doc"], "src": fix["src"],
            "dst_doc": fix["dst_doc"], "dst": fix["dst"],
            "new_dst": fix["new_dst"],
            "src_path": fix.get("src_path", ""),
            "dst_path": fix.get("dst_path", ""),
            "new_dst_path": fix.get("new_dst_path", ""),
            "surface": fix.get("surface", ""),
            "이유": note or "교정 백로그 승인",
            "evidence_qids": qids[:20], "created": _now(),
            # 출처 — 이 간선이 일반 규칙의 산출 위에서 태어났다면 그 규칙 id.
            # 귀납(induce)이 이 행을 표본에서 뺀다 — 규칙이 제 산출을 제
            # 증거로 삼는 자기확증을 막는다.
            **({"출처": fix["출처"]} if fix.get("출처") else {})})
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    _rules_cache.clear()
    from lawrag.core.rag import approvals
    approvals.safe_record(
        kind="landing_fix", decision=action, effect="redirect",
        failure="얕은_착지", subject={"fix_key": key,
                                 "src_doc": fix.get("src_doc"),
                                 "dst_doc": fix.get("dst_doc")},
        before={"dst": fix.get("dst")}, after={"dst": fix.get("new_dst")},
        note=note, actor="human", qids=qids,
        source={"ledger": "edge_rules", "derived_from_rule": fix.get("출처") or {}})
    return {"action": "승인", "fix_key": key, "redirected": True}


# ---------------------------------------------------------------- 조회
def _rule_add(section: str, row: dict, dedupe: tuple) -> bool:
    """규칙 파일의 한 갈래에 행을 더한다(같은 키가 있으면 두지 않는다)."""
    p = rules_path()
    data = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    rows = data.setdefault(section, [])
    if any(tuple(r.get(k) for k in dedupe) == tuple(row.get(k) for k in dedupe)
           for r in rows):
        return False
    rows.append({**row, "created": _now()})
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    _rules_cache.clear()
    return True


# ---------------------------------------------------------------- 축별 처리
# 판정 넷은 **고치는 자리가 다르다.** 같은 버튼으로 다루면 옳은 연결을 지우게 된다.
#
#   오참조    간선이 틀림      → resolve()          억제/재지정 (기존)
#   참조무관  연결은 옳음      → resolve_miss()     후순위(demote) — 지우지 않는다
#   검색무관  진입이 빗나감    → resolve_miss()     진입 제외(entry_block)
#   구조화오류 계층이 틀림      → resolve_struct()   구조 교정은 검수 화면에서, 여기선 닫기

MISS_ACTIONS = ("후순위", "진입제외", "정상")
STRUCT_ACTIONS = ("고침", "무시")


def miss_key(rec: dict) -> str:
    """회수 지문 하나의 키 — (판정, 구역 좌표, 간선). 같은 자리의 반복은 한 줄로 묶인다."""
    s = rec.get("구역") or {}
    e = rec.get("간선") or {}
    return (f"{rec.get('판정')}|{s.get('doc_id')}:{s.get('node')}"
            f"|{e.get('src_doc', '')}:{e.get('src', '')}")


def resolve_miss(rec: dict, action: str, note: str = "") -> dict:
    """회수 결함(참조무관·검색무관)의 처리.

    억제(간선 삭제)는 여기에 **없다** — 좌표가 맞는데 이번 질문에 안 맞았을 뿐이라
    지우면 옳은 참조를 영영 잃는다(실측 2026-08-11). 대신 두 갈래다:
      후순위   그 간선을 확장 자리 경쟁에서 뒤로 민다 (연결은 산다)
      진입제외 그 좌표를 벡터·용어 **진입**에서 뺀다 (참조로는 여전히 온다)
    """
    if action not in MISS_ACTIONS:
        raise ValueError(f"action 은 {MISS_ACTIONS} 중 하나여야 합니다")
    s, e = rec.get("구역") or {}, rec.get("간선") or {}
    # **먼저 검증한다.** 처리 기록을 앞서 적으면 거부된 동작도 항목을 백로그에서
    # 내려버린다 — 사람은 처리했다고 믿는데 아무 규칙도 안 생긴 상태가 된다.
    if action == "후순위" and not e:
        raise ValueError("간선이 없는 지문은 후순위로 미룰 수 없습니다 — "
                         "진입으로 들어온 것이라면 '진입제외'입니다")
    if action == "진입제외" and not s.get("doc_id"):
        raise ValueError("구역 좌표가 없어 진입 제외를 걸 수 없습니다")

    applied = False
    if action == "후순위":
        applied = _rule_add("demote", {
            "src_doc": e["src_doc"], "src": e["src"],
            "dst_doc": e["dst_doc"], "dst": e["dst"],
            "src_path": e.get("src_path", ""), "dst_path": e.get("dst_path", ""),
            "이유": note or "참조무관 지문 — 연결은 옳으나 회수 우선순위를 낮춤"},
            ("src_doc", "src", "dst_doc", "dst"))
    elif action == "진입제외":
        applied = _rule_add("entry_block", {
            "doc_id": s["doc_id"], "node": s.get("node"),
            "path": s.get("path", ""), "doc": s.get("doc", ""),
            "이유": note or "검색무관 지문 — 진입(벡터·용어)에서 제외"},
            ("doc_id", "node"))
    key = miss_key(rec)
    _append({"kind": "회수처리", "ts": _now(), "miss_key": key,
             "action": action, "note": note})
    from lawrag.core.rag import approvals
    effect = {"후순위": "demote", "진입제외": "entry_block", "정상": "rejected"}[action]
    failure = {"후순위": "과도한_참조확장", "진입제외": "검색_진입오염",
               "정상": ""}[action]
    approvals.safe_record(
        kind="retrieval_verdict", decision=action, effect=effect, failure=failure,
        subject={"miss_key": key, "doc_id": s.get("doc_id"),
                 "src_doc": e.get("src_doc"), "dst_doc": e.get("dst_doc")},
        after={"applied": applied}, note=note, actor="human",
        qids=rec.get("qids") or ([rec.get("qid")] if rec.get("qid") else []),
        source={"ledger": "edge_rules" if applied else "verdicts"})
    return {"action": action, "miss_key": key, "applied": applied}


def struct_key(rec: dict) -> str:
    s = rec.get("구역") or {}
    return f"{s.get('doc_id')}:{s.get('node')}"


def resolve_struct(section: dict, action: str, note: str = "") -> dict:
    """구조화오류의 처리 — 규칙을 만들지 않는다.

    계층은 검수 화면(계층 교정·틀 마커)에서 고친다. 여기서는 "고쳤다/무시한다"만
    적어 백로그에서 내린다 — 고침 기록이 남아야 같은 자리가 다시 올라올 때
    "또 그 자리"임을 알 수 있다.
    """
    if action not in STRUCT_ACTIONS:
        raise ValueError(f"action 은 {STRUCT_ACTIONS} 중 하나여야 합니다")
    if not section.get("doc_id"):
        raise ValueError("구역 좌표가 없습니다")
    key = f"{section.get('doc_id')}:{section.get('node')}"
    _append({"kind": "구조처리", "ts": _now(), "struct_key": key,
             "action": action, "note": note,
             "구역": {k: section.get(k) for k in ("doc_id", "doc", "node", "path")}})
    from lawrag.core.rag import approvals
    approvals.safe_record(
        kind="structure_verdict", decision=action,
        effect="structure_fixed" if action == "고침" else "rejected",
        failure="구조화_오류" if action == "고침" else "",
        subject={"struct_key": key, "doc_id": section.get("doc_id"),
                 "node": section.get("node")}, after={"action": action},
        note=note, actor="human", source={"ledger": "verdicts"})
    return {"action": action, "struct_key": key}


_rules_cache: dict = {}


_EMPTY_RULES = {"keys": set(), "redir": {}, "demote": set(), "entry": {}}


def _rules() -> dict:
    """edge_rules.json 을 mtime 캐시로. 규칙 네 종류 — 판정 네 갈래에 하나씩 대응한다.

        suppress  오참조    이 간선은 틀렸다 → 참조 확장에서 뺀다
        redirect  오참조    도착이 얕다 → 색인이 간선을 그 좌표로 옮겨 앉힌다
        demote    참조무관  연결은 옳다 → 자리 경쟁에서 **뒤로 민다**(지우지 않는다)
        entry     검색무관  진입(벡터·용어)이 빗나갔다 → 그 좌표를 **진입에서만** 뺀다
                            (참조를 타고는 여전히 올 수 있다 — 연결 지식은 그대로)
    """
    p = rules_path()
    if not p.exists():
        return dict(_EMPTY_RULES)
    # 경로도 서명에 든다 — mtime 만 보면 경로가 바뀌는 환경(테스트의 tmp,
    # env 전환)에서 다른 파일의 규칙이 스테일로 남는다.
    sig = (str(p), p.stat().st_mtime_ns)
    if _rules_cache.get("sig") != sig:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return dict(_EMPTY_RULES)
        _rules_cache["keys"] = {
            _edge_key(r["src_doc"], r["src"], r["dst_doc"], r["dst"])
            for r in data.get("suppress", [])}
        _rules_cache["redir"] = {
            (r["src_doc"], r["src"], r["dst_doc"], r["dst"]): r
            for r in data.get("redirect", [])}
        _rules_cache["demote"] = {
            _edge_key(r["src_doc"], r["src"], r["dst_doc"], r["dst"])
            for r in data.get("demote", [])}
        _rules_cache["entry"] = {
            (r["doc_id"], r["node"]): r for r in data.get("entry_block", [])}
        _rules_cache["sig"] = sig
    return _rules_cache


def rule_snapshot() -> dict:
    """한 조립 작업에서 재사용할 읽기 전용 규칙 스냅샷.

    간선 수만 개를 세우는 동안 매 간선이 rules_path의 mtime을 다시 ``stat``하지
    않도록 호출부가 한 번 받아 전달한다. Index 자체가 규칙 파일 mtime을 서명에
    포함하므로 다음 요청의 새 Index에는 최신 스냅샷이 적용된다.
    """
    return _rules()


def is_suppressed(src_doc, src, dst_doc, dst, *, snapshot: Optional[dict] = None) -> bool:
    rules = snapshot if snapshot is not None else _rules()
    return _edge_key(src_doc, src, dst_doc, dst) in rules.get("keys", set())


def is_demoted(src_doc, src, dst_doc, dst) -> bool:
    """참조 확장에서 **뒤로 밀 간선**인가. 지우는 것이 아니라 순서를 늦춘다 —
    자리가 남으면 여전히 온다(옳은 연결이므로 잃으면 안 된다)."""
    return _edge_key(src_doc, src, dst_doc, dst) in _rules().get("demote", set())


def is_entry_blocked(doc_id, node) -> bool:
    """이 좌표를 **진입**(벡터·용어)으로 데려오지 않는다. 참조 확장은 그대로다."""
    return (doc_id, node) in _rules().get("entry", {})


def redirect_map(*, snapshot: Optional[dict] = None) -> dict:
    """승인된 재지정 — (src_doc, src, dst_doc, dst) -> 규칙 행. 색인이 간선을
    세울 때 이 사전으로 도착 좌표를 옮겨 앉힌다."""
    rules = snapshot if snapshot is not None else _rules()
    return dict(rules.get("redir", {}))


def _records() -> list[dict]:
    p = verdicts_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def flagged_qids() -> set[str]:
    """감사·교정이 지적한 질의들의 qid — 시스템이 스스로 틀렸다고 표시한
    자리다. 위키 유입 판정(wiki_triage)이 이 질의들을 먼저 본다."""
    return {r.get("qid", "") for r in _records()
            if r.get("kind") in ("지문", "교정") and r.get("qid")}


# ---------------------------------------------------------------- 판단 수정
# LLM 판단(지문·교정)이 틀렸을 때 — "오참조라 했는데 실제로는 맞는 연결이다" —
# 사람이 그 기록을 고친다. append-only 는 그대로다: 원본은 남고 '수정' 레코드가
# 겹쳐 읽힌다(_effective). 무엇이 언제 왜 바뀌었는지가 이력으로 남는다.
_EDITABLE = {"판정", "사유", "간선", "새_dst", "새_dst_path"}


def edit(qid: str, target: str, idx: int, after: dict, note: str = "") -> dict:
    """qid 의 target(지문|교정) 중 idx 번째 기록을 고친다 — 허용 필드만.
    idx 는 그 qid 안에서의 적재 순서다(jsonl 은 append-only 라 안정적이다)."""
    if target not in ("지문", "교정"):
        raise ValueError("target 은 '지문' 또는 '교정'이어야 합니다")
    rows = [r for r in _records()
            if r.get("kind") == target and r.get("qid") == qid]
    if not (0 <= idx < len(rows)):
        raise ValueError(f"{qid} 의 {target} {idx}번째 기록이 없습니다")
    clean = {k: v for k, v in (after or {}).items() if k in _EDITABLE}
    if not clean:
        raise ValueError(f"고칠 수 있는 필드가 없습니다 — 허용: {sorted(_EDITABLE)}")
    before = {k: rows[idx].get(k) for k in clean}
    rec = {"kind": "수정", "qid": qid, "target": target, "idx": idx,
           "ts": _now(), "before": before, "after": clean, "메모": note}
    _append(rec)
    return rec


def _effective() -> list[dict]:
    """지문·교정 기록에 수정 레코드를 겹쳐 읽는다 — 마지막 수정이 이기고,
    수정된 기록에는 수정이력이 붙는다. 백로그·조회는 전부 이걸 본다."""
    recs = _records()
    edits: dict[tuple, list] = {}
    for r in recs:
        if r.get("kind") == "수정":
            edits.setdefault((r.get("qid"), r.get("target"), r.get("idx")),
                             []).append(r)
    if not edits:
        return recs
    out, counters = [], {}
    for r in recs:
        k = r.get("kind")
        if k in ("지문", "교정"):
            i = counters.get((r.get("qid"), k), 0)
            counters[(r.get("qid"), k)] = i + 1
            es = edits.get((r.get("qid"), k, i))
            if es:
                r = {**r, **es[-1]["after"],
                     "수정이력": [{"ts": e.get("ts"), "메모": e.get("메모", ""),
                                   "before": e.get("before"),
                                   "after": e.get("after")} for e in es]}
        out.append(r)
    return out


def score_terms(hit_keys: list[str], miss_keys: list[str]) -> dict:
    """용어 진입의 실적 — 인용되면 hits, 무관 지문을 받으면 misses.

    실적 기반 강등(§5.5 "적중률 붕괴 시 강등")의 재료다: misses 가 쌓인
    용어는 검수 큐에서 다시 심사받거나 진입 자격을 잃는다. 여기서는 세기만
    한다 — 상태를 바꾸는 것은 사람(또는 Phase 3 게이트)의 몫이다.
    glossary.json 을 직접 고친다(core.terms import 금지 — 아키텍처 격리)."""
    if not hit_keys and not miss_keys:
        return {"hits": 0, "misses": 0}
    from lawrag.core.rag.index import terms_path

    p = terms_path()
    if not p.exists():
        return {"hits": 0, "misses": 0}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"hits": 0, "misses": 0}
    rows = {t.get("key"): t for t in data.get("terms", [])}
    nh = nm = 0
    for k in hit_keys:
        if k in rows:
            rows[k]["hits"] = int(rows[k].get("hits") or 0) + 1
            nh += 1
    for k in miss_keys:
        if k in rows:
            rows[k]["misses"] = int(rows[k].get("misses") or 0) + 1
            nm += 1
    if nh or nm:
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return {"hits": nh, "misses": nm}


def _add_q(g: dict, r: dict, cap: int = 8) -> None:
    """묶음에 (qid, 질의 원문, 시각) 짝을 단다 — 화면이 qid 코드가 아니라
    질문 글자로 보여줄 수 있어야 한다. 같은 qid 는 한 번만."""
    qid = r.get("qid")
    if not qid or any(x["qid"] == qid for x in g["질의들"]):
        return
    if len(g["질의들"]) < cap:
        g["질의들"].append({"qid": qid, "질의": r.get("질의", ""),
                            "ts": r.get("ts", "")})


def backlog() -> dict:
    """백로그 — 간선 지문은 간선별로, 교정 제안은 (간선, 새 좌표)별로 묶는다
    (처리된 것 제외). 간선 없는 무관 지문은 최근 것만 통계로. 사람이 볼
    화면의 재료다. 수정 레코드가 겹쳐 읽히므로(_effective) 사람이 고친 판단이
    화면의 판단이다 — 판정을 "정상"으로 고친 지문은 백로그에서 빠진다."""
    recs = _effective()
    resolved: dict[str, str] = {}
    fix_resolved: dict[str, str] = {}
    miss_resolved: dict[str, str] = {}
    struct_resolved: dict[str, str] = {}
    for r in recs:
        if r.get("kind") == "처리":
            resolved[r["edge_key"]] = r["action"]
        elif r.get("kind") == "교정처리":
            fix_resolved[r["fix_key"]] = r["action"]
        elif r.get("kind") == "회수처리":
            miss_resolved[r["miss_key"]] = r["action"]
        elif r.get("kind") == "구조처리":
            struct_resolved[r["struct_key"]] = r["action"]

    edges: dict[str, dict] = {}
    fixes: dict[str, dict] = {}
    struct: dict[str, dict] = {}       # 구조화오류 — 구역(문서·마디)별로 묶는다
    misses: dict[str, dict] = {}       # 참조무관·검색무관 — 처리 단위로 묶는다
    loose: list[dict] = []
    for r in recs:
        if r.get("kind") == "교정":
            if r.get("새_dst") is None:
                continue                   # 수정으로 제안이 철회됐다
            e = r.get("간선") or {}
            key = _fix_key(e, r.get("새_dst"))
            # 기각된 제안도 지문이 **새로** 쌓이면 다시 올라온다 — 단순화:
            # 처리됐으면 숨긴다(승인이면 규칙 존재, 기각이면 닫힘).
            if key in fix_resolved:
                continue
            g = fixes.setdefault(key, {"edge": e, "new_dst": r.get("새_dst"),
                                       "new_dst_path": r.get("새_dst_path", ""),
                                       "n": 0, "사유": [], "질의": [], "qids": [],
                                       "질의들": []})
            g["n"] += 1
            if r.get("사유") and len(g["사유"]) < 3:
                g["사유"].append(r["사유"])
            if r.get("질의") and r["질의"] not in g["질의"][:5]:
                g["질의"].append(r["질의"])
            g["qids"].append(r.get("qid"))
            _add_q(g, r)
            continue
        if r.get("kind") != "지문":
            continue
        if r.get("판정") not in KINDS:
            continue                       # 수정으로 "정상" 처리됐다 — 지문이 아니다
        # 구조화오류는 간선이 아니라 **문서의 계층**을 가리킨다 — 억제와 무관하니
        # 따로 모은다(사람은 여기서 검수 화면으로 건너가 계층을 고친다).
        if r.get("판정") == "구조화오류":
            sec = r.get("구역") or {}
            key = f"{sec.get('doc_id')}:{sec.get('node')}"
            if key in struct_resolved:
                continue                   # 고쳤거나 무시하기로 한 자리
            g = struct.setdefault(key, {"구역": sec, "key": key, "n": 0, "사유": [],
                                        "질의": [], "qids": [], "질의들": []})
            g["n"] += 1
            if r.get("사유") and len(g["사유"]) < 3:
                g["사유"].append(r["사유"])
            if r.get("질의") and r["질의"] not in g["질의"][:5]:
                g["질의"].append(r["질의"])
            g["qids"].append(r.get("qid"))
            _add_q(g, r)
            continue
        e = r.get("간선")
        # 억제 후보는 **오참조뿐**이다. "무관"은 좌표가 맞는데 이번 질문에 안
        # 맞았다는 회수 신호라, 간선을 지우면 옳은 법령 참조를 영영 잃는다
        # (실측 2026-08-11: 과태료 6.→제19조제1항 설명의무는 옳은 연결인데
        # 무관 지문이 억제 후보로 올라와 있었다). 간선 없는 오참조도 지울
        # 대상이 없으니 신호로만 남긴다.
        if not e or r.get("판정") != "오참조":
            # 회수 결함 — 같은 자리의 반복은 한 줄로 묶는다(처리 버튼이 붙으려면
            # 카드 하나가 하나의 대상을 가리켜야 한다). 처리된 것은 내린다.
            mkey = miss_key(r)
            if mkey in miss_resolved:
                continue
            g = misses.setdefault(mkey, {
                "key": mkey, "판정": r.get("판정", "무관"), "구역": r.get("구역"),
                "간선": e, "경위": r.get("경위"), "매칭": r.get("매칭"),
                "n": 0, "사유": [], "질의": [], "qids": [], "질의들": []})
            g["n"] += 1
            if r.get("사유") and len(g["사유"]) < 3:
                g["사유"].append(r["사유"])
            if r.get("질의") and r["질의"] not in g["질의"][:5]:
                g["질의"].append(r["질의"])
            g["qids"].append(r.get("qid"))
            _add_q(g, r)
            loose.append(r)
            continue
        key = _edge_key(e["src_doc"], e["src"], e["dst_doc"], e["dst"])
        # 기각된 간선도 지문이 **새로** 쌓이면 다시 올라온다 — 기각 시각 이후
        # 지문만 다시 세는 대신, 단순화: 기각이면 숨기고 승인이면 규칙 존재.
        if key in resolved:
            continue
        g = edges.setdefault(key, {"edge": e, "n": 0, "판정": {}, "사유": [],
                                   "질의": [], "qids": [], "질의들": []})
        g["n"] += 1
        g["판정"][r["판정"]] = g["판정"].get(r["판정"], 0) + 1
        if r.get("사유") and len(g["사유"]) < 3:
            g["사유"].append(r["사유"])
        if r.get("질의") and r["질의"] not in g["질의"][:5]:
            g["질의"].append(r["질의"])
        g["qids"].append(r.get("qid"))
        _add_q(g, r)

    rules = _rules()
    # 회수 결함 통계 — 어느 단이 빗나갔나. 간선을 지울 대상이 아니라 **규칙을
    # 손볼 신호**라, 개수로만 보여 준다(참조무관=확장이 넓다, 검색무관=검색이 빗나갔다).
    miss = {k: sum(1 for r in loose if r.get("판정") == k)
            for k in ("참조무관", "검색무관", "무관")}
    return {"edges": sorted(edges.values(), key=lambda g: -g["n"]),
            "fixes": sorted(fixes.values(), key=lambda g: -g["n"]),
            "struct": sorted(struct.values(), key=lambda g: -g["n"]),
            "misses": sorted(misses.values(), key=lambda g: -g["n"])[:60],
            "miss": {k: v for k, v in miss.items() if v},
            "loose": loose[-30:],
            "resolved": (len(resolved) + len(fix_resolved)
                         + len(miss_resolved) + len(struct_resolved)),
            "suppressed": len(rules.get("keys", set())),
            "redirected": len(rules.get("redir", {})),
            "demoted": len(rules.get("demote", set())),
            "entry_blocked": len(rules.get("entry", {}))}


def by_qid() -> dict:
    """qid -> {"지문": [...], "교정": [...]} — 디버깅 화면이 질의 로그 행에
    그 질의가 남긴 판정·교정을 붙일 때 쓴다. 수정본이 실리고 이력이 붙는다."""
    out: dict[str, dict] = {}
    for r in _effective():
        k = r.get("kind")
        if k not in ("지문", "교정") or not r.get("qid"):
            continue
        g = out.setdefault(r["qid"], {"지문": [], "교정": []})
        row: dict
        if k == "지문":
            row = {"판정": r.get("판정"), "사유": r.get("사유", ""),
                   "간선": r.get("간선")}
        else:
            row = {"간선": r.get("간선"), "새_dst": r.get("새_dst"),
                   "새_dst_path": r.get("새_dst_path", ""),
                   "사유": r.get("사유", "")}
        if r.get("수정이력"):
            row["수정이력"] = r["수정이력"]
        g[k].append(row)
    return out
