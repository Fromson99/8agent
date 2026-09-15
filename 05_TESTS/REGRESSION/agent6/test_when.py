"""when DSL 단위 테스트 — 결정론이므로 LLM 도 픽스처도 필요 없다.

여기서 지키는 것은 두 가지다:
  1) 문법 오류는 **로드 시점에** 터진다 (런타임에 판정이 멈추지 않는다).
  2) 메타가 없을 때 항목이 조용히 사라지지 않는다 (UNKNOWN → 보수적 활성).
"""

import pytest

from lawrag.agents.agent6.src.when import (ACTIVE, INACTIVE, UNKNOWN, WhenSyntaxError,
                                    describe, evaluate, fields, parse)


# --- 문법 -------------------------------------------------------------------

@pytest.mark.parametrize("src", [
    "always",
    "is_high_difficulty == true",
    "customer_age >= 65",
    "product_type in [ELS, ELB, DLS, DLB]",
    "is_high_difficulty == true or customer_age >= 65",
    "risk_profile != 적합",
    "customer_age>=65",                                  # 공백 없이도
    "(customer_age >= 65 or is_high_difficulty == true) and product_type in [ELS]",
    'product_type in ["주가연계증권", ELS]',              # 따옴표 리터럴
    "customer_question_count >= 1",
    "product_type not in [예금, 보험]",
])
def test_문법_수용(src):
    assert parse(src) is not None


@pytest.mark.parametrize("src", [
    "",                                # 빈 식 — 'always' 라고 적어야 한다
    "   ",
    "customer_age >=",                 # 값 없음
    "customer_age 65",                 # 연산자 없음
    "== 65",                           # 필드 없음
    "customer_age >= 65 and",          # 매달린 and
    "(customer_age >= 65",             # 괄호 안 닫힘
    "product_type in ELS",             # 목록 아님
    "product_type in []",              # 빈 목록
    "product_type in [ELS ELB]",       # 쉼표 없음
    "나이 >= 65",                      # 한글 필드명
    "always and",
    "customer_age ≥ 65",               # DSL 에 없는 글자
    "always == true",                  # always 는 예약어
])
def test_문법_거부(src):
    with pytest.raises(WhenSyntaxError):
        parse(src)


def test_필드_추출():
    assert fields("is_high_difficulty == true or customer_age >= 65") == {
        "is_high_difficulty", "customer_age"}
    assert fields("always") == set()


def test_정규화_표기():
    assert describe("always") == "always"
    assert describe("customer_age>=65") == "customer_age >= 65"
    assert describe("is_high_difficulty==true") == "is_high_difficulty == true"


# --- 평가: 확정 -------------------------------------------------------------

def test_always_는_메타가_없어도_활성():
    r = evaluate("always", None)
    assert r.state == ACTIVE and r.active and not r.unknown
    assert r.confidence_penalty == 0


@pytest.mark.parametrize("age,expected", [(67, ACTIVE), (65, ACTIVE), (64, INACTIVE)])
def test_수_비교(age, expected):
    assert evaluate("customer_age >= 65", {"customer_age": age}).state == expected


def test_불리언_비교():
    assert evaluate("is_high_difficulty == true", {"is_high_difficulty": True}).state == ACTIVE
    assert evaluate("is_high_difficulty == true", {"is_high_difficulty": False}).state == INACTIVE
    assert evaluate("is_suitable == false", {"is_suitable": False}).state == ACTIVE


def test_목록_소속():
    meta = {"product_type": "ELS"}
    assert evaluate("product_type in [ELS, ELB, DLS, DLB]", meta).state == ACTIVE
    assert evaluate("product_type in [펀드, 신탁]", meta).state == INACTIVE
    assert evaluate("product_type not in [펀드, 신탁]", meta).state == ACTIVE


def test_문자열_비교는_공백_대소문자를_무시():
    assert evaluate("product_type == ELS", {"product_type": " els "}).state == ACTIVE
    assert evaluate("risk_profile != 적합", {"risk_profile": "부적합"}).state == ACTIVE
    assert evaluate("risk_profile != 적합", {"risk_profile": "적합"}).state == INACTIVE


# --- 평가: UNKNOWN — 이 시스템에서 가장 중요한 부분 --------------------------

def test_메타가_없으면_UNKNOWN_이고_보수적으로_활성된다():
    r = evaluate("customer_age >= 65", {})
    assert r.state == UNKNOWN
    assert r.active is True                      # 놓침 0 — 조용히 꺼지지 않는다
    assert r.confidence_penalty == 1
    assert "메타 부족: customer_age" in r.reasons
    assert "customer_age" in r.reason_text()


