"""canonical Assertion과 조문 참조를 결합한 fail-open 법률 적용관계 shadow.

온톨로지 관계 부재는 제외 근거가 아니다. 명시 시장 충돌만 hard conflict로 표시하고,
나머지는 적용 증명·보조 후보·문맥으로 등급화한다.
"""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from lawrag.research.experiments.governing_anchor_selector import issue_terms
from lawrag.research.experiments.typed_evidence_connections import enclosing_article


_FUNCTION_PATTERNS = {
    "근거·권한": re.compile(r"근거|권한|결의사항|누가\s*결정|어느\s*기관"),
    "제한": re.compile(r"금지|제한|제외|면제|예외|할\s*수\s*없"),
    "절차": re.compile(r"절차|신고|제출|서류|기재|승인"),
    "위임": re.compile(r"위임|준용|세칙으로\s*정"),
    "정의": re.compile(r"정의|뜻|의미|무엇을\s*말"),
    "법률효과": re.compile(r"효과|효력|포함|산입|인정|간주"),
}
_MODALITY_PATTERNS = {
    "의무": re.compile(r"의무|하여야|해야|요구되"),
    "금지": re.compile(r"금지|할\s*수\s*없|아니\s*된다|제외"),
    "허용": re.compile(r"가능|할\s*수\s*있|허용"),
    "절차 문형": re.compile(r"절차|승인|신고|제출"),
    "위임 문형": re.compile(r"위임|대통령령|세칙으로\s*정"),
    "간주": re.compile(r"간주|로\s*본다|으로\s*본다"),
    "정의 문형": re.compile(r"정의|이란|뜻"),
}


def _packed(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(value or "")).casefold()


