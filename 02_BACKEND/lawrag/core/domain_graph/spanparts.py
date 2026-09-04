"""질문의 실제 Span을 1급 지식 부품에 닫힌 메뉴로 정렬한다.

질문 쪽 동의어·검색문장을 만들지 않는다. LLM 1은 질문에 실제로 존재하는 부분
문자열만 역할별로 자르고, 회수기는 그 문자열을 그대로 데이터의 Concept 표면형과
용어 임베딩에 조회한다. LLM 2는 메뉴에 실린 active Concept ID만 제안하고, 코드는
실제 active Assertion에서 함께 출현하는 유일한 우세 부분집합과 정본 역할로 OQL
부품을 확정한다. 문서명·조문 좌표는 의미 후보가 아니라 결정론 구조 제약이다.
"""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from lawrag.core.rag import refs
from lawrag.core.rag.controls import value as control_value
from lawrag.core.rag.index import Index

from .alignment import Alignment, Candidate
from .tier1 import Tier1Concept, Tier1Registry


SPAN_ROLES = (
    "actor", "predicate", "object", "target", "method", "modality",
    "condition", "effect", "subject", "document", "toc", "heading",
    "locator", "unknown",
)
STRUCTURE_ROLES = frozenset({"document", "toc", "heading", "locator"})
PART_ROLES = tuple(r for r in SPAN_ROLES if r not in STRUCTURE_ROLES)
MAX_QUERY_SPANS = int(control_value("concept.query_spans_max"))
PARTS_PER_SPAN = int(control_value("concept.parts_per_span_max"))
RAW_SPAN_FACTOR = int(control_value("concept.raw_pool_factor"))
SEMANTIC_COS_MIN = float(control_value("concept.semantic_cos_min"))
SURFACE_SCORE_MIN = float(control_value("concept.surface_score_min"))
OCCURRENCES_PER_PART = int(control_value("concept.occurrences_per_part_max"))
OCCURRENCE_CONTEXT_CHARS = int(control_value("concept.occurrence_context_chars"))
PROMPT_CONTEXT_CHARS = int(control_value("concept.prompt_context_chars"))
MAPPINGS_MAX = int(control_value("concept.mappings_max"))
_TERM_CACHE: dict = {}
_GENERIC_RELATION = re.compile(r"관계|관련성|연관성")
SPAN_SYSTEM = (
    "너는 질문을 OQL 부품에 연결하기 위한 Span 분해기다. 질문에 실제로 연속해서 "
    "쓰인 부분 문자열만 span에 복사한다. 바꿔 쓰기·동의어·상위어·법률용어 번역을 "
    "절대 만들지 않는다. 복합 서술문은 가능한 한 행위자·목적어·대상·핵심 술어를 "
    "서로 다른 최소 Span으로 나눈다. 예를 들어 '보고서를 위원회에 제출하여야 하는가'는 "
    "'보고서'(object), '위원회'(target), '제출하여야 하는가'(predicate)로 나눈다. "
    "start/end는 파이썬 문자열 기준 [start,end) 위치다. "
    "문서 제목(document), 목차 항목(toc), 본문의 장·절·조 제목(heading), "
    "제N조제M항 같은 좌표(locator)도 각각 별도 Span으로 뽑는다. "
    "없는 역할은 만들지 않는다."
)
SPAN_SCHEMA = {
    "type": "object",
    "properties": {"spans": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "span": {"type": "string"},
            "start": {"type": "integer"},
            "end": {"type": "integer"},
            "role": {"type": "string", "enum": list(SPAN_ROLES)},
        },
        "required": ["span", "start", "end", "role"],
        "additionalProperties": False,
    }}},
    "required": ["spans"],
    "additionalProperties": False,
}

COMPOSE_SYSTEM = (
    "너는 질문 Span을 승인된 1급 지식 부품으로 조립하는 OQL 매퍼다. 각 Span 아래에 "
    "제공된 part_id만 고른다. 질문에 없는 낱말이나 새 Concept ID를 만들지 않는다. "
    "문서·조문 구조 제약은 확정값이므로 다른 문서의 비슷한 부품으로 우회하지 않는다. "
    "부분문자열인 일반 개념보다 질문 전체와 문서 문맥에 맞는 구체 개념을 고른다. "
    "A와 B의 일반 관계를 묻는 질문은 predicate Span이 없어도 A와 B가 같은 본문 "
    "좌표에 실제로 함께 출현하면 두 부품의 정확한 역할을 골라 SELECT한다. "
    "span_idx는 각 메뉴 앞의 S 번호이며 반드시 1부터 센다. 서로 다른 역할의 부품을 "
    "조립하되 근거가 부족하면 NO_MATCH를 고른다. "
    "intent는 역할별 교집합인 ASSERTION_BY_PARTS를 쓰고, 용어 정의 "
    "질문만 CONCEPT_DEFINITION을 쓴다. 자연어 SQL·Cypher·OQL 문자열은 출력하지 않는다."
)
# 상세 예시를 넣은 판정은 동치 paraphrase까지 과도하게 거부했고, 판정을 완전히
# 제거하면 wrong-predicate 음성 12건 중 4건이 실제 Assertion으로 오염됐다.
# 의미와 극성만 묻는 한 줄이 현재의 정밀도/재현율 절충점이다.
PREDICATE_SYSTEM = (
    "두 술어가 문맥상 같은 뜻이면 MATCH, 다르면 MISMATCH, 판단할 수 없으면 UNSURE."
)
PREDICATE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["MATCH", "MISMATCH", "UNSURE"]},
    },
    "required": ["verdict"],
    "additionalProperties": False,
}
PREDICATE_SURFACE_FLOOR = float(control_value("concept.predicate_surface_min"))


def _pack(value: str) -> str:
    return re.sub(r"\s+", "", value or "").casefold()


def _grams(value: str) -> set[str]:
    packed = _pack(value)
    if len(packed) < 2:
        return {packed} if packed else set()
    return {packed[i:i + 2] for i in range(len(packed) - 1)}


def _surface_score(span: str, surface: str) -> tuple[float, str]:
    """후보 회수 순서일 뿐 의미 선택 점수가 아니다."""
    left, right = _pack(span), _pack(surface)
    if not left or not right:
        return 0.0, ""
    if left == right:
        return 1.0, "exact"
    if right in left or left in right:
        specificity = min(len(left), len(right)) / max(len(left), len(right))
        return 0.72 + 0.20 * specificity, "subspan"
    lg, rg = _grams(left), _grams(right)
    if not lg or not rg:
        return 0.0, ""
    overlap = len(lg & rg)
    dice = 2 * overlap / (len(lg) + len(rg))
    return dice, "surface"


