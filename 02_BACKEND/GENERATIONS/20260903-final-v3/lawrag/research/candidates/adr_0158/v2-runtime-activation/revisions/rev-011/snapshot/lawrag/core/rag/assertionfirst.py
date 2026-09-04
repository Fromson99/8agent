"""임베딩 없이 정본 표현에서 Assertion 좌표로 가는 구조 검색.

원문 조문을 검색하지 않는다. active Concept의 label·alias·definition·example과
active Assertion의 query_cue만 역색인한다. 질문의 정확 구와 Kiwi 형태소가 정본
표현에 걸리면 Concept→Assertion 또는 cue→Assertion 간선을 따라 원문 좌표를 연다.
질문에서 추측한 역할은 쓰지 않고 Assertion에 저장된 역할을 그대로 반환한다.
"""

from __future__ import annotations

import re
import json
import math
import time
from dataclasses import dataclass
from functools import lru_cache

from lawrag.core.domain_graph.tier1 import Tier1Registry
from lawrag.core.domain_graph import normative, spanparts
from lawrag.core.rag.answer import Section
from lawrag.core.rag import exploration
from lawrag.core.rag.controls import value as control_value
from lawrag.core.rag.index import Index


CONCEPT_TOKEN_DF_MAX = 360
ASSERTION_TOKEN_DF_MAX = 480
MIN_PHRASE_CHARS = 2
NAVIGATION_PAGE_SIZE = int(control_value("assertion_tree.page_size"))
FAMILY_CANDIDATES_MAX = int(control_value("assertion_tree.family_candidates_max"))
FAMILY_PICKS_MAX = int(control_value("assertion_tree.families_max"))
DOCUMENT_PICKS_MAX = int(control_value("assertion_tree.documents_max"))
_CONTENT_TAGS = ("N", "VV", "VA", "XR", "SL", "SN")
_PACK = re.compile(r"[^0-9A-Za-z가-힣]+")


def _pack(value: str) -> str:
    return _PACK.sub("", str(value or "")).casefold()


def _fallback_tokens(value: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        token.casefold() for token in re.findall(r"[0-9A-Za-z가-힣]+", value or "")
        if len(token) >= 2))


@lru_cache(maxsize=1)
def _kiwi():
    from kiwipiepy import Kiwi

    return Kiwi()


def _token_values(rows) -> list[tuple[str, ...]]:
    """Kiwi가 없으면 실행을 막지 않고 보수적인 공백 토큰으로 내려간다."""
    texts = list(rows)
    try:
        kiwi = _kiwi()
        out = []
        for tokens in kiwi.tokenize(texts):
            values = []
            for token in tokens:
                if not (token.tag.startswith(_CONTENT_TAGS)
                        or token.tag in _CONTENT_TAGS):
                    continue
                value = str(token.lemma or token.form).casefold()
                if len(value) < 2 and not token.tag.startswith(("SL", "SN")):
                    continue
                values.append(value)
            out.append(tuple(dict.fromkeys(values)))
        return out
    except Exception:
        return [_fallback_tokens(text) for text in texts]


@dataclass(frozen=True)
class AssertionHit:
    assertion_id: str
    doc_id: str
    node: object
    roles: tuple[str, ...]
    concepts: tuple[str, ...]
    evidence: tuple[dict, ...]
    strength: int
    facet_score: int = 0

    @property
    def coordinate(self) -> tuple[str, object]:
        return self.doc_id, self.node


