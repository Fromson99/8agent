"""T22. fact 직조회 — 값 질문은 여기서 끝난다 (SPEC §D2-2).

임베딩도 LLM 생성도 거치지 않는다. `field=X, role=별지1_입력` 인 fact 를 찾아
`value` 로 답하고 `raw`+`source` 로 인용한다. 파생값은 온톨로지 `derived` 공식으로 계산한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Optional

import derive
from ontology import Ontology
from schema import ChunkDocument, Fact


@dataclass
class Answer:
    field_name: str
    value: Any = None
    raw: str = ""
    source: Optional[dict] = None
    derived_from: Optional[str] = None
    route: list[str] = dc_field(default_factory=list)   # 감사 추적 (§D2 말미)
    found: bool = False
    note: str = ""


class FactStore:
    def __init__(self, doc: ChunkDocument, onto: Ontology):
        import fact as fact_layer

        self.onto = onto
        self.facts: dict[str, Fact] = {
            f.field_name: f for f in fact_layer.from_contract(doc, onto)}

    def get(self, field_name: str) -> Answer:
        spec = self.onto.fields.get(field_name)
        if spec is None:
            return Answer(field_name, found=False, route=["fact_store:unknown_field"],
                          note=f"온톨로지에 '{field_name}' 필드가 없습니다")

        # 파생 필드는 계산으로 답한다 (비교기 인프라 재사용)
        if spec.derived:
            return self._derive(field_name, spec)

        f = self.facts.get(field_name)
        if f is None or not f.raw:
            return Answer(field_name, found=False, route=["fact_store:miss"],
                          note="계약서에서 값을 찾지 못했습니다")
        return Answer(field_name, value=f.value, raw=f.raw,
                      source=f.source.model_dump() if f.source else None,
                      route=["fact_store:hit"], found=True)

    def _derive(self, name: str, spec) -> Answer:
        """계산은 `derive` 가 온톨로지 식을 해석해서 한다 — reconcile 과 **같은 경로**다.

        같은 식을 두 곳에서 따로 계산하면 조용히 갈라진다(실제로 갈라져 있었다).
        """
        calc = derive.evaluate(spec.derived, self.onto.fields,
                               {k: f.raw for k, f in self.facts.items() if f.raw})
        if not calc.ok:
            return Answer(name, found=False, route=["fact_store:derive_fail"],
                          note=f"파생 계산 실패 ({spec.derived}): {calc.reason}")
        base = next((self.facts.get(b) for b in calc.basis if self.facts.get(b)), None)
        return Answer(name, value=calc.value, raw=str(calc.value),
                      source=base.source.model_dump() if base and base.source else None,
                      derived_from=spec.derived, found=True,
                      route=["fact_store:derived"],
                      note=f"계산: {calc.explain}"
                           + (f" (근거 {base.field_name} = {base.raw})" if base else ""))

    def all_fields(self) -> list[str]:
        return list(self.onto.fields)
