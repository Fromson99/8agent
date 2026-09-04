"""1급 Concept/Assertion을 기존 RAG의 첫 진입 채널로 연결한다."""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from pathlib import Path

from lawrag.core.domain_graph import oql
from lawrag.core.domain_graph.alignment import ConceptAligner
from lawrag.core.domain_graph.store import GraphStore
from lawrag.core.domain_graph.tier1 import Tier1Registry
from lawrag.core.rag.answer import SECTION_CHARS, Section
from lawrag.core.rag.controls import value as control_value
from lawrag.core.rag.index import ROOT, Index, store_path


log = logging.getLogger("lawrag.core.rag.conceptfirst")
ENTRY_CAP = int(control_value("entry.concept_sections_max"))
_GENERIC_RELATION = re.compile(r"관계|관련성|연관성")
_IDENTITY_ANCHOR_TYPES = frozenset({
    "person_role", "organization_role", "document", "artifact",
})


def _pack(value: str) -> str:
    return re.sub(r"\s+", "", value or "").casefold()


def _predicate_form(value: str) -> str:
    """법률 술어의 평서형/의문형 활용만 같은 비교형으로 접는다."""
    value = re.sub(r"[?？.!。]+$", "", _pack(value))
    replacements = (
        (r"하여야(?:하는가|하나|합니까|하나요|한다)$", "하여야"),
        (r"해야(?:하는가|하나|합니까|하나요|한다)$", "해야"),
        (r"할수(?:있는가|있나|있습니까|있나요|있는지|있다)$", "할수있"),
        (r"하여서는아니(?:되는가|되나|됩니까|된다)$", "하여서는아니되"),
        (r"해서는아니(?:되는가|되나|됩니까|된다)$", "해서는아니되"),
        (r"(?:하는가|하나|합니까|하나요|하는지|한다)$", "하"),
        (r"(?:되는가|되나|됩니까|되나요|되는지|된다)$", "되"),
        (r"(?:있는가|있나|있습니까|있나요|있는지|있다)$", "있"),
    )
    for pattern, replacement in replacements:
        changed = re.sub(pattern, replacement, value)
        if changed != value:
            return changed
    return value


def _cue_hit(question: str, cues) -> bool:
    packed_question = _pack(question)
    normalized_question = _predicate_form(question)
    for cue in cues:
        packed_cue = _pack(cue)
        if packed_cue and packed_cue in packed_question:
            return True
        normalized_cue = _predicate_form(str(cue))
        # ``한다``처럼 내용 없는 짧은 술어가 모든 질문을 여는 것을 막는다.
        if len(normalized_cue) >= 4 and normalized_cue in normalized_question:
            return True
    return False


def _assertion_allowed(question: str, alignment, assertion, *,
                       exact_structure: bool = False) -> bool:
    """승인 Concept가 하나 겹쳤다는 이유만으로 모든 Assertion을 열지 않는다.

    OQL은 구조적으로 정확해도 질문의 술어가 다르면 의미상 오답이다. 따라서 active
    Assertion에 승인된 query cue가 있거나, predicate Concept가 실제 후보로 잡혔거나,
    사용자가 둘 이상의 Concept 사이의 일반 관계를 물은 경우만 근거를 연다. 자연어는
    여기서 게이트로만 쓰이고 OQL/SQL 파라미터에는 들어가지 않는다.
    """
    selected = {c.concept_id for c in alignment.selected}
    predicates = set(assertion.roles.get("PREDICATE") or ())
    generic_relation = (len(selected) >= 2 and bool(_GENERIC_RELATION.search(question))
                        and (alignment.intent == "RELATION_BETWEEN_CONCEPTS"
                             or alignment.via == "span_parts_llm"))
    if generic_relation:
        return True

    # actor+책임만으로는 그 actor의 모든 책임 Assertion 중 어느 것인지 정해지지
    # 않는다. 최소한 SUBJECT/OBJECT/TARGET 같은 적용 맥락 Concept가 함께 잡혀야
    # 술어 cue 또는 PREDICATE를 근거로 특정 Assertion을 연다.
    context = set()
    for role in ("SUBJECT", "OBJECT", "TARGET", "CONDITION", "METHOD"):
        context.update(assertion.roles.get(role) or ())
    predicate_hit = bool(selected & predicates)

    # Span 조립 LLM이 질문의 활용형을 정본 PREDICATE에 연결했고 문서·조문 좌표도
    # 코드가 실제 source 좌표로 확정했다면 그 역할 결합을 신뢰한다. OQL의
    # assertion_by_parts가 PREDICATE와 나머지 부품을 각 정본 역할로 교집합한 뒤라
    # actor+predicate만 골랐다는 이유로 다시 원문 cue의 완전일치를 요구하면
    # ``제출하여야 한다/제출하여야 하는가`` 같은 정상 활용형을 전부 잃는다.
    # 무좌표 질문에는 이 예외를 적용하지 않아 광범위한 actor+책임 오염을 막는다.
    closed_role_binding = (
        exact_structure
        and alignment.via == "span_parts_llm"
        and alignment.intent == "ASSERTION_BY_PARTS"
        and len(selected) >= 2
        and predicate_hit
    )
    if closed_role_binding:
        return True

    cue_hit = _cue_hit(question, assertion.query_cues)
    return bool(len(selected) >= 2 and selected & context
                and (predicate_hit or cue_hit))