@dataclass(frozen=True)
class QuerySpan:
    text: str
    start: int
    end: int
    role: str
    # QueryGuide의 질의 한정 닫힌 후보 ID. 정본 ID가 아니며, 가이드가 꺼진
    # 기존 경로와 무LLM 경로에서는 항상 빈 tuple이다.
    reading_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        out = {"span": self.text, "start": self.start, "end": self.end,
               "role": self.role}
        if self.reading_ids:
            out["reading_ids"] = list(self.reading_ids)
        return out


@dataclass(frozen=True)
class StructureAnchors:
    doc_ids: tuple[str, ...] = ()
    documents: tuple[str, ...] = ()
    locators: tuple[str, ...] = ()
    source_coordinates: tuple[tuple[str, object], ...] = ()
    unresolved_locators: tuple[str, ...] = ()

    @property
    def explicit(self) -> bool:
        return bool(self.doc_ids or self.locators)

    @property
    def resolved(self) -> bool:
        """명시된 구조 좌표를 하나도 추측하지 않고 전부 확정했는가."""
        return not self.unresolved_locators

    def oql_constraints(self) -> dict:
        out = {}
        if self.doc_ids:
            out["source_doc_ids"] = list(self.doc_ids)
        if self.source_coordinates:
            out["source_coordinates"] = [
                {"doc_id": doc_id, "node": node}
                for doc_id, node in self.source_coordinates
            ]
        return out

    def as_dict(self) -> dict:
        return {
            "doc_ids": list(self.doc_ids), "documents": list(self.documents),
            "locators": list(self.locators),
            "source_coordinates": [
                {"doc_id": doc_id, "node": node}
                for doc_id, node in self.source_coordinates
            ],
            "unresolved_locators": list(self.unresolved_locators),
        }


@dataclass
class Part:
    concept_id: str
    label: str
    concept_type: str
    matched: str
    match_kind: str
    retrieval_score: float
    roles: tuple[str, ...] = ()
    occurrences: tuple[dict, ...] = ()

    def as_dict(self) -> dict:
        return {
            "part_id": self.concept_id, "label": self.label,
            "type": self.concept_type, "matched": self.matched,
            "match_kind": self.match_kind,
            "retrieval_score": round(self.retrieval_score, 3),
            "roles": list(self.roles),
            "occurrences": list(self.occurrences),
        }


@dataclass
class SpanMenu:
    span: QuerySpan
    parts: list[Part] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"span": self.span.as_dict(),
                "parts": [part.as_dict() for part in self.parts]}


class CachedTermLexicon:
    """컴파일된 실제 용어 벡터만 읽는 런타임 색인.

    기존 ``Lexicon``은 누락 표면형을 발견하면 임베딩을 새로 컴파일한다. 질의 경로는
    데이터 상태를 바꾸거나 수만 건을 재계산하면 안 되므로 names+emb 정본을 읽기
    전용으로만 사용한다.
    """

    def __init__(self, names, matrix):
        self.names = names
        self.matrix = matrix
        self._query_vector_cache: dict[str, object] = {}

    def _query_vectors(self, words: list[str]):
        """같은 질의 Span의 임베딩은 역할·구조 필터가 달라도 한 번만 계산한다."""
        import numpy as np
        from lawrag.core import embedding

        missing = list(dict.fromkeys(
            word for word in words if word not in self._query_vector_cache))
        if missing:
            vectors = np.asarray(embedding.encode(missing), dtype=np.float32)
            vectors /= np.linalg.norm(vectors, axis=1, keepdims=True) + 1e-9
            for col, word in enumerate(missing):
                self._query_vector_cache[word] = vectors[col]
            while len(self._query_vector_cache) > 512:
                self._query_vector_cache.pop(next(iter(self._query_vector_cache)))
        return np.stack([self._query_vector_cache[word] for word in words])

    def _similarities(self, words: list[str]):
        return self.matrix @ self._query_vectors(words).T

    def prepare(self, words: list[str]) -> None:
        """한 질문의 Span을 배치 계산해 뒤의 역할별 필터 조회를 예열한다."""
        if not words:
            return
        try:
            self._query_vectors(list(dict.fromkeys(words)))
        except Exception:
            return

    def neighbors_many(self, words: list[str], *, k: int = 24,
                       min_cos: float = 0.45) -> list[list[dict]]:
        if not words:
            return []
        try:
            import numpy as np
            sims = self._similarities(words)
            out = []
            for col in range(len(words)):
                order = np.argsort(-sims[:, col])[:k]
                rows = []
                for pos in order:
                    score = float(sims[pos, col])
                    if score < min_cos:
                        break
                    rows.append({"term": str(self.names[int(pos)]), "cos": round(score, 3)})
                out.append(rows)
            return out
        except Exception:
            return [[] for _ in words]

    def neighbors_many_filtered(self, words: list[str], allowed_terms: set[str], *,
                                k: int = 24, min_cos: float = 0.45) \
            -> list[list[dict]]:
        """Vector 유사도 계산 뒤 순위를 허용된 DB 표면형 안에서만 매긴다.

        ``allowed_terms``는 공백을 제거하고 casefold한 값이다. 전역 top-k를 먼저
        자른 뒤 역할을 거르는 방식과 달리, 같은 역할·구조 스코프의 Concept가
        실제 랭킹 모집단이 된다.
        """
        if not words or not allowed_terms:
            return [[] for _ in words]
        try:
            import numpy as np
            packed = getattr(self, "_packed_indices", None)
            if packed is None:
                packed = {}
                for pos, name in enumerate(self.names):
                    packed.setdefault(_pack(str(name)), []).append(pos)
                self._packed_indices = packed
            eligible = np.asarray(sorted({
                pos for term in allowed_terms for pos in packed.get(term, ())
            }), dtype=np.int64)
            if not len(eligible):
                return [[] for _ in words]
            vectors = self._query_vectors(words)
            out = []
            for col in range(len(words)):
                local_sims = self.matrix[eligible] @ vectors[col]
                local = np.argsort(-local_sims)[:k]
                rows = []
                for offset in local:
                    pos = int(eligible[int(offset)])
                    score = float(local_sims[int(offset)])
                    if score < min_cos:
                        break
                    rows.append({"term": str(self.names[pos]),
                                 "cos": round(score, 3)})
                out.append(rows)
            return out
        except Exception:
            return [[] for _ in words]


