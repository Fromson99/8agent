"""§9 완료 기준 — 판정 이후를 믿어도 되는가 (T-A6.9).

골든(test_golden)이 "모델이 무엇을 잡는가"를 본다면, 여기서는 **엔진이 그 판정을 어떻게
다루는가**를 본다. 다섯 가지다.

  아무것도 안 사라진다   체크리스트의 모든 항목이 리포트에 한 행씩 남는다. 스펙에서 꺼 둔
                        항목(enabled: false)도 행으로 남는다(§7).
  못 본 것은 통과가 아니다 근거 미해소로 점검하지 못한 항목이 하나라도 있으면 종합 판정은
                        완전판매요건충족이 될 수 없다 — 실제로 뚫렸던 구멍이다.
  인용이 진짜다          전사에 없는 문장·맞장구 한 마디·발화를 이어 붙인 문장·틀린 좌표는
                        전부 버려지고, 근거를 잃은 "있음의 주장"은 UNCLEAR 로 내려간다.
  고객이 한 말은 고지가 아니다 존재형의 근거는 PB 발화여야 한다(§비대칭 임계 2).
  갈리면 통과가 아니다    자기일관성 k회가 갈리면 다수결로 PASS 를 밀지 않는다.

여기서 쓰는 판정기는 **대본 판정기**(tests/agent6/fakes.py)다. 실제 모델에게 "지어낸
인용으로 PASS 하라"고 시킬 수는 없기 때문이며, 그 이유는 그 파일에 적어 두었다.
모델이 무엇을 잡는지는 test_golden·test_mutations 가 녹화 재생으로 본다.
"""

from __future__ import annotations

import ast
import json
import shutil
from pathlib import Path

import pytest

from lawrag.agents.agent6.src import (aggregate, basis, cli, context_asm, judge as judge_mod,
                               llm_cache, preprocess, schema)
from tests.agent6.fakes import (고객발화판정기, 대본판정기, 맞장구판정기, 없는좌표판정기,
                                이어붙인판정기, 지어내는판정기, 회차별판정기, row, run,
                                verdicts)

ROOT = next(
    path for path in Path(__file__).resolve().parents
    if (path / "00_SYSTEM" / "WORKSPACE.json").is_file()
)
FIXTURES = Path(__file__).resolve().parent / "fixtures"
SRC = Path(__import__("lawrag").__file__).resolve().parent / "agents/agent6/src"
ITEMS_DIR = Path(__import__("lawrag").__file__).resolve().parent / "agents/agent6/checklist/items"

픽스처들 = ["clean", "violation", "ambiguous"]


@pytest.fixture(scope="module")
def 항목들() -> list[schema.ChecklistItem]:
    return schema.load_items(ITEMS_DIR, warn=False)


# ===========================================================================
# §9-3 조용한 스킵 없음 — 행은 사라지지 않는다
# ===========================================================================

@pytest.mark.parametrize("name", 픽스처들)
def test_체크리스트_항목이_한_행씩_나온다(name, tmp_path, 항목들):
    r = run(name, tmp_path)
    ids = [row_.id for row_ in r.report.items]
    assert ids == sorted(i.id for i in 항목들)
    assert len(ids) == len(set(ids)) == 30

    활성 = {i.id for i in r.prepared.active_items()}
    assert {row_.id for row_ in r.report.items if row_.active} == 활성
    assert r.report.stats["active"] == len(활성)
    assert r.report.stats["total"] == len(ids)
    # 비활성 행은 사유를 반드시 달고 있다 — "점검하지 않음"과 "통과"의 구별(§7).
    for row_ in r.report.items:
        if not row_.active:
            assert row_.verdict == "NOT_APPLICABLE" and (row_.inactive_reason or "").strip()
    s = r.report.stats
    assert s["pass"] + s["fail"] + s["unclear"] + s["not_applicable"] == s["total"]


def _꺼둔_체크리스트(tmp_path: Path, item_id: str = "A-02") -> Path:
    """항목 하나를 `enabled: false` 로 꺼 둔 체크리스트 사본."""
    d = tmp_path / "items"
    shutil.copytree(ITEMS_DIR, d)
    p = d / f"{item_id}.yaml"
    p.write_text(p.read_text(encoding="utf-8").rstrip() + "\nenabled: false\n",
                 encoding="utf-8")
    return d


