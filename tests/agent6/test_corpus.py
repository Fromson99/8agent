"""코퍼스 빌드 · 근거 통로 테스트 (AGENT6 §2, T-A6.2).

여기서 지키는 것은 하나다: **근거 없는 판정이 나가지 않는다.**
그래서 "빌드가 돈다"보다 "빌드가 무엇을 거부하는가"에 더 많은 줄을 쓴다 —
거부하지 못하는 게이트는 게이트가 아니다.

합성 픽스처만 쓴다. 실제 법령 원문(agents/agent6/corpus/raw/KSB.pdf)은 docling 을
태워야 하므로 테스트에서 부르지 않는다. 대신 같은 라우터·같은 형식으로 도는 합성 txt 를
쓴다 — 검증하는 것은 조문 내용이 아니라 파이프라인이다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.agent6.src import basis, schema
from agents.agent6.src import corpus_build as cb

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/agent6/fixtures/corpus"
RAW = FIXTURES / "raw"
BAD = FIXTURES / "bad"
ITEMS = ROOT / "agents/agent6/checklist/items"


@pytest.fixture(scope="module")
def items() -> list[schema.ChecklistItem]:
    return schema.load_items(ITEMS, warn=False)


@pytest.fixture(scope="module")
def built(tmp_path_factory, items):
    """합성 코퍼스로 한 번 빌드해 두고 여러 테스트가 나눠 쓴다."""
    out = tmp_path_factory.mktemp("corpus")
    manifest = cb.build(RAW, out, items, allow_synthetic=True)
    return manifest, out


# ===========================================================================
# provenance — 출처 없는 원문은 근거가 될 수 없다
# ===========================================================================

def test_헤더_없는_원문은_거부된다():
    with pytest.raises(cb.ProvenanceError) as exc:
        cb.read_provenance(BAD / "NOHEAD.txt")
    assert "출처 표기가 없습니다" in str(exc.value)


def test_doc_id가_파일명과_다르면_거부된다():
    # 통과시키면 basis 좌표 "KSB/제19조" 가 엉뚱한 파일을 근거로 삼는다.
    with pytest.raises(cb.ProvenanceError) as exc:
        cb.read_provenance(BAD / "MISMATCH.txt")
    assert "파일명과 다릅니다" in str(exc.value)


def test_첫머리_주석에서_목록과_참거짓을_읽는다():
    prov = cb.read_provenance(RAW / "KSB.txt")
    assert prov.doc_id == "KSB"
    assert prov.verification == "SYNTHETIC"
    assert prov.doc_type == "금소법"
    assert prov.strip_patterns == [r"^테스트페이지 \d+ 합성코퍼스$"]


def test_같은_ID를_두_파일이_주장하면_둘_다_거부된다(tmp_path, items):
    """하나를 고르면(예: 이름순 첫 번째) 아무도 그 선택을 보지 못한 채 판정이 나간다."""
    raw = tmp_path / "raw"
    raw.mkdir()
    head = ("# doc_id: KSB\n# title: 합성\n# source: 테스트\n# collected: 2026-08-05\n"
            "# verification: SYNTHETIC\n# doc_type: 금소법\n\n합성 픽스처 — 실제 법령 아님\n")
    (raw / "KSB.txt").write_text(head + "제19조(설명의무) 합성 조문이다.\n", encoding="utf-8")
    (raw / "KSB.md").write_text(head + "제19조(설명의무) 다른 합성 조문이다.\n", encoding="utf-8")

    manifest = cb.build(raw, tmp_path / "out", items, allow_synthetic=True)
    ksb = [c for c in manifest["corpora"] if c["id"] == "KSB"]
    assert len(ksb) == 2 and all(c["status"] == cb.REJECTED for c in ksb)
    assert all("주장합니다" in c["reason"] for c in ksb)
    assert manifest["stats"]["resolved"] == 0


def test_verification_값이_어휘_밖이면_거부된다(tmp_path):
    p = tmp_path / "X.txt"
    p.write_text("# doc_id: X\n# title: t\n# source: s\n# collected: 2026-08-05\n"
                 "# verification: 아마도\n\n본문\n", encoding="utf-8")
    with pytest.raises(cb.ProvenanceError):
        cb.read_provenance(p)


# ===========================================================================
# 빌드 — 해소/미해소가 사실과 맞는가
# ===========================================================================

def test_합성_코퍼스로_빌드가_돈다(built):
    manifest, out = built
    ksb = next(c for c in manifest["corpora"] if c["id"] == "KSB")
    assert ksb["status"] == cb.OK
    # 잔여 2 = 픽스처 첫머리의 합성 고지문 두 줄(제1장 이전 = 기본 구역).
    # 출처 표기(# doc_id: …)는 빌드가 떼므로 잔여에 나타나면 안 된다.
    assert ksb["residual"] == 2
    assert (out / "structured/KSB.doc.json").exists()
    assert manifest["stats"]["resolved"] + manifest["stats"]["missing"] == len(manifest["basis"])


def test_요구된_KSB_좌표가_전부_해소된다(built, items):
    """픽스처가 체크리스트를 따라가지 못하면 여기서 걸린다.

    W3 이 새 조문 좌표를 추가했는데 픽스처에 그 조문이 없으면 이 테스트가 깨진다 —
    그것이 정상이다. 픽스처에 조문을 더하라는 신호다(지어내지 말고 합성문으로).
    """
    manifest, _ = built
    ksb_rows = [r for r in manifest["basis"] if r["doc"] == "KSB"]
    assert ksb_rows, "체크리스트에 KSB basis 가 하나도 없습니다"
    unresolved = [r["coord"] for r in ksb_rows if r["status"] != cb.RESOLVED]
    assert not unresolved, f"픽스처에 조문이 모자랍니다: {unresolved}"


def test_원문이_없는_코퍼스의_좌표는_MISSING이다(built):
    manifest, _ = built
    present = {c["id"] for c in manifest["corpora"] if c["status"] == cb.OK}
    for row in manifest["basis"]:
        if row["doc"] not in present:
            assert row["status"] == cb.MISSING
            assert row["reason"], f"{row['coord']}: 미해소인데 사유가 없습니다"


def test_코퍼스_ID만_적은_basis는_아예_받지_않는다():
    """예전에는 `{doc: REC}` 처럼 ID 만 적는 것을 허용했고, 그것이 영영 미해소로 남았다.

    지금은 스키마가 **로드 시점에** 거부한다 — 어느 조문을 말하는지 아무도 모르는 좌표는
    근거가 아니라 수집 대기 메모이며, 그런 메모는 항목의 note 에 적는다.
    """
    with pytest.raises(Exception) as exc:
        schema.Basis.model_validate({"doc": "REC"})
    assert "term 도 section 도 없습니다" in str(exc.value)


def test_체크리스트의_모든_basis는_용어이거나_좌표다(items):
    """근거의 자리에 "나중에 채울 것"이 남아 있지 않은지 — 미해소를 만드는 첫 번째 원인이다."""
    for item in items:
        for b in item.basis:
            assert b.anchored or b.pinned, f"{item.id}: {b.doc} 에 term 도 section 도 없습니다"
            assert basis.excerpt_path(b.coordinate())    # 좌표 → 파일 이름이 정해진다


def test_항_좌표는_원문자로_정규화되어_해소된다(built):
    """체크리스트는 '제3항', 원문은 '제③항' — 해소기가 그 간극을 메운다."""
    manifest, out = built
    row = next((r for r in manifest["basis"] if r["coord"] == "KSB/제19조/제3항"), None)
    assert row and row["status"] == cb.RESOLVED
    assert row["section_id"] == "제19조/제③항"


def test_조_좌표의_발췌에_항호목이_함께_들어간다(built):
    manifest, out = built
    text = basis.load_excerpt("KSB/제19조", corpus_dir=out)
    assert "제19조(설명의무)" in text
    assert "제1호" in text and "가목" in text and "제③항" in text


def test_요구되지_않은_조문은_발췌하지_않는다(built):
    """발췌는 '미리 연결'의 결과물이지 조문 덤프가 아니다."""
    manifest, out = built
    made = {p.stem for p in (out / "excerpts/KSB").glob("*.txt")}
    wanted = {r["section"].replace("/", "_") for r in manifest["basis"]
              if r["doc"] == "KSB" and r["section"]}
    assert made == wanted
    assert "제20조" not in made          # 원문에는 있지만 아무도 요구하지 않았다


def test_발췌에서_페이지_장식이_제거된다(built):
    manifest, out = built
    text = basis.load_excerpt("KSB/제19조", corpus_dir=out)
    assert "테스트페이지" not in text, "strip_patterns 가 적용되지 않았습니다"


def test_발췌_머리글에_판본과_verification이_남는다(built):
    manifest, out = built
    head = basis.excerpt_header("KSB/제19조", corpus_dir=out)
    assert head["verification"] == "SYNTHETIC"
    assert head["section_id"] == "제19조"
    # 프롬프트로 나가는 본문에는 머리글이 섞이지 않는다
    assert "verification" not in basis.load_excerpt("KSB/제19조", corpus_dir=out)


# ===========================================================================
# SYNTHETIC — 합성 조문이 진짜 근거처럼 유통되지 않게
# ===========================================================================

def test_SYNTHETIC은_기본_거부되고_플래그로만_통과한다(tmp_path, items):
    manifest = cb.build(RAW, tmp_path, items, allow_synthetic=False)
    ksb = next(c for c in manifest["corpora"] if c["id"] == "KSB")
    assert ksb["status"] == cb.REJECTED
    assert "SYNTHETIC" in ksb["reason"]
    assert manifest["stats"]["resolved"] == 0
    assert not list(tmp_path.glob("excerpts/**/*.txt"))


def test_거부된_코퍼스의_좌표는_사유에_코퍼스_상태를_담는다(tmp_path, items):
    manifest = cb.build(RAW, tmp_path, items, allow_synthetic=False)
    row = next(r for r in manifest["basis"] if r["coord"] == "KSB/제19조")
    assert row["status"] == cb.MISSING
    assert cb.REJECTED in row["reason"]


# ===========================================================================
# 조 연속성 — 파싱 누락이 조용히 지나가지 않게
# ===========================================================================

def test_조_결번이_보고된다(built):
    manifest, _ = built
    ksb = next(c for c in manifest["corpora"] if c["id"] == "KSB")
    art = ksb["articles"]
    assert art["range"] == [17, 47]
    assert 24 in art["gaps"] and 45 in art["gaps"]     # 픽스처는 제24~45조가 없다
    assert any("결번" in w for w in ksb["warnings"]), "결번이 경고로 나오지 않았습니다"


def test_조_마커가_없으면_그_사실이_남는다():
    """조 구조가 아닌 문서(예: 표준투자권유준칙)를 조/항/호로 자르면 여기서 드러난다."""
    from core.structurize import Document
    empty = Document(doc_type="x", format_version=1, source_file="x")
    assert cb._article_check(empty)["count"] == 0


# ===========================================================================
# 차단 — 미해소 basis 를 가진 항목은 활성화되지 않는다
# ===========================================================================

def test_미해소_basis_항목이_차단된다(built, items):
    manifest, _ = built
    blocked = basis.blocked_items(items, manifest)
    assert blocked, "미해소 basis 가 있는데 차단 항목이 없습니다"
    by_id = {i.id: i for i in items}
    resolved = {r["coord"] for r in manifest["basis"] if r["status"] == cb.RESOLVED}
    for item_id, reason in blocked.items():
        미해소 = [c for c in by_id[item_id].basis_refs() if c not in resolved]
        assert 미해소, f"{item_id} 는 전부 해소됐는데 차단됐습니다"
        assert 미해소[0] in reason
    # 근거가 전부 해소된 항목은 차단되지 않는다
    assert "B-07" not in blocked and "F-28" not in blocked


def test_차단은_기본이고_완화는_이름을_대야_한다(built, items):
    """완화는 **이름을 대야** 한다 — 코퍼스 ID 로도, 좌표 하나로도 된다. 전부 푸는 값은 없다."""
    manifest, _ = built
    strict = basis.blocked_items(items, manifest)
    assert "C-18" in strict and "A-03" in strict              # KOFIA-R 원문 미수집

    # 좌표 하나만 눈감으면 그 항목만 풀린다.
    좁게 = basis.blocked_items(items, manifest, allow_missing=["KOFIA-R#숙려기간"])
    assert "C-18" not in 좁게 and "A-03" in 좁게

    # 코퍼스 ID 를 대면 그 문서를 근거로 삼는 항목이 전부 풀린다.
    넓게 = basis.blocked_items(items, manifest, allow_missing=["KOFIA-R"])
    assert not ({"C-18", "A-03"} & set(넓게))


def test_manifest에_차단_결과가_박혀_있다(built, items):
    """호출자가 blocked_items 를 잊어도 리포트에는 남아야 한다."""
    manifest, _ = built
    assert manifest["blocked_items"] == basis.blocked_items(items, manifest)
    assert manifest["stats"]["blocked_items"] == len(manifest["blocked_items"])


def test_활성_가능_항목은_차단_항목의_여집합이다(built, items):
    manifest, _ = built
    ok = {i.id for i in basis.activatable(items, manifest)}
    assert ok.isdisjoint(manifest["blocked_items"])
    assert ok | set(manifest["blocked_items"]) == {i.id for i in items if i.enabled}


# ===========================================================================
# 근거 통로 — manifest 와 디스크가 어긋나면 시끄럽다
# ===========================================================================

def test_resolve는_해소된_좌표만_싣는다(built, items):
    manifest, out = built
    ctx = basis.resolve(items, manifest, corpus_dir=out)
    resolved = {r["coord"] for r in manifest["basis"] if r["status"] == cb.RESOLVED}
    assert set(ctx) == resolved
    assert all(t.strip() for t in ctx.values())


def test_manifest가_모르는_좌표는_예외다(built, items):
    """체크리스트를 고친 뒤 코퍼스를 다시 빌드하지 않은 상태 — 조용히 넘기면 안 된다."""
    manifest, out = built
    stale = json.loads(json.dumps(manifest))
    stale["basis"] = [r for r in stale["basis"] if r["coord"] != "KSB/제19조"]
    with pytest.raises(basis.BasisError) as exc:
        basis.resolve(items, stale, corpus_dir=out)
    assert "KSB/제19조" in str(exc.value)


def test_manifest는_RESOLVED인데_파일이_없으면_예외다(built, items, tmp_path):
    manifest, out = built
    with pytest.raises(basis.ExcerptMissing):
        basis.resolve(items, manifest, corpus_dir=tmp_path)   # 빈 디렉터리


def test_회수된_코퍼스의_묵은_발췌는_지워진다(tmp_path, items):
    """코퍼스가 빠졌는데 예전 발췌가 남아 있으면 런타임이 그것을 읽어 버린다."""
    cb.build(RAW, tmp_path, items, allow_synthetic=True)
    ghost = tmp_path / "excerpts/GHOST/제1조.txt"
    ghost.parent.mkdir(parents=True, exist_ok=True)
    ghost.write_text("# 좌표: GHOST/제1조\n\n묵은 발췌\n", encoding="utf-8")
    manifest = cb.build(RAW, tmp_path, items, allow_synthetic=True)
    assert not ghost.exists()
    assert any("GHOST" in p for p in manifest["removed_excerpts"])


def test_없는_발췌를_읽으면_시끄럽게_실패한다(tmp_path):
    with pytest.raises(basis.ExcerptMissing):
        basis.load_excerpt("KSB/제99조", corpus_dir=tmp_path)


def test_section_없는_좌표는_발췌를_특정할_수_없다():
    with pytest.raises(basis.BasisError):
        basis.excerpt_path("CASE")


# ===========================================================================
# 용어 앵커 — 문서 안의 좌표를 용어로 잡는다 (§새 basis 표기)
# ===========================================================================
#
# 용어집의 본래 용도는 **문서 안의 좌표를 잡는 것**이다. 손으로 조 번호를 세지 않아도
# 되고, 개정으로 번호가 밀려도 용어는 남는다. 그 대신 지켜야 하는 규율이 하나 있다:
# **여러 곳에 걸리면 고르지 않는다.** 아무 곳이나 고르면 판정자는 엉뚱한 조문을 근거로
# 확신하게 되고, 그 확신은 리포트에 근거 있는 판정처럼 실린다.

@pytest.fixture(scope="module")
def doc(built):
    """빌드가 만든 doc.json — 해소기는 이 안의 제목·fact 만 본다(검색이 아니다)."""
    _, out = built
    return json.loads((out / "structured/KSB.doc.json").read_text(encoding="utf-8"))


def test_제목에_있는_용어는_그_구역으로_해소된다(doc):
    got = basis.resolve_term(doc, "설명의무")
    assert got.status == basis.RESOLVED
    assert got.section_id == "제19조"
    assert got.via == "제목"


def test_여러_곳에_걸리면_고르지_않고_후보를_전부_보고한다(doc):
    """'원칙' 은 제17조(적합성 원칙)와 제18조(적정성 원칙) 두 제목에 걸린다."""
    got = basis.resolve_term(doc, "원칙")
    assert got.status == basis.AMBIGUOUS
    assert got.section_id is None                     # 추측하지 않는다
    assert {c["section_id"] for c in got.candidates} == {"제17조", "제18조"}
    assert "section 을 함께 적어 좁히세요" in got.reason


def test_section_으로_범위를_좁히면_해소된다(doc):
    """`{ doc: KSB, term: 원칙, section: 제17조 }` — 용어 + 좌표로 좁히는 표기."""
    scope = basis.subtree_ids(doc, ["제17조"])
    got = basis.resolve_term(doc, "원칙", scope=scope)
    assert got.status == basis.RESOLVED and got.section_id == "제17조"


def test_원문에_없는_용어는_지어내지_않는다(doc):
    """'없는 것을 있다고 쓰지 않는다' — 못 찾으면 왜 못 찾았는지까지 말한다."""
    got = basis.resolve_term(doc, "고령투자자")
    assert got.status == basis.MISSING
    assert got.section_id is None
    assert "구역 제목에도 fact 에도 없습니다" in got.reason


def _시험용_항목(tmp_path: Path, **basis_yaml: str) -> Path:
    """용어 앵커만 다른 최소 항목들을 만든다(실제 체크리스트를 건드리지 않는다)."""
    d = tmp_path / "items"
    d.mkdir(parents=True, exist_ok=True)
    for item_id, b in basis_yaml.items():
        (d / f"{item_id}.yaml").write_text(
            f"id: {item_id}\n"
            f"name: 용어 앵커 시험\n"
            f"type: 존재형\n"
            f"when: always\n"
            f"basis:\n  - {b}\n"
            f"operational_definition: >\n"
            f"  코퍼스 빌드의 용어 앵커 해소를 시험하기 위한 항목이다. 판정에 쓰지 않는다.\n"
            f"judgment_hints:\n  fail_route: PB보완\n", encoding="utf-8")
    return d


def test_용어_앵커가_manifest에_무엇을_물었고_어디로_갔는지_남긴다(tmp_path):
    items = schema.load_items(
        _시험용_항목(tmp_path, **{"B-06": "{ doc: KSB, term: 설명의무 }"}), warn=False)
    manifest = cb.build(RAW, tmp_path / "out", items, allow_synthetic=True)

    row = next(r for r in manifest["basis"] if r["coord"] == "KSB#설명의무")
    assert row["status"] == cb.RESOLVED
    assert row["anchor"]["section_id"] == "제19조" and row["anchor"]["via"] == "제목"

    # 발췌 파일 이름은 **물은 좌표**로 짓는다 — 개정으로 조 번호가 밀려도 런타임은
    # 같은 파일을 계속 찾는다(용어 앵커를 두는 이유가 그것이다).
    ref = basis.load_ref("KSB#설명의무", corpus_dir=tmp_path / "out")
    assert ref.query == "KSB#설명의무" and ref.coordinate == "KSB/제19조"
    assert ref.moved                                   # 물은 것 ≠ 해소된 곳
    assert "제19조(설명의무)" in ref.text
    assert ref.header["용어 앵커"].startswith("설명의무 → 제19조")


def test_모호한_앵커는_발췌를_만들지_않고_AMBIGUOUS로_보고한다(tmp_path):
    items = schema.load_items(
        _시험용_항목(tmp_path, **{"B-06": "{ doc: KSB, term: 원칙 }"}), warn=False)
    out = tmp_path / "out"
    manifest = cb.build(RAW, out, items, allow_synthetic=True)

    row = next(r for r in manifest["basis"] if r["coord"] == "KSB#원칙")
    assert row["status"] == cb.AMBIGUOUS
    assert len(row["anchor"]["candidates"]) == 2
    assert manifest["stats"]["ambiguous"] == 1
    # 모호한 항목은 차단되고, 사유가 리포트에 실린다.
    assert "B-06" in manifest["blocked_items"]
    assert "KSB#원칙" in cb.render_report(manifest)

    # 런타임이 그 좌표를 읽으려 하면 "없음"이 아니라 "모호함"으로 실패한다 —
    # 고치는 방법이 다르기 때문이다(수집 대기 ↔ 스펙에 section 추가).
    with pytest.raises(basis.AmbiguousTerm) as exc:
        basis.load_ref("KSB#원칙", corpus_dir=out, manifest=manifest)
    assert len(exc.value.candidates) == 2
    assert not list((out / "excerpts/KSB").glob("*원칙*"))   # 발췌를 만들지 않았다


def test_실제_코퍼스의_모호한_앵커도_같은_방식으로_보고된다():
    """운영 코퍼스(agents/agent6/corpus)의 manifest — 미해소는 전부 사유와 후보를 단다."""
    manifest = basis.load_manifest()
    미해소 = [r for r in manifest["basis"] if r["status"] != cb.RESOLVED]
    assert 미해소, "미해소가 하나도 없다면 이 시험은 공회전한다"
    for r in 미해소:
        assert r["reason"], f"{r['coord']}: 미해소인데 사유가 없습니다"
        if r["status"] == cb.AMBIGUOUS:
            assert len(r["anchor"]["candidates"]) >= 2
    # manifest 에 박힌 차단 결과가 지금 계산과 같은가(호출자가 잊어도 리포트에는 남는다).
    items = schema.load_items(ITEMS, warn=False)
    assert manifest["blocked_items"] == basis.blocked_items(items, manifest)


# ===========================================================================
# 보고 — 미해소는 반드시 눈에 띈다
# ===========================================================================

def test_보고서에_미해소_목록이_나온다(built):
    manifest, _ = built
    report = cb.render_report(manifest)
    assert "미해소 basis" in report
    for row in manifest["basis"]:
        if row["status"] != cb.RESOLVED:
            assert row["coord"] in report
    for item_id in manifest["blocked_items"]:
        assert item_id in report


def test_strict_모드는_미해소가_있으면_실패로_끝낸다(tmp_path, capsys):
    code = cb.main(["--raw", str(RAW), "--out", str(tmp_path), "--items", str(ITEMS),
                    "--allow-synthetic", "--strict"])
    assert code == 1
    assert "빌드 실패" in capsys.readouterr().out


# ===========================================================================
# 출처 표기 분리 — 메타데이터는 문서 내용이 아니다
# ===========================================================================

def test_출처표기_블록은_본문에서_떼어진다():
    text = ("# doc_id: X\n# title: 제목\n\n# source: s\n\n"
            "본문 첫 줄이다.\n제1조(목적) 내용.\n")
    assert cb.strip_provenance_header(text) == "본문 첫 줄이다.\n제1조(목적) 내용.\n"


def test_사이드카_쓰는_md의_진짜_제목은_떼지_않는다():
    """doc_id 없는 선두 `#` 블록은 markdown 제목일 수 있다 — 건드리지 않는다."""
    text = "# 제1장 총칙\n\n제1조(목적) 내용.\n"
    assert cb.strip_provenance_header(text) is None


def test_콜론없는_샵줄에서_떼기를_멈춘다():
    """출처 표기 직후 markdown 제목이 와도 본문이 잘리지 않는다."""
    text = "# doc_id: X\n# 제1장 총칙\n본문.\n"
    assert cb.strip_provenance_header(text) == "# 제1장 총칙\n본문.\n"
