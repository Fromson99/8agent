# 단계 계약

현행 계약과 소비자는 [DATA_MODEL.md](DATA_MODEL.md)와 [ARCHITECTURE.md](ARCHITECTURE.md)를 따른다.
`PIPELINE.json`의 활성 엔진은 `term_runtime/1.0.0`이고, 런타임 스키마는 `term-runtime-v1` 하나다.
기존 legal-semantic, rag-stage, semantic-storage, 의미 피드백 스키마는 과거 산출물 해석용으로만 보존한다.
신규 데이터 생성과 RAG는 이 파일들을 읽지 않는다.
