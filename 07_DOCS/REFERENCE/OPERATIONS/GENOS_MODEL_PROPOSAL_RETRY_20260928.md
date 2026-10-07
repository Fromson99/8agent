# 모델 호출 오류를 수정 요청으로 반환

2026-09-28 사용자 지시: 비슷한 모델 호출 문제가 발생하면 요청을 바로 중단하지 않고,
오류를 전달해 원래 질문에 다시 응답하도록 한다.

사진의 E 재읽기 오류와 현장 실행 경로는
[원인 기록](GENOS_EVIDENCE_READ_REPAIR_20260928.md)을 따른다.
이 후속 변경은 해당 EVIDENCE_READ 인계본을 포함하고 대체한다. 기존 ZIP/검증 기록은
보존하며 현재 반입에는 아래 PROPOSAL_RETRY ZIP/TXT를 사용한다.

## 동작

모델의 도구 대상·범위·커서·관계 선택이 부적합하면 실행 전 검증에서 거절하고
기존 `WORKFLOW_REPAIR`로 돌아간다. 원문 구조를 실제 해소한 뒤 도구 handler에서
판명한 `ProposalError`도 서버 500으로 포장하지 않고 같은 수정 경로로 돌려준다.

모델에 전달하는 수정 요청:

```text
Please respond again to the original question.
Correct only rejected operations using this view.
Successful source choices remain stored.
```

구조화 오류에는 실제 제안·거절 이유·가능한 수정 행동을 포함한다. 실행 중 거절에는
`error_code`, `recoverable=true`, `retry_instruction`을 기록한다. 행동 원장은
`NOT_EXECUTED`로 끝내고, 거절된 결과를 성공한 관측이나 인용 가능한 근거로 저장하지 않는다.
같은 턴의 성공한 출처 선택·독립 행동은 보존한다. 수정한 새 행동은 새 action ID로
실행하고, 거절된 action ID를 그대로 재전송하면 기존 거절 영수증을 반환한다.

기존 JSON/응답 스키마 오류는 gateway의 형식 보정 재요청을 계속 사용한다.
요청 deadline·모델/도구 예산·동일 오류 반복 제한도 유지한다. 이를 소진하면
수정 미완료 한계를 남긴다. 실제 SQL·저장소·해시/세대·계약·통신 장애는 이 정책으로
모델 호출 실수로 바꾸지 않는다. handler 밖의 cache/근거 원장 검증도 그대로 유지한다.

## 변경과 검증

변경 파일은 `workflow_relations_tools.py`, `workflow_tiers_session.py` 두 개다.
해당 파일을 결속한 엔진 manifest 20개와 PIPELINE 해시를 갱신했다.
데이터·CURRENT·로컬 frozen 릴리스는 변경하지 않았다.

로컬 모의 데이터 검증:

- v5/v4/v3·GENOS 채팅 브릿지 회귀 169개 통과. 고정 코드에서 168개 통과 후,
  복사본에 누락된 기존 ACTIVE_RELEASE 포인터를 읽는 검사 1개는 포인터를 복사해
  별도 재실행하고 통과했다. 제품 데이터나 활성 포인터의 값은 변경하지 않았다.
- 실행 전 E 인수 검증, handler에서 뒤늦게 거절한 read/locate/follow_relations,
  거절 영수증 재실행·수정 행동 실행·기존 근거 보존을 확인한다.
- 모의 HTTP 요청에서 채택 출처를 보존하고 모델에 오류·수정 행동을 전달한 뒤,
  수정 응답→원문 재읽기→최종 답변까지 확인한다.
- 실제 SQL/handler 장애가 기존대로 서버 실패가 되는 회귀도 확인한다.
- 설치기 계약 8개 및 등록된 실제 기준 코드 두 종류의 최종 ZIP/TXT
  적용·재실행·원복을 확인했다. 기준은 EVIDENCE_READ 적용 전/후다.

회귀 검사 중 공유 작업 공간의 별도 `observability.py` 변경으로 엔진 hash가
불일치했다. 해당 변경을 덮어쓰거나 검증을 해제하지 않고, 기존 검증 코드와 변경한
두 파일을 고정한 별도 코드 루트에서 다시 검사했다. 작업 코드의 두 파일과
인계 payload가 이 고정 코드의 바이트와 같음을 확인한다. 결과·검증 코드 루트는
[검증 영수증](../../../../09_ARTIFACTS/AUDITS/20260928-proposal-retry/validation.json),
[설치 영수증](../../../../09_ARTIFACTS/AUDITS/20260928-proposal-retry/installer-validation.json)에 남긴다.

GENOS 내부 모델·실제 내부 자료·현장 서버 연결은 실행하지 않았다. 현장 선택
generation/manifest, 배포 commit·리비전과 질문 성공은 아직 미확인이다.

## 반입·배포·원복

[ZIP](../../../../08_DEPLOYMENT/GENOS/patches/GENOS_PROPOSAL_RETRY_20260928_R1.zip)과
[적용 TXT](../../../../08_DEPLOYMENT/GENOS/patches/GENOS_PROPOSAL_RETRY_20260928_R1_APPLY.txt)를
같은 폴더에 둔다. 기존 `~/DEV` Git checkout에 백업 후 적용한다.

```bash
bash GENOS_PROPOSAL_RETRY_20260928_R1_APPLY.txt
```

등록한 기준 파일만 받으며 미지원 코드·다른 코드 drift는 쓰기 전에 거절한다.
지속 로그·실패 상태·백업/적용 영수증과 적용된 코드 ZIP을 만든다. 재실행하면
이미 적용된 바이트와 pin을 확인한다. 두 런타임 파일과 갱신된 엔진 manifest,
PIPELINE을 검토하고 commit한 뒤 실제 선택 generation으로 같은 checkout을 검증한다.

```bash
MODE=verify GENOS_GENERATION=/actual/selected/generation bash GENOS_PROPOSAL_RETRY_20260928_R1_APPLY.txt
```

통과한 commit을 push하고 그 commit의 새 코드서빙 리비전을 배포한다.
데이터 재구축·워크플로우 Python 교체·환경변수 변경은 필요 없다.
질문 검증은 워크플로우 테스트 화면에서만 한다. 실패한 질문을 다시 실행해
요청 ID·리비전·답변과 오류 수정 기록을 확인한다.

```bash
MODE=rollback ROLLBACK_FROM=/actual/backup-directory bash GENOS_PROPOSAL_RETRY_20260928_R1_APPLY.txt
```

원복 후 이전 검증 코드서빙 리비전으로 복귀한다. 적용 이후 사용자 수정은 덮어쓰지 않는다.

ZIP SHA-256: `9ae3f226d9e0d133a32f436fe532242e287cdf2444bde5a4d6b8b16c849cfd04`