def test_꺼둔_항목도_리포트에_행으로_남는다(tmp_path):
    """30항목짜리 체크리스트가 29행으로 나오면 "꺼 둔 것"과 "빠뜨린 것"을 구별할 수 없다."""
    items_dir = _꺼둔_체크리스트(tmp_path)
    r = run("clean", tmp_path / "out", items_dir=items_dir)
    assert len(r.report.items) == 30
    a02 = row(r, "A-02")
    assert (a02.active, a02.verdict, a02.method) == (False, "NOT_APPLICABLE", "disabled")
    assert "enabled: false" in (a02.inactive_reason or "")
    # 꺼 둔 항목은 **점검하지 못한 항목**이다 — 통과의 근거가 될 수 없다.
    assert "A-02" in {x.id for x in aggregate.unchecked(r.report.items)}
    assert r.report.overall != "완전판매요건충족"


# ===========================================================================
# 못 본 것은 통과가 아니다 (basis_policy=block)
# ===========================================================================

def test_점검하지_못한_항목이_있으면_통과로_적히지_않는다(tmp_path):
    """실제로 뚫렸던 구멍 — 근거 미해소로 활성이 차단된 항목이 NOT_APPLICABLE 로 빠지면서
    리포트가 "완전판매요건충족"이 됐다. 판정기가 나머지를 **전부 PASS** 라고 해도
    종합 판정은 통과가 아니어야 한다."""
    r = run("clean", tmp_path, basis_policy="block")
    막힘 = aggregate.unchecked(r.report.items)
    assert 막힘, "block 인데 차단된 항목이 하나도 없습니다 — 시험이 공회전했습니다"
    assert all(x.method == "basis_unresolved" for x in 막힘)
    assert (r.report.stats["fail"], r.report.stats["unclear"]) == (0, 0)   # 전부 PASS 대본
    assert r.report.overall != "완전판매요건충족"
    assert any("점검하지 못한" in n for n in r.report.notes)
    # 안내문에도 "통과로 읽지 마십시오"가 실린다.
    md = Path(r.paths["guidance"]).read_text(encoding="utf-8")
    assert "점검하지 못한 항목" in md and "통과로 읽지 마십시오" in md


def test_warn_에서는_활성을_유지하되_신뢰도를_깎는다(tmp_path):
    """차단이 기본이 아닌 이유(§preprocess): 3분의 1이 사라진 리포트를 운영에 내보내지 않는다."""
    r = run("clean", tmp_path, basis_policy="warn")
    assert aggregate.unchecked(r.report.items) == []
    c18 = row(r, "C-18")           # KOFIA-R#숙려기간 — 용어가 여러 곳에 걸려 미해소
    assert c18.active and c18.confidence != "high"
    assert any("미해소" in n for n in c18.when_notes)


# ===========================================================================
# §9-2 인용 검증 — 없는 말을 근거로 쓰지 않는다
# ===========================================================================

@pytest.mark.parametrize("name", 픽스처들)
def test_리포트에_실린_인용은_전부_전사의_그_발화다(name, tmp_path):
    r = run(name, tmp_path)
    tr = r.prepared.transcript
    인용수 = 0
    for row_ in r.report.items:
        for ev in row_.evidence or []:
            got = tr.verify_quote(ev.text, ev.section_id)
            assert got.found, f"{name}/{row_.id}: {got.reason}"
            assert ev.text == tr.by_section(ev.section_id).text
            인용수 += 1
    assert 인용수 > 0, f"{name}: 인용이 하나도 없습니다 — 검증이 공회전했습니다"


@pytest.mark.parametrize("판정기,기대_method", [
    (지어내는판정기, "evidence_unverified"),      # 전사에 없는 문장
    (맞장구판정기, "evidence_unverified"),        # "네" 한 글자
    (이어붙인판정기, "evidence_unverified"),      # 두 발화를 이어 붙인 문장
    (없는좌표판정기, "evidence_unverified"),      # 실재하지 않는 좌표
])
def test_규칙을_어긴_인용은_버려지고_판정이_강등된다(판정기, 기대_method, tmp_path):
    """§0 원칙 3: 근거를 대지 못한 "있음의 주장"은 판정이 아니다. **PASS 가 남으면 안 된다.**"""
    r = run("clean", tmp_path / 판정기.__name__, llm=판정기())
    존재형 = [x for x in r.report.items if x.active and x.type == "존재형"]
    assert 존재형
    for x in 존재형:
        assert x.verdict == "UNCLEAR", f"{x.id}: 규칙을 어긴 인용으로 {x.verdict} 가 살아남았습니다"
        assert x.method == 기대_method
        assert not x.evidence
    assert r.report.overall != "완전판매요건충족"