def _unscoped_alignment_allowed(alignment) -> bool:
    """문서·조문 제약 없는 결정론 정렬은 식별 가능한 부품이 있어야 한다.

    ``정보+공개``, ``보고서+제출``, ``발행+주식`` 같은 domain_term/action 쌍은
    법역을 가리지 않고 수백 문서에 나타난다. 이것만으로 1급 Assertion을 열면
    그래프 연결 자체가 의미 선택의 자기확증이 된다. 기관·사람 역할·문서·산출물처럼
    질문 대상을 식별하는 Concept가 없으면 하위 RAG가 문맥을 찾도록 넘긴다. LLM이
    역할을 정확히 조립해도 같은 범용 부품 쌍이 여러 법령에 존재할 수 있으므로 같은
    게이트를 적용한다.
    """
    return any(candidate.concept_type in _IDENTITY_ANCHOR_TYPES
               for candidate in alignment.selected)


def _data_dir() -> Path:
    # 서비스는 STRUCTURE_STORE를 명시한다. 저장소에서 모듈만 실행할 때 index의
    # 역사적 기본 var/out/... parent가 존재해도 실제 정본은 data/다.
    if os.environ.get("STRUCTURE_STORE"):
        return store_path().parent
    return ROOT / "data"


def graph_path() -> Path:
    from lawrag.core.rag.content_snapshot import current_content_snapshot

    snapshot = current_content_snapshot()
    if snapshot is not None:
        return snapshot.semantic_path("domain_graph", "graph.sqlite")
    return Path(os.environ.get("RAG_DOMAIN_GRAPH",
                               _data_dir() / "domain_graph" / "graph.sqlite"))


def registry_path() -> Path:
    from lawrag.core.rag.content_snapshot import current_content_snapshot

    snapshot = current_content_snapshot()
    if snapshot is not None:
        return snapshot.semantic_path("domain_graph", "canonical.json")
    return Path(os.environ.get("RAG_CONCEPT_REGISTRY",
                               _data_dir() / "domain_graph" / "canonical.json"))


@lru_cache(maxsize=1)
def _registry_cached(path: str, mtime_ns: int, size: int) -> Tier1Registry:
    # mtime·크기가 바뀌면 새 key가 되어 자동 재적재된다. 같은 서비스 프로세스에서
    # 48MB 정본을 질문마다 파싱·순환검사하지 않는다. 활성 정본은 하나뿐이므로
    # 재발행 뒤 구버전 레지스트리를 캐시에 붙잡아 두지 않는다.
    return Tier1Registry.load(path)


def _registry(path: Path) -> Tier1Registry:
    stat = path.stat()
    return _registry_cached(str(path), stat.st_mtime_ns, stat.st_size)


def load_registry(path: Path | None = None) -> Tier1Registry:
    """현재 승인 Concept/Assertion registry를 캐시된 공개 경계로 읽는다."""
    return _registry(path or registry_path())


