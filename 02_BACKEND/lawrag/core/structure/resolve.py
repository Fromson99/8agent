"""S5b · 잔여 해소 — **문서당 배치 1콜** (SPEC §0, §4 S5).

    resolve(result, llm) -> Resolution

결정론 캐스케이드가 다 돌고 나서 **신호가 서로 모순된 후보만** 모아 한 번에 묻는다.
per-후보 루프가 아니다. 잔여가 0건이면 호출 자체가 없다.

## 왜 여기만 LLM 인가

앞 단계는 전부 결정론이다(§0 "결정론 우선"). LLM 은 판별을 대신하는 것이 아니라
**결정론이 스스로 모순이라고 말한 지점**만 받는다. 그래서

    · 물어보는 것이 좁다 — "이 마커가 구조 경계냐 본문 속 인용이냐" 하나뿐
    · 답이 좁다 — structure | mention, 후보 id 로만 가리킨다
    · 지어낼 자리가 없다 — 후보 목록에 없는 id 는 버린다

§0 이 말한 "LLM은 결정론이 못 가른 잔여에만, 문서당 배치 1콜(대개 0콜)" 의 구현이다.

## 해소 뒤에 다시 세운다

판정을 후보에 심고 **S3(사다리)·S4(DP)·트리를 다시 돌린다.** 마커 하나가 살아나면
그 계열의 수열과 사다리가 통째로 달라질 수 있어서, 트리만 손보면 앞뒤가 안 맞는다.

## 결정론 유지

같은 문서를 두 번 돌리면 같은 결과여야 한다(§0). LLM 은 그것을 보장하지 못하므로
호출 전후를 전부 감사 로그에 남기고, 무엇이 사람/모델의 판정으로 바뀌었는지
`Candidate.decision_note` 에 표시한다. 재현이 필요한 경로(테스트·회귀)는 `llm=None`
으로 부르면 이 단계가 통째로 건너뛰어진다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SYSTEM = """당신은 한국어 구조화 문서의 **구조 경계 판별기**다. 답을 만들지 마라 — 분류만 한다.

결정론 판별이 이미 대부분을 갈랐다. 아래 후보들은 두 신호가 서로 다른 답을 낸 것들이다.

    가드   마커의 위치·조사·형태를 본다. "블록 첫머리 + 조사 없음 + 완전형" 이면 헤더로 본다.
    수열   같은 계열의 번호가 한 칸씩 전진하는지 본다. 건너뛰면 인용으로 본다.

각 후보가 둘 중 무엇인지만 판정한다.

    structure  이 마커가 문서의 구역을 **연다**. (조 제목, 항 번호, 목차 항목 …)
    mention    이 마커는 본문이 **가리키는 대상**이다. (다른 조문 인용, 개정 지시, 날짜 …)

## 판단 기준

- 마커 뒤에 그 구역의 **제목이나 내용**이 이어지면 structure 다.
- 마커가 문장의 목적어·수식어로 쓰였으면 mention 이다.
  `제7조(다른 법률의 개정) ①부터 <598>까지 생략` 처럼 **부칙의 개정 지시문**은
  형태가 조문 제목과 같아도 본문 구조를 여는 것이 아니다. 문서 종류를 보고 판단하라.
- 번호가 건너뛴 것(`5 뒤에 7`)은 개정으로 조가 삭제됐거나 파싱이 한 줄 빠뜨린 경우가
  많다. 원문이 멀쩡한 조문·항목이면 structure 다.
- 확신이 없으면 `unsure` 로 두고 이유를 적어라. 억지로 고르지 마라.