def cached_term_lexicon(path: Optional[Path] = None) -> Optional[CachedTermLexicon]:
    """기존 terms.npz만 연다. 파일이 없거나 깨졌으면 표면형 경로만 사용한다."""
    if path is None:
        from lawrag.core.rag.lexicon import lexicon_dir
        path = lexicon_dir() / "terms.npz"
    path = Path(path)
    try:
        sig = (path.stat().st_mtime_ns, path.stat().st_size)
    except OSError:
        return None
    if _TERM_CACHE.get("sig") != sig:
        try:
            import numpy as np

            blob = np.load(path, allow_pickle=False)
            names = blob["names"]
            matrix = blob["emb"].astype(np.float32)
            matrix /= np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9
            _TERM_CACHE.update(sig=sig, value=CachedTermLexicon(names, matrix))
        except Exception:
            return None
    return _TERM_CACHE.get("value")


@dataclass
class PartAlignment:
    alignment: Alignment
    spans: list[QuerySpan]
    menus: list[SpanMenu]
    anchors: StructureAnchors
    decision: str = "NO_MATCH"
    proposals: tuple[dict, ...] = ()

    def as_dict(self) -> dict:
        return {
            "decision": self.decision,
            "proposals": list(self.proposals),
            "spans": [span.as_dict() for span in self.spans],
            "anchors": self.anchors.as_dict(),
            "menus": [menu.as_dict() for menu in self.menus],
        }


def extract_spans(llm, question: str, *, guide=None) -> list[QuerySpan]:
    """LLM 출력 중 질문에 실제로 존재하는 연속 부분 문자열만 통과시킨다."""
    system, user, schema = SPAN_SYSTEM, f"[질문]\n{question}", SPAN_SCHEMA
    allowed_readings: set[str] = set()
    reading_table = {}
    if guide is not None and guide.readings:
        guide_prompt = guide.as_prompt()
        # prompt_chars_max 때문에 실제로 보이지 않은 후보 ID를 스키마로 우회해
        # 고를 수 없게 한다.
        allowed_readings = set(re.findall(r"\bQG\d+\b", guide_prompt))
        reading_table = guide.by_id
        system += (
            " 아래 DB 역매칭 표는 정답이 아니라 질문 문자열의 가능한 해석 메뉴다. "
            "같은 M의 여러 G는 OR 대안이므로 실제 뜻인 reading_ids만 고른다. "
            "서로 다른 M은 별도 Span으로 유지한다. 메뉴에 없는 실제 질문 Span도 "
            "기존 규칙대로 추가하고 reading_ids는 빈 배열로 둔다. DB 후보를 근거로 "
            "질문에 없는 문자열을 만들면 안 된다."
        )
        user += "\n\n" + guide_prompt
        schema = deepcopy(SPAN_SCHEMA)
        item = schema["properties"]["spans"]["items"]
        item["properties"]["reading_ids"] = {
            # Anthropic/OpenAI 공통 구조화 출력의 지원 교집합만 쓴다. 중복 제거는
            # 아래 파서가 수행하므로 uniqueItems 같은 공급자별 비지원 키가 불필요하다.
            "type": "array",
            "items": {"type": "string", "enum": sorted(allowed_readings)},
        }
        item["required"].append("reading_ids")
    out = llm.structured("rag.oql.spans", system, user, schema,
                         max_tokens=1200 if allowed_readings else 900, effort="low")
    if not out:
        return []
    spans, seen = [], set()
    for row in (out.get("spans") or [])[:MAX_QUERY_SPANS]:
        text = str(row.get("span") or "").strip()
        role = str(row.get("role") or "unknown")
        if not text or role not in SPAN_ROLES:
            continue
        start, end = row.get("start"), row.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or \
                not (0 <= start < end <= len(question)) or question[start:end] != text:
            # 숫자 위치만 틀렸더라도 실제 부분 문자열이면 코드가 좌표를 복구한다.
            start = question.find(text)
            if start < 0:
                continue
            end = start + len(text)
        reading_ids = []
        for rid in row.get("reading_ids") or []:
            candidate = reading_table.get(str(rid))
            if candidate is None or str(rid) not in allowed_readings:
                continue
            # 다른 질문 조각의 ID를 이 Span에 붙여 AND/OR 경계를 흐리지 못하게 한다.
            if (candidate.start, candidate.end) != (start, end):
                continue
            if str(rid) not in reading_ids:
                reading_ids.append(str(rid))
        key = (start, end, role, tuple(reading_ids))
        if key in seen:
            continue
        seen.add(key)
        spans.append(QuerySpan(text, start, end, role, tuple(reading_ids)))
    return sorted(spans, key=lambda s: (s.start, s.end, s.role))


def _doc_fold(value: str) -> str:
    return _pack(re.sub(r"\.[A-Za-z0-9]{1,5}$", "", value or ""))


def _descendants(view, root_id) -> list[object]:
    out = []
    for node in view.nodes:
        current, seen = node, set()
        while current is not None and current.get("id") not in seen:
            nid = current.get("id")
            seen.add(nid)
            if nid == root_id:
                out.append(node.get("id"))
                break
            current = view.by_id.get(current.get("parent"))
    return out


def structure_descendants(view, root_id) -> list[object]:
    """검색 구조 객체의 자신+하위 Section 좌표(공개 질의 helper)."""
    return _descendants(view, root_id)


def _document_mentions(index: Index, question: str) -> list[tuple[int, int, str, str]]:
    """질문에 실제로 적힌 문서명/승인 약칭의 겹치지 않는 최대 구간.

    이름 길이를 질문 전체에서 한 번에 비교하면 ``감사원법``과 ``국세기본법``처럼
    서로 다른 두 법 중 짧은 하나가 사라진다. 같은 위치에서만 긴 이름을 남겨
    ``개인정보 보호법 시행령`` 안의 ``개인정보 보호법`` 중복만 제거한다.
    """
    packed = _pack(question)
    names = {_doc_fold(view.name): (doc_id, view.name)
             for doc_id, view in index.entry_docs.items() if _doc_fold(view.name)}
    raw: list[tuple[int, int, str, str]] = []

    def add(surface: str, official: str) -> None:
        target = names.get(official)
        if not surface or target is None:
            return
        start = 0
        while True:
            pos = packed.find(surface, start)
            if pos < 0:
                break
            raw.append((pos, pos + len(surface), target[0], target[1]))
            start = pos + max(1, len(surface))

    for folded in names:
        add(folded, folded)

    aliases = refs.alias_map()
    for alias, official in aliases.items():
        for suffix in ("시행세칙", "시행규칙", "시행령", ""):
            add(alias + suffix, official + suffix)

    # 같은 문서/구간 중복부터 없앤 뒤, 더 긴 같은 위치의 문서명에 포함된 구간만
    # 버린다. 서로 떨어져 적힌 별개의 법령은 길이가 달라도 모두 남는다.
    unique = sorted(set(raw), key=lambda row: (row[0], -(row[1] - row[0]), row[2]))
    maximal = []
    for row in unique:
        start, end, _, _ = row
        if any(start >= other[0] and end <= other[1]
               and (start, end) != (other[0], other[1]) for other in unique):
            continue
        maximal.append(row)
    return sorted(maximal, key=lambda row: (row[0], row[1], row[2]))