def retrieve(index: Index, question: str, *, llm=None,
             cap: int = ENTRY_CAP, coordinate_first: bool = False) \
        -> tuple[list[Section], dict]:
    """질문 → Concept 정렬 → OQL → 근거 Section. 빈손이면 하위 사다리가 받는다."""
    meta = {"alignment": {}, "parts": {}, "structure": {},
            "oql": None, "hits": [], "fallback": ""}
    gp, rp = graph_path(), registry_path()
    if not rp.is_file():
        meta["fallback"] = "1급 레지스트리 없음"
        return [], meta
    try:
        registry = _registry(rp)
    except (ValueError, OSError) as exc:
        log.error("1급 레지스트리 거부 — %s", exc)
        meta["fallback"] = "1급 레지스트리 검증 실패"
        return [], meta
    if not registry.active_concepts:
        meta["fallback"] = "active Concept 없음"
        return [], meta

    # 기본 서비스 경로는 Document/Heading/역할·본문 조각의 **본문 좌표**
    # 교집합만 쓴다. Assertion ID는 추출 provenance이지 검색 키가 아니다.
    # 직접 conceptfirst 단위 API와 옛 회귀시험은 coordinate_first=False일 때만
    # 레거시 Assertion/OQL 경로를 재생한다.
    if coordinate_first:
        from lawrag.core.rag import landings

        sections, landing_meta = landings.retrieve(
            index, question, registry, llm=llm, cap=cap)
        # 빈손도 이 경로의 유효한 결과다. vecfirst가 그 다음 Keyword/Frame/Vector
        # 사다리로 내리며, 같은 요청을 명제 ID 교집합 OQL로 다시 해석하지 않는다.
        return sections, landing_meta

    if not gp.is_file():
        meta["fallback"] = "1급 그래프 없음"
        return [], meta

    from lawrag.core.domain_graph import spanparts

    # 문서명·조문 좌표는 LLM의 의미 판단과 무관한 결정론 제약이다. LLM이 없을
    # 때도 먼저 확정해 두어 범용 Concept가 명시 조문 밖 Assertion을 열지 못한다.
    anchors = spanparts.resolve_structure(index, question)
    meta["structure"] = anchors.as_dict()
    structural = anchors.oql_constraints()
    if not anchors.resolved:
        meta["fallback"] = "명시 구조 좌표를 하나로 확정하지 못함 — 하위 사다리로 하강"
        return [], meta
    def deterministic_alignment():
        coords = set(anchors.source_coordinates)
        docs = set(anchors.doc_ids)
        scoped_assertions = {
            assertion.id for assertion in registry.active_assertions
            if ((coords and (str(assertion.source.get("doc_id") or ""),
                             assertion.source.get("node")) in coords)
                or (not coords and docs
                    and str(assertion.source.get("doc_id") or "") in docs))
        }
        return ConceptAligner(registry).align(
            question,
            assertion_ids=scoped_assertions if anchors.explicit else None,
        )

    if llm is not None:
        # 이미 컴파일된 실제 데이터 표면형만 읽는다. 질의 중 새 용어 임베딩을
        # 만들거나 저장하지 않는다. 색인이 없으면 Concept 표면형 비교로 폴백한다.
        lexicon = spanparts.cached_term_lexicon()
        assembled = spanparts.align(llm, registry, index, question, lexicon=lexicon,
                                    anchors=anchors)
        alignment = assembled.alignment
        meta["parts"] = assembled.as_dict()
        if assembled.decision != "SELECT":
            # 모델의 NO_MATCH 변동성은 명시 좌표가 실제 source로 확정되고, 그 범위의
            # 정본 Concept 쌍이 결정론적으로 잡힐 때만 이어받는다. 최종 Assertion
            # 게이트에서 활용형 cue까지 일치해야 하므로 잘못된 술어는 열리지 않는다.
            proposals = list(assembled.proposals)
            last_proposal = proposals[-1] if proposals else {}
            model_decision = str(last_proposal.get("decision") or "")
            validation_error = str(last_proposal.get("validation_error") or "")
            safe_deterministic_handoff = (
                model_decision == "NO_MATCH"
                or (model_decision == "SELECT"
                    and validation_error == "no_grounded_assertion")
            )
            fallback_alignment = (
                deterministic_alignment()
                if anchors.source_coordinates and safe_deterministic_handoff
                else None
            )
            if fallback_alignment is not None and fallback_alignment.selected \
                    and not fallback_alignment.ambiguous:
                alignment = fallback_alignment
                meta["parts"]["deterministic_fallback"] = True
            else:
                meta["alignment"] = alignment.as_dict()
                meta["fallback"] = "LLM 부품 조립 결과 없음 — 하위 사다리로 하강"
                return [], meta
    else:
        alignment = deterministic_alignment()
    meta["alignment"] = alignment.as_dict()
    if alignment.ambiguous:
        meta["fallback"] = "Concept 정렬 중의성 — 하위 사다리로 하강"
        return [], meta
    if not anchors.explicit and not _unscoped_alignment_allowed(alignment):
        meta["fallback"] = "문서·조문 없는 범용 Concept 조합 — 하위 사다리로 하강"
        return [], meta
    request = oql.plan(alignment, structural=structural)
    if request is None:
        meta["fallback"] = "Concept 정렬 불충분"
        return [], meta
    try:
        with GraphStore(gp, readonly=True) as store:
            result = oql.execute(store, registry, request)
    except (ValueError, OSError) as exc:
        log.error("OQL 실행 거부 — %s", exc)
        meta["fallback"] = "OQL 검증 또는 실행 실패"
        return [], meta
    meta["oql"] = {"pattern": result["pattern"], "params": result["params"],
                   "count": result["count"]}

    assertions = {a.id: a for a in registry.active_assertions}
    eligible_rows = []
    for row in result["rows"]:
        aid = str(row.get("assertion_id") or "")
        assertion = assertions.get(aid.removeprefix("assertion:"))
        if assertion is None or _assertion_allowed(
                question, alignment, assertion,
                exact_structure=bool(anchors.source_coordinates)):
            eligible_rows.append(row)

    # 구조 앵커가 없는 질문은 의미 게이트를 통과한 Assertion들이 근거 좌표 하나로
    # 수렴할 때만 연다. 전수 승인 뒤 같은 조문 문장을 여러 Frame Assertion이
    # 표현할 수 있으므로 Assertion ID 개수 자체는 중의성이 아니다. 반면
    # ``금융투자업자+투자자``처럼 서로 다른 법령·의무 좌표로 갈리면 그래프 연결이
    # 의미 선택을 자기확증하지 못하게 하위 사다리로 넘긴다.
    eligible_sources = {
        (str(source.get("doc_id") or ""), str(source.get("node")))
        for row in eligible_rows for source in (row.get("sources") or [])
        if source.get("doc_id") and source.get("node") is not None
    }
    if not eligible_rows:
        meta["fallback"] = "질문 술어와 맞는 active Assertion 근거 없음"
        return [], meta
    # 수동 정본처럼 더 높은 confidence의 Assertion 하나가 문서/산출물 Concept를
    # 포함해 명확히 우세하면, 동일 부품으로 자동 생성된 0.8 Frame 후보들을 접는다.
    # actor+investor 같은 광범위 역할 쌍에는 적용하지 않아 고신뢰 Assertion 하나가
    # 일반 관계 질문을 독점하지 못하게 한다.
    identity_document = any(candidate.concept_type in {"document", "artifact"}
                            for candidate in alignment.selected)
    if not anchors.explicit and len(eligible_sources) != 1 and identity_document:
        levels = sorted({float(row.get("confidence") or 0)
                         for row in eligible_rows}, reverse=True)
        if len(levels) >= 2 and levels[0] - levels[1] >= 0.10:
            dominant = [row for row in eligible_rows
                        if float(row.get("confidence") or 0) == levels[0]]
            dominant_sources = {
                (str(source.get("doc_id") or ""), str(source.get("node")))
                for row in dominant for source in (row.get("sources") or [])
                if source.get("doc_id") and source.get("node") is not None
            }
            if len(dominant_sources) == 1:
                eligible_rows, eligible_sources = dominant, dominant_sources
    if not anchors.explicit and len(eligible_sources) != 1:
        meta["fallback"] = "문서·조문 없는 Assertion 다중 후보 — 하위 사다리로 하강"
        return [], meta

    sections, seen = [], set()
    labels = " · ".join(c.label for c in alignment.selected)
    for row in eligible_rows:
        for source in row.get("sources", []):
            doc_id, node = source.get("doc_id"), source.get("node")
            if not index.in_scope(doc_id) or (doc_id, node) in seen:
                continue
            view = index.docs.get(doc_id)
            section = view.by_id.get(node) if view else None
            if view is None or section is None:
                continue
            from lawrag.core.rag import verdicts as verdicts_mod
            if verdicts_mod.is_entry_blocked(doc_id, node):
                continue
            seen.add((doc_id, node))
            sections.append(Section(
                n=0, doc_id=doc_id, doc=view.name, node=node,
                path=view.path(node) or view.name, page=section.get("page"),
                kind="Concept", matched=f"1급 OQL {result['pattern']} — {labels}"[:160],
                text=view.section_outline(section, cap=SECTION_CHARS),
            ))
            meta["hits"].append({
                "assertion_id": row.get("assertion_id"), "doc_id": doc_id,
                "node": node, "confidence": row.get("confidence"),
                "roles": row.get("roles"),
            })
            if len(sections) >= cap:
                break
        if len(sections) >= cap:
            break
    if not sections:
        meta["fallback"] = "질문 술어와 맞는 active Assertion 근거 없음"
    return sections, meta
