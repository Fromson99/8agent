# data/ — 서버가 쓰는 자리 (호스트 직접 실행)

`scripts/serve.sh` 가 `STRUCTURE_STORE=data/structure` 등 기본 경로를 준다. 화면에서
올린 문서·해석 산출·페이지 캐시·등록한 규칙·용어·벡터·간선이 **여기 그대로 쌓인다.**
전체 구조와 무엇이 git 에 있고 무엇이 없는지는 [docs/OPS_TRANSPORT.md](../docs/OPS_TRANSPORT.md)
"첫 반입" 절과 `scripts/data_ship.list`.

    data/structure/{doc_id}/
      result.json        구조 정본 — nodes·blocks·stats·fingerprint
      meta.json          이름·kind·시행일·부처·fingerprint·folder
      source.xml         law.go.kr 원문 (lawxml 문서)
      source.pdf         원본 또는 검수용 합성 지면
      pages/{N}@2.png    페이지 렌더 캐시 (재생성됨)
    data/embeddings/sections/   구역 벡터 (vectors.npz + meta.jsonl)
    data/glossary.json          용어
    data/delegation.json · law_index.json   조문 간선·문서 색인 (core.lawnet)
    data/rag/ · rules/ · frames/            판정 지문·규칙·프레임
    data/wiki/                  해석 지식 llm-wiki (git 추적)

경로를 바꾸려면 `STRUCTURE_STORE=/어딘가 scripts/serve.sh`.