def test_이어붙인_인용은_사유까지_구별해_남긴다(tmp_path):
    """전사 전체에는 있으나 그 발화 안에는 없다 — 사유를 뭉뚱그리면 스펙을 고칠 수 없다."""
    r = run("clean", tmp_path, llm=이어붙인판정기())
    사유 = row(r, "B-07").llm_reason or ""
    assert "여러 발화를 이어 붙였거나" in 사유


# ===========================================================================
# 존재형의 근거는 PB 발화여야 한다 (§비대칭 임계 2)
# ===========================================================================

def test_고객_발화만_근거인_존재형_PASS_는_강등된다(tmp_path):
    """고객이 "원금 손실 얘기는 아직 못 들었네요"라고 한 말이 고지 이행의 증거가 되던 구멍."""
    r = cli.run_pipeline(
        FIXTURES / "customer_only.json", meta=FIXTURES / "customer_only.meta.json",
        out_dir=tmp_path, llm_mode="live", consistency=1, history=False,
        llm=고객발화판정기(고객_문장="원금 손실 얘기는 아직 못 들었네요"))
    b07 = row(r, "B-07")
    assert b07.verdict == "UNCLEAR", "고객이 한 말이 판매자의 고지 이행으로 통과했습니다"
    assert b07.method == "evidence_speaker"
    assert not b07.evidence
    assert "고객 발화만 근거" in (b07.llm_reason or "")
    # 강등된 것은 UNCLEAR 이므로 사람에게 간다(§6: 모든 UNCLEAR 는 준법감시큐).
    assert b07.route == "준법감시큐"
    assert r.report.overall != "완전판매요건충족"


def test_부재형은_고객_발화_규칙에_걸리지_않는다(tmp_path):
    """부재형 PASS 는 "없다"는 주장이라 인용할 스팬이 없다 — 화자 검사가 발동할 자리가 아니다."""
    r = cli.run_pipeline(
        FIXTURES / "customer_only.json", meta=FIXTURES / "customer_only.meta.json",
        out_dir=tmp_path, llm_mode="live", consistency=1, history=False,
        llm=고객발화판정기())
    부재형 = [x for x in r.report.items if x.active and x.type == "부재형"]
    assert 부재형 and all(x.verdict == "PASS" for x in 부재형)


# ===========================================================================
# 자기일관성 — 갈리면 PASS 가 아니다
# ===========================================================================

def test_회차가_갈리면_다수결로_PASS_를_밀지_않는다(tmp_path):
    r = run("clean", tmp_path, consistency=3,
            llm=회차별판정기({"B-07": ["PASS", "UNCLEAR", "PASS"],
                             "B-08": ["PASS", "PASS", "PASS"],
                             "B-09": ["PASS", "PASS", "FAIL"]}))
    assert row(r, "B-07").verdict == "UNCLEAR"      # 2:1 이어도 PASS 가 아니다
    assert row(r, "B-07").method == "llm_self_consistency"
    assert row(r, "B-08").verdict == "PASS"         # 만장일치만 PASS
    assert row(r, "B-09").verdict == "FAIL"         # 한 번이라도 FAIL 이면 FAIL
    assert "자기일관성 3회" in (row(r, "B-07").llm_reason or "")


def test_회차가_갈리면_신뢰도가_low_로_내려간다(tmp_path):
    r = run("clean", tmp_path, consistency=3,
            llm=회차별판정기({"B-07": ["PASS", "UNCLEAR", "PASS"]}))
    assert row(r, "B-07").confidence == "low"


# ===========================================================================
# 판정자를 쓸 수 없으면 — 못 한 점검은 통과가 아니다
# ===========================================================================