class AssertionIndex:
    def __init__(self, registry: Tier1Registry):
        self.registry = registry
        self.concept_phrases: dict[str, set[str]] = {}
        self.cue_phrases: dict[str, set[str]] = {}
        self.concept_tokens: dict[str, set[str]] = {}
        self.cue_tokens: dict[str, set[str]] = {}
        self.relations: dict[str, set[str]] = {}
        self.max_phrase_chars = MIN_PHRASE_CHARS
        self._build()

    def _build(self) -> None:
        token_texts: list[str] = []
        token_owners: list[tuple[str, str]] = []
        for cid, concept in self.registry.active_concepts.items():
            texts = (*concept.surfaces, *concept.definitions)
            for text in texts:
                packed = _pack(text)
                if len(packed) >= MIN_PHRASE_CHARS:
                    self.concept_phrases.setdefault(packed, set()).add(cid)
                    self.max_phrase_chars = max(self.max_phrase_chars, len(packed))
                token_texts.append(text)
                token_owners.append(("concept", cid))
        for assertion in self.registry.active_assertions:
            for cue in assertion.query_cues:
                packed = _pack(cue)
                if len(packed) >= MIN_PHRASE_CHARS:
                    self.cue_phrases.setdefault(packed, set()).add(assertion.id)
                    self.max_phrase_chars = max(self.max_phrase_chars, len(packed))
                token_texts.append(cue)
                token_owners.append(("assertion", assertion.id))
        for owner, tokens in zip(token_owners, _token_values(token_texts)):
            kind, object_id = owner
            target = self.concept_tokens if kind == "concept" else self.cue_tokens
            for token in tokens:
                target.setdefault(token, set()).add(object_id)
        self.concept_tokens = {
            token: ids for token, ids in self.concept_tokens.items()
            if len(ids) <= CONCEPT_TOKEN_DF_MAX
        }
        self.cue_tokens = {
            token: ids for token, ids in self.cue_tokens.items()
            if len(ids) <= ASSERTION_TOKEN_DF_MAX
        }
        for relation in self.registry.active_relations:
            if relation.type not in {"IS_A", "EQUIVALENT_TO", "REALIZES", "SATISFIES"}:
                continue
            self.relations.setdefault(relation.src, set()).add(relation.dst)
            self.relations.setdefault(relation.dst, set()).add(relation.src)

    def _exact(self, packed_query: str) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
        concepts: dict[str, set[str]] = {}
        assertions: dict[str, set[str]] = {}
        for start in range(len(packed_query)):
            end_max = min(len(packed_query), start + self.max_phrase_chars)
            for end in range(start + MIN_PHRASE_CHARS, end_max + 1):
                phrase = packed_query[start:end]
                for cid in self.concept_phrases.get(phrase, ()):
                    concepts.setdefault(cid, set()).add(phrase)
                for aid in self.cue_phrases.get(phrase, ()):
                    assertions.setdefault(aid, set()).add(phrase)
        return concepts, assertions

    def search(self, index: Index, question: str, *,
               scope: frozenset[tuple[str, object]] | None = None) \
            -> list[AssertionHit]:
        packed = _pack(question)
        exact_concepts, exact_assertions = self._exact(packed)
        question_tokens = set(_token_values([question])[0])
        concept_evidence: dict[str, list[dict]] = {}
        assertion_evidence: dict[str, list[dict]] = {}

        for cid, phrases in exact_concepts.items():
            concept_evidence.setdefault(cid, []).extend(
                {"kind": "concept-exact", "value": phrase, "strength": 5}
                for phrase in sorted(phrases))
        for aid, phrases in exact_assertions.items():
            assertion_evidence.setdefault(aid, []).extend(
                {"kind": "cue-exact", "value": phrase, "strength": 5}
                for phrase in sorted(phrases))
        for token in sorted(question_tokens):
            for cid in self.concept_tokens.get(token, ()):
                concept_evidence.setdefault(cid, []).append(
                    {"kind": "concept-token", "value": token, "strength": 2})
            for aid in self.cue_tokens.get(token, ()):
                assertion_evidence.setdefault(aid, []).append(
                    {"kind": "cue-token", "value": token, "strength": 3})

        # 정본 관계는 한 걸음만 연다. 관계로 열린 Concept도 실제 Assertion 간선이
        # 있어야 좌표가 되므로 구조 밖의 자유 연상은 생기지 않는다.
        for cid in list(concept_evidence):
            concept = self.registry.active_concepts.get(cid)
            if concept is not None and concept.type in normative.FACET_TYPES:
                continue
            for related in self.relations.get(cid, ()):
                concept_evidence.setdefault(related, []).append({
                    "kind": "concept-relation", "value": cid, "strength": 1})

        facet_evidence = {
            cid: evidence for cid, evidence in concept_evidence.items()
            if self.registry.active_concepts[cid].type in normative.FACET_TYPES
        }
        content_evidence = {
            cid: evidence for cid, evidence in concept_evidence.items()
            if self.registry.active_concepts[cid].type not in normative.FACET_TYPES
        }
        for cid, evidence in content_evidence.items():
            for aid in self.registry.concept_assertions.get(cid, ()):
                assertion_evidence.setdefault(aid, []).extend({
                    **row, "concept_id": cid,
                } for row in evidence)

        hits = []
        assertions = self.registry.active_assertions_by_id
        for aid, evidence in assertion_evidence.items():
            assertion = assertions.get(aid)
            if assertion is None:
                continue
            doc_id = str(assertion.source.get("doc_id") or "")
            node = assertion.source.get("node")
            coordinate = (doc_id, node)
            if (not doc_id or node is None or doc_id not in index.docs
                    or node not in index.docs[doc_id].by_id
                    or not index.in_scope(doc_id)
                    or (scope is not None and coordinate not in scope)):
                continue
            concepts = list(dict.fromkeys(
                str(row.get("concept_id")) for row in evidence
                if row.get("concept_id")))
            facet_score = 0
            facet_rows = []
            for role in ("MODALITY", "FUNCTION"):
                requested = {
                    cid for cid in facet_evidence
                    if role == normative.FACET_ROLE_BY_AXIS[
                        "mode" if self.registry.active_concepts[cid].type == "modality"
                        else "function"]
                }
                if not requested:
                    continue
                actual = set(assertion.roles.get(role) or ())
                matched = requested & actual
                if matched:
                    # 양태/기능은 닫힌 메뉴의 명시 신호로 제공하되 전역 문서·조문
                    # 점수는 바꾸지 않는다. 51건 실험에서 +6 보너스가 자기주식
                    # 신설 조문은 살렸지만 평가·기간 질문을 흔들어 50→48/70으로
                    # 회귀했다. subject/predicate 후보가 충분히 좁아진 후의 재정렬은
                    # 별도 실험으로 남긴다.
                    for cid in sorted(matched):
                        facet_rows.append({
                            "kind": "facet-match", "value": cid,
                            "concept_id": cid, "strength": 0,
                        })
                        if cid not in concepts:
                            concepts.append(cid)
                elif actual:
                    labels = "/".join(sorted(
                        self.registry.active_concepts[cid].label for cid in requested))
                    facet_rows.append({
                        "kind": "facet-conflict", "value": f"{role}:{labels}",
                        "strength": 0,
                    })
            evidence = [*evidence, *facet_rows]
            concepts = tuple(concepts)
            roles = tuple(sorted(
                role for role, ids in assertion.roles.items()
                if not concepts or any(cid in ids for cid in concepts)))
            unique = {(row["kind"], row["value"], row.get("concept_id")): row
                      for row in evidence}
            rows = tuple(sorted(unique.values(), key=lambda row: (
                -int(row["strength"]), row["kind"], row["value"])))
            hits.append(AssertionHit(
                aid, doc_id, node, roles, concepts, rows,
                max(0, sum(int(row["strength"]) for row in rows) + facet_score),
                facet_score,
            ))
        return sorted(hits, key=lambda row: (
            -row.strength,
            row.doc_id, str(row.node), row.assertion_id))


