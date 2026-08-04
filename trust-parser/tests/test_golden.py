"""§9 (Part A) + §B11 (Part B) 완료 기준 골든 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import ontology  # noqa: E402

GOLDEN = ROOT.parent / "trust_contract_chunks_sample.json"
SS2207 = ROOT.parent / "first-agent" / "dataset" / "ss2207_special_trust.pdf"
CHUNKS_OUT = ROOT / "out" / "ss2207.chunks.json"
PAIR = ROOT / "data" / "golden_pairs" / "acct_001"


@pytest.fixture(scope="module")
def onto():
    return ontology.load(ontology.default_path(ROOT))


@pytest.fixture(scope="module")
def chunks():
    if not CHUNKS_OUT.exists():
        pytest.skip("out/ss2207.chunks.json 이 없습니다 — 먼저 cli.py parse 를 실행하세요")
    return json.loads(CHUNKS_OUT.read_text(encoding="utf-8"))["chunks"]


# ===========================================================================
# 온톨로지 (§C)
# ===========================================================================

def test_ontology_loads_and_is_consistent(onto):
    assert onto.doc_type and onto.version
    assert onto.default_role() == "약관본문"
    assert onto.containment_chain("조") == ["조", "항", "호"]
    assert onto.fields and onto.shapes


def test_ontology_is_single_source_of_domain_knowledge():
    """§C8 완료기준 1 — 태깅·정합성 규칙이 코드에 하드코딩돼 있지 않아야 한다.

    별지1 필드명·별칭이 소스에 리터럴로 박혀 있으면 실패한다.
    """
    forbidden = ["투자금액", "신탁원금", "중도상환수수료", "계좌번호", "원금지급비율"]
    offenders = []
    for py in (ROOT / "src").glob("*.py"):
        text = py.read_text(encoding="utf-8")
        for line in text.split("\n"):
            code = line.split("#")[0]
            if '"""' in line or line.strip().startswith("#"):
                continue
            for word in forbidden:
                if f'"{word}"' in code or f"'{word}'" in code:
                    offenders.append(f"{py.name}: {line.strip()[:70]}")
    assert not offenders, "도메인 값이 코드에 있습니다:\n" + "\n".join(offenders)


def test_aliases_come_from_ontology(onto):
    idx = onto.alias_index()
    assert idx.get("투자금액") == "신탁금액"
    assert idx.get("성과보수") == "수익보수"
    # 의도적 공백 — 이 별칭이 없어야 UNMAPPED 가 난다
    assert onto.fields["세부 운용지시"].aliases == []


# ===========================================================================
# §9 — Part A 완료 기준
# ===========================================================================

def test_9_1_schema_and_required_tags(chunks, onto):
    roles, levels = set(onto.enum("role")), set(onto.enum("level"))
    for c in chunks:
        assert c["role"] in roles, c["chunk_id"]
        assert c["level"] in levels, c["chunk_id"]
        assert c["topic"], c["chunk_id"]
        assert c["provenance"]["page"], c["chunk_id"]


def test_9_2_all_articles_present_and_no_boundary_crossing(chunks):
    import recognizers as rec
    body = [c for c in chunks if c["role"] == "약관본문"]
    nos = sorted({int(c["article"].strip("제조")) for c in body if c.get("article")})
    assert nos, "본문에 조가 없습니다"
    assert set(range(1, 33)) <= set(nos), f"빠진 조: {sorted(set(range(1,33))-set(nos))}"

    for c in body:
        found = {m.no for line in c["text"].split("\n")
                 if (m := rec.korean_article(line))}
        if c.get("article"):
            found.add(c["article"].strip("제조"))
        assert len(found) <= 1, f"{c['chunk_id']} 가 조 경계를 넘었습니다: {found}"


def test_9_3_matches_golden_reference(chunks):
    """정본 6개 대표 요소가 구조적으로 일치해야 한다."""
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["chunks"]
    for gc in golden:
        hit = [c for c in chunks
               if c.get("article") == gc.get("article")
               and c.get("clause") == gc.get("clause")
               and c["role"] == gc["role"]]
        if not hit and gc["role"] != "약관본문":
            leaf = gc["heading_path"][-1]
            hit = [c for c in chunks if c["role"] == gc["role"]
                   and leaf in " ".join(c.get("heading_path", []))]
        assert hit, f"정본 {gc['chunk_id']} 에 대응하는 청크가 없습니다"
        assert set(gc["refs"]) <= set(hit[0]["refs"]), \
            f"{gc['chunk_id']} refs 부족: 기대 {gc['refs']} 실제 {hit[0]['refs']}"