def test_녹화가_없으면_조용히_넘어가지_않는다(tmp_path, capsys):
    """replay 인데 녹화가 없으면 CLI 는 판정 결과와 구별되는 종료코드로 끝난다."""
    code = cli.main(["run", "--transcript", str(FIXTURES / "clean.json"),
                     "--meta", str(FIXTURES / "clean.meta.json"),
                     "-o", str(tmp_path), "--llm-mode", "replay",
                     "--llm-cache", str(tmp_path / "없는녹화"),
                     "--fresh-queue", "--no-history"])
    assert code == cli.EXIT_NO_JUDGE
    err = capsys.readouterr().err
    assert "녹화가 없습니다" in err and "record" in err


def test_LLM을_열지_못하면_점검_실패로_끝난다(tmp_path, monkeypatch):
    """키가 없다고 "미비 없음"이 되면 그날의 통화는 아무도 점검하지 않은 것이 된다."""
    def _boom(*a, **kw):
        raise llm_cache.LLMUnavailable("API 키가 없습니다(시험)")
    monkeypatch.setattr(llm_cache, "open_client", _boom)

    r = cli.run_pipeline(FIXTURES / "clean.json", meta=FIXTURES / "clean.meta.json",
                         out_dir=tmp_path, llm_mode="live", history=False)
    assert not r.checked
    assert r.report.stats["total"] == 30              # 점검을 건너뛰지 않았다
    assert r.report.stats["pass"] == 0
    # 파생(F-29)은 LLM 을 부르지 않으므로 method 가 derived 다 — 그것까지 판정 실패로
    # 세면 "무엇을 못 했나"가 흐려진다. 판정 대상이었던 항목만 본다.
    판정대상 = {i.id for i in r.prepared.judgeable_items()}
    assert all(x.method == "llm_unavailable"
               for x in r.report.items if x.id in 판정대상)
    assert r.report.overall != "완전판매요건충족"
    assert any("점검 실패" in n for n in r.report.notes)


# ===========================================================================
# §9-4 컨텍스트 조립 — 근거가 실제로 실린다, 검색은 없다
# ===========================================================================

@pytest.fixture(scope="module")
def 배치들():
    """clean 전사로 실제 배치를 조립한다(코퍼스도 진짜 것을 읽는다)."""
    p = preprocess.prepare(FIXTURES / "clean.json", FIXTURES / "clean.meta.json")
    loader = context_asm.BasisLoader()
    batches = context_asm.build_batches(p.judgeable_items(), p.transcript, loader=loader)
    return p, batches, loader


def test_프롬프트에_코퍼스_발췌_원문이_들어간다(배치들):
    """§9-4: 판정 프롬프트에 코퍼스 발췌가 실제 포함됨."""
    _, batches, _ = 배치들
    ctxs = {c.item_id: (b, c) for b in batches for c in b.contexts}
    batch, ctx = ctxs["D-20"]                    # basis: KSB/제21조/제1호 (물질화 완료)

    원문 = basis.load_excerpt("KSB/제21조/제1호")
    assert 원문.strip()
    assert ctx.has_basis_text()
    assert ctx.block_contains_excerpts()         # 구조와 문자열이 어긋나지 않는다
    assert 원문[:40] in ctx.block
    assert 원문[:40] in batch.user()             # 실제로 호출에 실리는 문자열에도
    assert "KSB/제21조/제1호" in batch.user()
    # 머리글(판본·verification)은 프롬프트에 넣지 않는다 — 판정과 무관한 잡음이다.
    assert "# 좌표:" not in batch.user()


def test_용어_앵커도_해소된_원문이_실린다(배치들):
    """용어로 물어도 프롬프트에는 그 조문의 본문이 들어간다(§새 basis 표기)."""
    _, batches, _ = 배치들
    ctx = next(c for b in batches for c in b.contexts if c.item_id == "D-25")
    앵커 = next(e for e in ctx.excerpts if e.query == "KOFIA-R#투자권유시 유의사항")
    assert 앵커.present and 앵커.text.strip()
    assert 앵커.coordinate and 앵커.coordinate != 앵커.query   # 어디로 해소됐는지가 남는다
    assert 앵커.ref() == f"{앵커.query} → {앵커.coordinate}"
    # 블록은 발췌를 두 칸 들여 싣는다 — 줄바꿈이 낀 본문은 통째로 대조할 수 없어 첫 줄을 본다.
    assert 앵커.text.splitlines()[0][:30] in ctx.block