def _hint_docs(index: Index, hint: str) -> list[str]:
    folded = _doc_fold(hint.strip("「」"))
    if not folded:
        return []
    aliases = refs.alias_map()
    official = aliases.get(folded, folded)
    for suffix in ("시행세칙", "시행규칙", "시행령"):
        if folded.endswith(suffix) and folded[:-len(suffix)] in aliases:
            official = aliases[folded[:-len(suffix)]] + suffix
            break
    exact = [doc_id for doc_id, view in index.entry_docs.items()
             if _doc_fold(view.name) == official]
    if exact:
        return exact
    partial = [doc_id for doc_id, view in index.entry_docs.items()
               if official in _doc_fold(view.name) or _doc_fold(view.name) in official]
    return partial if len(partial) == 1 else []


def _ref_roots(view, ref) -> list[object]:
    roots = []
    for node in view.nodes:
        for label in (node.get("surface"), node.get("title")):
            if refs.label_key(label or "") == ref.key():
                roots.append(node.get("id"))
                break
    return roots


def _resolve_ref(view, ref) -> Optional[object]:
    """질문 좌표는 항·호까지 전부 실재하고 하나로 떨어질 때만 확정한다."""
    children: dict[object, list[object]] = {}
    for node in view.nodes:
        if node.get("parent") is not None:
            children.setdefault(node.get("parent"), []).append(node.get("id"))
    reached = []
    for root in _ref_roots(view, ref):
        target, depth = refs._descend(view, children, root, ref.chain)
        if depth == len(ref.chain):
            reached.append((root, target))
    reached = list(dict.fromkeys(reached))
    if len(reached) == 1:
        return reached[0][1]
    if len(reached) > 1:
        # 질문이 부칙을 명시하지 않았다면 본문 좌표 하나만 남는 경우에 한해 확정.
        main = [target for root, target in reached if "부칙" not in (view.path(root) or "")]
        if len(set(main)) == 1:
            return main[0]
    return None


def resolve_structure(index: Index, question: str) -> StructureAnchors:
    """질문에 실제로 적힌 문서명·승인 약칭·조문 좌표만 구조 제약으로 만든다."""
    matches = _document_mentions(index, question)
    doc_ids, documents = [], []
    for _, _, doc_id, name in matches:
        if doc_id not in doc_ids:
            doc_ids.append(doc_id)
            documents.append(name)

    found_refs = [ref for ref in refs.find(question) if ref.unit == "조"]
    locators = list(dict.fromkeys([
        *(ref.surface.strip() for ref in found_refs if ref.surface.strip()),
    ]))
    coords: list[tuple[str, object]] = []
    unresolved = []
    for ref in found_refs:
        hinted = _hint_docs(index, ref.hint) if ref.hint else []
        if ref.hint and hinted:
            target_docs = hinted
        elif doc_ids:
            target_docs = doc_ids
        elif not doc_ids and len(index.entry_docs) == 1:
            target_docs = list(index.entry_docs)
        else:
            target_docs = []
        targets = []
        for doc_id in target_docs:
            view = index.entry_docs[doc_id]
            root = _resolve_ref(view, ref)
            if root is not None:
                targets.append((doc_id, root))
        # 참조 뒤에 다른 법령명이 인용돼 문서명이 둘 이상 잡혀도, 해당 좌표가
        # 실제로 한 문서에서만 존재하면 그 유일한 구조 사실로 확정한다. 같은 좌표가
        # 여러 문서에서 성립하면 기존처럼 추측하지 않는다.
        if len(target_docs) > 1 and not hinted and \
                len({doc_id for doc_id, _ in targets}) != 1:
            targets = []
        if not targets:
            unresolved.append(ref.surface.strip())
            continue
        for doc_id, root in targets:
            coords.extend((doc_id, node)
                          for node in _descendants(index.entry_docs[doc_id], root))
    return StructureAnchors(tuple(doc_ids), tuple(documents), tuple(locators),
                            tuple(dict.fromkeys(coords)),
                            tuple(dict.fromkeys(x for x in unresolved if x)))


def resolve_named_structure(index: Index, anchors: StructureAnchors,
                            spans: list[QuerySpan]) -> StructureAnchors:
    """TOC/Heading Span을 실제 구조 노드와 그 하위 좌표로 바인딩한다.

    같은 제목이 여러 번 나오면 하나를 임의 선택하지 않는다. 그 Span 안에서는 후보
    하위 트리의 합집합(OR)을 유지하고, 서로 다른 Heading/법조문 제약끼리는 교집합
    (AND)을 취한다. 이후 ACTOR/PREDICATE Assertion 검색도 이 좌표 안에서만 실행된다.
    """
    named = [span for span in spans if span.role in ("toc", "heading")]
    if not named:
        return anchors

    target_docs = list(anchors.doc_ids)
    if not target_docs:
        target_docs = list(index.entry_docs)
    current = set(anchors.source_coordinates) if anchors.source_coordinates else None
    locators = list(anchors.locators)
    unresolved = list(anchors.unresolved_locators)

    for span in named:
        candidates = named_structure_candidates(
            index, span.text, doc_ids=tuple(target_docs))
        # 문서 범위가 없을 때 여러 문서의 흔한 제목을 구조 앵커로 간주하면 질문의
        # 일반 명사를 우연히 Heading으로 잠그게 된다. 단일 문서에서만 맞을 때 연다.
        if not anchors.doc_ids and len({doc_id for doc_id, _ in candidates}) > 1:
            candidates = []
        if not candidates:
            unresolved.append(span.text)
            continue
        span_coords = {
            (doc_id, descendant)
            for doc_id, root in candidates
            for descendant in _descendants(index.entry_docs[doc_id], root)
        }
        current = span_coords if current is None else current & span_coords
        locators.append(span.text)
        if not current:
            unresolved.append(f"구조 교집합 없음:{span.text}")

    return StructureAnchors(
        anchors.doc_ids, anchors.documents, tuple(dict.fromkeys(locators)),
        tuple(sorted(current or (), key=lambda row: (row[0], str(row[1])))),
        tuple(dict.fromkeys(x for x in unresolved if x)),
    )


def named_structure_candidates(index: Index, text: str, *,
                               doc_ids: tuple[str, ...] = ()) -> list[tuple[str, object]]:
    """제목/목차 표면형과 정확히 같은 실제 Section 객체를 반환한다."""
    packed = _pack(text)
    if not packed:
        return []
    target_docs = list(doc_ids) if doc_ids else list(index.entry_docs)
    candidates: list[tuple[str, object]] = []
    for doc_id in target_docs:
        view = index.entry_docs.get(doc_id)
        if view is None:
            continue
        for node in view.nodes:
            labels = (node.get("title"), node.get("surface"), view.path(node.get("id")))
            if any(_pack(str(label or "")) == packed for label in labels):
                candidates.append((doc_id, node.get("id")))
    return list(dict.fromkeys(candidates))