def current(registry: Tier1Registry) -> AssertionIndex:
    cached = getattr(registry, "_assertion_first_index", None)
    if cached is None:
        cached = AssertionIndex(registry)
        registry._assertion_first_index = cached
    return cached


_NAVIGATE_SYSTEM = (
    "너는 법률 근거 트리의 닫힌 메뉴를 고르는 탐색자다. 새 검색어·법령·조문을 "
    "만들지 말고 입력된 O id만 고른다. 질문의 행위자·대상·행위·조건·예외가 함께 "
    "맞는 가지를 고르고, 단어 하나만 같은 가지는 버린다. 답에 여러 근거가 필요하면 "
    "복수 선택할 수 있으며 적합한 가지가 없으면 picks를 비운다."
)


def _structure_scope(index: Index, anchors: spanparts.StructureAnchors) \
        -> tuple[frozenset[tuple[str, object]] | None, str]:
    if anchors.source_coordinates and anchors.resolved:
        coordinates = frozenset(
            (doc_id, child)
            for doc_id, node in anchors.source_coordinates
            if doc_id in index.docs and node in index.docs[doc_id].by_id
            for child in spanparts.structure_descendants(index.docs[doc_id], node)
        )
        return coordinates, "resolved-structure"
    if anchors.doc_ids:
        return frozenset(
            (doc_id, node.get("id"))
            for doc_id in anchors.doc_ids if doc_id in index.docs
            for node in index.docs[doc_id].nodes
            if node.get("id") in index.docs[doc_id].by_id
        ), "resolved-document"
    return None, "none"