def test_None_값은_없는_것과_같다():
    assert evaluate("customer_age >= 65", {"customer_age": None}).state == UNKNOWN


def test_타입이_안_맞으면_UNKNOWN(recwarn):
    r = evaluate("customer_age >= 65", {"customer_age": "예순일곱"})
    assert r.state == UNKNOWN and r.active
    assert "수로 비교할 수 없습니다" in r.reason_text()


def test_불리언으로_못_읽으면_UNKNOWN():
    r = evaluate("is_high_difficulty == true", {"is_high_difficulty": "아마도"})
    assert r.state == UNKNOWN
    assert "참/거짓" in r.reason_text()


# --- Kleene 3치 논리 ---------------------------------------------------------

def test_or_는_확정된_참이_있으면_UNKNOWN_을_흡수한다():
    # C-18(숙려기간)의 실제 식. 나이가 확정 67이면 고난도 여부를 몰라도 활성이고 감점도 없다.
    r = evaluate("is_high_difficulty == true or customer_age >= 65", {"customer_age": 67})
    assert r.state == ACTIVE and r.confidence_penalty == 0 and r.reasons == ()


def test_or_는_한쪽이_모르면_UNKNOWN():
    r = evaluate("is_high_difficulty == true or customer_age >= 65", {"customer_age": 40})
    assert r.state == UNKNOWN
    assert r.reasons == ("메타 부족: is_high_difficulty",)


def test_or_는_양쪽이_거짓이어야_비활성():
    r = evaluate("is_high_difficulty == true or customer_age >= 65",
                 {"customer_age": 40, "is_high_difficulty": False})
    assert r.state == INACTIVE and not r.active


def test_and_는_확정된_거짓이_있으면_비활성():
    r = evaluate("is_high_difficulty == true and customer_age >= 65", {"customer_age": 40})
    assert r.state == INACTIVE and r.reasons == ()


def test_and_는_한쪽이_모르면_UNKNOWN():
    r = evaluate("is_high_difficulty == true and customer_age >= 65", {"customer_age": 70})
    assert r.state == UNKNOWN and r.active


def test_and_가_or_보다_먼저_묶인다():
    # a or (b and c) — a 가 참이면 b·c 를 몰라도 활성
    src = "is_high_difficulty == true or customer_age >= 65 and risk_profile != 적합"
    assert evaluate(src, {"is_high_difficulty": True}).state == ACTIVE
    assert describe(src) == ("(is_high_difficulty == true or "
                            "(customer_age >= 65 and risk_profile != 적합))")


def test_괄호가_우선순위를_뒤집는다():
    src = "(is_high_difficulty == true or customer_age >= 65) and product_type in [ELS]"
    assert evaluate(src, {"customer_age": 70, "product_type": "펀드"}).state == INACTIVE
    assert evaluate(src, {"customer_age": 70, "product_type": "ELS"}).state == ACTIVE


# --- 결정론·입력 형태 --------------------------------------------------------

def test_같은_입력이면_같은_결과():
    src = "is_high_difficulty == true or customer_age >= 65"
    meta = {"customer_age": 40}
    a, b = evaluate(src, meta), evaluate(src, meta)
    assert (a.state, a.reasons, a.source) == (b.state, b.reasons, b.source)


def test_pydantic_메타도_받는다():
    from lawrag.agents.agent6.src.schema import TranscriptMeta
    m = TranscriptMeta(customer_age=67)
    assert evaluate("customer_age >= 65", m).state == ACTIVE
    # 선언되지 않은 필드는 없는 것 → UNKNOWN (조용한 비활성 아님)
    assert evaluate("is_high_difficulty == true", m).state == UNKNOWN


def test_사유는_중복_없이_한_번씩():
    r = evaluate("customer_age >= 65 and customer_age <= 80", {})
    assert r.reasons == ("메타 부족: customer_age",)


# --- 실제 체크리스트의 when 이 전부 파싱되는가 -------------------------------

def test_체크리스트_전체의_when_이_파싱된다():
    from pathlib import Path

    from lawrag.agents.agent6.src.schema import load_items

    root = Path(__import__("lawrag").__file__).resolve().parent
    items = load_items(root / "agents/agent6/checklist/items")
    for item in items:
        r = item.activation({"customer_age": 67, "product_type": "ELS",
                             "is_high_difficulty": True, "is_suitable": False,
                             "has_early_termination_penalty": True,
                             "has_withdrawal_right": True, "customer_question_count": 3})
        assert r.state in (ACTIVE, INACTIVE, UNKNOWN)


