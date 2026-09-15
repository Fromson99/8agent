"""변이 시험의 재료 — 위반 발화 표와 변이 전사 생성기 (AGENT6 §9 추가기준 1·6).

## 표를 손으로 적어 두는 이유

예전 변이표는 "항목 스펙의 `lexicon.hit` 에 실제로 있는 표현일 것"을 시험이 강제했다.
그러면 변이는 **엔진이 이미 아는 표현만** 주입하게 되고, 시험지와 답안지를 같은 사람이
쓴 것이 된다. 실제로 그 시험은 12종 전부를 통과하면서, 목록에 없는 표현으로 말한
위반은 하나도 잡지 못했다.

그래서 여기서는 **어디에도 등록되어 있지 않아도 되는 문장**을 손으로 적는다. 스펙이
바뀌어도 이 표는 그대로 남아 같은 것을 묻는다 — 표가 스펙을 따라 줄어들면 시험이
조용히 무력해지기 때문에, 스펙에서 표현을 읽어 오는 방식은 쓰지 않는다.

## 두 갈래

    적대검증   적대적 검증에서 **실제로 PASS 로 샜던** 문장들. 하나도 등록된 적이 없다.
    스펙예시   항목 스펙의 few_shot 이 FAIL 로 확정해 둔 문장들. 스펙 자신이 위반이라고
               적어 둔 것조차 예전에는 통과했다(D-20·D-21·D-22).

부재형 6항목(D-20~D-25)마다 두 갈래에서 하나씩, 모두 12종이다.

## 심는 자리

수수료 설명 직전(고객 응답과 PB 발화 사이)에 끼운다. 앞뒤 발화가 위반과 무관해서
"이 문장 하나 때문에 걸렸다"가 분명해지는 자리다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# 이 발화 **앞**에 끼운다. 위반 발화와 붙어 있는 앞뒤 문장이 위반과 무관한 자리다.
삽입_기준_발화 = "판매수수료는 선취로"


@dataclass(frozen=True)
class Mutation:
    """변이 하나 — 어느 항목을 겨냥해 어떤 발화를 심는가."""
    item_id: str
    key: str                                   # 시험 id (사람이 읽는 이름)
    turns: tuple[tuple[str, str], ...]         # (화자, 발화문) — 대화 흐름이 필요한 변이는 2턴
    origin: str                                # 적대검증 | 스펙예시

    @property
    def text(self) -> str:
        """심은 PB 발화 — 인용 대조에 쓴다(고객 턴은 위반의 주체가 아니다)."""
        return next(t for who, t in self.turns if who == "PB")

    def label(self) -> str:
        return f"{self.item_id}:{self.key}"


def _pb(item_id: str, key: str, text: str, origin: str) -> Mutation:
    return Mutation(item_id=item_id, key=key, turns=(("PB", text),), origin=origin)


# --- 적대검증: 실제로 PASS 로 샜던 문장들 (금지어 목록에 하나도 없다) -------------
적대검증: list[Mutation] = [
    _pb("D-20", "하락부인",
        "지수가 여기서 더 내려갈 일은 없으니 안심하셔도 됩니다.", "적대검증"),
    _pb("D-21", "개인보전",
        "만에 하나 손실이 나면 제 개인 돈으로라도 채워 넣어 드리겠습니다.", "적대검증"),
    _pb("D-22", "보호오인",
        "이 상품은 예금자보호 대상이라 5천만원까지 나라가 지켜 줍니다.", "적대검증"),
    _pb("D-23", "적금비유",
        "사실상 정기적금 넣으시는 거랑 위험이 똑같다고 보시면 됩니다.", "적대검증"),
    _pb("D-24", "타사비방",
        "옆 은행 상품은 사기꾼들이 만든 쓰레기라 근처도 가지 마세요.", "적대검증"),
    _pb("D-25", "즉시결정",
        "지금 사인 안 하시면 이 조건 다시는 못 받으십니다.", "적대검증"),
]

# --- 스펙예시: 항목 스펙이 FAIL 로 확정해 둔 문장들 ------------------------------
# 앞의 셋(D-20·D-21·D-22)이 예전에 PASS 로 샜던 것들이다. 나머지 셋은 부재형 전체를
# 같은 방식으로 덮기 위해 각 항목의 FAIL 예시에서 하나씩 가져와 손으로 적었다.
스펙예시: list[Mutation] = [
    _pb("D-20", "망국단정", "이건 나라가 망하지 않는 한 안전해요.", "스펙예시"),
    _pb("D-21", "수익보장", "최소 연 4%는 나오게 해 드리겠습니다.", "스펙예시"),
    _pb("D-22", "무손실단언", "이 시리즈는 지금까지 손실 난 적이 한 번도 없습니다.", "스펙예시"),
    _pb("D-23", "반문부인", "지수가 반토막이 나야 손실인데 그런 일이 있겠습니까.", "스펙예시"),
    _pb("D-24", "근거없는우월", "이게 요즘 나온 것 중에는 제일 낫습니다.", "스펙예시"),
    # 대화의 흐름이 위반인 유일한 변이 — 고객이 유보 의사를 밝힌 뒤의 권유 계속.
    Mutation(item_id="D-25", key="유보무시",
             turns=(("고객", "좀 생각해 볼게요."),
                    ("PB", "생각하실 게 뭐 있습니까, 지금 바로 하시죠.")),
             origin="스펙예시"),
]

변이들: list[Mutation] = [*적대검증, *스펙예시]


def retime(turns: list[dict]) -> list[dict]:
    """발화 길이에 비례해 타임스탬프를 다시 매긴다(픽스처 생성기와 같은 규칙).

    **결정론이어야 한다.** 타임스탬프는 프롬프트에 실리고, 프롬프트가 한 글자라도
    달라지면 녹화 키가 달라져 재생이 통째로 깨진다.
    """
    t = 0.0
    for u in turns:
        dur = round(1.2 + len(u["text"]) * 0.13, 1)
        u["start"], u["end"] = round(t, 1), round(t + dur, 1)
        t = t + dur + 0.6
    return turns


def build(mutation: Mutation, out_dir: Path, base: str = "clean") -> Path:
    """정상 통화(clean)에 위반 발화를 끼운 전사를 쓴다. **바꾸는 것은 그 발화들뿐이다.**"""
    turns = json.loads((FIXTURES / f"{base}.json").read_text(encoding="utf-8"))
    i = next(i for i, u in enumerate(turns) if 삽입_기준_발화 in u["text"])
    for offset, (who, text) in enumerate(mutation.turns):
        turns.insert(i + offset, {"speaker": who, "start": 0.0, "end": 0.0, "text": text})
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"mutation_{mutation.item_id}_{mutation.key}.json"
    p.write_text(json.dumps(retime(turns), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def build_combined(out_dir: Path, base: str = "clean") -> Path:
    """변이 12종을 **한 전사에** 흩어 심는다.

    ## 왜 12벌이 아니라 한 벌인가

    변이마다 전사를 따로 만들면 전사가 12개가 되고, 판정은 전사마다 카테고리 배치를
    다시 태우므로 녹화가 12벌 필요하다(실측 72회 호출). 물어보는 것은 같은데 비용만
    열두 배다 — 시험이 재는 것은 **"부재형 항목이 PASS 로 통과하지 않는가"** 이고,
    그 판정은 항목마다 독립이므로 한 전사에 다 심어도 항목별로 따로 나온다.

    거짓 양성(멀쩡한 통화를 걸어 버리는 것)은 이 전사가 아니라 **clean 대조군**이 잡는다.
    둘을 합쳐야 시험이 성립한다 — 이쪽만 있으면 "전부 FAIL 을 내는 판정기"도 만점이다.

    ## 흩어 심는 이유

    한자리에 12개를 몰아넣으면 그 구간 전체가 수상해 보여서, 판정기가 문장을 읽지 않고
    구간을 통째로 의심해도 시험을 통과한다. 통화 전체에 고르게 흩어 두면 **어느 발화가
    왜 걸렸는지**를 인용으로 확인할 수 있다.
    """
    turns = json.loads((FIXTURES / f"{base}.json").read_text(encoding="utf-8"))
    # PB 발화 자리에만 심는다(위반의 주체는 판매자다). 고르게 벌려 배치한다 —
    # 결정론이어야 하므로 난수를 쓰지 않고 등간격으로 고른다.
    pb = [i for i, u in enumerate(turns) if u.get("speaker") == "PB"]
    step = max(1, len(pb) // (len(변이들) + 1))
    지점 = [pb[min(len(pb) - 1, (n + 1) * step)] for n in range(len(변이들))]

    # 뒤에서부터 끼워 넣어야 앞의 삽입이 뒤 지점의 인덱스를 밀지 않는다.
    for m, at in sorted(zip(변이들, 지점), key=lambda x: -x[1]):
        for offset, (who, text) in enumerate(m.turns):
            turns.insert(at + offset, {"speaker": who, "start": 0.0, "end": 0.0, "text": text})

    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / "mutation_combined.json"
    p.write_text(json.dumps(retime(turns), ensure_ascii=False, indent=2), encoding="utf-8")
    return p
