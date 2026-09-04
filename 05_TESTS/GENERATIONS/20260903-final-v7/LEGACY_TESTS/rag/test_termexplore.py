from lawrag.core.rag.index import Index
from lawrag.core.rag import termexplore


def _index():
    return Index.from_docs([
        ("law", {"name": "시험법"}, {
            "nodes": [{"id": 1, "parent": None, "level": 1,
                       "surface": "제1조", "title": "담당자", "span": [0, 1]}],
            "blocks": [{"idx": 0,
                        "text": "회사는 관리업무를 담당하는 상근이사 한 명을 담당자로 지정한다.",
                        "kind": "text"}],
        }),
        ("form", {"name": "제출서식"}, {
            "nodes": [{"id": 1, "parent": None, "level": 1,
                       "surface": "서식", "title": "인적사항", "span": [0, 1]}],
            "blocks": [{"idx": 0, "text": "담당자 성명:", "kind": "text"}],
        }),
    ])


class _LLM:
    def __init__(self):
        self.calls = []

    def structured(self, kind, system, user, schema, **_kwargs):
        self.calls.append((kind, system, user, schema))
        if kind == "rag.term_explore.extract":
            return {"anchor_terms": ["담당자", "질문에 없는 법령"],
                    "condition_terms": [],
                    "fallback_terms": []}
        ids = schema["properties"]["picks"]["items"]["enum"]
        # 원문 지정 규정이 든 메뉴만 선택한다.
        if "상근이사 한 명을 담당자로 지정" in user:
            return {"picks": ids[:1], "reason": "정의를 직접 규정"}
        return {"picks": [], "reason": "단순 서식"}


class _NumericLLM(_LLM):
    def structured(self, kind, system, user, schema, **kwargs):
        if kind == "rag.term_explore.extract":
            return {"anchor_terms": ["45일", "반기보고서"],
                    "condition_terms": [], "fallback_terms": []}
        return super().structured(kind, system, user, schema, **kwargs)


class _EmptyLLM(_LLM):
    def structured(self, kind, system, user, schema, **kwargs):
        self.calls.append((kind, system, user, schema))
        if kind == "rag.term_explore.extract":
            return {"anchor_terms": [], "condition_terms": [],
                    "fallback_terms": []}
        return {"picks": [], "reason": "선택 없음"}


class _OperationLLM(_LLM):
    def structured(self, kind, system, user, schema, **kwargs):
        self.calls.append((kind, system, user, schema))
        if kind == "rag.term_explore.extract":
            return {"anchor_terms": ["채무조정"], "condition_terms": [],
                    "fallback_terms": [], "operation_terms": ["겸직업무"]}
        ids = schema["properties"]["picks"]["items"]["enum"]
        if "겸직업무를 담당해서는 아니 된다" in user:
            return {"picks": ids[-1:], "reason": "법적 업무유형의 직접 규율"}
        return {"picks": [], "reason": "표면 용어만 같은 다른 문맥"}


def test_extractor_rejects_model_terms_not_present_in_question():
    plan = termexplore.extract_terms(_LLM(), "담당자는 누구인가?")

    assert plan.terms == ("담당자",)
    assert plan.anchor_terms == ("담당자",)
    assert plan.condition_terms == ()
    assert plan.fallback_terms == ()
    assert plan.rejected == ("질문에 없는 법령",)


def test_extractor_rejects_numeric_expression_without_term_hardcoding():
    plan = termexplore.extract_terms(
        _NumericLLM(), "반기보고서는 45일 이내에 제출하는가?")

    assert plan.terms == ("반기보고서",)
    assert plan.rejected == ("45일",)


def test_semantic_operation_is_grounded_in_real_corpus_before_seed_promotion():
    idx = Index.from_docs([
        ("noise", {"name": "일반규정"}, {
            "nodes": [{"id": 1, "parent": None, "surface": "제1조",
                       "title": "채무조정", "span": [0, 1]}],
            "blocks": [{"idx": 0, "node": 1,
                        "text": "채무조정 신청서를 제출한다."}],
        }),
        ("law", {"name": "지배구조법"}, {
            "nodes": [{"id": 29, "parent": None, "surface": "제29조",
                       "title": "겸직 금지", "span": [0, 1]}],
            "blocks": [{"idx": 0, "node": 29,
                        "text": "준법감시인은 겸직업무를 담당해서는 아니 된다."}],
        }),
    ])

    sections, meta = termexplore.retrieve(
        idx, "채무조정 전담을 겸직할 수 있는가?", llm=_OperationLLM(), cap=4)

    assert ("법", 29) not in {(row.doc, row.node) for row in sections}
    assert ("지배구조법", 29) in {(row.doc, row.node) for row in sections}
    assert meta["term_plan"]["grounded_operation_terms"] == ["겸직업무"]
    assert meta["semantic_operation_candidate_branches"] == 1


