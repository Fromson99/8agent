# GENOS 완료 자료 재사용 경로의 적재·로딩·RAG 최적화 구현

2026-10-03. 작업 코드와 현장 실행 묶음까지 구현했다. GENOS에 연결하거나 배포하지 않았다.
공개 로컬 ACTIVE_RELEASE와 기존 완료 자료는 보존했다. 실제 내부 모델을 사용하는 전체 E2E와
현장 NFS 지연은 워크플로우 테스트 화면에서 추가로 확인해야 한다.

## 구현과 연결

기존 `genos_reindex_runner.py build --serving --storage-profile compact-v1 --fulltext-granularity unit`을 확장했다.
별도 중복 파이프라인을 만들지 않고 `rebuild_serving → term_generation.build_generation → generation_build_steps`
안에 단계별 입력·결속·checkpoint를 연결했다. prepared 원문/사전 및 명시된 완료 의미 검토본을 재사용하며
모델 호출은 0회다. 새 RAW 파싱·구조화 자체의 알고리즘과 내부 LLM 생성 속도는 이번 구현의 변경 범위가 아니다.

| 구간 | 바뀐 동작 | 보존하는 계약 |
|---|---|---|
| 입력 연결 | 연결표 생성 때 원문 DB 재복사 제거 | 입력 DB hash, 문서 범위, 사전/검토 결속 |
| 원문 저장 | v2 metadata document, text 중복을 줄인 block payload와 호환 view | native 전체 DB를 audit에 보존; unit, 원문 text, 버전, span |
| navigation | v6 내부 정수 occurrence key, 호환 ID view | term/source ID, 명시 참조, 미해결·후보 상태, 감사 색인 |
| 용어집 | serving-v2에 정의·라벨·lookup·identity·translations만 투영 | 전체 raw graph/원천을 별도 보존; 정의 ordinal/원문/출처 |
| 최초/반복 로딩 | 작은 서빙 DB, 준비된 cache 강제, stat가 같은 hash proof를 최대 128개 재사용 | drift 시 재검증/거부; 요청 범위와 권한 |
| RAG 원문 읽기 | 페이지 블록 묶음 SELECT, 검증도 묶음 읽기 | 순서·중복·누락 오류·정확한 인용 검사 |
| FTS 조회 | 허용 범위를 SQL에서 걸러 JSON 읽기 감소 | 동일 순위/동점 기준과 결과 |
| 요청 원장 | 핸들/커서를 메모리에 모아 결과 기록 전 짧은 transaction에서 반영 | FULL 동기화, 불변 로그, 중단 시 미노출, 검색·모델 호출 동안 쓰기 잠금 없음 |
| 구축 | 64문서 단위 commit, 완료 token forms의 제한된 재사용 | 어휘 결과 동일; 8MiB/256항목 제한, 큰 본문은 기존 chunker |
| 처리 규모 | 기본 16MiB 이하 입력 DB는 worker 1, 초과는 2 | 명시 worker override, 실제 PeCab 버전 고정 |
| 실패/재개 | links/source/glossary/navigation/fulltext별 hash checkpoint | 완료 파일 변조·입력/코드/설정 변경 시 재사용 거부 |
| 현장 설정 | GENOS_LLM_MAX_INPUT_BYTES를 실제 적용 | 선택 profile 및 내부 model binding; 과대 입력을 숨기지 않음 |

새 생성물은 `term-source-generation-v2`, `term-navigation-index-v6`, `term-navigation-storage-v2`,
`glossary-serving-v2`다. `source_block`/`occurrence`는 view이며 기존 외부 ID와 블록 내용이 유지된다.
`document.json`의 native nodes/blocks를 직접 소비하는 authoring 작업은 보존된 원본/감사 DB를 사용한다.
선택된 MAIN 계약과 활성 세대를 자동 교체하지 않는다. full_glossary compiler가 달라졌으므로
새 코드와 새 generation/cache를 함께 배포하고, 원복할 때도 이전 코드·세대를 쌍으로 사용한다.

## 실제 확인한 수치

아래는 모두 WSL의 합성 자료이며 GENOS 실측이 아니다. OS cache를 통제한 반복 p95가 아니다.
ADR0632의 시간은 이미 구조화된 합성 입력 161문서·3,381블록과 용어집 1,501노드를 이용한
연결·서빙 투영·navigation·article FTS 구축 구간만 측정했다. 짧은 반복 본문과 합성 사전
61개 용어를 사용했으며, RAW 파싱·구조화, 용어집 생성·의미 검토, 모델 호출, RAG 질의는
이 시간에 포함되지 않는다. 현장 인계 기본값인 unit FTS와도 설정이 다르다.
따라서 이전 안내의 “전체 구축 6.16초”는 전체 MAIN 또는 GENOS 전체 구축을 뜻하지 않으며,
그렇게 해석할 수 있는 표현을 아래와 같이 정정한다.