입력에 없는 id 를 만들지 마라. 원문에 없는 말을 근거로 삼지 마라."""

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdicts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "verdict": {"type": "string",
                                "enum": ["structure", "mention", "unsure"]},
                    "reason": {"type": "string"},
                },
                "required": ["id", "verdict", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdicts"],
    "additionalProperties": False,
}


@dataclass
class Resolution:
    called: bool = False
    asked: int = 0
    structure: list[str] = field(default_factory=list)
    mention: list[str] = field(default_factory=list)
    unsure: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)   # 후보에 없는 id 를 지어낸 것
    changed: int = 0                                   # 판정으로 실제로 바뀐 개수
    notes: list[str] = field(default_factory=list)

    def dump(self) -> dict:
        return {"called": self.called, "asked": self.asked, "changed": self.changed,
                "structure": self.structure, "mention": self.mention,
                "unsure": self.unsure, "ignored": self.ignored, "notes": self.notes}


def resolve(result, llm, *, rebuild=True, **rebuild_kw) -> Resolution:
    """잔여를 한 번에 묻고 판정을 심는다. 잔여가 없으면 호출하지 않는다."""
    from lawrag.core.structure import pipeline

    by_id = {c.id: c for c in result.candidates}
    # 잔여 리스트에는 후보 항목(`[모순] c7 …`)과 s5_thin 의 의심(`[놓친 제목?] blk5 …`)이
    # 섞여 있다. S5b 는 **후보 판정**만 한다 — blkN 은 후보가 아니라서 물어봐야 응답이
    # `ignored` 로 버려지고 asked 만 부풀며, 그 자리는 S5c(VLM)의 몫이다.
    asked_ids = {cid for cid in (r.split()[1] for r in result.residual) if cid in by_id}
    res = Resolution(asked=len(asked_ids))
    if not asked_ids:
        res.notes.append("후보 잔여 0건 — LLM 을 부르지 않았습니다")
        return res
    if llm is None:
        res.notes.append(f"잔여 {res.asked}건이 있으나 llm 이 없어 건너뜁니다")
        return res

    prompt = pipeline.residual_prompt(result)
    data = llm.structured("structure_residual", SYSTEM, prompt, SCHEMA, effort="high")
    res.called = True
    if not data:
        res.notes.append("LLM 호출이 실패했습니다 — 결정론 판정을 그대로 둡니다")
        result.warnings.append("잔여 해소 실패: LLM 응답을 받지 못했습니다")
        return res

    for v in data.get("verdicts", []):
        cid, verdict = v.get("id", ""), v.get("verdict", "")
        reason = (v.get("reason") or "").strip()
        cand = by_id.get(cid)
        if cand is None or cid not in asked_ids:
            res.ignored.append(cid)          # 지어낸 id 는 버린다
            continue
        # 판정이 온 후보는 결과와 무관하게 표시한다 — 결정론 판정과 같더라도
        # 다시 물을 이유가 없다.
        cand.llm_verdict = verdict
        if verdict == "structure":
            res.structure.append(cid)
            if not cand.survives:
                cand.survives = True
                cand.family_note = f"LLM 판정: 구조 — {reason}"
                res.changed += 1
        elif verdict == "mention":
            res.mention.append(cid)
            if cand.survives:
                cand.survives = False
                cand.family_note = f"LLM 판정: 인용 — {reason}"
                res.changed += 1
        else:
            res.unsure.append(cid)

    missing = sorted(asked_ids - set(res.structure) - set(res.mention) - set(res.unsure))
    if missing:
        res.notes.append(f"판정이 오지 않은 후보 {len(missing)}건은 결정론 판정을 유지합니다")
    if res.ignored:
        res.notes.append(f"후보 목록에 없는 id {res.ignored} 를 버렸습니다")

    result.audit_log.append(
        f"[LLM 배치 1콜] 물음 {res.asked}건 → 구조 {len(res.structure)}, "
        f"인용 {len(res.mention)}, 보류 {len(res.unsure)}; 실제 변경 {res.changed}건")

    if res.changed and rebuild:
        pipeline.rebuild(result, **rebuild_kw)
        res.notes.append("판정을 심고 사다리·DP·트리를 다시 세웠습니다")
    else:
        # 바뀐 것이 없어도 잔여는 다시 뽑는다 — 판정을 받은 후보가 빠져야
        # 목록이 수렴하고, 두 번째 콜이 같은 질문을 반복하지 않는다.
        # thin 의심도 다시 올린다 — rebuild 경로(pipeline.rebuild)와 잔여 구성이
        # 같아야 두 경로의 결과를 나란히 볼 수 있다.
        result.residual = []
        pipeline.s5_residual(result)
        pipeline.s5_thin(result, rebuild_kw.get("blocks"))
    return res
