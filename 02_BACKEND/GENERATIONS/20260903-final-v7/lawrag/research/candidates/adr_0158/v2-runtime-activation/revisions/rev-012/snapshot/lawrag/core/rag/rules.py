"""일반 규칙(귀납층) — 승인 사례를 문서 무관 술어로 일반화한 규칙.

docs/RULE_LOOP.md 가 정본이다. 이 모듈은 연역만 한다 — LLM 이 없다.
규칙의 생성(귀납)은 induce.py, 검증은 replay.py, 여기는 적재·평가·원장이다.

두 폐쇄가 안전의 전부다:
  행동 어휘 — then 은 사람 승인이 남길 수 있는 행동만(지금은 redirect 한 종).
  술어 어휘 — when 은 PREDICATES 에 등록된 이름만. doc_id·노드 좌표 리터럴은
              적재 시점에 거부한다(structure/registry.py FORBIDDEN_ATTRS 규율).

스위치(§6): 유효 모드 = min(RAG_RULES_MODE, 차단기).
  off     파일을 로드조차 않는다 — 오늘의 시스템과 같다.
  shadow  술어를 평가하고 적중을 "그림자"로 기록하되 간선은 안 건드린다.
  on      발동. 옮긴 간선에는 via="규칙"·rule=id 가 새겨진다 — 무기명 발동 금지.

적중 원장(rule_hits.jsonl)은 append-only 다. 규칙이 증거를 심판한 모든 사건이
미검→확정/뒤집힘 으로 남고, 뒤집힘이 곧 반례다 — 통계·차단기·강등 영향 분석이
전부 이 원장의 파생 뷰다. 파괴적 쓰기는 없다: 발동도 오버레이(간선 이동)까지,
원본(result.json·edge_rules.json)은 건드리지 않는다.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lawrag.core.rag import refs
from lawrag.core.rag.index import store_path

log = logging.getLogger("lawrag.core.rag.rules")

# ---------------------------------------------------------------- 상수 (정의층)
# 문서 무관 상수다 — 특정 코퍼스에 맞춘 값이 아니라 운영 안전 여유다.
MIN_EVIDENCE = 3        # 잠정→규칙 자동 승격의 최소 근거 사례 수
BREAKER_WINDOW = 200    # 차단기 판정 창 — 최근 실발동 적중 수
BREAKER_MIN = 20        # 표본이 이보다 적으면 차단기를 밟지 않는다(초기 요동 방지)
BREAKER_RATIO = 0.10    # 창 안 뒤집힘율이 이를 넘으면 on→shadow 자동 강하
RULE_DEMOTE_N = 3       # 규칙 하나의 뒤집힘 누적이 이에 닿으면 그 규칙만 보류로
                        # — 전역 차단기(집단 강하)보다 먼저 작동해야 좋은 규칙이
                        # 연좌되지 않는다

STATUSES = ("잠정", "규칙", "정착", "보류", "강등")
ACTIVE = ("규칙", "정착")               # 발동하는 상태
KIND_ACTIONS = ("redirect",)            # 행동 어휘 — 승인이 남기는 행동만 자란다
FORBIDDEN_KEYS = ("doc_id", "src_doc", "dst_doc", "src", "dst", "node", "new_dst")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------- 저장 경로
def rules_file() -> Path:
    """일반 규칙 — edge_rules.json(사례층)과 같은 자리, 다른 파일."""
    return Path(os.environ.get("RAG_RULES_DIR", store_path().parent / "rules")) \
        / "general_rules.json"


def breaker_file() -> Path:
    return Path(os.environ.get("RAG_RULES_DIR", store_path().parent / "rules")) \
        / "breaker.json"


def hits_file() -> Path:
    """적중 원장 — verdicts.jsonl(판정)과 같은 자리, append-only."""
    return Path(os.environ.get("RAG_LOG_DIR", store_path().parent / "rag")) \
        / "rule_hits.jsonl"


# ---------------------------------------------------------------- 스위치
def breaker() -> dict:
    p = breaker_file()
    if not p.exists():
        return {"state": "정상"}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"state": "정상"}


def trip_breaker(reason: str) -> dict:
    """on→shadow 자동 강하. off 로는 안 간다 — 그림자 증거는 계속 모아야
    원인을 안다. 복귀(해제)는 사람만: reset_breaker()."""
    rec = {"state": "강하", "reason": reason, "ts": _now()}
    p = breaker_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    log.warning("규칙 차단기 강하 — %s", reason)
    return rec


def reset_breaker(note: str = "") -> dict:
    rec = {"state": "정상", "note": note, "ts": _now()}
    p = breaker_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


def mode() -> str:
    """유효 모드 — env 와 차단기 중 약한 쪽. 색인 서명에 이 값이 들어가므로
    전환은 재시작 없이 다음 질의부터다."""
    from lawrag.core.rag.content_snapshot import current_content_snapshot

    if current_content_snapshot() is not None:
        return "off"
    m = os.environ.get("RAG_RULES_MODE", "off").strip().lower()
    if m not in ("off", "shadow", "on"):
        m = "off"
    if m == "on" and breaker().get("state") == "강하":
        return "shadow"
    return m


# ---------------------------------------------------------------- 술어 어휘
# 전부 색인이 이미 가진 값(참조 표면·마디 제목·부모자손)으로만 계산한다.
# 새 술어는 여기 등록 + PRED_ARGS 에 허용 인자 선언 — 그것이 정의층 변경이다.
def _p_surface_chain(ctx: dict, arg: str) -> bool:
    """참조 표면이 조 아래 하강 사슬(제N항·제N호·N목…)까지 말했는가."""
    return arg == "있음" and ctx["ref"] is not None and bool(ctx["ref"].chain)


def _p_dst_unit(ctx: dict, arg: str) -> bool:
    """도착 마디의 번호 단위 — 제목을 refs.label_key 로 읽는다."""
    for label in (ctx["dst_node"].get("surface"), ctx["dst_node"].get("title")):
        k = refs.label_key(label or "")
        if k:
            return k[0] == arg
    return False


def _descend_target(ctx: dict) -> Optional[int]:
    """표면 사슬을 도착 마디에서 실존하는 데까지 내린 좌표 — **완전히**
    내려갔고 제자리가 아닐 때만. 부분 하강은 안 옮긴다(없는 것은 없는 것)."""
    ref = ctx["ref"]
    if ref is None or not ref.chain:
        return None
    node, depth = refs._descend(ctx["view"], ctx["children"],
                                ctx["dst_node"].get("id"), ref.chain)
    if depth == len(ref.chain) and node != ctx["dst_node"].get("id"):
        return node
    return None


def _p_descend_full(ctx: dict, arg: str) -> bool:
    return arg == "완전" and _descend_target(ctx) is not None


PREDICATES = {
    "간선.표면사슬": _p_surface_chain,
    "간선.도착단위": _p_dst_unit,
    "도착.사슬하강": _p_descend_full,
}
PRED_ARGS = {
    "간선.표면사슬": {"있음"},
    "간선.도착단위": {"조", "항", "호", "목", "편", "장", "절", "관", "별표", "별지"},
    "도착.사슬하강": {"완전"},
}
ACTIONS = {"표면사슬_하강": _descend_target}


# ---------------------------------------------------------------- 적재·검증
def validate(rule: dict) -> Optional[str]:
    """규칙 하나의 적재 자격 — 위반 사유를 돌려준다(None 이면 통과).
    induce 의 LLM 재시도가 이 사유를 그대로 모델에게 되돌린다."""
    if not rule.get("id"):
        return "id 가 없습니다"
    if rule.get("kind") not in KIND_ACTIONS:
        return f"kind 는 {KIND_ACTIONS} 중 하나여야 합니다"
    if rule.get("status") not in STATUSES:
        return f"status 는 {STATUSES} 중 하나여야 합니다"
    when = rule.get("when")
    if not isinstance(when, dict) or not when:
        return "when 이 비었습니다"
    for k, v in when.items():
        if k in FORBIDDEN_KEYS:
            return f"좌표 리터럴 금지 — when 에 {k} 는 올 수 없습니다"
        if k not in PREDICATES:
            return f"모르는 술어 {k} — 허용: {sorted(PREDICATES)}"
        if not isinstance(v, str) or v not in PRED_ARGS[k]:
            return f"{k} 의 인자는 {sorted(PRED_ARGS[k])} 중 하나여야 합니다"
    then = rule.get("then")
    if not isinstance(then, dict) or set(then) != {"redirect"}:
        return 'then 은 {"redirect": <행동>} 하나여야 합니다'
    if then["redirect"] not in ACTIONS:
        return f"모르는 행동 {then['redirect']} — 허용: {sorted(ACTIONS)}"
    return None


_load_cache: dict = {}


def load() -> list[dict]:
    """general_rules.json 을 mtime 캐시로 — 유효한 규칙만, 발동 상태 먼저.
    무효 규칙은 싣지 않고 **경고를 남긴다** — 조용한 실패 금지."""
    p = rules_file()
    if not p.exists():
        return []
    sig = (str(p), p.stat().st_mtime_ns)
    if _load_cache.get("sig") != sig:
        rows: list[dict] = []
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("general_rules.json 파싱 실패 — 규칙층 없이 간다: %s", e)
            data = {}
        for r in data.get("rules", []):
            why = validate(r)
            if why:
                log.warning("규칙 %s 적재 거부 — %s", r.get("id", "?"), why)
                continue
            rows.append(r)
        # 구체적인 규칙이 먼저다 — first-match 가 파일 순서라는 암묵이 아니라
        # "좁은 when 우선"이라는 원칙이 되게 한다. 발동 상태가 잠정보다 앞서는
        # 것은 그대로.
        rows.sort(key=lambda r: (0 if r.get("status") in ACTIVE else 1,
                                 -len(r.get("when") or {}), r.get("id", "")))
        for narrow, wide in overlaps(rows):
            log.warning("규칙 중첩 — %s ⊂ %s (좁은 쪽이 먼저 평가된다)",
                        narrow, wide)
        _load_cache["rows"] = rows
        # Publish the signature last.  Another thread that observes the new
        # signature must also be guaranteed to observe its matching rows.
        _load_cache["sig"] = sig
    return list(_load_cache["rows"])


def overlaps(rows: Optional[list] = None) -> list[tuple]:
    """when 이 포함 관계인 같은 kind 규칙 쌍 — (좁은 쪽 id, 넓은 쪽 id).

    중첩 자체는 오류가 아니라 신호다: 규칙 집합은 목록이 아니라 이론이어야
    하고, 이론은 겹침을 알고 있어야 한다. 넓은 쪽은 좁은 쪽이 안 잡은 잔여만
    잡는다(정렬이 보장). 화면(/rules)이 이 목록을 보여준다."""
    rows = load() if rows is None else rows
    out = []
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if a.get("kind") != b.get("kind"):
                continue
            wa = set((a.get("when") or {}).items())
            wb = set((b.get("when") or {}).items())
            if wa != wb and (wa <= wb or wb <= wa):
                narrow, wide = (a, b) if len(wa) >= len(wb) else (b, a)
                out.append((narrow.get("id"), wide.get("id")))
    return out


def _write_rules(rows: list[dict]) -> None:
    p = rules_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"rules": rows}, ensure_ascii=False, indent=2),
                 encoding="utf-8")
    _load_cache.clear()


def add_rule(rule: dict) -> Optional[dict]:
    """후보 규칙 등재 — 같은 (kind, when, then) 이 있으면 두지 않는다.
    id 는 여기서 배번한다(gr-NNNN)."""
    p = rules_file()
    rows: list[dict] = []
    if p.exists():
        try:
            rows = json.loads(p.read_text(encoding="utf-8")).get("rules", [])
        except Exception:
            rows = []
    body = (rule.get("kind"), json.dumps(rule.get("when"), sort_keys=True),
            json.dumps(rule.get("then"), sort_keys=True))
    for r in rows:
        if (r.get("kind"), json.dumps(r.get("when"), sort_keys=True),
                json.dumps(r.get("then"), sort_keys=True)) == body:
            return None
    rule = {**rule, "id": f"gr-{len(rows) + 1:04d}", "created": _now()}
    why = validate(rule)
    if why:
        raise ValueError(why)
    rows.append(rule)
    _write_rules(rows)
    _event({"kind": "등재", "rule": rule["id"], "status": rule["status"]})
    return rule


def set_status(rule_id: str, status: str, by: str, note: str = "") -> dict:
    """상태 전이. 방향 전환(→정착, 정착→)은 사람만 — 의심의 방향을 뒤집는
    행위라 자동화하지 않는다(RULE_LOOP.md §4)."""
    if status not in STATUSES:
        raise ValueError(f"status 는 {STATUSES} 중 하나여야 합니다")
    p = rules_file()
    rows = json.loads(p.read_text(encoding="utf-8")).get("rules", []) \
        if p.exists() else []
    for r in rows:
        if r.get("id") == rule_id:
            cur = r.get("status")
            if status == "정착" and (cur != "규칙" or by != "사람"):
                raise ValueError("정착 승격은 '규칙' 상태에서 사람만 할 수 있습니다")
            if cur == "정착" and by != "사람":
                raise ValueError("정착의 강등은 사람만 할 수 있습니다")
            r["status"] = status
            r["resolved_by"] = by
            _write_rules(rows)
            _event({"kind": "상태변경", "rule": rule_id, "이전": cur,
                    "이후": status, "by": by, "note": note})
            # 정착 승격·강등은 지식 위키의 연대기에도 잇는다 — 기계가 배운
            # 것의 "왜"는 위키가 남긴다(wikilife.py 머리). 부가 기록이라
            # 실패해도 전이는 성립한다.
            try:
                from lawrag.core.rag import wikilife
                wikilife.note_rule_transition(rule_id, cur or "", status,
                                              rationale=r.get("rationale", ""),
                                              by=by)
            except Exception:                          # pragma: no cover
                log.exception("위키 연대기 기록 실패 — 전이는 성립")
            from lawrag.core.rag import approvals
            approvals.safe_record(
                kind="general_rule_status", decision=status,
                effect="rule_activate" if status in ACTIVE else "rule_hold",
                failure="", subject={"rule": rule_id},
                before={"status": cur}, after={"status": status}, note=note,
                actor=by, source={"ledger": "general_rules"})
            return r
    raise ValueError(f"규칙 {rule_id} 가 없습니다")


# ---------------------------------------------------------------- 평가 (연역)
def _ctx(index, edge: dict) -> Optional[dict]:
    """간선 하나의 평가 문맥 — 규칙 수와 무관하게 한 번만 만든다."""
    dst_doc = edge.get("dst_doc")
    if not dst_doc:                    # 문서 안 간선은 resolve 가 이미 하강한다
        return None
    view = index.docs.get(dst_doc)
    if view is None:
        return None
    dst_node = view.by_id.get(edge.get("dst"))
    if dst_node is None:
        return None
    rs = refs.find(edge.get("surface") or "")
    return {"edge": edge, "view": view, "dst_node": dst_node,
            "ref": rs[0] if rs else None,
            "children": refs._children(view)}


def evaluate(index, edge: dict, statuses: tuple = ACTIVE,
             only: Optional[dict] = None) -> Optional[tuple[dict, int]]:
    """첫 번째로 전부 참인 규칙과 그 행동 결과 — (규칙, 새 dst). only 를 주면
    그 규칙 하나만 본다(replay 가 후보를 단독 평가할 때)."""
    rules = [only] if only is not None else \
        [r for r in load() if r.get("status") in statuses]
    if not rules:
        return None
    ctx = _ctx(index, edge)
    if ctx is None:
        return None
    for r in rules:
        if r.get("kind") != "redirect":
            continue
        if not all(PREDICATES[k](ctx, v) for k, v in r["when"].items()):
            continue
        new_dst = ACTIONS[r["then"]["redirect"]](ctx)
        if new_dst is not None and new_dst != edge.get("dst"):
            return r, new_dst
    return None


def apply_edge(index, edge: dict) -> dict:
    """모드에 따라 간선 하나에 규칙을 적용한다 — cross_refs 의 마지막 단.

    on      발동 상태(규칙·정착) 규칙이 옮긴다. 잠정은 그림자 기록만 —
            승격 전에도 증거는 모인다.
    shadow  아무도 안 옮긴다. 전부 그림자 기록.
    off     여기 안 온다(호출부가 모드를 본다) — 와도 그대로 돌려준다.
    """
    m = mode()
    if m == "off":
        return edge
    if edge.get("via") == "규칙":       # 이미 옮겨진 간선 — 중복 발동 금지
        return edge
    hit = evaluate(index, edge, statuses=ACTIVE + ("잠정",))
    if hit is None:
        return edge
    rule, new_dst = hit
    live = m == "on" and rule.get("status") in ACTIVE
    # 사람 우선 — 옮길 좌표가 억제돼 있으면 발동하지 않는다. 사람이 죽인
    # 간선을 규칙이 되살리는 것은 그 규칙의 반례이므로, 옮기는 대신 원장에
    # 적는다(그림자·잠정은 애초에 안 옮기니 반례로 세지 않는다).
    from lawrag.core.rag import verdicts as verdicts_mod       # 순환 의존 회피 — 지연
    if verdicts_mod.is_suppressed(edge.get("src_doc"), edge.get("src"),
                                  edge.get("dst_doc", ""), new_dst):
        if live:
            log_overturn_auto(rule["id"], edge,
                              "억제 간선 재생 시도 — 사람의 끊기가 이긴다")
        return edge
    log_hit(rule, edge, new_dst, 시점="색인" if live else "그림자")
    if not live:
        return edge
    # 규칙_전 — 옮기기 전 착지. 사후 반례 귀속(원장·차단기)이 원좌표로
    # 이루어져야 적중 기록과 짝이 맞는다.
    return {**edge, "dst": new_dst, "via": "규칙", "rule": rule["id"],
            "규칙_전": edge.get("dst")}


# ---------------------------------------------------------------- 적중 원장
_seen_hits: dict = {}                  # 경로 -> 이미 적힌 적중 키 (프로세스 캐시)


def _hit_key(rule_id: str, edge: dict, 시점: str) -> str:
    return (f"{rule_id}|{edge.get('src_doc')}:{edge.get('src')}"
            f"→{edge.get('dst_doc')}:{edge.get('dst')}|{시점}")


def _seen(p: Path) -> set:
    key = str(p)
    if key not in _seen_hits:
        s: set = set()
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("kind") == "적중":
                    t = r.get("대상") or {}
                    s.add(_hit_key(r.get("rule", ""), t, r.get("시점", "")))
                elif r.get("kind") == "뒤집힘" and r.get("auto"):
                    t = r.get("대상") or {}
                    s.add("뒤집힘|" + _hit_key(r.get("rule", ""), t, "자동"))
        _seen_hits[key] = s
    return _seen_hits[key]


def _event(rec: dict) -> None:
    p = hits_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps({**rec, "ts": _now()}, ensure_ascii=False) + "\n")


def log_hit(rule: dict, edge: dict, new_dst, 시점: str) -> bool:
    """적중 한 건 — 같은 (규칙, 간선, 시점)은 한 번만 적는다. 색인은 서명이
    바뀔 때마다 다시 서므로, 중복을 접지 않으면 원장이 재구축 횟수를 센다."""
    p = hits_file()
    target = {"src_doc": edge.get("src_doc"), "src": edge.get("src"),
              "dst_doc": edge.get("dst_doc"), "dst": edge.get("dst")}
    k = _hit_key(rule["id"], target, 시점)
    if k in _seen(p):
        return False
    _event({"kind": "적중", "rule": rule["id"], "대상": target,
            "행동": {"redirect_to": new_dst},
            "시점": 시점, "status": "미검"})
    _seen(p).add(k)
    return True


def resolve_hit(rule_id: str, target: dict, action: str, note: str = "") -> dict:
    """적중의 부검 — 확정(규칙이 옳았다) | 뒤집힘(데이터가 옳았다 — 반례).
    뒤집힘이 쌓이면 규칙 단위 강등을 먼저, 전역 차단기를 다음에 검사한다."""
    if action not in ("확정", "뒤집힘"):
        raise ValueError("action 은 확정|뒤집힘 이어야 합니다")
    _event({"kind": action, "rule": rule_id,
            "대상": {k: target.get(k) for k in
                     ("src_doc", "src", "dst_doc", "dst")},
            "note": note})
    out = {"action": action, "rule": rule_id}
    if action == "뒤집힘":
        _maybe_demote(rule_id)
        out["breaker"] = maybe_trip()
    from lawrag.core.rag import approvals
    approvals.safe_record(
        kind="rule_autopsy", decision=action,
        effect="rule_overturn" if action == "뒤집힘" else "confirmed",
        failure="규칙_반례" if action == "뒤집힘" else "",
        subject={"rule": rule_id, "target": {k: target.get(k) for k in
                 ("src_doc", "src", "dst_doc", "dst")}},
        after={"action": action}, note=note, actor="human",
        source={"ledger": "rule_hits"})
    return out


def log_overturn_auto(rule_id: str, target: dict, note: str) -> bool:
    """시스템이 감지한 반례 — 사람의 행동(끊기·재지정)이 규칙의 산출을 덮었다.

    반례는 일어나는 자리에서 세어져야 한다: 사람은 원장을 모른 채 화면에서
    끊었을 뿐이고, 그 사실을 원장으로 나르는 것은 시스템의 몫이다. 같은
    (규칙, 원좌표 간선)은 한 번만 적는다 — 색인 재구축마다 세지 않는다."""
    t = {k: target.get(k) for k in ("src_doc", "src", "dst_doc", "dst")}
    p = hits_file()
    k = "뒤집힘|" + _hit_key(rule_id, t, "자동")
    if k in _seen(p):
        return False
    _event({"kind": "뒤집힘", "rule": rule_id, "대상": t, "auto": True,
            "note": note})
    _seen(p).add(k)
    _maybe_demote(rule_id)
    maybe_trip()
    return True


def _maybe_demote(rule_id: str) -> None:
    """규칙 단위 자동 강등 — 뒤집힘이 쌓인 그 규칙만 보류로 내린다.
    처벌의 단위는 행위의 단위와 같아야 한다. 정착은 여기서 안 내린다 —
    방향 전환의 해제도 사람 몫이다(set_status 가드가 지킨다)."""
    n = sum(1 for r in _ledger()
            if r.get("kind") == "뒤집힘" and r.get("rule") == rule_id)
    if n < RULE_DEMOTE_N:
        return
    rule = next((r for r in load() if r.get("id") == rule_id), None)
    if rule is not None and rule.get("status") in ("잠정", "규칙"):
        set_status(rule_id, "보류", by="자동(반증)",
                   note=f"뒤집힘 {n}건 누적 — 자동 강등")


def _ledger() -> list[dict]:
    p = hits_file()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def stats() -> dict:
    """규칙별 실적 — 전부 원장의 파생 뷰다. 별도 카운터 없음."""
    per: dict[str, dict] = {}
    for r in _ledger():
        rid = r.get("rule")
        if not rid:
            continue
        g = per.setdefault(rid, {"발동": 0, "그림자": 0, "확정": 0, "뒤집힘": 0,
                                 "scopes": set(), "발동스코프": set(), "last": ""})
        if r.get("kind") == "적중":
            shadow = r.get("시점") == "그림자"
            g["그림자" if shadow else "발동"] += 1
            g["scopes"].add((r.get("대상") or {}).get("dst_doc"))
            if not shadow:
                g["발동스코프"].add((r.get("대상") or {}).get("dst_doc"))
        elif r.get("kind") in ("확정", "뒤집힘"):
            g[r["kind"]] += 1
        g["last"] = r.get("ts", g["last"])
    for g in per.values():
        g["scopes"] = len(g["scopes"] - {None})
        g["발동스코프"] = len(g["발동스코프"] - {None})
    return per


def maybe_trip() -> dict:
    """차단기 — 최근 BREAKER_WINDOW 건 실발동 적중의 뒤집힘율 검사.
    표본 미달이면 안 밟는다. 밟혀도 on→shadow 까지만."""
    led = _ledger()
    recent = [r for r in led
              if r.get("kind") == "적중" and r.get("시점") != "그림자"]
    recent = recent[-BREAKER_WINDOW:]
    if len(recent) < BREAKER_MIN:
        return breaker()
    overturned = {(r.get("rule"), json.dumps(r.get("대상"), sort_keys=True))
                  for r in led if r.get("kind") == "뒤집힘"}
    n = sum(1 for r in recent
            if (r.get("rule"), json.dumps(r.get("대상"), sort_keys=True))
            in overturned)
    ratio = n / len(recent)
    if ratio > BREAKER_RATIO and breaker().get("state") != "강하":
        return trip_breaker(
            f"최근 {len(recent)}건 적중 중 뒤집힘 {n}건({ratio:.0%}) — "
            f"임계 {BREAKER_RATIO:.0%} 초과")
    return breaker()


# ---------------------------------------------------------------- 승격 보고서
def promotable(rule_id: str) -> dict:
    """4기준 보고서 — 판정만, 승격하지 않는다(방향 전환은 사람 몫).
    RULE_LOOP.md §4: 성숙·안정·하중·부검."""
    rule = next((r for r in load() if r.get("id") == rule_id), None)
    if rule is None:
        raise ValueError(f"규칙 {rule_id} 가 없습니다")
    st = stats().get(rule_id, {"발동": 0, "그림자": 0, "확정": 0,
                               "뒤집힘": 0, "scopes": 0, "발동스코프": 0})
    edits = [r for r in _ledger()
             if r.get("kind") == "상태변경" and r.get("rule") == rule_id]
    last_loss = next((r.get("ts") for r in reversed(_ledger())
                      if r.get("kind") == "뒤집힘" and r.get("rule") == rule_id),
                     None)
    # 그림자는 "발동했을 것"의 증거지 옳음의 증거가 아니다 — 그림자 적중은
    # 효과가 없어 뒤집힐 기회 자체가 없으니(생존편향), 성숙은 실발동으로만 센다.
    total = st["발동"]
    ratio = st["뒤집힘"] / max(st["발동"], 1)
    ev = rule.get("evidence") or {}
    report = {
        "rule": rule_id, "status": rule.get("status"),
        "성숙": {"발동": st["발동"], "그림자": st["그림자"],
                 "뒤집힘율": round(ratio, 3), "스코프": st["scopes"]},
        "안정": {"상태변경": len(edits),
                 "예외술어": max(0, len(rule.get("when", {})) - 3)},
        "하중": {"근거사례": len(ev.get("instances") or []),
                 "확정": st["확정"]},
        "부검": {"확정": st["확정"], "뒤집힘": st["뒤집힘"],
                 "마지막_규칙패배": last_loss},
    }
    if rule.get("status") != "규칙":
        report["권고"] = f"해당 없음 — {rule.get('status')} 상태"
    elif total < MIN_EVIDENCE * 2:
        report["권고"] = "미달 — 실발동 실적 부족(그림자는 세지 않는다)"
    elif st.get("발동스코프", 0) < 2:
        report["권고"] = "미달 — 실발동 단일 스코프(문서군 로컬 규칙일 수 있음)"
    elif ratio > BREAKER_RATIO:
        report["권고"] = "역신호 — 뒤집힘율 초과"
    else:
        report["권고"] = "정착 후보"
    return report
