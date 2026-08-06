"""§9 골든 — 목업 전사 3종의 기대 판정 (AGENT6 §9, T-A6.9).

## 이 파일이 검증하는 것

`clean` / `violation` / `ambiguous` 세 전사를 파이프라인에 통째로 태워, **심어 둔 것만
걸리고 심지 않은 것은 걸리지 않는지** 본다. 항목 하나의 단위 시험이 아니라 전 국면
(전처리 → 컨텍스트 조립 → LLM 판정 → 파생 → 집계 → 리포트·안내문·큐)의 시험이다.

## 판정은 녹화 재생이다

lexicon 이 사라지면서 판정은 전부 LLM 이 한다. 테스트가 키 없이 도는 길은
`--llm-mode replay` 뿐이다 — 실제 모델 응답을 `fixtures/llm/` 에 녹화해 두고 그것만 쓴다.
녹화가 없으면 **조용히 통과하지 않고 예외**로 실패하며, 무엇을 녹화해야 하는지 출력한다.
다시 녹화하려면 `python -m tests.agent6.record_fixtures`.

## 회차(consistency)가 픽스처마다 다른 이유 — 비용이 아니라 문턱이다

    clean       k=3. PASS 의 문턱이 가장 높은 설정이다(3회 만장일치가 아니면 통과가 아니다).
                정상 통화가 통과하는지를 가장 엄한 조건에서 본다.
    violation   k=1. 위반을 잡는 문턱이 가장 높은 설정이다. 회차를 늘리면 "한 번이라도
    ambiguous   FAIL 이면 FAIL" 규칙 덕에 잡기가 쉬워진다 — 한 번에 잡는지를 본다.

## 픽스처 설계 메모 (읽는 사람이 놀라지 않도록)

- 세 픽스처는 같은 통화 대본에서 갈라져 나왔다. clean 이 기준이고, violation 은 고지
  하나를 지우고 위반 발화를 넣은 것, ambiguous 는 경계 발화와 고객 질문을 더한 것이다.
- clean·violation 에는 **고객 질문이 없다**. F-30(고객 질문에 대한 성실 응답)은 질문이
  있어야 켜지므로, 질문 있는 통화는 ambiguous 가 맡는다.
- 2026-08: clean 의 두 발화를 고쳤다. A-04 는 "확인서를 보니 …로 나와 있습니다"(통보)가
  운영 정의의 **확인 왕복**을 충족하지 못했고, C-16 은 "정해진 기간 안에"라 기간·방법이
  없어 경계였다. 픽스처가 낡았던 것이므로 기대치를 낮추는 대신 픽스처를 고쳤다.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.agent6.src import schema
from tests.agent6.fakes import replay, row, verdicts

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# 심어 둔 것 — 픽스처와 이 상수가 정본이다.
심은_D20_발화 = "이 정도 지수대에서는 무조건 오릅니다"
심은_경계_발화 = "나라가 망하지 않는 한 손해 볼 일 없다고"
지운_고지 = "위법계약해지"          # C-17 — violation 에서 통째로 뺐다
회차 = {"clean": 3, "violation": 1, "ambiguous": 1}


def _run(name: str, tmp_path_factory):
    return replay(FIXTURES / f"{name}.json", FIXTURES / f"{name}.meta.json",
                  tmp_path_factory.mktemp(name), consistency=회차[name])


@pytest.fixture(scope="module")
def r_clean(tmp_path_factory):
    return _run("clean", tmp_path_factory)


@pytest.fixture(scope="module")
def r_violation(tmp_path_factory):
    return _run("violation", tmp_path_factory)


@pytest.fixture(scope="module")
def r_ambiguous(tmp_path_factory):
    return _run("ambiguous", tmp_path_factory)


def _queue(result) -> dict[str, dict]:
    p = Path(result.paths["queue"])
    rows = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    return {q["item_id"]: q for q in rows}


# ===========================================================================
# clean — 활성 항목 전부 충족
# ===========================================================================

def test_clean_은_자기일관성_3회_만장일치로_통과한다(r_clean):
    """§9: overall=완전판매요건충족, fail=0, unclear=0.

    그물이 아무거나 잡는다면 놓침 0 은 의미가 없다(전부 UNCLEAR 로 두면 달성된다).
    정상 통화가 **가장 엄한 설정에서** 통과하는 것이 그 반대편의 시험이다.
    """
    s = r_clean.report.stats
    assert (s["fail"], s["unclear"]) == (0, 0)
    assert s["active"] == s["pass"] == 27
    assert s["not_applicable"] == 3
    assert r_clean.report.overall == "완전판매요건충족"
    # 통과한 통화에는 갈 곳이 없다 — 안내문도 큐도 비어야 한다.
    assert r_clean.guidance == [] and r_clean.queue == []


def test_clean_의_모든_PASS_는_회차가_갈리지_않았다(r_clean):
    """method 가 llm 이면 k회 만장일치다. llm_self_consistency 는 갈렸다는 뜻이다.

    파생 항목(F-29)은 애초에 LLM 을 부르지 않으므로 회차라는 것이 없다(§9-5) — 제외한다.
    """
    for x in r_clean.report.items:
        if x.active and x.verdict == "PASS" and x.method != "derived":
            assert x.method == "llm", f"{x.id}: {x.method} / {x.llm_reason}"


def test_clean_의_존재형_PASS_는_PB_발화를_인용한다(r_clean):
    """존재형의 근거는 판매자의 발화여야 한다(§비대칭 임계 2)."""
    tr = r_clean.prepared.transcript
    존재형 = [x for x in r_clean.report.items if x.active and x.type == "존재형"]
    assert 존재형
    for x in 존재형:
        assert x.evidence, f"{x.id}: 존재형 PASS 인데 인용이 없습니다"
        for ev in x.evidence:
            u = tr.by_section(ev.section_id)
            assert u is not None and not u.is_customer(), f"{x.id}: 고객 발화를 인용했습니다"


def test_clean_의_부재형_PASS_가_인용하면_실재하는_PB_발화여야_한다(r_clean):
    """부재형 PASS 는 "금지 표현이 없다"는 **없음의 주장**이라 인용이 없어도 된다.

    다만 인용하는 것 자체를 막지는 않는다 — 실제로 판정기는 "원금이 보장되지 않으며 …"
    처럼 **적법하게 말한 자리**를 근거로 든다. 준법감시자가 "무엇을 보고 괜찮다고 했나"를
    확인할 수 있어 오히려 쓸모가 있다. (예전 시험은 인용이 없을 것을 요구했는데, 그것은
    엔진의 계약이 아니라 시험의 억측이었다.)

    막아야 하는 것은 따로 있다 — **지어낸 인용**과 **고객 발화를 판매자 행위의 근거로
    드는 것**이다. 그래서 여기서는 그 둘만 본다.
    """
    tr = r_clean.prepared.transcript
    부재형 = [x for x in r_clean.report.items if x.active and x.type == "부재형"]
    assert len(부재형) == 6
    assert all(x.verdict == "PASS" for x in 부재형)
    for x in 부재형:
        for ev in x.evidence or []:
            assert tr.verify_quote(ev.text, ev.section_id).found, \
                f"{x.id}: 전사에 없는 인용입니다 — {ev.section_id} {ev.text[:40]!r}"
            u = tr.by_section(ev.section_id)
            assert u is not None and u.speaker == "PB", \
                f"{x.id}: 판매자 발화가 아닌 것을 근거로 들었습니다 — {ev.section_id}"


# ===========================================================================
# violation — C-17 고지 삭제 + D-20 위반 발화
# ===========================================================================

def test_violation_은_심은_것만_걸린다(r_violation):
    """심은 위반이 걸리고, 심지 않은 항목이 덩달아 무너지지 않는다(거짓 양성)."""
    v = verdicts(r_violation)
    미비 = {i for i, x in v.items() if x in ("FAIL", "UNCLEAR")}
    # D-20(단정) · D-22(사실과 다른 설명) · D-23(확실 오인)은 **같은 발화**가 세 항목에
    # 걸린 것이다 — 항목이 겹치는 것은 스펙이 정상이라고 적어 둔 동작이다(D-20 운영 정의).
    # C-17 은 고지를 통째로 지운 자리다.
    assert 미비 == {"C-17", "D-20", "D-22", "D-23"}
    assert r_violation.report.overall == "보완필요"
    # 파생은 구성 항목(B-07·B-09·F-28)이 전부 살아 있으므로 함께 무너지지 않는다.
    assert v["F-29"] == "PASS" and row(r_violation, "F-29").method == "derived"


def test_violation_D20_인용이_심은_발화와_일치한다(r_violation):
    """§9: D-20 evidence 가 심은 발화 스팬과 일치."""
    d20 = row(r_violation, "D-20")
    assert d20.verdict == "FAIL"
    assert d20.evidence and len(d20.evidence) >= 1
    ev = d20.evidence[0]
    심은 = next(u for u in r_violation.prepared.transcript.utterances
                if 심은_D20_발화 in u.text)
    assert ev.section_id == 심은.section_id
    assert ev.text == 심은.text
    assert (ev.start, ev.end) == (심은.start, 심은.end)     # 좌표는 코드가 정한다


def test_violation_지운_고지는_전사_전체에서_미발견으로_걸린다(r_violation):
    """존재형 FAIL 은 "없음의 주장"이라 인용할 스팬이 없다 — 그때만 evidence 가 빈다."""
    전문 = "\n".join(u.text for u in r_violation.prepared.transcript.utterances)
    assert 지운_고지 not in 전문                       # 전제 확인
    c17 = row(r_violation, "C-17")
    assert c17.verdict == "FAIL"
    assert not c17.evidence
    assert "미발견" in (c17.llm_reason or "")
    assert c17.method == "llm"                       # 강등이 아니라 정당한 FAIL 이다


def test_violation_존재형_미비는_PB보완으로_안내문에_실린다(r_violation):
    """§9: C-17 은 route=PB보완 이고 guidance.md 에 재안내 문구가 있다."""
    md = Path(r_violation.paths["guidance"]).read_text(encoding="utf-8")
    assert row(r_violation, "C-17").route == "PB보완"
    entry = next(e for e in r_violation.guidance if e.item_id == "C-17")
    assert entry.status == "재안내필요"
    assert entry.recommended_script.strip(), "C-17: 재안내 문구가 비었습니다"
    assert entry.recommended_script in md and "### C-17" in md


def test_violation_부재형_위반은_준법감시큐로만_간다(r_violation):
    """이미 한 말은 PB 재설명으로 지워지지 않는다 — 안내문에 권장 문구를 적지 않는다."""
    assert row(r_violation, "D-20").route == "준법감시큐"
    d20 = next(e for e in r_violation.guidance if e.item_id == "D-20")
    assert (d20.route, d20.status, d20.recommended_script) == ("준법감시큐", "검토중", "")

    q = _queue(r_violation)
    assert "D-20" in q and q["D-20"]["verdict"] == "FAIL"
    assert 심은_D20_발화 in q["D-20"]["evidence"][0]["text"]
    assert q["D-20"]["transcript"].endswith("violation.json")
    assert "C-17" not in q                       # 재설명으로 해소되는 항목은 큐로 가지 않는다


# ===========================================================================
# ambiguous — 경계 발화 + 고객 질문
# ===========================================================================

def test_ambiguous_의_경계_발화는_자동_PASS_가_아니다(r_ambiguous):
    """§9: 자동 PASS 아님. 완곡하게 말한 안전 단정도 통과시키지 않는다."""
    v = verdicts(r_ambiguous)
    assert v["D-20"] != "PASS", "완곡한 단정이 통과했습니다"
    assert v["D-23"] != "PASS", "확실 오인 소지 표현이 통과했습니다"
    for item_id in ("D-20", "D-23"):
        assert row(r_ambiguous, item_id).route == "준법감시큐"
    assert r_ambiguous.report.overall == "보완필요"


def test_ambiguous_의_인용이_경계_발화를_짚는다(r_ambiguous):
    걸린 = [row(r_ambiguous, i) for i in ("D-20", "D-23")]
    assert any(x.evidence and 심은_경계_발화 in x.evidence[0].text for x in 걸린), \
        "경계 발화를 짚지 않고 다른 곳을 근거로 들었습니다"


def test_ambiguous_는_큐에_적재된다(r_ambiguous):
    q = _queue(r_ambiguous)
    assert "D-20" in q
    assert q["D-20"]["verdict"] in ("FAIL", "UNCLEAR")
    assert q["D-20"]["basis_refs"] == ["KSB/제21조/제1호"]


def test_ambiguous_의_고객질문이_F30_을_켠다(r_ambiguous):
    """경계 픽스처는 F-30(고객 질문 존재 시)까지 태운다 — clean 이 못 태우는 자리다."""
    assert r_ambiguous.prepared.meta.customer_question_count == 1
    assert r_ambiguous.prepared.activations["F-30"].active
    assert row(r_ambiguous, "F-30").active


# ===========================================================================
# §0 원칙 2 — 결정론 (재생 모드)
# ===========================================================================

def _report_without_time(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("generated_at")
    return data


@pytest.mark.parametrize("name", ["clean", "violation", "ambiguous"])
def test_두_번_돌리면_같은_리포트가_나온다(name, tmp_path):
    """§9: 같은 입력 2회 → report.json 이 완전히 동일(재생 모드).

    비교에서 빼는 것은 `generated_at` 하나다. 실행 시각은 입력이 아니다 — 그것까지
    같기를 요구하면 시계를 멈춰야 한다. 그 밖의 모든 칸(판정·인용·신뢰도·비고 순서까지)은
    글자 하나 다르지 않아야 한다.
    """
    a = replay(FIXTURES / f"{name}.json", FIXTURES / f"{name}.meta.json",
               tmp_path / "1", consistency=회차[name])
    b = replay(FIXTURES / f"{name}.json", FIXTURES / f"{name}.meta.json",
               tmp_path / "2", consistency=회차[name])
    assert _report_without_time(a.paths["report"]) == _report_without_time(b.paths["report"])

    def _md(p):
        return [l for l in Path(p).read_text(encoding="utf-8").splitlines()
                if not l.startswith("- 생성:")]
    assert _md(a.paths["guidance"]) == _md(b.paths["guidance"])

    def _q(r):
        return [{k: v for k, v in json.loads(l).items() if k != "created_at"}
                for l in Path(r.paths["queue"]).read_text(encoding="utf-8").splitlines()
                if l.strip()]
    assert _q(a) == _q(b)


# ===========================================================================
# 픽스처 자체의 건전성 — 심은 것이 정말 거기 있는가
# ===========================================================================

@pytest.mark.parametrize("name", ["clean", "violation", "ambiguous", "customer_only"])
def test_픽스처_형식(name):
    """§9: 각 40~80 발화, speaker/start/end/text 포함."""
    turns = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    assert 40 <= len(turns) <= 80
    for i, t in enumerate(turns):
        assert set(t) == {"speaker", "start", "end", "text"}, f"{name}[{i}]"
        assert t["speaker"] in ("PB", "고객")
        assert t["start"] < t["end"]
        assert t["text"].strip()
    assert [t["start"] for t in turns] == sorted(t["start"] for t in turns)


def test_violation_은_clean_에서_심은것만_다르다():
    """거짓 양성을 픽스처 차이로 설명할 수 있어야 한다."""
    clean = [t["text"] for t in json.loads((FIXTURES / "clean.json").read_text("utf-8"))]
    viol = [t["text"] for t in json.loads((FIXTURES / "violation.json").read_text("utf-8"))]
    assert 심은_D20_발화 in "\n".join(viol)
    assert 지운_고지 not in "\n".join(viol)          # 지운 고지가 다른 데서 새어 나오지 않는다
    assert len(set(clean) - set(viol)) == 3          # 원금손실 고지 · C-17 고지 · 그 반응 발화


def test_체크리스트_판본이_리포트에_박힌다(r_clean):
    """어떤 스펙으로 판정했는지 모르면 나중에 같은 판정을 재현할 수 없다(§7)."""
    items_dir = Path(__file__).resolve().parents[2] / "agents/agent6/checklist/items"
    items = schema.load_items(items_dir, warn=False)
    assert r_clean.report.checklist_version.startswith(f"items{len(items)}-")
    assert r_clean.report.meta is not None
