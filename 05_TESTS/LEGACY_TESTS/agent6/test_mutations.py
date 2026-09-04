"""변이 시험 — **놓침 0** (AGENT6 §9 추가기준 1·6, T-A6.9).

## 무엇을 시험하는가

정상 통화(clean)에 위반 발화를 **하나씩** 심는다. 심은 항목이 PASS 로 통과하는 변이가
하나라도 있으면 이 시스템은 이름값을 못 한다("불완전판매 Zero"). 그래서 여기서 요구하는
것은 "대체로 걸린다"가 아니라 **전부 걸린다**이다.

## 예전 시험지를 버린 이유

예전 변이 12종은 "표현이 항목 스펙의 `lexicon.hit` 에 실재할 것"을 시험 자신이 강제했다.
엔진이 이미 아는 표현만 주입하도록 강제된 시험이었고, 그래서 12종을 전부 통과하면서도
목록 밖의 표현으로 말한 위반은 하나도 잡지 못했다 — 자기가 낸 문제를 자기가 푼 것이다.

지금 표(tests/agent6/mutations.py)는 **어디에도 등록되어 있지 않은 문장**을 손으로 적어
둔다. 절반은 적대적 검증에서 실제로 PASS 로 샜던 문장이고, 절반은 항목 스펙의 few_shot 이
FAIL 로 확정해 둔 문장이다(그중 셋도 예전에는 샜다). 여기서는 **표현이 어딘가에
등록되어 있는지 묻지 않는다** — 그 물음이 자기 채점을 만든 원인이었다.

## 문턱을 가장 높게 두고 잰다

자기일관성 k=1 로 돌린다. 회차를 늘리면 "한 번이라도 FAIL 이면 FAIL" 규칙 덕에 잡기가
쉬워지므로, 놓침 0 은 **한 번에 잡는지**로 재야 한다. 판정은 녹화 재생이라 결정론이다
(다시 녹화하려면 `python -m tests.agent6.record_fixtures`).

## 한 전사에 다 심는다

12종을 각각 태우면 전사가 12개가 되고 판정 녹화도 열두 배가 된다(실측 72회 호출).
항목별 판정은 서로 독립이므로 **한 전사에 흩어 심어 한 번** 태워도 묻는 것은 같다.
대신 대조군(clean)이 반드시 함께 있어야 한다 — 이 전사만으로는 "전부 FAIL 을 내는
판정기"도 만점을 받기 때문이다. `test_변이_없는_clean_은_그대로_통과한다` 가 그 짝이다.
"""

from __future__ import annotations

import pytest

from tests.agent6 import mutations as mut
from tests.agent6.fakes import FIXTURES, queue_rows, replay, row, verdicts

ids = [m.label() for m in mut.변이들]


부재형 = [f"D-{n}" for n in range(20, 26)]


@pytest.fixture(scope="module")
def 결과(tmp_path_factory):
    """변이 12종을 **한 전사에 흩어 심고 한 번** 태운다(재생 — 키도 네트워크도 쓰지 않는다).

    전사를 변이마다 따로 만들면 판정 녹화가 12벌 필요하고 호출이 열두 배가 된다.
    항목별 판정은 서로 독립이므로 한 전사에 다 심어도 항목마다 따로 나온다
    (자세한 근거는 tests/agent6/mutations.py 의 `build_combined` 설명).
    """
    base = tmp_path_factory.mktemp("mutations")
    transcript = mut.build_combined(base / "transcripts")
    return replay(transcript, FIXTURES / "clean.meta.json", base / "run", consistency=1)


def 심은_말(item_id: str) -> set[str]:
    """그 항목을 겨냥해 심은 PB 발화들(고객 턴은 위반의 주체가 아니다)."""
    return {m.text for m in mut.변이들 if m.item_id == item_id}


# ===========================================================================
# 변이표 자체의 건전성
# ===========================================================================

def test_변이표가_부재형_전체를_두_갈래로_덮는다():
    """부재형 항목이 늘면 표도 늘어야 한다 — 새 항목이 시험 없이 들어오지 않는다.

    표의 문장이 스펙 어딘가에 "등록"되어 있는지는 **묻지 않는다.** 그 물음이 시험을
    엔진의 사본으로 만든다.
    """
    부재형 = {f"D-{n}" for n in range(20, 26)}
    assert {m.item_id for m in mut.적대검증} == 부재형
    assert {m.item_id for m in mut.스펙예시} == 부재형
    assert len(mut.변이들) == 12
    assert len(ids) == len(set(ids))


def test_변이는_기준_전사에서_그_발화만_다르다(결과):
    """걸린 이유를 픽스처 차이로 설명할 수 있어야 한다."""
    import json
    clean = {t["text"] for t in json.loads((FIXTURES / "clean.json").read_text("utf-8"))}
    for m in mut.변이들:
        더한_말 = {t for _, t in m.turns}
        assert not (더한_말 & clean), f"{m.label()}: 심은 발화가 이미 clean 에 있습니다"


# ===========================================================================
# 놓침 0 — PASS 로 통과하는 변이가 하나도 없다
# ===========================================================================

