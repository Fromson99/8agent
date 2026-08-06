"""대본 판정기 — 키도 네트워크도 쓰지 않는 가짜 LLM (테스트 전용).

## 녹화/재생이 있는데 왜 가짜 판정기가 또 필요한가

둘이 보는 것이 다르다.

    녹화/재생   **모델이 무엇을 잡는가**. 변이·골든이 이쪽이다(실제 응답을 고정해 둔다).
    대본 판정기 **판정 이후가 옳은가**. 인용 대조·화자 검사·파생 계산·라우팅·안내문·
                큐·종합 판정은 모델이 아니라 엔진의 일이고, 그것을 시험하려면 모델이
                **일부러 틀리게** 답해 줘야 한다. 지어낸 인용, 고객 발화만 든 근거,
                전부 PASS 같은 최악의 응답은 실제 모델에게 시킬 수 없다.

대본 판정기가 검증을 무르게 만들지 않는 이유: 가짜가 대신하는 것은 "무엇이 위반인가"라는
판단 하나뿐이고, 그 뒤의 응답 파싱·인용 검증·강등·파생·라우팅·리포트는 전부 진짜 코드가
돈다. 오히려 여기서 쓰는 대본은 실제 모델보다 **적대적**이다.

## 프롬프트를 읽어서 답한다

대본 판정기는 전사도 항목 목록도 **프롬프트에서 파싱**한다. 그래서 이 클래스가 도는
것 자체가 "프롬프트에 전사와 항목 블록이 실제로 실렸다"는 증거다(컨텍스트가 비면
인용을 만들지 못해 판정이 강등되고 시험이 깨진다).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from agents.agent6.src import cli, judge as judge_mod, schema

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# 프롬프트 판독기 — context_asm 이 만드는 모양 그대로다.
#   "### D-20 단정적 판단 제공 없음  (부재형)"
#   "  [발화001 PB 0.0s] 안녕하세요 …"
항목머리 = re.compile(r"^### ([A-F]-\d{2}) (.+?)\s+\((\S+)\)\s*$", re.M)
발화줄 = re.compile(r"^  \[(발화\d+) (\S+) [^\]]*\] (.*)$", re.M)

# 대본에서 인용을 고를 때 쓰는 최소 길이. 맞장구("네")를 근거로 삼으면 엔진이
# 정당하게 버리므로, 정상 경로를 시험할 때는 충분히 긴 발화를 고른다.
인용_최소길이 = 20


class 대본판정기:
    """프롬프트를 읽고 대본대로 답하는 판정기.

    대본은 `{항목id: (판정, 인용에 쓸 문자열|None)}`. 적지 않은 항목은 PASS 다.
    인용 문자열을 주지 않으면 **엔진의 인용 요구 규칙**(judge.requires_evidence)에 맞춰
    필요한 때만 PB 발화를 하나 골라 인용한다 — 규칙을 여기서 다시 적으면 언젠가 갈린다.
    """

    model = "대본"

    def __init__(self, script: Optional[dict[str, tuple[str, Optional[str]]]] = None):
        self.script = dict(script or {})
        self.calls: list[dict] = []
        self.stray: dict[str, list[dict]] = {}   # 배치 응답에 몰래 끼워 넣을 행
        self.log: list[object] = []

    # --- 프롬프트 읽기 ------------------------------------------------------
    @staticmethod
    def 전사(user: str) -> dict[str, tuple[str, str]]:
        return {m.group(1): (m.group(2), m.group(3)) for m in 발화줄.finditer(user)}

    @staticmethod
    def 항목들(user: str) -> list[tuple[str, str]]:
        return [(m.group(1), m.group(3)) for m in 항목머리.finditer(user)]

    def _인용(self, item_id: str, item_type: str, verdict: str,
              quote: Optional[str], 전사표: dict[str, tuple[str, str]]) -> list[dict]:
        if quote is not None:
            sid = next((s for s, (_, t) in 전사표.items() if quote in t), None)
            assert sid, f"{item_id}: 대본의 인용 '{quote}' 가 전사에 없습니다"
            return [{"section_id": sid, "text": 전사표[sid][1]}]
        if not judge_mod.requires_evidence(item_type, verdict):
            return []
        sid = next((s for s, (who, t) in 전사표.items()
                    if who == "PB" and len(t) >= 인용_최소길이), None)
        assert sid, f"{item_id}: 인용할 PB 발화가 프롬프트에 없습니다"
        return [{"section_id": sid, "text": 전사표[sid][1]}]

    # --- 응답 만들기 --------------------------------------------------------
    def structured(self, kind: str, system: str, user: str, schema: dict, **kw) -> dict:
        self.calls.append({"kind": kind, "system": system, "user": user})
        전사표 = self.전사(user)
        assert 전사표, f"{kind}: 프롬프트에 전사가 실리지 않았습니다"
        항목 = self.항목들(user)
        assert 항목, f"{kind}: 프롬프트에 항목 블록이 실리지 않았습니다"

        rows = []
        for item_id, item_type in 항목:
            verdict, quote = self.script.get(item_id, ("PASS", None))
            rows.append({
                "item_id": item_id, "verdict": verdict,
                "evidence": self._인용(item_id, item_type, verdict, quote, 전사표),
                "reason": f"대본 판정({verdict})", "confidence": "high"})
        rows.extend(self.stray.get(kind, []))
        return {"judgments": rows}

    def totals(self) -> dict:
        return {"calls": len(self.calls), "input_tokens": 0, "output_tokens": 0, "errors": 0}


# ===========================================================================
# 적대적 대본 — 인용 규칙을 어기는 판정기들
# ===========================================================================

class 지어내는판정기(대본판정기):
    """전사에 없는 문장을 인용한다."""

    지어낸_문장 = "이 상품은 금융감독원이 원금을 보증하는 상품입니다"

    def structured(self, **kw):
        payload = super().structured(**kw)
        for row in payload["judgments"]:
            row["evidence"] = [{"section_id": "발화001", "text": self.지어낸_문장}]
        return payload


class 맞장구판정기(대본판정기):
    """"네" 한 글자를 근거로 댄다 — 전사 어딘가에는 반드시 있는 문자열이다."""

    def structured(self, **kw):
        payload = super().structured(**kw)
        전사표 = self.전사(kw["user"])
        sid = next(s for s, (who, t) in 전사표.items() if who == "고객" and t.startswith("네"))
        for row in payload["judgments"]:
            row["evidence"] = [{"section_id": sid, "text": "네"}]
        return payload


class 이어붙인판정기(대본판정기):
    """인접한 두 발화를 이어 붙인, 아무도 말한 적 없는 문장을 인용한다."""

    def structured(self, **kw):
        payload = super().structured(**kw)
        전사표 = list(self.전사(kw["user"]).items())
        (sid, (_, first)), (_, (_, second)) = 전사표[12], 전사표[13]
        for row in payload["judgments"]:
            row["evidence"] = [{"section_id": sid, "text": f"{first} {second}"}]
        return payload


class 없는좌표판정기(대본판정기):
    """실재하는 문장을 인용하되 좌표를 틀리게 적는다."""

    좌표 = "발화999"

    def structured(self, **kw):
        payload = super().structured(**kw)
        전사표 = self.전사(kw["user"])
        text = next(t for _, (who, t) in 전사표.items() if who == "PB" and len(t) >= 20)
        for row in payload["judgments"]:
            row["evidence"] = [{"section_id": self.좌표, "text": text}]
        return payload


class 고객발화판정기(대본판정기):
    """존재형 PASS 를 **고객 발화만으로** 주장한다 — 실제로 뚫렸던 구멍이다."""

    def __init__(self, script=None, 고객_문장: Optional[str] = None):
        super().__init__(script)
        self.고객_문장 = 고객_문장

    def structured(self, **kw):
        payload = super().structured(**kw)
        전사표 = self.전사(kw["user"])
        후보 = [(s, t) for s, (who, t) in 전사표.items()
                if who == "고객" and (self.고객_문장 is None or self.고객_문장 in t)]
        assert 후보, f"고객 발화를 찾지 못했습니다({self.고객_문장})"
        sid, text = 후보[0]
        for row in payload["judgments"]:
            row["evidence"] = [{"section_id": sid, "text": text}]
        return payload


class 회차별판정기(대본판정기):
    """자기일관성 회차마다 다른 답을 낸다 — 갈림이 어떻게 합쳐지는지 시험한다.

    대본은 `{항목id: [1회차 판정, 2회차 판정, …]}`. 회차는 `kind` 끝의 "N회차"에서 읽는다
    (녹화 키가 회차를 포함하는 것과 같은 규약이다).
    """

    def __init__(self, 회차대본: dict[str, list[str]]):
        super().__init__()
        self.회차대본 = dict(회차대본)

    def structured(self, **kw):
        n = int(re.search(r"-(\d+)회차$", kw["kind"]).group(1))
        self.script = {iid: (판정[min(n, len(판정)) - 1], None)
                       for iid, 판정 in self.회차대본.items()}
        return super().structured(**kw)


# ===========================================================================
# 실행 도우미
# ===========================================================================

def run(name: str, out_dir: Path, *, llm=None, consistency: int = 1, **kw):
    """픽스처 하나를 파이프라인에 태운다(대본 판정기 경로).

    `llm_mode="live"` 인데 네트워크를 쓰지 않는 이유: 녹화 래퍼는 주입된 클라이언트를
    그대로 부르기만 한다(llm_cache.wrap). 녹화도 재생도 하지 않는 경로다.
    """
    return cli.run_pipeline(
        FIXTURES / f"{name}.json", meta=FIXTURES / f"{name}.meta.json",
        out_dir=out_dir, llm_mode="live", consistency=consistency,
        llm=llm if llm is not None else 대본판정기(), history=False, **kw)


def replay(transcript: Path, meta, out_dir: Path, *, consistency: int = 1, **kw):
    """녹화 재생 — 키가 없어도 돌고, 같은 입력이면 같은 결과다."""
    return cli.run_pipeline(transcript, meta=meta, out_dir=out_dir,
                            llm_mode="replay", consistency=consistency,
                            history=False, **kw)


def verdicts(result) -> dict[str, str]:
    return {r.id: r.verdict for r in result.report.items}


def row(result, item_id: str) -> schema.ItemVerdict:
    return next(r for r in result.report.items if r.id == item_id)


def queue_rows(result) -> list[dict]:
    import json
    p = Path(result.paths["queue"])
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
