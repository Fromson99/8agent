# GENOS 참조 연결·저장·재개 구현 결과

2026-10-03. 사용자의 “측정 없이 쭉 진행” 지시에 따라 R2 계획을 구현했다.
완료된 구조화/용어집을 재사용하는 기존 GENOS 실행기에서 새 `compact-v2`를 명시 선택한다.
작업 코드와 반입 패키지까지 완료했으며 GENOS 접근·배포·실제 성능 측정은 하지 않았다.

## 해결한 반복 작업

| 기존 비용 | 구현과 유지 계약 |
|---|---|
| 별표마다 모든 문서명 정규식 검사 | 빌드당 역방향 문자 색인. 문자 그대로의 이름·왼쪽 경계·공백·가장 긴 이름·등록 순서 동률을 보존 |
| 선언/등록 약칭마다 전체 약칭 검사 | 같은 문자 색인으로 교체. named/self/same/declared/registered 우선순위 유지 |
| 모든 source JSON/블록을 list와 dict로 보유 | 메타데이터 순회와 source별 지연 읽기. 본문 cache UTF-8 직렬화 8MiB/64항목, 큰 단일 source는 cache 제외 |
| 같은 블록 본문/해시를 인용마다 저장·계산 | hash별 reference_body와 작은 reference_payload. reference view로 원래 JSON 복원; 쓰기 trigger 지원 |
| source_block 전체 JSON 복원 후 버림 | 실제 필요한 block_id/unit_id/text/source hash 컬럼만 선택 |
| 큰 전체 navigation을 완성한 뒤 감사/서빙으로 복사 | runtime와 감사 DB를 처음부터 구분해 작성. occurrence는 처음부터 정수 키 |
| 문서당 연결 원장 행 리스트 누적 | 최대 2,048개씩 SQL 전달. 검증된 연결 확인용 조건부 색인 추가 |
| navigation 도중 실패하면 문서/참조 처음부터 재시작 | 문서 및 reference source의 완료 경계, 64개 단위 commit. 참조 목격 수·전역 근거·통계 완료 경계 |

일반 조문 이름 찾기의 기존 마지막 80자 규칙, 구/신 참조 해석 모드, 문서 중복 버전의
모호함과 미해결 판정, 원문 span/ID/대상/후보/감사 상태를 유지했다. 구조 내부 해석을 바꿔 속도를 얻지 않는다.
8MiB는 cache의 직렬화 크기 예산이다. Python 객체 오버헤드와 현재 처리 중인 단일 문서는 별도로 존재한다.

## 실행 연결과 새 산출물

`genos_reindex_runner.py build --serving --storage-profile compact-v2 --fulltext-granularity unit`
→ `genos_reindex_only.rebuild_serving` → `term_generation.build_generation`
→ `generation_build_steps.build`의 links/source/glossary/navigation/fulltext/verify 순서다.
새 실행기나 연구 후보를 제품 registry에서 자동 선택하는 경로를 추가하지 않았다.

완료 구조화와 선택 용어집/knowledge를 보존한 채 새 `serving/baseline`에 generation과 감사 자료를 만든다.
원문 source-v2, glossary-serving-v2는 이전 검증 계약을 유지한다. navigation은 v7/storage-v3이다.
reference는 읽기/쓰기 가능한 호환 view이며 승인 참조 적용도 새 세대에 반영할 수 있다.

**감사 v3는 구축 근거 4개 표의 논리적 전수 보존이다.** 과거 감사 v1/v2의 분리 전 전체 DB snapshot과
동일한 물리 계약이 아니다. 새 runtime DB·구축 audit DB·native source audit를 함께 보존한다.
원문, HELD/ACCEPTED 근거, 기존 스냅샷, 완료 세대를 삭제하거나 덮어쓰지 않았다.

입력·코드·범위가 같을 때만 중단 작업을 재개한다. 문서/참조 결과와 완료 표식을 함께 commit한다.
참조 source 안의 연속 인용 문맥은 하나의 처리 단위로 유지하며, 전역 위임/근거 결합은 완료 경계를 분리한다.
마지막 미완료 묶음은 다시 처리한다. NFS에서 무제한 안전하다고 인증한 것은 아니다.

## 실제 검증