def _values(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [str(value)] if str(value or "") else []


def question_profile(question: str) -> dict[str, Any]:
    packed = _packed(question)
    market = "kosdaq" if "코스닥" in packed else (
        "kospi" if "유가증권시장" in packed or "코스피" in packed else "")
    functions = [label for label, pattern in _FUNCTION_PATTERNS.items()
                 if pattern.search(question)]
    modalities = [label for label, pattern in _MODALITY_PATTERNS.items()
                  if pattern.search(question)]
    return {
        "market": market,
        "issue_terms": sorted(issue_terms(question)),
        "functions": functions,
        "modalities": modalities,
        "packed": packed,
    }


class ApplicabilityOntology:
    """canonical blob을 source article 좌표로 다시 묶은 읽기 전용 뷰."""

    def __init__(self, index, blob: dict[str, Any]):
        self.index = index
        self.concepts: dict[str, dict[str, Any]] = {}
        for row in blob.get("concepts") or []:
            cid = str(row.get("id") or "")
            if not cid:
                continue
            self.concepts[cid] = row
            self.concepts[f"concept:{cid}"] = row
        self.parents: dict[str, list[str]] = defaultdict(list)
        for row in blob.get("relations") or []:
            if row.get("status") != "active" or row.get("type") != "IS_A":
                continue
            self.parents[str(row.get("src") or "")].append(
                str(row.get("dst") or ""))
        self.by_article: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)
        for assertion in blob.get("assertions") or []:
            if assertion.get("status") != "active":
                continue
            source = assertion.get("source") or {}
            doc_id = str(source.get("doc_id") or "")
            view = index.docs.get(doc_id)
            if view is None:
                continue
            article = enclosing_article(view, source.get("node"))
            if article is not None:
                self.by_article[(doc_id, article)].append(assertion)

    def _concept_surfaces(self, concept_id: str) -> set[str]:
        row = self.concepts.get(concept_id) or {}
        surfaces = {str(row.get("label") or "")}
        surfaces.update(str(value) for value in row.get("aliases") or [])
        for parent in self.parents.get(concept_id, []):
            parent_row = self.concepts.get(parent) or {}
            surfaces.add(str(parent_row.get("label") or ""))
        return {surface for surface in surfaces if surface}

    def assertion_view(self, assertion: dict[str, Any]) -> dict[str, Any]:
        role_surfaces: dict[str, set[str]] = defaultdict(set)
        for role, values in (assertion.get("roles") or {}).items():
            for value in _values(values):
                surfaces = self._concept_surfaces(value)
                role_surfaces[str(role)].update(surfaces or {value})
        basis = assertion.get("candidate_basis") or {}
        for role, values in (basis.get("role_labels") or {}).items():
            role_surfaces[str(role)].update(_values(values))
        return {
            "assertion_id": str(assertion.get("id") or ""),
            "roles": {role: sorted(values) for role, values in role_surfaces.items()},
            "query_cues": [str(value) for value in assertion.get("query_cues") or []],
            "note": str(assertion.get("note") or ""),
        }

    def article_assertions(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        doc_id = str(row.get("doc_id") or "")
        view = self.index.docs.get(doc_id)
        if view is None:
            return []
        article = enclosing_article(view, row.get("node"))
        return [self.assertion_view(value)
                for value in self.by_article.get((doc_id, article), [])]


def _market_conflict(profile: dict[str, Any], document: str) -> str:
    packed = _packed(document)
    if profile["market"] == "kosdaq" and "유가증권시장" in packed:
        return "explicit_kosdaq_vs_kospi_document"
    if profile["market"] == "kospi" and "코스닥" in packed:
        return "explicit_kospi_vs_kosdaq_document"
    return ""


def _alignment(profile: dict[str, Any], assertions: list[dict[str, Any]]) \
        -> dict[str, Any]:
    terms = {_packed(value) for value in profile["issue_terms"] if _packed(value)}
    best = {"assertion_id": "", "matched_roles": [], "matched_terms": [],
            "function_match": False, "modality_match": False, "score": 0}
    for assertion in assertions:
        role_hits = []
        term_hits = set()
        functions = {_packed(value) for value in
                     assertion.get("roles", {}).get("FUNCTION", [])}
        modalities = {_packed(value) for value in
                      assertion.get("roles", {}).get("MODALITY", [])}
        function_match = any(_packed(value) in functions
                             for value in profile["functions"])
        modality_match = any(_packed(value) in modalities
                             for value in profile["modalities"])
        for role in ("ACTOR", "OBJECT", "PREDICATE", "TARGET", "SUBJECT"):
            surfaces = assertion.get("roles", {}).get(role, [])
            packed_surfaces = [_packed(value) for value in surfaces]
            matched = {term for term in terms
                       if any(term in surface or surface in term
                              for surface in packed_surfaces if len(surface) >= 2)}
            if matched:
                role_hits.append(role)
                term_hits.update(matched)
        cue_text = _packed(" ".join(
            assertion.get("query_cues", []) + [assertion.get("note", "")]))
        term_hits.update(term for term in terms if term in cue_text)
        score = 2 * len(role_hits) + len(term_hits)
        score += 2 * int(function_match) + 2 * int(modality_match)
        if score > best["score"]:
            best = {
                "assertion_id": assertion["assertion_id"],
                "matched_roles": role_hits,
                "matched_terms": sorted(term_hits),
                "function_match": function_match,
                "modality_match": modality_match,
                "score": score,
            }
    best["ontology_supported"] = bool(
        len(best["matched_roles"]) >= 2
        or (best["matched_roles"]
            and (best["function_match"] or best["modality_match"])))
    return best


def classify_applicability(question: str, evidence: list[dict[str, Any]],
                           ontology: ApplicabilityOntology) \
        -> list[dict[str, Any]]:
    profile = question_profile(question)
    out = []
    for row in evidence:
        connection = dict(row.get("typed_connection") or {})
        assertions = ontology.article_assertions(row)
        alignment = _alignment(profile, assertions)
        conflict = _market_conflict(profile, str(row.get("document") or ""))
        strict = bool(connection.get("conclusion_eligible"))
        support = bool(connection.get("support_eligible"))
        incident_typed = bool(set(connection.get("incident_relations") or []) & {
            "배제", "준용", "위임", "수임", "근거", "정의", "의제"})
        if conflict:
            status = "hard_conflict"
        elif strict:
            status = "applicable"
        # E1과 분리된 selected pair는 감사 신호다. 간선 하나만으로 모든 pair를
        # 결론 후보로 올리면 관계 fan-out이 가지치기를 무효화한다. 기존 구조 근거나
        # source Assertion 정합이 함께 있을 때만 support로 승격한다.
        elif support or alignment["ontology_supported"]:
            status = "support"
        else:
            status = "context"
        copy = dict(row)
        copy["applicability"] = {
            "status": status,
            "conclusion_candidate": status in {"applicable", "support"},
            "hard_conflict": conflict,
            "typed_strict": strict,
            "typed_support": support,
            "incident_typed": incident_typed,
            "assertion_count": len(assertions),
            "ontology_alignment": alignment,
            "profile": {key: profile[key] for key in
                        ("market", "issue_terms", "functions", "modalities")},
        }
        out.append(copy)
    return out
