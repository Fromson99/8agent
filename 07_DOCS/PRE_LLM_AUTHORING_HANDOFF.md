# 대량 LLM 전 작성 경로 인계 — 2026-09-05

## 결론과 실행 경계

207문서의 새 입력 스키마로 Graph·정의 저장소·lexical 인덱스·추출 배치 계획을
연결하고 hash로 고정했다. 실행은 오프라인 연구 후보/STAGING에서만 이루어졌다.
원본·MAIN·ACTIVE는 변경하지 않았으며 실제 LLM 호출과 신규 답변 성능 평가는 0이다.
신규 의미 READY 0은 기존 운영 DP 3,232건 삭제를 뜻하지 않는다.

## 확정 산출물

| 항목 | 위치·검증 |
|---|---|
| 입력 | `09_ARTIFACTS/STAGING/ADR-0197/inputs/source-set.lock.json`, 5,105 selected artifacts |
| Graph | `09_ARTIFACTS/STAGING/ADR-0202/run-002/derived/legal_graph`, `lgv1-08bfdb963dbed8e8b5e86aa3` |
| Graph 전체 검증 | 207문서, 341,969 StructuralUnit, 629,080 ClauseSpan; 2,554,813행/30 artifact, 오류·경고 0 |
| 정의 저장소 | `09_ARTIFACTS/STAGING/ADR-0204/derived/definitions`, `defv2-75a557647616358470d65608`; 명시적 reviewed-only empty, READY 0 |
| lexical | `09_ARTIFACTS/STAGING/ADR-0206/derived/lexical`, 54,537 entries (제목 50,886 + legacy 용어 3,651) |
| 계획 | `09_ARTIFACTS/STAGING/ADR-0204/extraction-batches.json`; 341,790 node jobs, 58,136 batches |
| 연결 | [작성용 binding](../09_ARTIFACTS/STAGING/ADR-0206/derived/runtime-binding.json); 각 component 경로와 SHA-256 |
| 격리 영수증 | [quarantine-receipt](../09_ARTIFACTS/STAGING/ADR-0206/quarantine-receipt.json); 원본 수정 없음 |
| 최종 검증 | [ADR-0206 run-001](../04_EXPERIMENTS/ADR/ADR-0206-input-snapshot-binding/artifacts/run-001.json), 24/24; 16.894초, 최대 RSS 1,328,128 KiB |

공통 입력 SourceSet SHA-256:
`ad951c434ab805ba7dacec2c1870539e45e55c734f102e23b94b369898f1b7b3`.
공통 authority generation:
`68e7b2eebe25f602fa802d2f24d5c66735172219e59b5cdcf3159879f600dd99`.

`authoring-input-content-snapshot-v1`은 release/MAIN 세대를 꾸며 넣지 않는다.
검증된 원본 bundle과 준비된 meta/result의 동일성, 보조 입력 hash, SourceSet, authority,
compiler revision을 묶고 캐시 fingerprint를 바꾼다. 운영 bootstrap에 등록된 객체가 아니다.
legacy 용어는 검색 입력일 뿐 새 의미 추출의 승인 근거나 법적 결론이 아니다.

## 추출 단위와 토큰 절감

조만 처리하지 않는다. 실제 조·항·호·목, 별표 및 기타 구조 family의 본문 소유 노드마다
작업을 만들고 같은 문서·조문·보안 경계 안에서 묶는다. 본문과 조상 문맥을 보존하며
조상 문맥은 context-only로 표시한다. 중복 문맥은 합치지만 원문을 잘라내지 않는다.
최대 24 node jobs / serialized request 24,000 characters이며 실측 최대 23,987자다.
이는 token·비용 상한이나 검증된 최적 batching을 뜻하지 않는다.

- 배정: 341,655 node jobs → 58,136 batches.
- 초과: 135 jobs → `REQUEST_REQUIRES_REVIEWED_SPLIT`.
- 소유권 문제: 56 source blocks → 원문/노드 경계 검토 필요.
- 배치 반출: 58,136건 모두 `EXPORT_DENIED`, `executable=false`.