| 비교 | 이전 | 후보 |
|---|---:|---:|
| 원문 DB, ADR0629 | 9,629,696 B | 4,005,888 B |
| document metadata 읽기 대상 | 2,687,936 B | 5,568 B |
| occurrence 테이블/색인 | 143,360 B | 24,576 B |
| 서빙 용어집 bundle | 5,738,496 B | 339,968 B |
| 48개 블록 조회 SQL | 48회 | 1회 |
| 핸들 80개 durable commit | 80회 | 1회 |
| 구축 document commit, ADR0632 | 161회 | 3회 |
| 반복 어휘 tokenizer 호출 | 63회 | 7회 |
| 합성 완료 입력 → article FTS까지 서빙 구축, ADR0632 | 7.39초 | 6.16초 |

원문·navigation 각 논리 테이블·정의·원장·읽기 결과의 hash가 같다. source metadata에서는
명시적으로 제외한 native nodes/blocks를 감사 DB로 분리한 계약을 검사했다. article/unit FTS,
범위 차단, 중단 후 재개, 입력 변조, 정확 span, 실제 인계 스크립트의 재적용/변조 차단/원복을 검사했다.
최종 통합 검사 **216개 통과**, reference-scope-v2 별도 **6개 통과**.
최종 테스트 결과는 `09_ARTIFACTS/AUDITS/genos-compact-lifecycle-20261003/FINAL-CONTRACTS-R2.log`에 보존한다.

첫 저장 최적화만으로는 해당 합성 입력의 서빙 구축이 10.42→10.54초로 개선되지 않았다. 후속 ADR0630/0631의
“전체 구축 최소 10% 개선” 가설(각 합성 입력의 서빙 구축 범위)도 각각 약 3%/4.7% 개선으로 기각했다. 이를 사후 통과로 바꾸지 않았다.
ADR0632는 새 자료에서 디스크 기록·반복 계산 감소라는 별도 기준을 사전 고정해 채택했으며,
7.39→6.16초는 이 다른 합성 자료에서 관찰한 값이다. 실서비스 배수나 모든 병목 제거를 주장하지 않는다.

별도의 2026-10-02 GENOS 현장 기록에서는 navigation 단계만 33,384.2초(9시간16분24초),
전문 색인 시작 시점까지 누적 34,002.4초(9시간26분42초)가 걸린 뒤 실패했다.
이는 성공한 전체 구축 시간이 아니며, 위 로컬 합성 측정과 개선율을 계산할 수 없다.
[현장 시간 정정 근거](../../../../09_ARTIFACTS/AUDITS/20261002-navigation-timing-correction/receipt.json)를
보존하며, 최적화 적용 후 같은 완료 입력·설정으로 GENOS에서 측정한 결과는 아직 없다.

## 실행·검증·원복

[GENOS 실행 안내](../../../../08_DEPLOYMENT/GENOS/handoffs/compact_lifecycle_20261003_r2/GENOS_COMPACT_LIFECYCLE_GUIDE_UTF8.txt)에
정확한 환경, 완료 입력 선택, 코드 적용, 구축/재개, NFS 게시, Git/세대 게이트, 워크플로우 E2E, 원복을 연결했다.
68개 파일 패치와 741개 미변경 의존 hash를 대조한다. 키·DB·내부 질문은 ZIP에 포함하지 않는다.
기존 실행기와 PeCab 환경을 사용하며 실제 python3 경로·버전·단계 시간·실패 상태를 로그로 남긴다.

검증된 코드가 실제 배포되었다는 현장 receipt는 아직 없다. CURRENT/GENOS_GENERATION 변경,
Git push와 코드서빙 배포를 실행하지 않았다. 큰 원천 glossary 검증/최초 투영, FTS 계산,
내부 모델의 응답 지연, 과도한 법령 목록 prompt는 여전히 별도 비용이다. BYTE 제한 설정을
지키도록 고쳤지만 큰 법령 목록을 자동 축약해 품질이 바뀌는 변경은 넣지 않았다.

## 근거

- [ADR0629 저장·읽기](../../../../04_EXPERIMENTS/ADR/ADR-0629-genos-compact-lifecycle/README.md)
- [ADR0630 기각 기록](../../../../04_EXPERIMENTS/ADR/ADR-0630-genos-build-work-reduction/README.md)
- [ADR0631 기각 기록](../../../../04_EXPERIMENTS/ADR/ADR-0631-genos-adaptive-fulltext-build/README.md)
- [ADR0632 작업량 검증](../../../../04_EXPERIMENTS/ADR/ADR-0632-genos-build-io-contract/README.md)

이번 네 ADR의 final validator는 통과했다. 전체 graph는 이전부터 있던 7개 오류가 남아 있다.
선택된 legal/term 엔진의 파일 결속 불일치는 0개다. 비활성 legacy semantic 엔진의 기존 66개
불일치는 이번 변경 전부터 있었으며 임의로 고쳐 과거 상태를 덮지 않았다.