def structure_scope(index: Index, anchors: spanparts.StructureAnchors) \
        -> tuple[frozenset[tuple[str, object]] | None, str]:
    """명시 법령·조문 anchor를 Assertion 검색 좌표 범위로 바꾸는 공개 API."""
    return _structure_scope(index, anchors)


def _document_family(view) -> tuple[str, str]:
    """법률과 시행령·시행규칙·시행세칙을 같은 승인 문서군 단위로 접는다."""
    name = re.sub(r"[\s·ㆍ]+", "", view.name)
    name = re.split(r"[_\[(]", name, maxsplit=1)[0]
    for suffix in ("시행규칙", "시행령", "시행세칙"):
        if name.endswith(suffix) and len(name) > len(suffix) + 2:
            name = name[:-len(suffix)]
            break
    folder = view.folder or view.scope_kind
    return f"{folder}:{name}", name


def _route_document_families(index: Index, hits: list[AssertionHit], *,
                             limit: int = FAMILY_CANDIDATES_MAX) \
        -> tuple[list[AssertionHit], dict]:
    """독립 질문 신호의 문서 커버리지를 합산해 상위 문서군만 연다.

    원문 BM25나 임베딩 점수가 아니다. 같은 canonical 표현이 여러 Assertion에서
    반복돼도 질문 신호 하나로 접고, 여러 문서에 퍼진 신호는 약하게 센다. 가족
    점수는 구성 문서 점수의 합이라 법률과 하위법령이 서로 경쟁하지 않는다.
    """
    documents = sorted({hit.doc_id for hit in hits})
    if not documents:
        return [], {"candidate_families": 0, "selected_families": [],
                    "selected_documents": []}
    signal_documents: dict[str, set[str]] = {}
    prepared = []
    for hit in hits:
        direct = [row for row in hit.evidence
                  if row["kind"] not in {
                      "concept-relation", "facet-match", "facet-conflict"}]
        signals = {str(row["value"]) for row in direct}
        exact = {str(row["value"]) for row in direct
                 if str(row["kind"]).endswith("exact")}
        for signal in signals:
            signal_documents.setdefault(signal, set()).add(hit.doc_id)
        prepared.append((hit, signals, exact))

    total = max(1, len(documents))
    document_scores: dict[str, float] = {doc_id: 0.0 for doc_id in documents}
    document_roles: dict[str, set[str]] = {doc_id: set() for doc_id in documents}
    for hit, signals, exact in prepared:
        for signal in signals:
            rarity = math.log((total + 1) /
                              (len(signal_documents[signal]) + 1)) + 1
            document_scores[hit.doc_id] += rarity * (2 if signal in exact else 1)
        document_roles[hit.doc_id].update(
            role for role in hit.roles if role not in {"MODALITY", "FUNCTION"})
    for doc_id in documents:
        document_scores[doc_id] += 2 * len(document_roles[doc_id])

    families: dict[str, dict] = {}
    for doc_id in documents:
        key, label = _document_family(index.docs[doc_id])
        family = families.setdefault(key, {
            "key": key, "label": label, "folder": index.docs[doc_id].folder,
            "documents": [], "score": 0.0,
        })
        family["documents"].append(doc_id)
        family["score"] += document_scores[doc_id]
    ranked = sorted(families.values(), key=lambda row: (
        -float(row["score"]), row["label"], row["key"]))
    selected = ranked[:max(1, int(limit))]
    allowed = {doc_id for family in selected for doc_id in family["documents"]}
    return [hit for hit in hits if hit.doc_id in allowed], {
        "candidate_families": len(ranked),
        "candidate_documents": len(documents),
        "selected_family_count": len(selected),
        "selected_document_count": len(allowed),
        "selected_families": [{
            "key": row["key"], "label": row["label"],
            "folder": row["folder"],
            "documents": [index.docs[doc_id].name for doc_id in row["documents"]],
        } for row in selected],
        "selected_documents": sorted(allowed),
    }