def _type_role_compatible(role: str, concept_type: str) -> bool:
    if role == "predicate":
        return concept_type == "action"
    if role == "modality":
        return concept_type in ("modality", "action")
    if role in STRUCTURE_ROLES:
        return False
    if role in ("actor", "object", "target", "subject"):
        return concept_type != "action"
    return True


def _role_compatible(role: str, concept: Tier1Concept) -> bool:
    return _type_role_compatible(role, concept.type)


class PartRetriever:
    """Span마다 데이터에 실제 존재하는 부품을 회수한다. 점수는 메뉴 절삭용이다."""

    def __init__(self, registry: Tier1Registry, index: Index, *, lexicon=None,
                 per_span: int = PARTS_PER_SPAN):
        self.registry = registry
        self.index = index
        self.lexicon = lexicon
        # EXPAND 재호출 제거 뒤 남아 있던 12개 비밀 ceiling을 없앤다. 실험자가
        # 인자로 더 큰 값을 넣어도 등록된 단일 상한을 우회하지 못한다.
        self.per_span = max(1, min(int(per_span), PARTS_PER_SPAN))
        self.assertions = {a.id: a for a in registry.active_assertions}
        self.surface_index: dict[str, set[str]] = {}
        for cid, concept in registry.active_concepts.items():
            for surface in concept.surfaces:
                packed = _pack(surface)
                if packed:
                    self.surface_index.setdefault(packed, set()).add(cid)

    def _scope_assertions(self, anchors: StructureAnchors) -> set[str]:
        coords = set(anchors.source_coordinates)
        docs = set(anchors.doc_ids)
        out = set()
        for aid, assertion in self.assertions.items():
            source = assertion.source
            pair = (str(source.get("doc_id") or ""), source.get("node"))
            if coords and pair in coords:
                out.add(aid)
            elif not coords and docs and pair[0] in docs:
                out.add(aid)
        return out

    def _vector_ids(self, neighbors: list[dict]) -> set[str]:
        out = set()
        for row in neighbors:
            out.update(self.surface_index.get(_pack(row.get("term") or ""), ()))
        return out

    def _occurrences(self, concept_id: str, scope_aids: set[str]) -> tuple[dict, ...]:
        aids = list(self.registry.concept_assertions.get(concept_id, ()))
        aids.sort(key=lambda aid: (aid not in scope_aids, aid))
        out = []
        for aid in aids[:OCCURRENCES_PER_PART]:
            assertion = self.assertions.get(aid)
            if assertion is None:
                continue
            source = assertion.source
            doc_id, node = str(source.get("doc_id") or ""), source.get("node")
            view = self.index.docs.get(doc_id)
            section = view.by_id.get(node) if view else None
            roles = sorted(role for role, ids in assertion.roles.items()
                           if concept_id in ids)
            item = {"assertion_id": aid, "doc_id": doc_id, "node": node,
                    "roles": roles}
            if view is not None and section is not None:
                item.update(doc=view.name, path=view.path(node),
                            span=view.section_text(
                                section, cap=OCCURRENCE_CONTEXT_CHARS))
            out.append(item)
        return tuple(out)

    def menus(self, spans: list[QuerySpan], anchors: StructureAnchors) -> list[SpanMenu]:
        scope_aids = self._scope_assertions(anchors)
        scoped_ids = {cid for aid in scope_aids
                      for cid in self.registry.assertion_concepts.get(aid, ())}
        scoped_roles: dict[str, set[str]] = {}
        for aid in scope_aids:
            assertion = self.assertions[aid]
            for role, ids in assertion.roles.items():
                for cid in ids:
                    scoped_roles.setdefault(cid, set()).add(role)
        semantic_rows = [[] for _ in spans]
        if self.lexicon is not None:
            try:
                semantic_rows = self.lexicon.neighbors_many(
                    [span.text for span in spans],
                    k=self.per_span * RAW_SPAN_FACTOR,
                    min_cos=SEMANTIC_COS_MIN)
            except Exception:
                semantic_rows = [[] for _ in spans]
        menus = []
        for span_pos, span in enumerate(spans):
            if span.role in ("locator", "toc", "heading"):
                continue
            # ``document``는 두 뜻이 있다. 실제 코퍼스 문서명(구조 제약)은 메뉴에서
            # 빼지만, 투자설명서·계약서처럼 Assertion의 document Concept인 질문
            # 부품은 SUBJECT 후보로 계속 회수한다.
            structural_document = span.role == "document" and any(
                _doc_fold(name) in _pack(span.text) for name in anchors.documents
                if _doc_fold(name)
            )
            if structural_document:
                continue
            retrieval_role = "subject" if span.role == "document" else span.role
            vector_ids = self._vector_ids(semantic_rows[span_pos])
            ranked = []
            wanted_scope_roles = {
                "actor": {"ACTOR"}, "predicate": {"PREDICATE"},
                "object": {"OBJECT"}, "target": {"TARGET"},
                "subject": {"SUBJECT"}, "method": {"METHOD"},
                "modality": {"MODALITY", "PREDICATE"},
                "condition": {"CONDITION", "PREDICATE"},
                "effect": {"EFFECT", "PREDICATE"},
            }.get(retrieval_role, set())
            for cid, concept in self.registry.active_concepts.items():
                if not _role_compatible(retrieval_role, concept):
                    continue
                best = (0.0, "", "")
                for surface in concept.surfaces:
                    score, kind = _surface_score(span.text, surface)
                    if score > best[0]:
                        best = (score, surface, kind)
                in_scope = cid in scoped_ids and (not wanted_scope_roles or bool(
                    scoped_roles.get(cid, set()) & wanted_scope_roles))
                by_vector = cid in vector_ids
                if not (best[0] >= SURFACE_SCORE_MIN or in_scope or by_vector):
                    continue
                # 아래 값은 LLM의 의미 판단이 아니라 좁은 메뉴를 만들기 위한 순서다.
                retrieval = best[0] + (0.24 if in_scope else 0) + (0.16 if by_vector else 0)
                ranked.append((retrieval, best[0], in_scope, by_vector, cid,
                               best[1] or concept.label, best[2] or
                               ("vector" if by_vector else "scope")))
            ranked.sort(key=lambda row: (-row[0], -row[1], -len(_pack(row[5])), row[4]))
            chosen = ranked[:self.per_span]
            if scope_aids:
                # 조문 좌표가 확정된 질문에서는 그 조문에 실제로 등장하는 역할 부품을
                # 메뉴의 절반까지 보장한다. 전역에서 표면이 비슷한 일반어가 여덟 칸을
                # 모두 먹으면 LLM도 정답 부품을 볼 수 없다.
                scoped = [row for row in ranked if row[2]][:max(2, self.per_span // 2)]
                merged = {row[4]: row for row in scoped}
                for row in chosen:
                    if len(merged) >= self.per_span:
                        break
                    merged.setdefault(row[4], row)
                chosen = sorted(merged.values(),
                                key=lambda row: (-row[0], -row[1],
                                                 -len(_pack(row[5])), row[4]))
            parts = []
            for retrieval, _, _, _, cid, matched, kind in chosen[:self.per_span]:
                concept = self.registry.active_concepts[cid]
                occurrences = self._occurrences(cid, scope_aids)
                roles = sorted({role for occurrence in occurrences
                                for role in occurrence.get("roles", [])})
                parts.append(Part(
                    cid, concept.label, concept.type, matched, kind, retrieval,
                    tuple(roles), occurrences,
                ))
            menus.append(SpanMenu(span, parts))
        return menus


def _compose_schema(part_ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["SELECT", "NO_MATCH"]},
            "intent": {"type": "string",
                       "enum": ["ASSERTION_BY_PARTS", "CONCEPT_DEFINITION"]},
            "mappings": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "span_idx": {"type": "integer"},
                    "part_id": {"type": "string", "enum": part_ids},
                    "role": {"type": "string", "enum": list(PART_ROLES)},
                },
                "required": ["span_idx", "part_id", "role"],
                "additionalProperties": False,
            }},
        },
        "required": ["decision", "intent", "mappings"],
        "additionalProperties": False,
    }


