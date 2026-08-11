"""agent1 — 신탁계약서 ↔ 투자설명서 정합성 검증 서비스.

이 파일은 **조립만** 한다. 부품은 전부 `core/` 에 있고, 도메인 지식은 전부
이 폴더의 데이터 파일(`glossary/`, `formats/`, `tasks/`)에 있다.
새 에이전트 = 새 폴더 + 새 데이터 파일이지 새 코드가 아니다.

    agents/agent1/
      glossary/  용어집                          ← 사용자 최우선 입력 (§1)
      formats/   형식 (컴파일 산출물, §2.4)
      tasks/     reconcile_*.yaml                ← 비교 규칙 (§4.1)
      data/      samples/ (컴파일용) · golden/ (검증용)
      output/    {stem}.doc.json · *.reconcile.json

## 이 에이전트는 형식을 고르지 않는다 (SPEC §00)

예전에는 이 파일이 용어집·형식 파일 경로를 모듈 상수로 들고 직접 실었다. 그러면
에이전트마다 자기 형식을 고를 수 있고, 같은 `특정금전신탁` 문서가 agent1 과 agent6
에서 다르게 잘려도 아무도 그것을 막지 못한다. 지금은 이 파일에 자산 경로가 **없다.**
말할 수 있는 것은 doc_type 뿐이고, 무엇으로 처리할지는 `core/registry.yaml` 이 정한다.

    routed = router.route(path, doc_type=CONTRACT_TYPE)   # 경로를 넘길 자리가 없다

바꾸고 싶으면 등록부를 고쳐야 하고, 그 변경은 이 에이전트만이 아니라 모든 호출자에게
동시에 적용된다 — 그것이 "같은 doc_type 은 누가 불러도 같게 처리된다"의 실체다.
이 규율은 tests/architecture/test_no_bypass.py 가 코드로 지킨다.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

AGENT_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = AGENT_ROOT.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import fitness_gate, parse_adapter, reconcile, router, structurize  # noqa: E402
from core import glossary as glossary_mod                                     # noqa: E402

# --- 이 에이전트가 다루는 문서 유형 (등록부의 키) ----------------------------
CONTRACT_TYPE = "특정금전신탁"
PROSPECTUS_TYPE = "투자설명서"

TASK = AGENT_ROOT / "tasks" / "reconcile_trust_vs_prospectus.yaml"
OUTPUT = AGENT_ROOT / "output"


@dataclass
class Structured:
    """구조화 결과 — 문서와, 그것을 어떻게 처리했는지.

    router.Routed 를 이 에이전트의 그릇으로 옮긴 것이다. doc/fitness/parsed 는
    이관 전과 같은 필드이고(호출자를 깨지 않는다), route 는 "등록부의 어느 규칙으로
    처리됐는가"를 남기는 감사 정보다.
    """
    doc: structurize.Document
    fitness: fitness_gate.Fitness
    parsed: parse_adapter.ParseResult
    route: Optional[router.Route] = None

    @property
    def quarantined(self) -> bool:
        return not self.fitness.passed

    @property
    def doc_type(self) -> str:
        return self.route.doc_type if self.route else self.doc.doc_type

    @property
    def glossary(self) -> glossary_mod.Glossary:
        """범위 좁히기(scope)가 별칭을 펴는 데 쓴다.

        경로를 고르지 않는다 — 등록부가 이 doc_type 에 못박아 둔 용어집을 그대로
        받는다. 그래서 여기에는 '어느 파일이냐'는 선택지가 없다.
        """
        return glossary_of(self.doc_type)


@lru_cache(maxsize=8)
def glossary_of(doc_type: str) -> glossary_mod.Glossary:
    """등록부가 이 doc_type 에 지정한 용어집. 파일 경로는 호출자가 정하지 못한다.

    router 의 자산 적재기를 그대로 쓴다 — 형식·용어집·등록부 세 곳의 doc_type 이
    맞는지까지 거기서 확인하므로, 어긋난 자산을 이 에이전트가 조용히 쓰는 일이 없다.
    """
    return router.assets(router.load().get(doc_type))[0]


def _structurize(path: str | Path, doc_type: str, *,
                 strict: bool = False, label: str = "", **kw) -> Structured:
    """문서 하나를 등록부에 맡겨 구조화한다 — 이 파일의 유일한 진입점.

    배차 실패(미등록 유형·자산 없음)는 router.RoutingError 그대로 올려 보낸다.
    그 메시지는 이미 무엇을 어떻게 고치는지 말하고, 여기서 RuntimeError 로 바꾸면
    호출자가 종류별로 잡을 수 없게 된다.

    격리 판정은 strict 일 때만 한다. router.require() 와 같은 판정이지만
    (Routed.quarantined 를 그대로 쓴다) 예외는 여기서 만든다 — 코어는 이 문서가
    '계약서'인지 '설명서'인지 모르고, 이 에이전트의 강제 스위치가
    router.route() 가 아니라 allow_quarantined 이기 때문이다.
    """
    routed = router.route(path, doc_type, **kw)
    s = Structured(doc=routed.doc, fitness=routed.fitness, parsed=routed.parsed,
                   route=routed.route)
    if strict and s.quarantined:
        first = s.fitness.warnings[0] if s.fitness.warnings else ""
        raise RuntimeError(
            f"{label or Path(path).name}가 형식 '{routed.doc_type}' 과 "
            f"{s.fitness.score:.0%}만 부합해 격리됐습니다. {first} "
            "(allow_quarantined=True 로 강제할 수 있습니다)")
    return s


def structurize_contract(path: str | Path, **kw) -> Structured:
    """신탁계약서 → doc.json (런타임 국면, LLM 없음)."""
    return _structurize(path, CONTRACT_TYPE, label="계약서", **kw)


def structurize_prospectus(path: str | Path, **kw) -> Structured:
    """투자설명서 → doc.json."""
    return _structurize(path, PROSPECTUS_TYPE, label="투자설명서", **kw)


def save(structured: Structured, out: Optional[str | Path] = None) -> Path:
    p = Path(out) if out else OUTPUT / f"{Path(structured.parsed.path).stem}.doc.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(structured.doc.dump(), ensure_ascii=False, indent=2),
                 encoding="utf-8")
    return p


def verify(contract: str | Path, prospectus: str | Path,
           task_path: Optional[str | Path] = None,
           allow_quarantined: bool = False) -> tuple[reconcile.Report, Structured, Structured]:
    """계약서와 투자설명서를 대조한다 — 이 에이전트의 본체.

    게이트에 걸린 문서는 기본적으로 대조하지 않는다(§3.4 "확정하지 않고 격리").
    형식과 다른 문서를 그럴듯한 리포트로 내보내는 것이 가장 위험한 실패 모드다.
    """
    strict = not allow_quarantined
    src = _structurize(contract, CONTRACT_TYPE, strict=strict, label="계약서")
    tgt = _structurize(prospectus, PROSPECTUS_TYPE, strict=strict, label="투자설명서")

    task = reconcile.load_task(task_path or TASK)
    report = reconcile.run(src.doc, tgt.doc, task)
    return report, src, tgt
