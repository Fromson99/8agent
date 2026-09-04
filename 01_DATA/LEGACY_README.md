# data/ — 서버가 쓰는 자리 (호스트 직접 실행)

## 세 층 — 무엇이 원본이고 무엇을 다시 만들 수 있는가 (2026-08-19)

| 층 | 어디 | 성질 | 잃으면 |
|---|---|---|---|
| **raw (원본)** | `data/corpus/<출처>/` + 출처별 `manifest.json` | 불변. 수집기·업로드·inbox·손 반입 전부 여기 한 번 | 못 만든다 — 다시 수집·반입해야 |
| 파생 | `data/structure/` `embeddings/` `frames/` `glossary.json` `delegation.json` `links.json` `law_index.json` | raw 에서 규칙·모델로 다시 만든다 (배치 `/pipeline/`) | 다시 만들면 된다 |
| 큐레이션 (사람) | `data/rules/` `rag/candidates.json·verdicts` `rag/scopes.yml` `structure_fixes.json` `glossary.json` 의 승인 상태 `wiki/wiki/` | 사람의 승인·정의·편집 | 못 만든다 |

**raw 의 규약 — 출처마다 manifest 한 줄이 곧 등록이다.** 항목의 최소 칸:
`source · name · kind · status(ok) · body_file(저장소 뿌리 상대) · body_sha256 · body_format · collected_at`
(+ enforce/revised/folder/series 등 출처가 아는 것). 구조 스토어의 doc_id 가 **본문 sha256 앞
16자리**라 이름 없이 이어진다 — 계보 원장(`/lineage`)과 배치 라인업(`/pipeline/`)이 이 키로
"수집됐는데 구조화 안 됨"을 센다. 출처 폴더:

    corpus/law · krx · kofia        수집기(collect) — 법령 XML·위임 XML·조문 HTML·HWP
    corpus/expc · fsc · prec · moleg 해석례·회신·판례 원문 (phase_model — 위키 raw 로 간다)
    corpus/forms                    KRX 서식·상장협 표준정관 (손 반입, 옛 from_samsung/)
    corpus/internal                 내규 docx (+ 검토요청서) — series/version/status_label
    corpus/uploads/<YYYY-MM>/        화면·inbox 로 올린 원본 사본 — 구조화 문(core.ingest)이 자동 등록

손으로 둔 파일을 등록하려면 `lawrag.core.rawstore.register_files(...)` (옮기고 manifest 생성),
전체 합본은 `python scripts/merge_manifests.py` → `corpus/manifest.json`.


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