def _menu_prompt(question: str, anchors: StructureAnchors,
                 menus: list[SpanMenu]) -> str:
    """조립에 필요한 최소 정보만 보낸다.

    정의는 정본 4만여 개 중 한 항목에만 있고, Assertion ID·문서 경로는 이미
    근거 주소로 확정되어 선택에 기여하지 않았다. 첫 실제 문맥 하나는 동형
    대표명의 뜻을 가르는 데 필요하므로 남긴다.
    """
    lines = [f"[질문]\n{question}", "\n[근거 주소]",
             f"문서={list(anchors.documents) or '없음'}",
             f"조문={list(anchors.locators) or '없음'}", "\n[단서별 후보]"]
    for idx, menu in enumerate(menus, 1):
        lines.append(f"\nS{idx} {menu.span.text!r} 자리={menu.span.role}")
        for part in menu.parts:
            context = str(
                (part.occurrences[0].get("span") if part.occurrences else "") or ""
            )[:PROMPT_CONTEXT_CHARS]
            lines.append(
                f"- {part.concept_id} | {part.label} | 종류={part.concept_type} | "
                f"발견={part.matched} | 자리={','.join(part.roles) or '-'} | "
                f"문맥={context}"
            )
    return "\n".join(lines)


def _predicate_semantics_match(llm, question: str, pairs: list[tuple[str, str]]) \
        -> tuple[bool, dict]:
    """낮은 표면 유사도의 술어만 닫힌 의미 판정으로 보강한다."""
    lines = [f"[전체 질문]\n{question}", "\n[비교할 술어]"]
    for pos, (query_span, approved) in enumerate(pairs, 1):
        lines.append(f"{pos}. 질문 술어={query_span!r} | 승인 술어={approved!r}")
    out = llm.structured(
        "rag.oql.predicate", PREDICATE_SYSTEM, "\n".join(lines),
        PREDICATE_SCHEMA, max_tokens=300, effort="low",
    )
    verdict = str((out or {}).get("verdict") or "UNSURE")
    audit = {"mode": "llm", "pairs": [list(pair) for pair in pairs],
             "verdict": verdict}
    # 구조 좌표와 닫힌 Concept 메뉴가 이미 후보를 제한한다. 의미 판정기가
    # 명시적으로 다른 술어라고 판정한 경우만 차단하고, 단순 불확실성 때문에
    # 유효한 바꿔쓰기를 버리지는 않는다.
    return verdict != "MISMATCH", audit