@pytest.mark.parametrize("item_id", 부재형)
def test_변이가_PASS_로_통과하지_않는다(item_id, 결과):
    """§9-1: 위반을 심은 항목이 PASS 면 그것이 곧 놓침이다."""
    x = row(결과, item_id)
    assert x.active, f"{item_id}: 변이를 심었는데 항목이 비활성입니다"
    assert x.verdict in ("FAIL", "UNCLEAR"), \
        f"{item_id}: {sorted(심은_말(item_id))} 를 심었는데 " \
        f"{x.verdict} 로 통과했습니다 — 놓침입니다"
    # 부재형 위반은 재녹취로 지워지지 않는다 — 반드시 사람에게 간다(§4·§6).
    assert x.route == "준법감시큐"


def test_위반이_있는_통화는_통과하지_않는다(결과):
    """항목이 걸렸는데 종합 판정이 통과면 판매 프로세스가 그대로 진행돼 버린다."""
    assert 결과.report.overall != "완전판매요건충족"


@pytest.mark.parametrize("item_id", 부재형)
def test_걸린_항목은_심은_발화를_인용한다(item_id, 결과):
    """인용 없는 미비는 사람이 확인할 수 없다. FAIL 이면 심은 발화를 짚어야 한다.

    한 항목에 두 문장(적대검증·스펙예시)을 심었으므로 **둘 중 하나**를 짚으면 된다.
    엉뚱한 발화를 근거로 들면 실패다 — 그것은 문장을 읽지 않고 구간을 의심한 것이다.
    """
    x = row(결과, item_id)
    if x.verdict != "FAIL":
        pytest.skip(f"{item_id}: UNCLEAR — 인용은 강등 사유에 따라 비어 있을 수 있다")
    assert x.evidence, f"{item_id}: FAIL 인데 인용이 없습니다"
    심은 = 심은_말(item_id)
    assert any(ev.text in 심은 for ev in x.evidence), \
        f"{item_id}: 심은 발화가 아니라 다른 곳을 근거로 들었습니다: " \
        f"{[ev.text[:30] for ev in x.evidence]}"


@pytest.mark.parametrize("item_id", 부재형)
def test_걸린_항목은_준법감시큐에_적재된다(item_id, 결과):
    """라우팅 없는 미비는 사라진 미비다(§5-7)."""
    q = {row_["item_id"]: row_ for row_ in queue_rows(결과)}
    assert item_id in q, f"{item_id}: 큐에 실리지 않았습니다"
    assert q[item_id]["verdict"] in ("FAIL", "UNCLEAR")
    assert q[item_id]["type"] == "부재형"


def test_변이가_고지_항목을_무너뜨리지_않는다(결과):
    """그물이 아무거나 잡는다면 놓침 0 은 의미가 없다.

    심은 것은 부재형 발화뿐이고 고지·설명(존재형) 발화는 clean 그대로다. 그러니 존재형
    판정이 바뀔 이유가 없다 — 여기서 무너지면 거짓 양성이다. (부재형 위반이 잔뜩 섞인
    전사에서도 존재형이 버텨야 한다는 뜻이라, 변이를 따로 태우던 때보다 오히려 엄하다.)
    """
    무너진 = [x.id for x in 결과.report.items
              if x.active and x.type == "존재형" and x.verdict != "PASS"]
    assert not 무너진, f"심지 않은 존재형 항목이 걸렸습니다: {무너진}"


def test_변이_없는_clean_은_그대로_통과한다(tmp_path):
    """대조군 — 같은 판정기가 정상 통화는 통과시킨다(전부 UNCLEAR 로 두면 놓침 0 은 공짜다)."""
    r = replay(FIXTURES / "clean.json", FIXTURES / "clean.meta.json",
               tmp_path, consistency=3)
    assert r.report.overall == "완전판매요건충족"
    assert all(verdicts(r)[f"D-{n}"] == "PASS" for n in range(20, 26))


# ===========================================================================
# 결과표 — 사람이 한눈에 보는 자리
# ===========================================================================

def 결과표(결과) -> str:
    """항목 → 판정 표. 실패했을 때 무엇이 샜는지 바로 보이도록 시험이 직접 만든다."""
    lines = [f"{'항목':<7} {'판정':<8} {'라우팅':<9} {'인용':<36} 심은 말"]
    for item_id in 부재형:
        x = row(결과, item_id)
        인용 = (x.evidence[0].text[:34] if x.evidence else "-")
        말 = " / ".join(t[:22] for t in sorted(심은_말(item_id)))
        lines.append(f"{item_id:<7} {x.verdict:<8} {x.route or '-':<9} {인용:<36} {말}")
    return "\n".join(lines)


def test_결과표를_남긴다(결과, capsys):
    """놓침 0 이 성립하는지 사람이 표로 확인할 수 있어야 한다(`-s` 로 출력)."""
    표 = 결과표(결과)
    print("\n" + 표)
    assert 표.count("\n") == len(부재형)
    assert " PASS " not in 표, "PASS 로 통과한 항목이 있습니다"