def test_용어가_여러_곳에_걸리면_지어내지_않는다(배치들):
    """§4 절대 규칙: 없는 것을 있다고 쓰지 않는다. 모호한 앵커는 빈 자리로 남고 시끄럽다."""
    _, batches, loader = 배치들
    ctx = next(c for b in batches for c in b.contexts if c.item_id == "C-18")
    assert not ctx.has_basis_text()
    assert ctx.ambiguous_excerpts() == ["KOFIA-R#숙려기간"]
    assert "용어가" in ctx.block and "section 을 함께 적어 좁히세요" in ctx.block
    assert any("KOFIA-R#숙려기간" in w for w in loader.warnings)


def test_런타임이_읽는_것은_사전_물질화된_발췌_파일뿐이다(배치들):
    """§0 원칙 1: 런타임에 규정을 **찾지** 않는다. 좌표를 파일로 바꿔 읽을 뿐이다."""
    _, batches, loader = 배치들
    assert loader.source == "basis.load_ref"
    발췌_뿌리 = (Path(__import__("lawrag").__file__).resolve().parent / "agents/agent6/corpus/excerpts").resolve()
    실린 = [e for b in batches for c in b.contexts for e in c.excerpts if e.present]
    assert 실린
    for e in 실린:
        p = basis.excerpt_path(e.query).resolve()
        assert p.exists(), f"{e.query}: 발췌 파일이 없습니다"
        assert 발췌_뿌리 in p.parents, f"발췌가 아닌 곳을 읽었습니다: {p}"


# 런타임 모듈만 본다. corpus_build 는 **컴파일 국면** 도구라 원문 수집·구조화를 하고,
# 그 자리에서 규정을 다루는 것은 설계상 맞다. 금지하는 것은 판정 도중의 검색이다.
런타임_모듈 = ["preprocess.py", "context_asm.py", "judge.py", "llm_cache.py",
              "aggregate.py", "report.py", "basis.py", "schema.py", "when.py",
              "transcript.py", "cli.py", "harvest.py"]

금지_모듈 = {"requests", "httpx", "urllib", "http", "socket", "aiohttp", "ftplib",
           "faiss", "chromadb", "qdrant_client", "pinecone", "weaviate", "elasticsearch",
           "sentence_transformers", "sklearn", "numpy", "scipy", "gensim", "torch"}

금지_이름 = {"embed", "embedding", "embeddings", "encode_query", "vector_search",
           "semantic_search", "similarity", "cosine_similarity", "knn", "rerank",
           "urlopen", "urlretrieve"}


@pytest.mark.parametrize("fname", 런타임_모듈)
def test_런타임에_검색도_벡터조회도_없다(fname):
    """§9-4: 런타임에 corpus 외부 검색·벡터 조회가 일절 없음.

    문자열이 아니라 AST 로 본다 — 이 파일들의 설명글에는 "벡터 조회를 하지 않는다"는
    **문장**이 있어서, 문자열 검색은 설명을 위반으로 오인한다.
    """
    tree = ast.parse((SRC / fname).read_text(encoding="utf-8"), filename=fname)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert a.name.split(".")[0] not in 금지_모듈, f"{fname}: '{a.name}' import"
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            assert top not in 금지_모듈, f"{fname}: '{node.module}' 에서 import 합니다"
        elif isinstance(node, ast.Attribute):
            assert node.attr.lower() not in 금지_이름, f"{fname}: .{node.attr}() 호출"
        elif isinstance(node, ast.Name):
            assert node.id.lower() not in 금지_이름, f"{fname}: '{node.id}' 사용"


def test_판정_경로에_문자열_매칭_판정기가_남아_있지_않다():
    """lexicon(금지어 목록)·cross_signal 은 판정에서 제거됐다 — 되살아나면 여기서 걸린다.

    파일이 있는지가 아니라 **판정 경로가 그것을 부르는지**를 본다. 쓰이지 않는 파일은
    판정을 바꾸지 못하지만, import 가 하나라도 살아 있으면 문자열 매칭이 다시 판정에
    끼어든다.
    """
    금지 = {"lexicon", "cross_signal"}
    for fname in 런타임_모듈:
        tree = ast.parse((SRC / fname).read_text(encoding="utf-8"), filename=fname)
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[-1] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [a.name for a in node.names] + [(node.module or "").split(".")[-1]]
            assert not (금지 & set(names)), f"{fname}: {금지 & set(names)} 을 import 합니다"