def _hit_signals(registry: Tier1Registry, hit: AssertionHit) -> tuple[str, ...]:
    out = []
    assertion = registry.active_assertions_by_id.get(hit.assertion_id)
    for row in hit.evidence:
        cid = str(row.get("concept_id") or "")
        concept = registry.active_concepts.get(cid)
        if concept is not None:
            roles = [role for role, ids in assertion.roles.items() if cid in ids] \
                if assertion is not None else []
            label = concept.label
            suffix = f" [{'/'.join(roles)}]" if roles else ""
            value = f"{label}{suffix}"
        else:
            value = f"질문표현: {row['value']}"
        if value not in out:
            out.append(value)
    return tuple(out)


@dataclass
class _Range:
    doc_id: str
    node: object
    path: str
    heading: str
    signals: tuple[str, ...]
    strength: int

def _ranges(index: Index, registry: Tier1Registry, hits: list[AssertionHit],
            structural_roots: set[tuple[str, object]]) -> list[_Range]:
    grouped: dict[tuple[str, object], dict] = {}
    for hit in hits:
        view = index.docs[hit.doc_id]
        root = exploration.selection_root(view, hit.node)
        row = grouped.setdefault((hit.doc_id, root), {
            "signals": [], "strength": 0,
        })
        row["strength"] = max(row["strength"], hit.strength)
        for signal in _hit_signals(registry, hit):
            if signal not in row["signals"]:
                row["signals"].append(signal)
    for doc_id, node in structural_roots:
        view = index.docs.get(doc_id)
        if view is None or node not in view.by_id:
            continue
        root = exploration.selection_root(view, node)
        row = grouped.setdefault((doc_id, root), {
            "signals": [], "strength": 10 ** 9,
        })
        row["strength"] = 10 ** 9
        row["signals"].insert(0, "사용자가 명시한 확정 구조")
    out = []
    for (doc_id, node), data in grouped.items():
        view = index.docs[doc_id]
        raw = view.by_id[node]
        heading = " ".join(filter(None, (
            str(raw.get("surface") or "").strip(),
            str(raw.get("title") or "").strip(),
        )))
        out.append(_Range(
            doc_id, node, view.path(node) or heading or view.name,
            heading or view.path(node) or view.name,
            tuple(data["signals"][:12]), int(data["strength"]),
        ))
    return sorted(out, key=lambda row: (
        -row.strength, index.docs[row.doc_id].name, row.path, str(row.node)))


def _card(key: str, label: str, detail: dict, members: list[_Range]) -> dict:
    signals = []
    for row in members:
        for signal in row.signals:
            if signal not in signals:
                signals.append(signal)
    return {
        "key": key, "label": label, "detail": detail,
        "signals": signals[:8], "members": members,
        "strength": max((row.strength for row in members), default=0),
    }


