from lawrag.core.rag import companion_recovery, relation_navigation, relations
from lawrag.core.rag.index import Index


def _index():
    def doc(article, title, text):
        return {
            "nodes": [{"id": 1, "parent": None, "level": 1,
                       "surface": article, "title": title, "span": [0, 1]}],
            "blocks": [{"idx": 0, "node": 1, "text": text, "kind": "text"}],
        }
    return Index.from_docs([
        ("law2", {"name": "지배구조법", "kind": "law"},
         doc("제2조", "정의", "주요주주란 대통령령으로 정하는 자를 말한다")),
        ("decree4", {"name": "지배구조법 시행령", "kind": "law"},
         doc("제4조", "주요주주의 범위", "주요주주의 범위를 정한다")),
        ("law29", {"name": "지배구조법", "kind": "law"},
         doc("제29조", "겸직 금지 등", "준법감시인은 다른 업무를 겸직할 수 없다")),
        ("decree24", {"name": "지배구조법 시행령", "kind": "law"},
         doc("제24조", "겸직 금지의 세부업무", "준법감시인의 겸직 금지 업무")),
        ("debt", {"name": "개인채무자보호법", "kind": "law"},
         doc("제9조", "채무조정", "채무조정 전담인력의 업무")),
    ])


def _edge(src, dst):
    return relations.SectionRelation(
        "DELEGATES_TO", src, 1, dst, 1,
        {"status": "resolved", "provenance": ["law.go.kr:lsDelegated"],
         "link": "대통령령"})


def test_D신규좌표에서_공식위임을_한번더_소비한다(monkeypatch):
    idx = _index()
    edge = _edge("law2", "decree4")
    monkeypatch.setattr(
        relation_navigation.relations, "incident",
        lambda _idx, doc, node: ((edge,), ()) if doc == "law2" else ((), ()))

    rows, meta = companion_recovery.bounded_delegation_hop(
        idx, [("law2", 1)], "주요주주에 해당하는지", cap=2)

    assert [row.coordinate for row in rows] == [("decree4", 1)]
    assert meta["selected"][0]["graph_kind"] == "DELEGATES_TO"
    assert rows[0].mandatory is True


def test_bare_negative는_카드좌표나_본문없이_governing법을_재검색한다(monkeypatch):
    idx = _index()
    monkeypatch.setattr(companion_recovery.wikictx, "spot", lambda _q: [{
        "slug": "쟁점/겸직의-경계",
        "title": "겸직의 경계",
        "axis": "준법감시인의 다른 업무 겸직과 이해상충",
        "why": ["준법감시인"],
        "provisions": ["절대로 사용하면 안 되는 제29조"],
        "text": "절대로 사용하면 안 되는 카드 본문",
    }])
    edge = _edge("law29", "decree24")
    monkeypatch.setattr(
        relation_navigation.relations, "incident",
        lambda _idx, doc, node: ((edge,), ()) if doc == "law29" else ((), ()))

    rows, meta = companion_recovery.governing_axis_feedback(
        idx,
        "상호저축은행의 준법감시인이 채무조정 전담인력 업무를 수행할 수 있는지",
        answer_incorrect=True,
        direct_cap=2,
        companion_cap=2,
    )

    coordinates = {row.coordinate for row in rows}
    assert ("law29", 1) in coordinates
    assert ("decree24", 1) in coordinates
    assert meta["forbidden_fields_used"] == []
    assert set(meta["spots"][0]) == {
        "slug", "title", "axis", "matched_triggers"}
    assert "provisions" not in str(meta)
    assert "카드 본문" not in str(meta)


def test_부정피드백이_없으면_자가복구를_열지_않는다():
    rows, meta = companion_recovery.governing_axis_feedback(
        _index(), "준법감시인 질문", answer_incorrect=False)
    assert rows == []
    assert meta["ran"] is False


def test_add_only는_기존좌표를_삭제하지_않고_빈슬롯만_쓴다():
    floor = [("a", 1), ("b", 2)]
    assert companion_recovery.add_only_coordinates(
        floor, [("b", 2), ("c", 3)], cap=3) == [
            ("a", 1), ("b", 2), ("c", 3)]


def test_role_predicate_router는_행위자와_판단술어를_검증해_bundle을_연다(
        monkeypatch):
    idx = _index()
    monkeypatch.setattr(companion_recovery.wikictx, "spot", lambda _q, limit=2: [{
        "slug": "쟁점/겸직의-경계",
        "title": "겸직의 경계",
        "why": ["준법감시인"],
        "axis": "준법감시인의 다른 업무 겸직과 이해상충",
        "provisions": ["「지배구조법」 제29조", "「지배구조법 시행령」 제24조"],
        "text": "이 카드 본문은 절대로 읽지 않아야 한다",
    }])
    monkeypatch.setattr(
        companion_recovery.general_search, "search_keywords",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("general lexical search must not run")))

    rows, meta = companion_recovery.role_predicate_governing_feedback(
        idx,
        "상호저축은행의 준법감시인이 채무조정 전담인력 업무를 수행할 수 있는지",
        answer_incorrect=True,
    )

    assert [row.coordinate for row in rows] == [("law29", 1), ("decree24", 1)]
    assert meta["general_lexical_search_calls"] == 0
    assert meta["forbidden_fields_used"] == []
    assert "카드 본문" not in str(meta)
    assert all(
        row["validation"]["accepted"]
        for row in meta["cards"][0]["hypotheses"])


def test_role_predicate_router는_행위자만_있으면_열리지_않는다(monkeypatch):
    idx = _index()
    monkeypatch.setattr(companion_recovery.wikictx, "spot", lambda _q, limit=2: [{
        "slug": "쟁점/겸직의-경계", "title": "겸직의 경계",
        "why": ["준법감시인"], "axis": "겸직",
        "provisions": ["「지배구조법」 제29조"],
    }])

    rows, meta = companion_recovery.role_predicate_governing_feedback(
        idx, "준법감시인의 법적 지위가 무엇인지", answer_incorrect=True)

    assert rows == []
    assert meta["cards"][0]["actor_roles"] == ["준법감시인"]
    assert meta["cards"][0]["predicate_families"] == []
    assert meta["cards"][0]["gate_open"] is False


def test_role_predicate_router는_판단술어만_있으면_열리지_않는다(monkeypatch):
    idx = _index()
    monkeypatch.setattr(companion_recovery.wikictx, "spot", lambda _q, limit=2: [{
        "slug": "쟁점/겸직의-경계", "title": "겸직의 경계",
        "why": ["겸직"], "axis": "겸직",
        "provisions": ["「지배구조법」 제29조"],
    }])

    rows, meta = companion_recovery.role_predicate_governing_feedback(
        idx, "다른 업무를 겸직할 수 있는지", answer_incorrect=True)

    assert rows == []
    assert meta["cards"][0]["actor_roles"] == []
    assert meta["cards"][0]["predicate_families"] == ["role_compatibility"]
    assert meta["cards"][0]["gate_open"] is False


def test_role_predicate_router는_피드백없이는_열리지_않는다():
    rows, meta = companion_recovery.role_predicate_governing_feedback(
        _index(), "준법감시인이 업무를 수행할 수 있는지",
        answer_incorrect=False)
    assert rows == []
    assert meta["ran"] is False