# ===========================================================================
# §9-5 파생 항목 — F-29 는 LLM 을 부르지 않는다
# ===========================================================================

def test_F29_는_프롬프트에_들어가지_않는다(배치들):
    p, batches, _ = 배치들
    실린_항목 = {i for b in batches for i in b.item_ids}
    assert "F-29" not in 실린_항목
    assert "F-29" not in {i.id for i in p.judgeable_items()}
    assert "F-29" in {i.id for i in p.active_items()}      # 활성이되 판정 대상이 아니다
    for b in batches:
        assert "F-29" not in b.user()


@pytest.mark.parametrize("name", 픽스처들)
def test_F29_는_구성항목의_계산_결과다(name, tmp_path, 항목들):
    """§9-5: 독립 LLM 판정 없이 파생 계산."""
    item = next(i for i in 항목들 if i.id == "F-29")
    assert item.derived and item.derived.all_pass == ["B-07", "B-09", "F-28"]

    r = run(name, tmp_path / name, llm=대본판정기({"B-07": ("FAIL", None)}))
    f29 = row(r, "F-29")
    assert f29.method == "derived"
    assert f29.verdict == item.derived.evaluate(verdicts(r)) == "FAIL"
    assert f29.evidence is None
    assert "독립 LLM 판정 없음" in (f29.llm_reason or "")
    assert "B-07" in (f29.llm_reason or "")


def test_F29_판정을_LLM이_보내와도_무시된다(tmp_path):
    """판정자가 스키마를 어기고 파생 항목을 판정해 보내도 리포트는 계산 결과를 쓴다."""
    llm = 대본판정기({"B-07": ("FAIL", None)})
    llm.stray["agent6-판정-F-1회차"] = [
        {"item_id": "F-29", "verdict": "PASS", "evidence": [],
         "reason": "판정자가 멋대로 낸 판정", "confidence": "high"}]
    r = run("clean", tmp_path, llm=llm)
    f29 = row(r, "F-29")
    assert (f29.method, f29.verdict) == ("derived", "FAIL")
    assert "멋대로" not in (f29.llm_reason or "")
    # 모르는 항목 id 가 온 사실 자체는 조용히 사라지지 않는다.
    assert any("모르는 항목 id" in n and "F-29" in n for n in r.report.notes)


# ===========================================================================
# 라우팅 — 미비에는 갈 곳이 있다
# ===========================================================================

def test_모든_미비에는_갈_곳이_있다(tmp_path):
    r = run("clean", tmp_path,
            llm=대본판정기({"B-07": ("FAIL", None), "D-20": ("FAIL", "무조건"),
                           "C-17": ("UNCLEAR", None)}))
    for x in r.report.items:
        if x.verdict in ("FAIL", "UNCLEAR"):
            assert x.route in ("PB보완", "준법감시큐"), f"{x.id}: 라우팅이 없습니다"
    assert row(r, "B-07").route == "PB보완"            # 존재형 미비는 재설명으로 해소
    assert row(r, "C-17").route == "준법감시큐"        # 모든 UNCLEAR 는 사람에게
    # 준법감시큐로 간 항목만 큐에 적재된다.
    from tests.agent6.fakes import queue_rows
    적재 = {q["item_id"] for q in queue_rows(r)}
    assert "C-17" in 적재 and "B-07" not in 적재


def test_같은_전사를_두_번_돌려도_큐가_불어나지_않는다(tmp_path):
    """큐는 사람의 작업 목록이다 — 같은 일이 두 줄이 되면 해소율 통계가 망가진다."""
    대본 = {"C-17": ("UNCLEAR", None)}
    r1 = run("clean", tmp_path, llm=대본판정기(대본))
    r2 = run("clean", tmp_path, llm=대본판정기(대본))
    assert int(r1.paths["queue_added"]) > 0
    assert int(r2.paths["queue_added"]) == 0
    lines = Path(r2.paths["queue"]).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == int(r1.paths["queue_added"])