def test_9_4_article15_clause1_refs(chunks):
    hit = [c for c in chunks if c.get("article") == "제15조" and c.get("clause") == "①"]
    assert hit, "제15조① 청크가 없습니다"
    assert {"제3조", "제12조", "별지1"} <= set(hit[0]["refs"])


def test_9_5_appendix_fields_link_to_articles(chunks, onto):
    ap1 = [c for c in chunks if c["role"] == "별지1_입력"]
    linked = [c for c in ap1 if c.get("cross_ref_explicit")]
    assert len(linked) >= 8, f"별지1 조 링크가 부족합니다: {len(linked)}"
    body_articles = {c["article"] for c in chunks
                     if c["role"] == "약관본문" and c.get("article")}
    for c in linked:
        target = c["cross_ref_explicit"].replace("계약서", "").strip()
        assert target in body_articles, f"{c['chunk_id']} → {target} 가 본문에 없습니다"
        assert c["article"] == target


def test_9_6_chunk_boundaries_are_semantic(chunks, onto):
    """§9-6 — 모든 청크 경계가 의미 경계(조/항/필드/표)와 일치한다.

    토큰 예산은 폐기됐다(§D1: 임베딩 미사용 → 크기 제약이 사라짐).
    남은 기준은 **문장 중간·항 중간에서 잘린 청크가 없는가** 뿐이다.
    """
    levels = set(onto.enum("level"))
    bad_level = [c["chunk_id"] for c in chunks if c["level"] not in levels]
    assert not bad_level, f"의미 단위가 아닌 level: {bad_level}"

    # 조 경계는 hard — 온톨로지 선언과 청킹 결과가 같은 말을 해야 한다
    assert "조" in onto.hard_boundary_nodes()

    cut = []
    for c in chunks:
        text = c["text"].strip()
        if c["role"] != onto.default_role() or len(text) <= 60:
            continue
        if text[-1] in ",·" or text.endswith(("하며", "하고", "이며", "되며", "또는", "및")):
            cut.append(c["chunk_id"])
    assert not cut, f"문장 중간에서 끊긴 청크: {cut}"


def test_9_6_chunking_follows_ontology(chunks, onto):
    """청킹 단위가 코드 상수가 아니라 온톨로지 선언에서 나온다(§C6)."""
    import chunk as chunk_mod
    assert not hasattr(chunk_mod, "TOKEN_HARD_MAX"), "토큰 예산이 남아 있습니다 (§D1 폐기)"

    primary = onto.nodes_with_chunk("primary")        # 조
    splittable = onto.nodes_with_chunk("split_if_long")  # 항
    inline = onto.nodes_with_chunk("inline")          # 호
    body_levels = {c["level"] for c in chunks if c["role"] == onto.default_role()}
    assert body_levels <= set(primary) | set(splittable), \
        f"본문 청크 level 이 선언 밖입니다: {body_levels}"
    assert body_levels & set(inline) == set(), "inline 선언 단위가 독립 청크로 나왔습니다"


def test_9_7_refs_resolve(chunks, onto):
    """미해소 참조는 경고여야 하고, 내부 조 참조는 전부 해소돼야 한다."""
    articles = {c["article"] for c in chunks if c.get("article")}
    appendices = {f"별지{p.appendix_no}" for p in onto.appendix_parts() if p.appendix_no}
    known = articles | appendices | {"각호"}
    unresolved = {r for c in chunks for r in c["refs"] if r not in known}
    # 외부 법령 참조(「금융소비자보호법」 제46·47조)만 남아야 한다
    assert unresolved <= {"제46조", "제47조"}, f"예상 밖 미해소 참조: {unresolved}"


def test_shape_validation_has_no_errors(chunks, onto):
    import validate
    from schema import ChunkDocument
    doc = ChunkDocument.model_validate(
        {"document": "t", "schema_version": "facet-v1", "chunks": chunks})
    violations = validate.run(doc, onto)
    errors = [v for v in violations if v.severity == "error"]
    assert not errors, "\n".join(f"{v.shape}: {v.message}" for v in errors)
