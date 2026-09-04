"""범용 모듈 — 문서 종류·에이전트와 무관한 부품 (SPEC v2).

진입점:              router (registry 를 보고 판별·배차 — 에이전트가 부르는 유일한 문 §00)
컴파일 국면 (LLM):  glossary → parse_adapter → term_marker → format_induce → holdout_check
런타임 국면 (결정론): parse_adapter → structurize → normalize → fitness_gate
태스크:              reconcile

에이전트는 이 부품들을 자기 자산(용어집·형식·태스크 규칙)과 조립할 뿐이고,
도메인 지식은 전부 에이전트 폴더의 데이터 파일에 있다.

**에이전트는 형식·용어집을 직접 싣지 않는다.** `router.route(파일, doc_type=...)` 만
부르고, 무엇으로 처리할지는 `lawrag/core/registry.yaml` 이 정한다. 같은 doc_type 이 호출자마다
다르게 처리되는 일을 코드로 막기 위해서다(lawrag/core/router.py 설명 참조).
"""
__all__ = ["router", "glossary", "parse_adapter", "term_marker", "format_model",
           "format_induce", "holdout_check", "structurize", "normalize", "fitness_gate",
           "reconcile"]