def _choose_page(llm, question: str, level: str, cards: list[dict], *,
                 keep: int, parent: str, audit: list[dict]) -> list[dict]:
    options = cards[:NAVIGATION_PAGE_SIZE]
    ids = [f"O{pos}" for pos in range(1, len(options) + 1)]
    public = [{"id": oid, "label": row["label"],
               **row["detail"], "matched": row["signals"]}
              for oid, row in zip(ids, options)]
    schema = {
        "type": "object",
        "properties": {
            "picks": {"type": "array", "items": {"type": "string", "enum": ids}},
            "reason": {"type": "string"},
        },
        "required": ["picks", "reason"], "additionalProperties": False,
    }
    response = llm.structured(
        f"rag.assertion_tree.{level}", _NAVIGATE_SYSTEM,
        f"[질문]\n{question}\n\n[현재 단계]\n{level}\n"
        f"[상위 가지]\n{parent or '(root)'}\n[선택 상한]\n{keep}\n\n"
        f"[닫힌 메뉴]\n{json.dumps(public, ensure_ascii=False, indent=1)}",
        schema, max_tokens=500, effort="low") or {}
    allowed = {oid: row for oid, row in zip(ids, options)}
    selected_ids = list(dict.fromkeys(
        oid for oid in response.get("picks") or () if oid in allowed))[:keep]
    audit.append({
        "level": level, "parent": parent, "option_count": len(options),
        "options": [{key: value for key, value in row.items() if key != "members"}
                    for row in public],
        "picks": selected_ids, "reason": str(response.get("reason") or ""),
    })
    return [allowed[oid] for oid in selected_ids]


def _reduce(llm, question: str, level: str, cards: list[dict], *, keep: int,
            parent: str, audit: list[dict]) -> list[dict]:
    """모든 가지를 상한 이하 메뉴에 한 번씩 보인 뒤 토너먼트로 접는다."""
    current = sorted(cards, key=lambda row: (-row["strength"], row["label"], row["key"]))
    if len(current) <= keep:
        return current
    round_no = 1
    while len(current) > NAVIGATION_PAGE_SIZE:
        winners = []
        for page in range(0, len(current), NAVIGATION_PAGE_SIZE):
            winners.extend(_choose_page(
                llm, question, f"{level}.round{round_no}",
                current[page:page + NAVIGATION_PAGE_SIZE], keep=2,
                parent=parent, audit=audit))
        if not winners or len(winners) >= len(current):
            return winners[:keep]
        current = winners
        round_no += 1
    return _choose_page(
        llm, question, f"{level}.final", current, keep=keep,
        parent=parent, audit=audit) if current else []


def _next_child(view, parent, node):
    chain = []
    current_node = view.by_id.get(node)
    seen = set()
    while current_node is not None and current_node.get("id") not in seen:
        current_id = current_node.get("id")
        seen.add(current_id)
        chain.append(current_id)
        if current_node.get("parent") == parent:
            return current_id
        current_node = view.by_id.get(current_node.get("parent"))
    return node if parent is None else None


def _document_tree_select(index: Index, llm, question: str, doc_card: dict, *,
                          keep: int, audit: list[dict]) -> list[_Range]:
    """평면 조문 후보를 문서의 실제 편·장·절·조·항 계층으로 늦게 펼친다."""
    view = index.docs[doc_card["key"]]
    selected: list[_Range] = []
    frontier: list[tuple[object | None, list[_Range], int]] = [
        (None, list(doc_card["members"]), 0)]
    while frontier and len(selected) < keep:
        parent, members, depth = frontier.pop(0)
        grouped: dict[object, list[_Range]] = {}
        for row in members:
            child = _next_child(view, parent, row.node)
            if child is not None:
                grouped.setdefault(child, []).append(row)
        cards = []
        for child, rows in grouped.items():
            node = view.by_id.get(child) or {}
            heading = " ".join(filter(None, (
                str(node.get("surface") or "").strip(),
                str(node.get("title") or "").strip(),
            ))) or view.path(child) or str(child)
            cards.append(_card(
                f"{doc_card['key']}:{child}", heading,
                {"path": view.path(child) or heading,
                 "candidate_provisions": len(rows),
                 "examples": [row.path for row in rows[:5]]}, rows))
        if not cards:
            break
        winners = _reduce(
            llm, question, f"document_tree.depth{depth + 1}", cards,
            keep=min(2, keep - len(selected)), parent=(
                view.name if parent is None else view.path(parent)), audit=audit)
        for winner in winners:
            child = winner["key"].rsplit(":", 1)[-1]
            # node id는 정수/문자열이 섞일 수 있으므로 card의 실제 member 경로에서
            # 다시 찾는다. 선택 단위 자체가 이 가지의 루트면 하위보다 먼저 확정한다.
            actual_child = next(
                (_next_child(view, parent, row.node) for row in winner["members"]
                 if str(_next_child(view, parent, row.node)) == child), None)
            direct = [row for row in winner["members"] if row.node == actual_child]
            if direct:
                selected.append(direct[0])
            else:
                frontier.append((actual_child, winner["members"], depth + 1))
    return selected[:keep]


