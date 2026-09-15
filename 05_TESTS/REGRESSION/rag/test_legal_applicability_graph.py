from types import SimpleNamespace

from lawrag.research.experiments import legal_applicability_graph as graph


class _Index:
    def __init__(self):
        self.docs = {"D": SimpleNamespace(by_id={
            1: {"id": 1, "parent": None, "family": "kr_article",
                "surface": "제1조"},
            2: {"id": 2, "parent": 1, "family": "kr_clause",
                "surface": "제1항"},
            10: {"id": 10, "parent": None, "family": "kr_article",
                 "surface": "제2조"},
        })}


def _blob():
    return {
        "concepts": [
            {"id": "actor", "label": "상장주선인", "aliases": []},
            {"id": "act", "label": "의무인수", "aliases": []},
            {"id": "norm.function.authority", "label": "근거·권한", "aliases": []},
            {"id": "norm.modality.obligation", "label": "의무", "aliases": []},
        ],
        "relations": [],
        "assertions": [{
            "id": "A1", "status": "active",
            "roles": {
                "ACTOR": ["concept:actor"], "PREDICATE": ["concept:act"],
                "FUNCTION": ["concept:norm.function.authority"],
                "MODALITY": ["concept:norm.modality.obligation"],
            },
            "source": {"doc_id": "D", "node": 2},
            "query_cues": ["상장주선인의 의무인수"],
        }],
    }


def _evidence(document="코스닥시장 상장규정"):
    return [{
        "id": "E1", "doc_id": "D", "node": 1, "document": document,
        "path": "제1조 상장주선인의 의무", "role": "keyword-bm25",
        "typed_connection": {
            "conclusion_eligible": False, "support_eligible": False,
            "incident_relations": [],
        },
    }]


def test_assertion_roles_promote_candidate_without_treating_absence_as_conflict():
    ontology = graph.ApplicabilityOntology(_Index(), _blob())
    rows = graph.classify_applicability(
        "상장주선인의 의무인수 근거는?", _evidence(), ontology)
    app = rows[0]["applicability"]
    assert app["status"] == "support"
    assert app["ontology_alignment"]["ontology_supported"]
    assert set(app["ontology_alignment"]["matched_roles"]) == {"ACTOR", "PREDICATE"}


def test_explicit_market_conflict_is_the_only_hard_prune():
    ontology = graph.ApplicabilityOntology(_Index(), _blob())
    rows = graph.classify_applicability(
        "코스닥시장 상장주선인의 의무는?",
        _evidence("유가증권시장 상장규정"), ontology)
    assert rows[0]["applicability"]["status"] == "hard_conflict"
    assert not rows[0]["applicability"]["conclusion_candidate"]


def test_missing_assertion_stays_context_not_hard_conflict():
    ontology = graph.ApplicabilityOntology(_Index(), {
        "concepts": [], "relations": [], "assertions": []})
    rows = graph.classify_applicability("요건은?", _evidence(), ontology)
    assert rows[0]["applicability"]["status"] == "context"
    assert not rows[0]["applicability"]["hard_conflict"]