- ADR-0633: 첫 후보 35 통과/4 실패, 기각. 공백 약칭 동률 및 scope-v2 함수 연결 오류와 테스트 FTS 파일명 오류를 보존했다.
- ADR-0634: 수정본 고정 후 핵심 계약 42개와 준비본 재사용/발행·참조 연결 11개 통과. 두 참조 모드의 기존 컴파일러 결과와 전체 논리 참조/목표/후보/역참조 행을 비교했다.
- 적용 후 실제 작업 경로: 관련 계약 60개, 기존 runtime 회귀 62개, compact-v2+unit FTS의 모의 v6 RAG 3개, 실제 반입 TXT 적용/재실행/배포 코드 게이트/롤백 2개, 합계 **127개 통과**.
- 로컬 프로세스 강제 종료 후 runtime/audit의 함께 복구되는 결과, 일반 예외 중단 후 문서·참조·근거·마무리 재개 결과를 새 구축과 비교했다.
- 완료 자료의 hash 보존, 코드/입력 변경 재개 거부, 공유 경로 발행 후 변조 거부, source scope와 참조 검토 쓰기를 확인했다.
- 제품 모델 호출은 모두 모의 transport. 외부/GENOS 모델 API 호출 0. 시간 benchmark는 하지 않았다.

새 모의 RAG 검사에서 기존 조 단위 fixture 응답을 단위 선택에 그대로 사용해 3개가 먼저 실패했다.
테스트 transport에 필수 `needs_search`와 제공된 읽기 범위 선택을 추가한 뒤 3개 통과했다.
제품 코드를 변경하거나 출력 검증을 완화하지 않았다. 두 로그를 모두 보존했다.

확장 검사에서 **기존 코드에서도 재현되는 실패 5개**는 남아 있다:
구 TermAgent mock의 open_session 부재 2개, 옛 schema 목록 기대 1개, 범위 밖 용어 기대 1개,
문서 이름별 순위 기대 1개다. 이번 저장/참조 수정의 신규 실패로 보지는 않지만 전체 저장소가 모두 통과한다고 보고하지 않는다.
격리 후보의 임시 코드 루트에 PIPELINE.json이 없어 실행되지 못했던 3개는 실제 작업 경로에서 모두 통과했다.
ADR graph의 기존 오류 7개도 그대로 남아 있다. 두 신규 ADR의 `validate --final`은 통과했다.

검증 원본: [실험 결정](../../../04_EXPERIMENTS/ADR/ADR-0634-genos-reference-build-repair/README.md),
[적용/백업/검사 기록](../../../09_ARTIFACTS/AUDITS/genos-reference-build-20261003/FINAL-VALIDATION.json).
제품 코드 10개 파일, 관련 엔진 manifest 36개와 PIPELINE의 해당 코드 hash를 갱신했다.
다른 코드·스키마·데이터의 기존 pin 차이를 새 값으로 일괄 덮어쓰지 않았다.

## 반입과 남은 현장 확인

[GENOS 실행 안내](../../../08_DEPLOYMENT/GENOS/handoffs/reference_build_20261003_r1/GENOS_REFERENCE_BUILD_GUIDE_UTF8.txt)의
ZIP/TXT는 기존 `~/DEV` 적용 방식이다. 반입 파일 72개와 미변경 의존성 739개를 검증한다.
기존 v6 R4 및 compact lifecycle R2 바이트에서 적용·재실행·코드 비교 게이트·롤백을 검사했다.
완료 입력 재사용 → 단위 FTS → 서빙 자산 검사 → 새 공유 경로 발행을 제공한다.

현장에서는 동일 코드 commit·Python·generation을 배포 게이트로 확인한 뒤 push/새 리비전/워크플로우 반영을 구분한다.
warmup과 근거 질문은 워크플로우 테스트 화면에서 확인한다. 기존 코드 리비전과 구 generation은 롤백용으로 보존한다.
현재 ACTIVE 포인터, GENOS CURRENT, Git push 및 코드서빙 리비전을 변경하지 않았다.

과거 사진의 navigation **9시간16분**에서 얼마나 단축되는지, 실제 NFS의 저널/잠금 복구,
내부 모델 응답·법률 품질·실제 데이터 전체 E2E는 미확인이다. 이전 합성 **6초** 수치를 전체 구축 시간으로 사용하지 않는다.
