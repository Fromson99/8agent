# E 근거 재읽기 오류와 실행 전 검증

후속 사용자 지시로 모델 호출 오류 전반의 수정 재요청을 추가했다.
현재 반입은 [PROPOSAL_RETRY 안내](GENOS_MODEL_PROPOSAL_RETRY_20260928.md)를 따른다.
이 문서의 EVIDENCE_READ ZIP·검증은 최초 수정 이력으로 보존한다.

## 현장 근거와 원인

2026-09-28 사용자 채팅 사진과 추가 터미널 사진에서 다음 오류를 확인했다.

```text
SOURCE_TOOL_ERROR: tool=read mode=n/a stage=execute
cause=ProposalError: E rehydration requires exact extent and no cursor duration_ms=361
```

추가 사진의 실행 경로는 `app.ask → pipeline → coordinator → stages.retrieve →
workflow_tiers_session.investigate → question_obligations.apply_turn →
workflow_tiers_session.apply_turn:223 → workflow_relations_tools.execute:427`이다.
`runtime.request.finished`에는 `answer_chars=0`, `http_status=500`이 기록됐다.
전체 요청은 약 299초였지만 읽기 실패는 361ms다. 이 기록으로 300초 HTTP 대기
제한을 원인으로 판정하지 않는다. 앞선 검색·모델 호출의 시간 분배는 미확인이다.
현장 배포 커밋·리비전·선택 generation도 사진만으로는 미확인이다.

`E`는 이미 저장한 정확한 원문 fragment다. `extent="exact", cursor=null`로만
재사용할 수 있다. 조문 전체·하위 구조·다음 원문 페이지는 원래 P/U 위치와 서버가
제공한 continuation으로 읽는다. 사진에는 실제 제안 인수가 없으므로 잘못된 extent와
cursor 중 어느 인수가 들어왔는지는 확정하지 않는다.

기존 실행 전 검증이 이 조건을 확인하지 않아 `ExplorationTools.read`에서
`ProposalError`가 발생했다. 실행기의 일반 예외 처리에서 이를 `ToolExecutionError`로
포장해 모델 수정 루프에 돌아가지 못하고 요청 전체를 HTTP 500으로 종료했다.

## 작업 코드 변경

`workflow_relations_tools.RelationsTools.validate_action`에서 요청 범위와 대상 해소를
검증한 다음, E 재읽기의 extent/cursor 조건을 실행 전에 확인한다. 부적합하면
`ProposalError`와 구체적인 수정 지침을 돌려준다. v5의 기존
`corrective_actions → WORKFLOW_REPAIR → investigate` 경로를 재사용하며 모델이
수정할 수 있는 `extent="exact", cursor=null` 행동을 제공한다. 같은 턴의 성공한
출처 선택은 보존한다. 직접 execute 호출은 `NOT_EXECUTED`를 남기며 재실행할 수 있다.

원문·범위·세대·해시·cursor 결속과 기존 read 내부 검증은 유지한다.
실제 SQL/저장소/handler 장애는 기존대로 요청을 실패시킨다. 모든 예외를 모델의
수정 가능한 오류로 바꾸지 않는다. 모델이 반복해서 잘못된 호출을 하면 기존 요청·
모델 예산에 따라 종료할 수 있으며 답변 성공을 보장하지 않는다.

런타임 변경은 파일 1개다. 이 파일을 결속한 엔진 manifest 20개와 PIPELINE 해시를
함께 갱신했다. 작업 코드 변경이며 로컬 활성 frozen 릴리스·CURRENT·데이터 세대는
변경하지 않았다. Git commit/push·GENOS 리비전 배포는 미실행이다.

## 로컬 확인

- 수정 전 모의 데이터에서 사진과 같은 ProposalError → SOURCE_TOOL_ERROR 경로 재현.
- v5/v4/v3 및 GENOS 채팅 브릿지 계약·회귀 158개 통과.
- subtree/article, E에 원래 위치의 유효 cursor를 붙인 호출, 기존 근거 보존,
  실패 행동 재실행, 실제 모델 호출 없는 모의 HTTP 요청의 수정 제안→재읽기→답변 확인.
- SQL/handler 오류가 계속 서버 실패로 반환되는 기존 회귀도 통과.
- 설치기 계약 8개 통과: 적용·재실행·원복·gate ZIP, 미지원/변조 파일 차단,
  중간 쓰기 실패 복구, 적용 이후 사용자 수정 보호.
- 등록된 실제 기준 코드와 pin을 격리 Git checkout에 복제해 최종 ZIP/TXT의
  적용·재실행·원복 확인. 바인딩 파일 186개, 원복 후 원래 바이트 일치.
- 전체 작업 엔진 26개와 참조 코드 152개 hash 불일치 0, `git diff --check` 통과.

설치 검증 영수증은
[installer-validation.json](../../../../09_ARTIFACTS/AUDITS/20260928-evidence-read-repair/installer-validation.json)에 있다.
외부 모델 호출·실제 내부 데이터 처리·현장 서버 연결은 수행하지 않았다.

## 현장 적용과 원복

[ZIP](../../../../08_DEPLOYMENT/GENOS/patches/GENOS_EVIDENCE_READ_20260928_R1.zip)과
[실행 TXT](../../../../08_DEPLOYMENT/GENOS/patches/GENOS_EVIDENCE_READ_20260928_R1_APPLY.txt)를
같은 폴더에 둔 뒤 기존 `~/DEV` Git checkout에 적용한다.

```bash
bash GENOS_EVIDENCE_READ_20260928_R1_APPLY.txt
```

TXT는 첫 단계부터 지속 로그와 종료 상태를 남긴다. 등록된 이전 파일 또는 이미 적용한
파일을 확인하고, 변경 전 파일·엔진 pin·PIPELINE을 백업한다. 다른 코드 drift는 쓰기
전에 차단한다. 데이터·CURRENT·용어집 캐시 receipt는 수정하지 않는다.

로그가 안내한 런타임 파일·변경 엔진 manifest·PIPELINE을 검토하고 commit한 뒤,
실제 코드서빙에서 선택한 generation 절대경로로 같은 checkout을 검증한다.

```bash
MODE=verify GENOS_GENERATION=/actual/selected/generation bash GENOS_EVIDENCE_READ_20260928_R1_APPLY.txt
```

gate를 통과한 commit을 push하고 코드서빙 새 리비전을 배포한다. 데이터 재구축,
워크플로우 Python 교체, 환경변수 변경은 필요 없다. 워크플로우 테스트 화면에서
실패한 질문을 다시 실행하고 답변 수신과 요청 ID·리비전을 확인한다. 내부 모델의
수정 제안 수용과 실제 질문 성공은 현장 확인 전까지 미확인이다.

원복은 적용 로그의 `BACKUP_READY` 경로를 사용한다.

```bash
MODE=rollback ROLLBACK_FROM=/actual/backup-directory bash GENOS_EVIDENCE_READ_20260928_R1_APPLY.txt
```

코드서빙도 이전 검증 리비전으로 복귀한다. 적용 후 사용자가 파일을 수정했으면
원복이 덮어쓰기를 거부한다.

ZIP SHA-256: `bb29cc4e879e05d34121fac95687cbe1b49da82e5e1ada7cb63fe54c02c923b0`

등록 기준 런타임 SHA-256: `d5c0a48be5f5486314abce33aa2a4a5afe9259d425cdcae450e5186ede98ce88`

수정 런타임 SHA-256: `328114c4394d980289c3c2fb7c9dfcce81a83bbd9128b5a60bfa9a72ec3630af`
