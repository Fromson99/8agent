"""운영 기본선에서 격리한 검색 실험 구현.

실험 코드는 운영 경로와 떨어져 있어야 하지만, 존재 자체가 숨겨져서는 안 된다.
``SPECS``는 UI·문서가 같은 이름과 상태를 읽는 작은 공개 레지스트리다. 새 모듈을
추가할 때 여기에도 한 줄을 더하며, 카탈로그는 등재되지 않은 ``*.py``도 누락으로
표시한다.
"""

SPECS = (
    {
        "key": "haiku_legal_methods",
        "title": "Haiku 법률 해석 방법론",
        "status": "진행 중",
        "decision": "운영 미배선",
        "purpose": "문언 연산자·규범 위계·삼단논법·반대규칙 탐색을 일반 방법론으로 비교",
        "module": "lawrag.core.rag.experiments.haiku_legal_methods",
        "runner": "scripts/rag_haiku_legal_methods_eval.py",
        "document": "",
        "artifact_patterns": ("haiku_legal_methods", "haiku-legal-methods"),
    },
    {
        "key": "legal_answer_repair",
        "title": "답변 최종 검증·교정",
        "status": "격리 실험",
        "decision": "운영 미배선",
        "purpose": "고정된 검색 근거와 초안을 문언 단위로 대조해 결론·조건·예외 오류를 교정",
        "module": "lawrag.core.rag.experiments.legal_answer_repair",
        "runner": "scripts/rag_legal_answer_repair_eval.py",
        "document": "docs/LEGAL_ANSWER_REPAIR_EXPERIMENT.md",
        "artifact_patterns": ("legal_answer_repair", "legal-answer-final-verifier-repair"),
    },
    {
        "key": "typed_assertion_shortcuts",
        "title": "ROLE:Concept Assertion Shortcut",
        "status": "기각",
        "decision": "재현 전용",
        "purpose": "질문 문자열 없이 canonical 역할 부품만으로 Assertion 직행 좌표를 재현",
        "module": "lawrag.core.rag.experiments.typed_assertion_shortcuts",
        "runner": "scripts/rag_legalclosure_typed_shortcut_eval.py",
        "document": "docs/adr/0022-legalclosure-v2-boundary-refactor.md",
        "artifact_patterns": ("typed_shortcut", "canonical-typed-assertion-shortcut"),
    },
)


def specs() -> list[dict]:
    """호출자가 레지스트리 상수를 바꾸지 못하도록 복사본을 반환한다."""
    return [{**row, "artifact_patterns": list(row.get("artifact_patterns") or ())}
            for row in SPECS]