def compose(llm, registry: Tier1Registry, question: str, spans: list[QuerySpan],
            menus: list[SpanMenu], anchors: StructureAnchors) -> PartAlignment:
    empty = Alignment(question, via="span_parts_llm")
    allowed_by_span = {idx: {part.concept_id: part for part in menu.parts}
                       for idx, menu in enumerate(menus, 1)}
    part_ids = sorted({cid for parts in allowed_by_span.values() for cid in parts})
    if not part_ids:
        return PartAlignment(empty, spans, menus, anchors)
    out = llm.structured("rag.oql.compose", COMPOSE_SYSTEM,
                         _menu_prompt(question, anchors, menus),
                         _compose_schema(part_ids), max_tokens=1200, effort="low")
    if not out:
        return PartAlignment(empty, spans, menus, anchors)
    raw_mappings = [dict(row) for row in (out.get("mappings") or [])[:MAPPINGS_MAX]
                    if isinstance(row, dict)]

    # 일부 모델은 명시적인 S1 표기를 보고도 배열 관습대로 span_idx=0부터 센다.
    # ID가 실제로 어느 Span 메뉴에 속하는지 코드가 알고 있으므로 두 해석을 모두
    # 검증하고 하나만 성립할 때만 정규화한다. 둘 다 불가능하면 기존처럼 NO_MATCH,
    # 둘 다 가능하면 계약에 적힌 1-based를 택한다.
    mapping_options = []
    for shift, base in ((0, 1), (1, 0)):
        normalized = []
        valid = True
        for row in raw_mappings:
            raw_idx = row.get("span_idx")
            cid = str(row.get("part_id") or "")
            if not isinstance(raw_idx, int):
                valid = False
                break
            span_idx = raw_idx + shift
            if cid not in allowed_by_span.get(span_idx, {}):
                valid = False
                break
            normalized.append({**row, "span_idx": span_idx})
        if valid:
            mapping_options.append((base, normalized))
    # 모델이 선택한 항목만 1,2,3으로 다시 세어 sparse 메뉴 번호를 틀리는 경우가
    # 있다. 각 part_id가 전체 닫힌 메뉴 중 딱 한 곳에만 있으면 새 부품을 추론하지
    # 않고 그 유일한 소속 메뉴 번호로 복구할 수 있다.
    if not mapping_options and str(out.get("decision") or "NO_MATCH") == "SELECT":
        recovered = []
        for row in raw_mappings:
            cid = str(row.get("part_id") or "")
            locations = [idx for idx, parts in allowed_by_span.items() if cid in parts]
            requested_role = str(row.get("role") or "unknown")
            role_locations = [idx for idx in locations
                              if menus[idx - 1].span.role == requested_role]
            if len(role_locations) == 1:
                location = role_locations[0]
            elif len(locations) == 1:
                location = locations[0]
            else:
                recovered = []
                break
            recovered.append({**row, "span_idx": location})
        if recovered:
            mapping_options.append(("part_membership", recovered))
    if not mapping_options and str(out.get("decision") or "NO_MATCH") == "SELECT":
        proposal = {
            "decision": str(out.get("decision") or "NO_MATCH"),
            "intent": str(out.get("intent") or "ASSERTION_BY_PARTS"),
            "mappings": raw_mappings,
            "span_index_base": "invalid",
        }
        return PartAlignment(empty, spans, menus, anchors, "NO_MATCH", (proposal,))
    index_base, mappings = next(
        ((base, rows) for base, rows in mapping_options if base == 1),
        mapping_options[0] if mapping_options else (1, raw_mappings),
    )
    # 선택 ID가 현재 번호의 메뉴에도 있어 형식상 유효하더라도, 모델이 선언한 role과
    # 그 Span의 role이 다르고 같은 ID가 role 일치 메뉴에 딱 하나 있으면 위치만
    # 옮긴다. ID 선택 자체는 그대로라 메뉴 밖 의미를 보충하지 않는다.
    relocated = []
    normalized_mappings = []
    for row in mappings:
        cid = str(row.get("part_id") or "")
        requested_role = str(row.get("role") or "unknown")
        current_idx = row.get("span_idx")
        current_span_role = (
            menus[current_idx - 1].span.role
            if isinstance(current_idx, int) and 1 <= current_idx <= len(menus)
            else "unknown"
        )
        role_locations = [
            idx for idx, parts in allowed_by_span.items()
            if cid in parts and menus[idx - 1].span.role == requested_role
        ]
        if current_span_role != requested_role and len(role_locations) == 1:
            new_row = {**row, "span_idx": role_locations[0]}
            relocated.append({"from": current_idx, "to": role_locations[0],
                              "part_id": cid})
            normalized_mappings.append(new_row)
        else:
            normalized_mappings.append(row)
    mappings = normalized_mappings
    proposal = {
        "decision": str(out.get("decision") or "NO_MATCH"),
        "intent": str(out.get("intent") or "ASSERTION_BY_PARTS"),
        "mappings": mappings,
        "span_index_base": index_base,
    }
    if relocated:
        proposal["role_relocated_mappings"] = relocated
    proposals = (proposal,)
    decision = str(out.get("decision") or "NO_MATCH")
    if decision == "NO_MATCH":
        return PartAlignment(empty, spans, menus, anchors, "NO_MATCH", proposals)

    # 같은 Concept를 여러 Span에 중복 연결한 출력은 새 의미를 더하지 않는다.
    # 질문 Span과 실제 표면형의 일치도가 유일하게 높은 연결만 남기고, 동률이면
    # 여전히 모호하므로 전체를 거부한다.
    by_cid: dict[str, list[dict]] = {}
    for row in mappings:
        by_cid.setdefault(str(row.get("part_id") or ""), []).append(row)
    deduped, dropped = [], []
    for cid, rows in by_cid.items():
        if len(rows) == 1:
            deduped.extend(rows)
            continue
        scored = []
        for row in rows:
            span_idx = row.get("span_idx")
            part = allowed_by_span.get(span_idx, {}).get(cid)
            if part is None:
                continue
            span = menus[span_idx - 1].span
            role_hint = int(str(row.get("role") or "") == span.role)
            surface = max(_surface_score(span.text, part.matched)[0],
                          _surface_score(span.text, part.label)[0])
            scored.append(((role_hint, round(surface, 6)), row))
        if not scored:
            deduped = []
            break
        top_score = max(score for score, _ in scored)
        best = [row for score, row in scored if score == top_score]
        if len(best) != 1:
            deduped = []
            break
        deduped.append(best[0])
        dropped.extend(row for _, row in scored if row is not best[0])
    if mappings and not deduped:
        proposal["validation_error"] = "ambiguous_duplicate_mapping"
        return PartAlignment(empty, spans, menus, anchors, "NO_MATCH", proposals)
    if dropped:
        mappings = sorted(deduped, key=lambda row: row["span_idx"])
        proposal["mappings"] = mappings
        proposal["deduplicated_mappings"] = dropped

    picked, seen = [], set()
    if decision == "SELECT":
        for row in mappings:
            if not isinstance(row, dict):
                proposal["validation_error"] = "malformed_mapping"
                return PartAlignment(empty, spans, menus, anchors, "NO_MATCH", proposals)
            span_idx, cid = row.get("span_idx"), str(row.get("part_id") or "")
            role = str(row.get("role") or "unknown")
            if not isinstance(span_idx, int) or cid not in allowed_by_span.get(span_idx, {}) \
                    or role not in PART_ROLES or cid in seen:
                proposal["validation_error"] = "invalid_mapping"
                return PartAlignment(empty, spans, menus, anchors, "NO_MATCH", proposals)
            part = allowed_by_span[span_idx][cid]
            if not _type_role_compatible(role, part.concept_type):
                proposal["validation_error"] = "incompatible_role"
                return PartAlignment(empty, spans, menus, anchors, "NO_MATCH", proposals)
            seen.add(cid)
            picked.append((span_idx, part, role))
    intent = str(out.get("intent") or "ASSERTION_BY_PARTS")
    if intent not in ("ASSERTION_BY_PARTS", "CONCEPT_DEFINITION"):
        intent = "ASSERTION_BY_PARTS"
    selected = []
    if intent == "CONCEPT_DEFINITION":
        if len(picked) != 1:
            return PartAlignment(empty, spans, menus, anchors, "NO_MATCH", proposals)
        _, part, role = picked[0]
        selected.append(Candidate(part.concept_id, part.label, part.concept_type, 1.0,
                                  part.matched, "llm_part", role=role))
    else:
        # LLM은 복합 Span 하나에 여러 부품을 과선택할 수 있다. 전부의 교집합을
        # 요구하면 올바른 부품도 같이 탈락하므로, 실제 active Assertion마다 선택
        # 부품이 몇 Span에서 함께 나타나는지 센다. 구조 스코프 안에서 가장 많은
        # Span·식별 부품을 설명하는 Assertion의 일관된 부분집합만 채택한다.
        # 모델이 SELECT한 부품만 검증한다. 메뉴에 보였지만 고르지 않은 부품을 코드가
        # Assertion에 맞춰 대신 넣으면 NO_MATCH나 잘못된 predicate가 그 좌표의 실제
        # predicate로 바뀌는 자기확증이 된다. 과선택은 선택 부품의 일관된 부분집합을
        # 고르는 방식으로만 정리하고, 미선택 부품을 새로 추가하지 않는다.
        pool = [(span_idx, part, role, True) for span_idx, part, role in picked]

        coords = set(anchors.source_coordinates)
        docs = set(anchors.doc_ids)
        packed_question = _pack(question)
        generic_relation = bool(_GENERIC_RELATION.search(question))
        ranked = []
        for assertion in registry.active_assertions:
            source = assertion.source
            source_pair = (str(source.get("doc_id") or ""), source.get("node"))
            if coords and source_pair not in coords:
                continue
            if not coords and docs and source_pair[0] not in docs:
                continue
            by_span = {}
            for span_idx, part, requested_role, chosen in pool:
                actual = {role for role, ids in assertion.roles.items()
                          if part.concept_id in ids}
                if not actual:
                    continue
                identity = int(part.concept_type in {
                    "person_role", "organization_role", "document", "artifact",
                })
                predicate = int("PREDICATE" in actual)
                option = (int(chosen), identity, predicate, part.retrieval_score,
                          len(_pack(part.matched)), part.concept_id, part,
                          requested_role, actual)
                current = by_span.get(span_idx)
                if current is None or option[:5] > current[:5]:
                    by_span[span_idx] = option
            if len(by_span) < 2:
                continue
            choices = [(span_idx, *option) for span_idx, option in by_span.items()]
            identity_count = sum(row[2] for row in choices)
            predicate_count = sum(row[3] for row in choices)
            cue_hit = any(_pack(cue) in packed_question
                          for cue in assertion.query_cues if _pack(cue))
            if not generic_relation and not (predicate_count or cue_hit):
                continue
            score = (
                identity_count,
                int(bool(predicate_count)) + int(cue_hit),
                len(choices),
                sum(row[1] for row in choices),
                round(sum(row[4] for row in choices), 6),
                round(assertion.confidence, 6),
            )
            ranked.append((score, assertion.id, choices))
        if not ranked:
            proposal["validation_error"] = "no_grounded_assertion"
            return PartAlignment(empty, spans, menus, anchors, "NO_MATCH", proposals)
        ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
        top_score = ranked[0][0]
        top = [row for row in ranked if row[0] == top_score]

        def signature(row) -> tuple:
            return tuple(sorted((choice[0], choice[6], tuple(sorted(choice[9])))
                                for choice in row[2]))

        if len({signature(row) for row in top}) != 1:
            proposal["validation_error"] = "ambiguous_grounding"
            return PartAlignment(empty, spans, menus, anchors, "NO_MATCH", proposals)
        grounded_choices = sorted(top[0][2], key=lambda row: row[0])
        predicate_choices = [row for row in grounded_choices if "PREDICATE" in row[9]]
        if len(predicate_choices) > 1:
            ranked_predicates = []
            role_priority = {"predicate": 3, "modality": 2,
                             "effect": 1, "condition": 1}
            for row in predicate_choices:
                span = menus[row[0] - 1].span
                part = row[7]
                surface = max(_surface_score(span.text, part.matched)[0],
                              _surface_score(span.text, part.label)[0])
                rank = (role_priority.get(span.role, 0), round(surface, 6),
                        round(row[4], 6), row[5])
                ranked_predicates.append((rank, row))
            best_rank = max(rank for rank, _ in ranked_predicates)
            best = [row for rank, row in ranked_predicates if rank == best_rank]
            if len(best) == 1:
                keep = best[0]
                removed = [row for row in predicate_choices if row is not keep]
                grounded_choices = [row for row in grounded_choices if row not in removed]
                proposal["predicate_choice"] = {
                    "kept_part_id": keep[6],
                    "dropped_part_ids": [row[6] for row in removed],
                }

        predicate_pairs = []
        for span_idx, _chosen, _identity, _predicate, _retrieval, _length, _cid, part, \
                requested_role, actual \
                in grounded_choices:
            requested = requested_role.upper()
            if len(actual) == 1:
                resolved_role = next(iter(actual)).lower()
            elif requested in actual:
                resolved_role = requested_role
            else:
                proposal["validation_error"] = "ambiguous_role"
                return PartAlignment(empty, spans, menus, anchors, "NO_MATCH", proposals)
            selected.append(Candidate(part.concept_id, part.label, part.concept_type, 1.0,
                                      part.matched, "llm_part", role=resolved_role))
            if resolved_role == "predicate":
                query_span = menus[span_idx - 1].span.text
                score = max(_surface_score(query_span, part.matched)[0],
                            _surface_score(query_span, part.label)[0])
                if score < PREDICATE_SURFACE_FLOOR:
                    predicate_pairs.append((query_span, part.label))
        # 일반적인 A-B 관계 질문만 predicate 생략을 허용한다. 그 밖의 질문에서
        # 모델이 전송·신고 같은 다른 술어를 과선택했다가 일관된 부분집합에서 버리면,
        # 남은 두 실체만으로 전혀 다른 Assertion을 열지 못하게 한다.
        top_assertion = next(a for a in registry.active_assertions if a.id == top[0][1])
        cue_hit = any(_pack(cue) in packed_question
                      for cue in top_assertion.query_cues if _pack(cue))
        if not generic_relation and not cue_hit and \
                not any(candidate.role == "predicate" for candidate in selected):
            proposal["validation_error"] = "missing_predicate"
            return PartAlignment(empty, spans, menus, anchors, "NO_MATCH", proposals)
        if predicate_pairs:
            matched, audit = _predicate_semantics_match(
                llm, question, predicate_pairs)
            proposal["predicate_verification"] = audit
            if not matched:
                proposal["validation_error"] = "predicate_mismatch"
                return PartAlignment(empty, spans, menus, anchors, "NO_MATCH", proposals)
    alignment = Alignment(question, candidates=selected, selected=selected,
                          intent=intent, via="span_parts_llm", ambiguous=False)
    return PartAlignment(alignment, spans, menus, anchors, "SELECT", proposals)


def align(llm, registry: Tier1Registry, index: Index, question: str, *,
          lexicon=None, per_span: int = PARTS_PER_SPAN,
          anchors: Optional[StructureAnchors] = None) -> PartAlignment:
    spans = extract_spans(llm, question)
    anchors = anchors if anchors is not None else resolve_structure(index, question)
    if not spans:
        return PartAlignment(Alignment(question, via="span_parts_llm"), [], [], anchors)
    menus = PartRetriever(registry, index, lexicon=lexicon,
                          per_span=per_span).menus(spans, anchors)
    return compose(llm, registry, question, spans, menus, anchors)
