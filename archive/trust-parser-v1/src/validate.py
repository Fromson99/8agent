"""T16. fact 검증기 — 인스턴스 계층을 온톨로지에 대해 검사 (SPEC §C7-3).

의미론은 **검증형(SHACL 계열)** 이다(§C2). 새 사실을 유도하지 않고,
"이미 추출된 fact 가 규칙에 부합하는가"만 본다.

shape 이름은 온톨로지가 선언하고(`shapes:`), 검사 로직은 여기 등록돼 있다.
어떤 검사를 켤지는 선언, 어떻게 검사할지는 코드 — 이 경계가 실용적 한계선이다.
(완전한 선언성은 임의 술어를 표현할 언어가 필요해 지금 단계에선 과하다.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from ontology import Ontology
from schema import Chunk, ChunkDocument


@dataclass
class Violation:
    shape: str
    severity: str          # error | warning
    message: str
    chunk_id: Optional[str] = None

    def as_dict(self) -> dict:
        d = {"shape": self.shape, "severity": self.severity, "message": self.message}
        if self.chunk_id:
            d["chunk_id"] = self.chunk_id
        return d


Check = Callable[[ChunkDocument, Ontology], list[Violation]]
REGISTRY: dict[str, Check] = {}


def shape(name: str):
    def deco(fn: Check) -> Check:
        REGISTRY[name] = fn
        return fn
    return deco


# ===========================================================================
# 등록된 shape 검사
# ===========================================================================

@shape("required_tags_present")
def _required_tags(doc: ChunkDocument, onto: Ontology) -> list[Violation]:
    """§9-1 — 모든 청크에 role·topic·level·provenance.page 가 있어야 한다."""
    roles, levels = set(onto.enum("role")), set(onto.enum("level"))
    out = []
    for c in doc.chunks:
        if not c.role or c.role not in roles:
            out.append(Violation("required_tags_present", "error",
                                 f"role '{c.role}' 이 온톨로지 enum 밖입니다", c.chunk_id))
        if not c.level or c.level not in levels:
            out.append(Violation("required_tags_present", "error",
                                 f"level '{c.level}' 이 온톨로지 enum 밖입니다", c.chunk_id))
        if not c.topic:
            out.append(Violation("required_tags_present", "error", "topic 이 비어 있습니다", c.chunk_id))
        if not c.provenance or not c.provenance.page:
            out.append(Violation("required_tags_present", "error", "provenance.page 가 없습니다", c.chunk_id))
    return out


@shape("no_chunk_crosses_조_boundary")
def _no_cross_article(doc: ChunkDocument, onto: Ontology) -> list[Violation]:
    """§9-2 — 어떤 청크도 조 경계를 넘지 않는다.

    청크 하나에 서로 다른 조 헤더가 두 개 이상 등장하면 경계를 넘은 것이다.
    """
    import recognizers as rec
    out = []
    for c in doc.chunks:
        if c.role != onto.default_role():
            continue
        found = set()
        for line in c.text.split("\n"):
            m = rec.korean_article(line)
            if m:
                found.add(m.no)
        if c.article:
            found.add(c.article.strip("제조"))
        if len(found) > 1:
            out.append(Violation("no_chunk_crosses_조_boundary", "error",
                                 f"한 청크에 여러 조가 섞였습니다: {sorted(found)}", c.chunk_id))
    return out


@shape("every_조_has_exactly_one_번호")
def _article_numbering(doc: ChunkDocument, onto: Ontology) -> list[Violation]:
    """조 번호가 연속이고 중복이 없어야 한다."""
    body = doc.by_role(onto.default_role())
    nos = []
    for c in body:
        if c.article:
            n = c.article.strip("제조")
            if n.isdigit() and int(n) not in nos:
                nos.append(int(n))
    if not nos:
        return [Violation("every_조_has_exactly_one_번호", "error", "본문에 조가 없습니다")]
    out = []
    missing = sorted(set(range(1, max(nos) + 1)) - set(nos))
    if missing:
        out.append(Violation("every_조_has_exactly_one_번호", "error",
                             f"조 번호가 빠졌습니다: {missing}"))
    return out


@shape("refs_resolve_to_existing_target")
def _refs_resolve(doc: ChunkDocument, onto: Ontology) -> list[Violation]:
    """§9-7 — refs 의 모든 항목이 실제 조/별지로 해소돼야 한다. 미해소는 경고."""
    articles = {c.article for c in doc.chunks if c.article}
    appendices = {f"별지{p.appendix_no}" for p in onto.appendix_parts() if p.appendix_no}
    known = articles | appendices | {"각호"}
    out = []
    for c in doc.chunks:
        for r in c.refs:
            if r not in known:
                out.append(Violation("refs_resolve_to_existing_target", "warning",
                                     f"참조 '{r}' 를 해소하지 못했습니다", c.chunk_id))
    return out


@shape("appendix_field_links_to_article")
def _appendix_links(doc: ChunkDocument, onto: Ontology) -> list[Violation]:
    """§9-5 — 별지 입력 필드가 `계약서제N조` 링크로 올바른 topic 에 연결돼야 한다."""
    body_role = onto.default_role()
    articles = {c.article for c in doc.chunks if c.article and c.role == body_role}
    out = []
    for c in doc.chunks:
        if c.role == body_role or c.level not in ("필드", "표"):
            continue
        if not c.cross_ref_explicit:
            continue                       # 링크가 없는 필드도 있다(계좌번호 등) — 오류 아님
        target = c.cross_ref_explicit.replace("계약서", "").strip()
        if target not in articles:
            out.append(Violation("appendix_field_links_to_article", "error",
                                 f"cross_ref '{c.cross_ref_explicit}' 가 본문에 없는 조를 가리킵니다",
                                 c.chunk_id))
        elif c.article != target:
            out.append(Violation("appendix_field_links_to_article", "error",
                                 f"article '{c.article}' 이 cross_ref '{target}' 와 다릅니다",
                                 c.chunk_id))
    return out


@shape("chunk_boundaries_are_semantic")
def _semantic_boundaries(doc: ChunkDocument, onto: Ontology) -> list[Violation]:
    """§9-6 — 모든 청크 경계가 의미 경계(조/항/필드/표)와 일치해야 한다.

    토큰 예산은 폐기됐다(§D1: 임베딩 미사용 → 크기 제약 없음).
    대신 **문장 중간·항 중간에서 잘린 청크가 없는지**를 본다.
    """
    levels = set(onto.enum("level"))
    out = []
    for c in doc.chunks:
        if c.level not in levels:
            out.append(Violation("chunk_boundaries_are_semantic", "error",
                                 f"level '{c.level}' 이 의미 단위가 아닙니다", c.chunk_id))
            continue
        text = (c.text or "").strip()
        if not text:
            continue
        # 서술형 청크가 조사·접속으로 끝나면 문장 중간에서 잘린 것이다
        if c.role == onto.default_role() and len(text) > 60:
            tail = text[-1]
            if tail in ",·" or text.endswith(("하며", "하고", "이며", "되며", "또는", "및")):
                out.append(Violation("chunk_boundaries_are_semantic", "warning",
                                     f"문장 중간에서 끊긴 것으로 보입니다: …{text[-24:]}",
                                     c.chunk_id))
    return out


# ===========================================================================

def run(doc: ChunkDocument, onto: Ontology, extra: Optional[list[str]] = None) -> list[Violation]:
    """온톨로지가 선언한 shape 만 실행한다."""
    names = list(onto.shapes) + list(extra or [])
    out: list[Violation] = []
    for name in names:
        fn = REGISTRY.get(name)
        if fn is None:
            out.append(Violation(name, "warning", "등록되지 않은 shape 입니다 — 검사를 건너뜁니다"))
            continue
        out.extend(fn(doc, onto))
    return out


def summarize(violations: list[Violation]) -> dict:
    return {
        "total": len(violations),
        "error": sum(1 for v in violations if v.severity == "error"),
        "warning": sum(1 for v in violations if v.severity == "warning"),
    }