def test_exact_fulltext_search_keeps_definition_and_mention_as_branches():
    branches = termexplore.search_all(_index(), ("담당자",))

    assert {(row.doc, row.path) for row in branches} == {
        ("시험법", "제1조 담당자"), ("제출서식", "서식 인적사항")}
    assert any("상근이사 한 명" in row.body for row in branches)


def test_retrieve_shows_actual_body_and_returns_closed_selected_branch():
    llm = _LLM()
    sections, meta = termexplore.retrieve(
        _index(), "담당자는 누구인가?", llm=llm, cap=1)

    assert [(row.doc, row.node) for row in sections] == [("시험법", 1)]
    assert "상근이사 한 명" in sections[0].text
    assert meta["selected"][0]["mandatory_reason"] == "selected-exact-seed"
    assert meta["concept_reverse_match"] is False
    assert meta["embedding"] is False
    assert meta["strategy"] == "anchor_scoped_intersection_structural_expansion"
    select_call = next(row for row in llm.calls if ".select." in row[0])
    assert "상근이사 한 명을 담당자로 지정" in select_call[2]
    assert any(".document." in row[0] for row in llm.calls)
    # 정확 seed는 이미 닫힌 메뉴 선택을 통과했으므로 최종 검토가 다시 삭제하지 않는다.
    assert not any(".review." in row[0] for row in llm.calls)


def test_explicit_article_is_mandatory_seed_even_without_term_hit():
    llm = _EmptyLLM()
    sections, meta = termexplore.retrieve(
        _index(), "시험법 제1조의 내용은?", llm=llm, cap=4)

    assert [(row.doc, row.node) for row in sections] == [("시험법", 1)]
    assert meta["structure"]["locators"] == ["제1조"]
    assert meta["selected"][0]["origin"] == "explicit-coordinate"
    assert meta["selected"][0]["mandatory"] is True


def test_search_all_법률_명사구의_관형격_조사_생략을_정규화한다():
    idx = Index.from_docs([("commercial", {"name": "상법"}, {
        "nodes": [{"id": 1, "parent": None, "level": 1,
                   "surface": "제341조의4", "title": "자기주식의 소각의무 등",
                   "span": [0, 1]}],
        "blocks": [{"idx": 0, "text": "회사는 자기주식의 소각의무를 부담한다.",
                    "kind": "text"}],
    })])

    rows = termexplore.search_all(idx, ("자기주식 소각의무",))

    assert [(row.doc, row.node) for row in rows] == [("상법", 1)]


def test_condition_search_is_restricted_to_anchor_documents():
    idx = Index.from_docs([
        ("anchored", {"name": "대상법"}, {
            "nodes": [{"id": 1, "parent": None, "level": 1,
                       "surface": "제1조", "title": "관리자 처분", "span": [0, 1]}],
            "blocks": [{"idx": 0, "text": "관리자가 재산을 처분한다.", "kind": "text"}],
        }),
        ("noise", {"name": "일반법"}, {
            "nodes": [{"id": 1, "parent": None, "level": 1,
                       "surface": "제1조", "title": "처분", "span": [0, 1]}],
            "blocks": [{"idx": 0, "text": "그 밖의 처분 절차를 정한다.", "kind": "text"}],
        }),
    ])

    anchors = termexplore.search_all(idx, ("관리자",))
    scoped = termexplore.search_all(
        idx, ("관리자", "처분"), doc_ids={row.doc_id for row in anchors})

    assert {row.doc for row in scoped} == {"대상법"}
    assert scoped[0].terms == ("관리자", "처분")


def test_structural_expansion_opens_adjacent_article_without_embedding():
    idx = Index.from_docs([("law", {"name": "시험법", "kind": "law"}, {
        "nodes": [
            {"id": 1, "parent": None, "level": 1,
             "surface": "제1조", "title": "원칙", "span": [0, 1]},
            {"id": 2, "parent": None, "level": 1,
             "surface": "제2조", "title": "예외", "span": [1, 2]},
        ],
        "blocks": [
            {"idx": 0, "text": "관리자의 권한은 제2조에 따른다.", "kind": "text"},
            {"idx": 1, "text": "특별한 경우에는 권한을 제한한다.", "kind": "text"},
        ],
    })])
    seed = termexplore.search_all(idx, ("관리자",))[0]

    expanded, meta = termexplore.expand_structural(idx, [seed], ("관리자",))

    assert any("제2조 예외" in row.path for row in expanded)
    assert meta["expanded_count"] == 1
    assert expanded[0].origin.startswith(("relation:", "neighbor:"))
    assert expanded[0].mandatory is True
    assert expanded[0].mandatory_reason == "relation:BASED_ON"
