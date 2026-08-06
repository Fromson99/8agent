"""구조 해석기 — 범용 계층구조 인식 엔진 (SPEC: `docs/structure_interpreter_SPEC.md`).

    from core import parse_adapter
    from core.structure import pipeline
    from core.structure.model import Block

    parsed = parse_adapter.parse("계약서.pdf")
    result = pipeline.interpret(Block.from_elements(parsed.elements), doc="계약서.pdf")

## 구성 (SPEC §1.1 세 role = 파이프라인 세 단계)

    proposers/      제안자        S0  text → 후보[]              레벨 의미 0
    guards/         국소 가드      S1  후보 → score (방향 있는 점수)
    global_outer/   전역 바깥      S2  family 집합 → 레벨 사다리
    global_inner/   전역 안쪽      S3  후보집합 + 컨텍스트 → 트리
    dp.py           S3 DP (Viterbi)
    fingerprint.py  S5 재현 판정 / 저장 분기
    scoring.py      §5 수치 — 파이프라인 전체가 여기에 매달린다
    registry.py     관리소 — 신호를 role 로 등록만
    pipeline.py     core 파이프라인 (고정)

**core 파이프라인은 고정, 신호는 plug-in.** 새 신호 추가 = 파일 떨궈 등록,
파이프라인 코드 불변.

## 어휘에 없는 것

`level`. 용어집은 "마커가 어떻게 생겼나" 만 담고 "몇 번째 레벨이냐" 는 담지 않는다
(§0, §6). 레벨은 문서가 유도하고 그 문서의 StructureResult 에 저장된다.
관리소가 등록 시점에 그것을 검사한다.
"""

from core.structure import (dp, fingerprint, guards, global_inner, global_outer,
                            lexicon, model, pipeline, proposers, registry, scoring)
from core.structure.model import (Block, Candidate, Fingerprint, Ladder, Node,
                                  ScopeStack, StructureResult)

__all__ = [
    "dp", "fingerprint", "guards", "global_inner", "global_outer", "lexicon",
    "model", "pipeline", "proposers", "registry", "scoring",
    "Block", "Candidate", "Fingerprint", "Ladder", "Node", "ScopeStack",
    "StructureResult",
]