def test_메타가_전혀_없으면_모든_항목이_활성된다():
    """놓침 0 — 메타 미제출 호출에서 항목이 조용히 빠지지 않는지 확인한다."""
    from pathlib import Path

    from lawrag.agents.agent6.src.schema import load_items

    root = Path(__import__("lawrag").__file__).resolve().parent
    items = load_items(root / "agents/agent6/checklist/items")
    inactive = [i.id for i in items if not i.activation({}).active]
    assert inactive == []


def test_나이_67이면_C_18_과_E_27_이_활성된다():
    """AGENT6 §9-3 의 when 평가 기준."""
    from pathlib import Path

    from lawrag.agents.agent6.src.schema import load_items

    root = Path(__import__("lawrag").__file__).resolve().parent
    items = {i.id: i for i in load_items(root / "agents/agent6/checklist/items")}
    meta = {"customer_age": 67, "is_high_difficulty": False}
    for item_id in ("C-18", "E-27"):
        r = items[item_id].activation(meta)
        assert r.state == ACTIVE, f"{item_id} 가 활성되지 않았습니다: {r.reason_text()}"
    # 나이가 낮고 고난도도 아니면 두 항목은 비활성 — 사유가 리포트에 남는다
    young = {"customer_age": 40, "is_high_difficulty": False}
    for item_id in ("C-18", "E-27"):
        r = items[item_id].activation(young)
        assert r.state == INACTIVE and "조건 미충족" in r.reason_text()


def test_when_이_보는_필드는_전부_메타에_선언돼_있다():
    """선언되지 않은 필드는 **영원히 UNKNOWN** 이다 — 그 항목은 늘 보수 활성되고 늘 감점된다.

    오타 하나("customer_ages")가 조용히 그 상태를 만들기 때문에 여기서 잡는다.
    """
    from pathlib import Path

    from lawrag.agents.agent6.src.schema import TranscriptMeta, load_items

    root = Path(__import__("lawrag").__file__).resolve().parent
    items = load_items(root / "agents/agent6/checklist/items")
    선언된 = set(TranscriptMeta.model_fields)
    for item in items:
        모르는 = item.when_fields() - 선언된
        assert not 모르는, f"{item.id}: when 이 보는 {모르는} 이 메타에 선언돼 있지 않습니다"


# --- 파이프라인에서의 활성 확정 (§5-1) ---------------------------------------

def _prepare(meta):
    from pathlib import Path

    from lawrag.agents.agent6.src import preprocess

    fixtures = Path(__file__).resolve().parent / "fixtures"
    return preprocess.prepare(fixtures / "clean.json", meta)


def test_메타가_없으면_보수적으로_켜지고_신뢰도를_깎는다():
    """모르면 켠다 — 끄면 리포트에 흔적조차 남지 않는다(§5-1)."""
    p = _prepare(None)
    for item_id in ("C-18", "E-27", "E-26", "B-10"):
        a = p.activations[item_id]
        assert a.active and a.state == UNKNOWN, f"{item_id}: {a.text}"
        assert a.confidence_penalty >= 1
        assert any("메타 부족" in r for r in a.reasons)


def test_고령_메타면_고령_항목이_켜지고_사유가_남는다():
    """§9-3: age=67 → C-18·E-27 활성. 근거 미해소 감점이 한 단계 더 붙는 것까지 본다.

    감점이 둘로 나뉘어 있다는 것을 모른 채 "감점 0" 을 기대하면, 나중에 KOFIA-R 앵커가
    해소돼 감점이 사라져도 아무도 알아채지 못한다.
    """
    p = _prepare({"customer_age": 67, "product_type": "ELS"})
    for item_id in ("C-18", "E-27"):
        a = p.activations[item_id]
        assert a.active and a.state == ACTIVE, f"{item_id}: {a.text}"
        assert a.confidence_penalty == 1
        assert "미해소 basis" in (a.blocked_reason or "")
    assert "E-27" in {i.id for i in p.active_items()}


def test_해당하지_않는_항목은_꺼지되_행은_남는다():
    p = _prepare({"customer_age": 58, "is_high_difficulty": False, "product_type": "펀드"})
    e27 = p.activations["E-27"]
    assert not e27.active and e27.state == INACTIVE
    assert "customer_age" in e27.text or "조건 미충족" in e27.text
    assert not p.activations["C-18"].active     # 고난도 아님 + 65세 미만
    assert not p.activations["B-14"].active     # ELS 계열이 아님