해당 구조 package가 restricted/export=false인 것이 현재 차단 근거다. 법령처럼 보인다는
이유로 공개 정책을 추정해서 바꾸지 않는다. 공개 원문 계보와 권한자 승인으로 별도 입력
package를 만들면 새 SourceSet hash에 맞는 파생 binding과 계획을 다시 만들어야 한다.
정책을 변경한 뒤 기존 frozen plan만 수정해 실행하면 안 된다.

## 의미 승인과 RAG

LLM 출력은 `semantic-observation-v2`의 CANDIDATE다. source span, clause,
ALL/ANY 조건, 결과, 예외 대상·효과, 관계, provenance를 갖고 별도 검증을 받는다.
compiler는 외부의 검증 성공 boolean이나 모델의 APPROVE를 믿지 않고 trusted
source/provider/review store로 재검증한 뒤 `reviewed_semantics.json`을 만든다.
독립 validator도 다시 검증한다. UNKNOWN·미해결 관계는 Canonical 승인에서 제외한다.

기존 결정론적 관찰의 자동 ACCEPTED는 격리 compiler에서 제거했다.
v2 typed payload를 기존 v1 row type으로 가장하지 않는다. 검증된 v2 bundle도
runtime에는 범위와 문서 ACL에 묶인 근거로 전달하고 자동 법적 판단으로 실행하지 않는다.
용어 READY는 TERM_LOOKUP 전용이다. 비어 있는 reviewed DP의 실제 runtime 확인은
`NO_RULE_MATCH`이며, 기존 일반 RAG로 돌아가는 경계이지 의미 데이터 완성을 뜻하지 않는다.

## 아직 필요한 구현·판단

1. 135개 과대 작업의 검토된 분할 recipe와 56개 block의 실제 소유권 검토.
   텍스트/노드 변경이 필요하면 before/after와 수정 receipt를 만들고 재검증한다.
2. 실제 반출 대상 package·사용자 전송 범위·금액 상한 확정. 이전 CM 6건 승인은
   전체 원문/대량 추출 승인과 다르다.
3. 고정 가격·금액/호출/output-token 상한과 중단 복구를 연결한 유료 실행 CLI.
   기존 offline plan/immutable claim은 이 executor의 대체가 아니다. uncertain provider
   attempt를 자동 재호출하지 말고 기존 attempt/usage와 대조해야 한다.
4. host 소유 provider/review trust store와 reviewer 권한·폐기 운영 검증.
   사용자 요청 JSON을 그대로 trust store로 넘기지 않는다.
5. 작은 대표 조·항·호·목/조건·예외 표본 추출→사람 검토→확대→OOS 답변 평가.
   제품 모델은 `claude-haiku-4-5-20251001`; 새 score를 아직 측정하지 않았다.
6. release/ACL/cache/runtime/rollback 검증과 명시적 MAIN 승격; 실제 onsite/GenOS
   확인을 로컬 manifest만으로 완료 처리하지 않는다.

## 재현과 실패 이력

각 ADR README에 exact frozen candidate/revision/input hashes와 명령이 있다.
완료 run·staging은 덮어쓸 수 없다. 재실행은 새로 사전 동결한 run/ADR에서 한다.

- [ADR-0202](../04_EXPERIMENTS/ADR/ADR-0202-pre-llm-integration/README.md): 통합 compiler와 Graph 전체 생성·검증, empty-DP guard에서 중단.
- [ADR-0203](../04_EXPERIMENTS/ADR/ADR-0203-pre-llm-ready-bundle/README.md): 두 번째 empty-term guard 실패, 그대로 보존.
- [ADR-0204](../04_EXPERIMENTS/ADR/ADR-0204-empty-reviewed-ready/README.md): DP/runtime/batch 완료 후 Index snapshot 누락 실패, 그대로 보존.
- [ADR-0205](../04_EXPERIMENTS/ADR/ADR-0205-terminal-audit-receipts/README.md): 실패-only final 감사의 실제 영수증 검증 후보, 17/17. 활성 도구 세대 미변경.
- [ADR-0206](../04_EXPERIMENTS/ADR/ADR-0206-input-snapshot-binding/README.md): 검증된 작성용 snapshot과 인덱스 연결 완료, 24/24.

전체 이슈의 정본은 [KNOWN_GAPS](../00_SYSTEM/MIGRATION/KNOWN_GAPS.md)다.
