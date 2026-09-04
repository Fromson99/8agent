"""일반 규칙(귀납층) — 평가기·스위치·원장·replay·귀납 (RULE_LOOP.md).

색인은 Index.from_docs 로 값에서 바로 세운다(저장소 없이). 시나리오는 설계
문서의 사례 그대로다: "동규정 제2조제3항" 참조가 후보 유일이라 추정 자동
링크로 제2조(조 전체)에 앉는다 — 이름대조가 아니라서 사슬 하강이 없다.
규칙 gr(표면사슬 하강)이 그 갭을 메운다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from lawrag.core.rag import induce as induce_mod       # noqa: E402
from lawrag.core.rag import replay as replay_mod       # noqa: E402
from lawrag.core.rag import rules as rules_mod         # noqa: E402
from lawrag.core.rag.index import Index                # noqa: E402


# ===========================================================================
# 시험 코퍼스 — 갑규정(제2조에 ①②③, 제3조에 ①) · 을세칙(동규정 참조)
# ===========================================================================

def _doc_a():
    nodes = [
        {"id": 1, "parent": None, "level": 1, "span": [0, 1],
         "surface": "제1조", "title": "목적"},
        {"id": 2, "parent": None, "level": 1, "span": [1, 5],
         "surface": "제2조", "title": "정의"},
        {"id": 3, "parent": 2, "level": 2, "span": [2, 3], "surface": "①", "title": ""},
        {"id": 4, "parent": 2, "level": 2, "span": [3, 4], "surface": "②", "title": ""},
        {"id": 5, "parent": 2, "level": 2, "span": [4, 5], "surface": "③", "title": ""},
        {"id": 6, "parent": None, "level": 1, "span": [5, 7],
         "surface": "제3조", "title": "적용"},
        {"id": 7, "parent": 6, "level": 2, "span": [6, 7], "surface": "①", "title": ""},
    ]
    blocks = [{"idx": i, "text": t} for i, t in enumerate(
        ["제1조 (목적) 이 규정의 목적.", "제2조 (정의) 용어의 뜻.",
         "① 첫째 정의.", "② 둘째 정의.", "③ 셋째 정의.",
         "제3조 (적용) 적용 범위.", "① 적용 세부."])]
    return ("docA", {"name": "갑규정.pdf"}, {"nodes": nodes, "blocks": blocks})


def _doc_b():
    nodes = [{"id": 1, "parent": None, "level": 1, "span": [0, 1],
              "surface": "제1조", "title": "업무"}]
    blocks = [{"idx": 0, "text": "제1조 (업무) 업무는 동규정 제2조제3항에 따라 처리한다."}]
    return ("docB", {"name": "을세칙.pdf"}, {"nodes": nodes, "blocks": blocks})


def _index() -> Index:
    return Index.from_docs([_doc_a(), _doc_b()])


RULE = {"kind": "redirect", "tier": "core", "status": "규칙",
        "when": {"간선.표면사슬": "있음", "간선.도착단위": "조",
                 "도착.사슬하강": "완전"},
        "then": {"redirect": "표면사슬_하강"},
        "falsify_when": "부검 뒤집힘", "rationale": "시험",
        "evidence": {"instances": [], "holdout": [], "qids": []}}


@pytest.fixture()
def store(monkeypatch, tmp_path):
    """규칙·원장을 임시 자리로 — 모듈 캐시도 함께 비운다."""
    monkeypatch.setenv("RAG_RULES_DIR", str(tmp_path / "rules"))
    monkeypatch.setenv("RAG_LOG_DIR", str(tmp_path / "rag"))
    # 위키도 격리 — 정착·강등 전이는 위키 연대기(log.md)에 부가 기록되는데
    # (rules.set_status → wikilife.note_rule_transition), 이걸 안 가리면
    # 시험이 돌 때마다 **실제** data/wiki/wiki/log.md 에 gr-0001 항목이
    # 쌓인다 (2026-08-16~18 실측 — 컴파일 대기가 시험 산물로 오염됐다).
    monkeypatch.setenv("WIKI_STORE", str(tmp_path / "wiki"))
    monkeypatch.delenv("RAG_RULES_MODE", raising=False)
    monkeypatch.delenv("RAG_RULES_AUTOPROMOTE", raising=False)
    from lawrag.core.rag import verdicts as verdicts_mod
    rules_mod._load_cache.clear()
    rules_mod._seen_hits.clear()
    verdicts_mod._rules_cache.clear()
    yield tmp_path
    rules_mod._load_cache.clear()
    rules_mod._seen_hits.clear()
    verdicts_mod._rules_cache.clear()


def _write_rules(rows):
    p = rules_mod.rules_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"rules": rows}, ensure_ascii=False),
                 encoding="utf-8")
    rules_mod._load_cache.clear()


def _cross(idx):
    return [e for e in idx.cross_refs()[0]
            if e["src_doc"] == "docB" and e.get("dst_doc") == "docA"]


# ===========================================================================
# 기준선 — 추정 자동 링크는 조에 머문다 (규칙이 메울 갭의 실재 확인)
# ===========================================================================

def test_baseline_estimated_link_lands_on_article(store):
    edges = _cross(_index())
    assert len(edges) == 1
    assert edges[0]["dst"] == 2 and edges[0]["via"] == "추정"


# ===========================================================================
# 스위치 3단 — off 무변화·무로그 / shadow 기록만 / on 발동
# ===========================================================================

def test_mode_off_is_todays_system(store, monkeypatch):
    monkeypatch.setenv("RAG_RULES_MODE", "off")
    _write_rules([{**RULE, "id": "gr-0001"}])
    edges = _cross(_index())
    assert edges[0]["dst"] == 2 and "rule" not in edges[0]
    assert not rules_mod.hits_file().exists()      # 로드조차 안 한다


def test_mode_shadow_logs_but_does_not_move(store, monkeypatch):
    monkeypatch.setenv("RAG_RULES_MODE", "shadow")
    _write_rules([{**RULE, "id": "gr-0001"}])
    edges = _cross(_index())
    assert edges[0]["dst"] == 2
    led = rules_mod._ledger()
    assert [r["시점"] for r in led if r["kind"] == "적중"] == ["그림자"]


def test_mode_on_fires_with_attribution(store, monkeypatch):
    monkeypatch.setenv("RAG_RULES_MODE", "on")
    _write_rules([{**RULE, "id": "gr-0001"}])
    edges = _cross(_index())
    # 제2조 → ③ (node 5). 발동은 무기명 금지 — via·rule 이 새겨진다.
    assert edges[0]["dst"] == 5
    assert edges[0]["via"] == "규칙" and edges[0]["rule"] == "gr-0001"
    hits = [r for r in rules_mod._ledger() if r["kind"] == "적중"]
    assert hits[0]["시점"] == "색인" and hits[0]["행동"]["redirect_to"] == 5


def test_tentative_rule_shadows_even_when_on(store, monkeypatch):
    """잠정은 on 에서도 안 옮긴다 — 그림자 증거만 쌓는다(승격 전 실적)."""
    monkeypatch.setenv("RAG_RULES_MODE", "on")
    _write_rules([{**RULE, "id": "gr-0001", "status": "잠정"}])
    edges = _cross(_index())
    assert edges[0]["dst"] == 2
    led = [r for r in rules_mod._ledger() if r["kind"] == "적중"]
    assert led and led[0]["시점"] == "그림자"


def test_instance_redirect_beats_general_rule(store, monkeypatch):
    """사람이 그 간선에 직접 확정한 재지정이 규칙을 이긴다 — ②로 보냈다면
    규칙이 ③으로 다시 옮기지 않는다."""
    monkeypatch.setenv("RAG_RULES_MODE", "on")
    _write_rules([{**RULE, "id": "gr-0001"}])
    er = Path(rules_mod.rules_file()).parent / "edge_rules.json"
    er.write_text(json.dumps({"redirect": [
        {"src_doc": "docB", "src": 1, "dst_doc": "docA", "dst": 2,
         "new_dst": 4}]}, ensure_ascii=False), encoding="utf-8")
    edges = _cross(_index())
    assert edges[0]["dst"] == 4 and edges[0]["via"] == "교정"


def test_suppression_beats_rule_and_logs_overturn(store, monkeypatch):
    """사람이 죽인 좌표를 규칙이 되살리지 않는다 — 대신 반례로 원장에 남는다.
    색인을 다시 세워도 같은 반례는 한 번만 센다."""
    monkeypatch.setenv("RAG_RULES_MODE", "on")
    _write_rules([{**RULE, "id": "gr-0001"}])
    er = Path(rules_mod.rules_file()).parent / "edge_rules.json"
    er.write_text(json.dumps({"suppress": [
        {"src_doc": "docB", "src": 1, "dst_doc": "docA", "dst": 5}]},
        ensure_ascii=False), encoding="utf-8")
    edges = _cross(_index())
    assert edges[0]["dst"] == 2 and edges[0]["via"] == "추정"   # 사람이 이긴다
    over = [r for r in rules_mod._ledger() if r["kind"] == "뒤집힘"]
    assert len(over) == 1 and over[0]["auto"] and over[0]["rule"] == "gr-0001"
    _cross(_index())                                            # 재구축
    assert len([r for r in rules_mod._ledger() if r["kind"] == "뒤집힘"]) == 1


def test_post_rule_instance_redirect_beats_rule(store, monkeypatch):
    """규칙이 옮긴 좌표 위의 인스턴스 재지정도 이긴다 — 사람이 규칙의 착지를
    ②로 재교정했다면 그리 가고, 반례는 원좌표(규칙_전)로 귀속된다."""
    monkeypatch.setenv("RAG_RULES_MODE", "on")
    _write_rules([{**RULE, "id": "gr-0001"}])
    er = Path(rules_mod.rules_file()).parent / "edge_rules.json"
    er.write_text(json.dumps({"redirect": [
        {"src_doc": "docB", "src": 1, "dst_doc": "docA", "dst": 5,
         "new_dst": 4}]}, ensure_ascii=False), encoding="utf-8")
    edges = _cross(_index())
    assert edges[0]["dst"] == 4 and edges[0]["via"] == "교정"
    assert "rule" not in edges[0] and "규칙_전" not in edges[0]
    over = [r for r in rules_mod._ledger() if r["kind"] == "뒤집힘"]
    assert len(over) == 1 and over[0]["대상"]["dst"] == 2


def test_rule_auto_demotes_after_overturns(store):
    """뒤집힘 누적은 그 규칙만 보류로 내린다 — 전역 차단기보다 먼저,
    좋은 규칙을 연좌하지 않고."""
    _write_rules([{**RULE, "id": "gr-0001"}])
    for i in range(rules_mod.RULE_DEMOTE_N):
        rules_mod.resolve_hit("gr-0001",
                              {"src_doc": "docB", "src": i,
                               "dst_doc": "docA", "dst": 2}, "뒤집힘")
    rule = next(r for r in rules_mod.load() if r["id"] == "gr-0001")
    assert rule["status"] == "보류" and rule["resolved_by"] == "자동(반증)"
    assert rules_mod.breaker()["state"] == "정상"   # 전역은 안 밟혔다


def test_promotable_ignores_shadow_evidence(store):
    """그림자 적중은 뒤집힐 기회가 없어(효과 없음) 성숙의 증거가 아니다."""
    _write_rules([{**RULE, "id": "gr-0001"}])
    rule = {**RULE, "id": "gr-0001"}
    for i in range(10):
        rules_mod.log_hit(rule, {"src_doc": "docB", "src": i,
                                 "dst_doc": f"docA{i % 3}", "dst": 2},
                          5, 시점="그림자")
    rep = rules_mod.promotable("gr-0001")
    assert rep["권고"].startswith("미달")


def test_load_orders_specific_first_and_reports_overlap(store):
    """first-match 는 파일 순서가 아니라 '좁은 when 우선' 원칙이다.
    중첩은 오류가 아니라 신호 — overlaps 가 쌍을 돌려준다."""
    wide = {**RULE, "id": "gr-0002",
            "when": {"간선.표면사슬": "있음", "도착.사슬하강": "완전"}}
    _write_rules([wide, {**RULE, "id": "gr-0001"}])   # 파일엔 넓은 쪽이 먼저
    rows = rules_mod.load()
    assert rows[0]["id"] == "gr-0001"                 # 술어 3개 쪽이 먼저
    assert rules_mod.overlaps() == [("gr-0001", "gr-0002")]


# ===========================================================================
# 적재 검증 — 닫힌 어휘, 좌표 리터럴 거부, 조용한 실패 금지
# ===========================================================================

def test_unknown_predicate_rejected(store):
    _write_rules([{**RULE, "id": "gr-0001",
                   "when": {"간선.없는술어": "있음"}}])
    assert rules_mod.load() == []


def test_coordinate_literal_rejected(store):
    _write_rules([{**RULE, "id": "gr-0001",
                   "when": {**RULE["when"], "doc_id": "docA"}}])
    assert rules_mod.load() == []
    assert "좌표 리터럴" in rules_mod.validate(
        {**RULE, "id": "x", "when": {**RULE["when"], "doc_id": "docA"}})


# ===========================================================================
# 차단기 — 뒤집힘율 초과 시 on→shadow 자동 강하, 복귀는 사람만
# ===========================================================================

def test_breaker_downgrades_on_to_shadow(store, monkeypatch):
    monkeypatch.setenv("RAG_RULES_MODE", "on")
    assert rules_mod.mode() == "on"
    rules_mod.trip_breaker("시험 강하")
    assert rules_mod.mode() == "shadow"
    rules_mod.reset_breaker("사람 복귀")
    assert rules_mod.mode() == "on"


def test_breaker_trips_on_overturn_ratio(store, monkeypatch):
    monkeypatch.setattr(rules_mod, "BREAKER_MIN", 5)
    rule = {**RULE, "id": "gr-0001"}
    for i in range(10):
        edge = {"src_doc": "docB", "src": i, "dst_doc": "docA", "dst": 2}
        rules_mod.log_hit(rule, edge, 5, 시점="색인")
    for i in range(3):                 # 10건 중 3건 뒤집힘 — 10% 초과
        rules_mod.resolve_hit("gr-0001",
                              {"src_doc": "docB", "src": i,
                               "dst_doc": "docA", "dst": 2}, "뒤집힘")
    assert rules_mod.breaker()["state"] == "강하"


def test_hit_dedup(store):
    rule = {**RULE, "id": "gr-0001"}
    edge = {"src_doc": "docB", "src": 1, "dst_doc": "docA", "dst": 2}
    assert rules_mod.log_hit(rule, edge, 5, 시점="색인") is True
    assert rules_mod.log_hit(rule, edge, 5, 시점="색인") is False
    assert len([r for r in rules_mod._ledger() if r["kind"] == "적중"]) == 1


# ===========================================================================
# 상태 사다리 — 방향 전환은 사람만
# ===========================================================================

def test_settle_requires_human(store):
    _write_rules([{**RULE, "id": "gr-0001"}])
    with pytest.raises(ValueError, match="사람만"):
        rules_mod.set_status("gr-0001", "정착", by="자동(replay)")
    rules_mod.set_status("gr-0001", "정착", by="사람")
    with pytest.raises(ValueError, match="사람만"):
        rules_mod.set_status("gr-0001", "보류", by="자동(반증)")
    rules_mod.set_status("gr-0001", "보류", by="사람")


# ===========================================================================
# replay — 근거 재현 + 충돌 대조
# ===========================================================================

INSTANCE = {"src_doc": "docB", "src": 1, "dst_doc": "docA", "dst": 2,
            "new_dst": 5, "surface": "제2조제3항", "created": "2026-08-01"}


def test_replay_green_on_reproducible_instance(store):
    res = replay_mod.verify({**RULE, "id": "gr-후보"}, _index(),
                            instances=[INSTANCE])
    assert res["green"] and res["reproduced"] == 1 and not res["충돌"]


def test_replay_conflict_with_instance_redirect(store):
    """규칙이 ③으로 보내는데 사람 사례는 ② — 사례상충으로 non-green."""
    er = Path(rules_mod.rules_file()).parent / "edge_rules.json"
    er.parent.mkdir(parents=True, exist_ok=True)
    er.write_text(json.dumps({"redirect": [
        {"src_doc": "docB", "src": 1, "dst_doc": "docA", "dst": 2,
         "new_dst": 4, "surface": "제2조제3항"}]}, ensure_ascii=False),
        encoding="utf-8")
    res = replay_mod.verify({**RULE, "id": "gr-후보"}, _index(),
                            instances=[{**INSTANCE, "new_dst": 4}])
    assert not res["green"]
    assert any(c["종류"] == "사례상충" for c in res["충돌"])


# ===========================================================================
# 귀납 — 군집 → 기계 일반화 → replay → 잠정 등재 (→ 자동 승격)
# ===========================================================================

def _seed_instances():
    rows = [INSTANCE,
            {"src_doc": "docB", "src": 1, "dst_doc": "docA", "dst": 6,
             "new_dst": 7, "surface": "제3조제1항", "created": "2026-08-02"},
            {"src_doc": "docA", "src": 1, "dst_doc": "docA", "dst": 2,
             "new_dst": 3, "surface": "제2조 제1항", "created": "2026-08-03"}]
    er = Path(rules_mod.rules_file()).parent / "edge_rules.json"
    er.parent.mkdir(parents=True, exist_ok=True)
    er.write_text(json.dumps({"redirect": rows}, ensure_ascii=False),
                  encoding="utf-8")


def test_induce_registers_tentative_rule(store):
    _seed_instances()
    report = induce_mod.run(_index(), llm=None)
    assert len(report) == 1 and report[0]["등재"] == "gr-0001"
    rule = rules_mod.load()[0]
    assert rule["status"] == "잠정"
    assert rule["when"] == RULE["when"] and rule["then"] == RULE["then"]
    assert len(rule["evidence"]["instances"]) == 3


def test_induce_autopromotes_when_enabled(store, monkeypatch):
    monkeypatch.setenv("RAG_RULES_AUTOPROMOTE", "on")
    _seed_instances()
    report = induce_mod.run(_index(), llm=None)
    assert report[0].get("승격") == "규칙"
    assert rules_mod.load()[0]["status"] == "규칙"
    # 개정판 pull 흉내 — doc_id 가 바뀌어(sha256 재계산) 사례 행은 전부 죽은
    # 좌표다. 좌표 규칙 없이도 술어가 새 문서에서 그대로 참 → 사람 0회 발동.
    monkeypatch.setenv("RAG_RULES_MODE", "on")
    a, b = _doc_a(), _doc_b()
    idx2 = Index.from_docs([("docA2", a[1], a[2]), ("docB2", b[1], b[2])])
    edges = [e for e in idx2.cross_refs()[0] if e["src_doc"] == "docB2"]
    assert edges[0]["dst"] == 5
    assert edges[0]["via"] == "규칙" and edges[0]["rule"] == "gr-0001"


def test_induce_dedupes_existing_rule(store):
    _seed_instances()
    assert induce_mod.run(_index(), llm=None)[0]["등재"] == "gr-0001"
    assert induce_mod.run(_index(), llm=None)[0]["등재"] is None
    assert len(rules_mod.load()) == 1


def test_induce_excludes_rule_born_instances(store):
    """규칙 산출 위에서 태어난 사례(출처 있음)는 귀납 표본에서 빠진다 —
    자기확증 방지. 제외 사실은 보고에 남는다(조용한 실패 금지)."""
    rows = [INSTANCE,
            {"src_doc": "docB", "src": 1, "dst_doc": "docA", "dst": 6,
             "new_dst": 7, "surface": "제3조제1항", "created": "2026-08-02"},
            {"src_doc": "docA", "src": 1, "dst_doc": "docA", "dst": 2,
             "new_dst": 3, "surface": "제2조 제1항", "created": "2026-08-03"},
            {"src_doc": "docB", "src": 1, "dst_doc": "docA", "dst": 2,
             "new_dst": 4, "surface": "제2조제2항", "created": "2026-08-04",
             "출처": {"rule": "gr-0000"}}]
    er = Path(rules_mod.rules_file()).parent / "edge_rules.json"
    er.parent.mkdir(parents=True, exist_ok=True)
    er.write_text(json.dumps({"redirect": rows}, ensure_ascii=False),
                  encoding="utf-8")
    report = induce_mod.run(_index(), llm=None)
    cluster = next(r for r in report if r.get("등재"))
    assert cluster["사례"] == 3                       # 출처 행은 안 세었다
    assert any(r.get("제외") == 1 for r in report)