def _navigate(index: Index, question: str, ranges: list[_Range], *, llm,
              cap: int, pinned: set[tuple[str, object]]) \
        -> tuple[list[_Range], list[dict], dict]:
    audit: list[dict] = []
    by_family: dict[str, list[_Range]] = {}
    family_labels: dict[str, str] = {}
    for row in ranges:
        view = index.docs[row.doc_id]
        family, label = _document_family(view)
        by_family.setdefault(family, []).append(row)
        family_labels[family] = label
    family_cards = [_card(
        family, family_labels[family],
        {"documents": len({row.doc_id for row in members}),
         "folder": index.docs[members[0].doc_id].folder,
         "provisions": len(members),
         "examples": list(dict.fromkeys(index.docs[row.doc_id].name
                                         for row in members))[:5]},
        members) for family, members in by_family.items()]

    pinned_docs = {doc_id for doc_id, _node in pinned}
    if pinned_docs:
        selected_families = [row for row in family_cards
                             if any(item.doc_id in pinned_docs
                                    for item in row["members"])]
    elif len(family_cards) <= FAMILY_PICKS_MAX:
        selected_families = family_cards
    else:
        selected_families = _reduce(
            llm, question, "document_family", family_cards,
            keep=FAMILY_PICKS_MAX,
            parent="", audit=audit)

    document_cards = []
    for family in selected_families:
        by_doc: dict[str, list[_Range]] = {}
        for row in family["members"]:
            by_doc.setdefault(row.doc_id, []).append(row)
        for doc_id, members in by_doc.items():
            view = index.docs[doc_id]
            document_cards.append(_card(
                doc_id, view.name,
                {"folder": view.folder or view.scope_kind,
                 "provisions": len(members),
                 "headings": [row.path for row in members[:5]]},
                members))
    if pinned_docs:
        selected_docs = [row for row in document_cards if row["key"] in pinned_docs]
    elif len(document_cards) == 1:
        selected_docs = document_cards
    else:
        selected_docs = _reduce(
            llm, question, "document", document_cards,
            keep=DOCUMENT_PICKS_MAX, parent=" / ".join(
                row["label"] for row in selected_families), audit=audit)

    pinned_roots = {(doc_id, exploration.selection_root(index.docs[doc_id], node))
                    for doc_id, node in pinned if doc_id in index.docs
                    and node in index.docs[doc_id].by_id}
    provision_cards = [_card(
        f"{row.doc_id}:{row.node}", row.path,
        {"document": index.docs[row.doc_id].name, "heading": row.heading}, [row])
        for doc in selected_docs for row in doc["members"]]
    if pinned_roots:
        picked = [card for card in provision_cards
                  if (card["members"][0].doc_id,
                      card["members"][0].node) in pinned_roots]
    else:
        tree_selected = []
        per_document = max(1, math.ceil(cap / max(1, len(selected_docs))))
        for document in selected_docs:
            tree_selected.extend(_document_tree_select(
                index, llm, question, document, keep=per_document, audit=audit))
        final_cards = [_card(
            f"{row.doc_id}:{row.node}", row.path,
            {"document": index.docs[row.doc_id].name, "heading": row.heading}, [row])
            for row in tree_selected]
        picked = (_reduce(
            llm, question, "provision.final", final_cards, keep=cap,
            parent=" / ".join(row["label"] for row in selected_docs), audit=audit)
            if final_cards else [])
    selected = [card["members"][0] for card in picked]
    return selected[:cap], audit, {
        "families": len(family_cards), "documents": len(document_cards),
        "provisions": len(provision_cards), "calls": len(audit),
        "page_size": NAVIGATION_PAGE_SIZE,
    }


