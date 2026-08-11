"""용어층 컴파일 국면 — 문서에서 용어를 낳는 파이프라인 (ontology_kg §3).

    transcribe   Tier 1: 저자가 이미 만들어 둔 정의 구조물의 전사 (정규식, LLM 0)
    (Phase 1 예정) candidates/stats/embed/judge/gate — 통계 깔때기 + LLM 배치 판정

여기 코드는 **컴파일 국면 전용**이다. 질의·검색 런타임(core/rag)은 이 패키지의
산출물(data 의 glossary.json)만 읽고, 이 패키지를 import 하지 않는다 —
특히 임베딩(Phase 1)은 절대 검색 경로에 들어가지 않는다.
"""