def retrieve(index: Index, question: str, registry: Tier1Registry, *, llm,
             cap: int = 4) -> tuple[list[Section], dict]:
    """원 질문을 보존하고 canonical Assertion 트리를 단계적으로 선택한다."""
    started = time.perf_counter()
    meta = {
        "strategy": "assertion_first_structural_navigation",
        "embedding": False, "raw_law_bm25": False, "query": question,
        "fallback": "", "selected": [],
    }
    if llm is None or not callable(getattr(llm, "structured", None)):
        meta["fallback"] = "선택기 없음"
        return [], meta
    anchors = spanparts.resolve_structure(index, question)
    scope, scope_kind = _structure_scope(index, anchors)
    all_hits = current(registry).search(index, question, scope=scope)
    hits = list(all_hits)
    pinned = set(anchors.source_coordinates) if anchors.resolved else set()
    if pinned:
        route = {
            "policy": "confirmed-structure",
            "candidate_families": len({_document_family(index.docs[hit.doc_id])[0]
                                       for hit in hits}),
            "selected_documents": sorted({hit.doc_id for hit in hits}),
        }
    else:
        hits, route = _route_document_families(index, hits)
        route["policy"] = "canonical-signal-family-topk"
    ranges = _ranges(index, registry, hits, pinned)
    meta["structure"] = {**anchors.as_dict(), "constraint": scope_kind,
                         "coordinate_count": len(scope or ())}
    meta["assertion_hits"] = len(hits)
    meta["raw_assertion_hits"] = len(all_hits)
    meta["assertion_hit_rows"] = [{
        "assertion_id": hit.assertion_id,
        "doc_id": hit.doc_id,
        "node": hit.node,
        "roles": list(hit.roles),
        "concepts": list(hit.concepts),
        "strength": hit.strength,
        "facet_score": hit.facet_score,
        "routed": hit in hits,
    } for hit in all_hits]
    meta["document_route"] = route
    meta["candidate_ranges"] = len(ranges)
    meta["candidate_range_rows"] = [{
        "doc_id": row.doc_id, "node": row.node,
        "doc": index.docs[row.doc_id].name, "path": row.path,
        "heading": row.heading, "signals": list(row.signals),
        "strength": row.strength,
    } for row in ranges]
    if not ranges:
        meta["fallback"] = "canonical 표현과 확정 구조 후보 없음"
        return [], meta
    selected, calls, tree = _navigate(
        index, question, ranges, llm=llm, cap=max(1, int(cap)), pinned=pinned)
    meta["tree"] = tree
    meta["navigation"] = calls
    if not selected:
        meta["fallback"] = "구조 트리에서 선택 없음"
        meta["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        return [], meta
    sections = []
    for row in selected:
        view = index.docs[row.doc_id]
        node = view.by_id[row.node]
        sections.append(Section(
            n=0, doc_id=row.doc_id, doc=view.name, node=row.node,
            path=view.path(row.node) or view.name, page=node.get("page"),
            kind="Assertion트리선택",
            matched=("canonical — " + " · ".join(row.signals))[:200],
            text=exploration.subtree_text(view, row.node, cap=None),
        ))
        meta["selected"].append({
            "doc_id": row.doc_id, "node": row.node, "doc": view.name,
            "path": view.path(row.node) or view.name,
            "signals": list(row.signals),
        })
    meta["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    return sections, meta
