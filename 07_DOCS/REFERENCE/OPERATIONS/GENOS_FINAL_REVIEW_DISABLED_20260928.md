# v5 최종 답변 검토 기본 비활성화

2026-09-28 사용자 지시: 최종 답변 검토를 일단 기본 경로에서 제외한다.
현재 MAIN 작업 코드의 일반 수정이며 모델 효과 비교·품질 인증 실험은 수행하지 않는다.

## 배선과 동작

`service.py` 또는 기존 Pipeline/Coordinator → `ServingLegalAgent` →
`ObligationSession` / `BoundedSourceSession` → 기존 answer 단계에 적용한다.

- `workflow_tiers_policy.DEFAULT_PROFILE`과 `00_SYSTEM/LEGAL_AGENT/profile-tools-v5.json`에
  `final_review_enabled=false`를 설정한다. 필드가 없는 v5 프로필도 기본 false이며
  기존 GENOS 환경 모델 결속에 그대로 적용된다. 새 환경변수는 필요 없다.
- 작성 결과를 commit한 뒤 review view와 `ReviewDecision` LLM 호출을 만들지 않는다.
  해당 검토의 JSON 형식 보정·transport 재시도·재검토·반박 호출도 발생하지 않는다.
- 원문 회수·선별·누락 복구·질문 요구 정리와 작성의 형식 보정은 기존 경로를 따른다.
  출처 선별의 `source-omission-review`는 답변 검토와 다른 단계이며 유지한다.
- 작성된 모든 현재 claim을 반환한다. 검토 생략만으로 원문별·질문 요구별
  “최종 대조 미완료” 문구를 생성하지 않는다. 실제 작성 한계는 `확인 한계`에 표시한다.
- 원장에 `FINAL_REVIEW_SKIPPED`와 작성 claim 버전을 남긴다. 응답 receipt는
  `final_review_policy=disabled`, `final_review_status=SKIPPED`,
  `claim_review_status=UNREVIEWED`, `quality_certified=false`다.
  질문 요구 검토는 OPEN이며 검토 통과·법률 의미 품질 인증으로 처리하지 않는다.
- `final_review_enabled=true`를 명시한 v5 프로필에서는 기존 독립 검토와 advisory
  출력 경로를 사용할 수 있다. v1~v4는 기존 검토 기본값을 유지한다.

원문·선택 근거·제시 영수증·좌표·접근 범위·세대·해시·질문 요구 참조 검증은
기존 작성 commit과 출처 발행 경로에서 수행한다. 출력 스키마와 데이터는 변경하지 않는다.
변경 파일을 소비하는 현재 엔진 manifest와 PIPELINE의 엔진·프로필 해시를 다시 결속한다.
완료된 실험·고정 코드 세대·릴리스·활성 포인터는 수정하지 않는다.

## 검증과 실행 상태

모의 응답으로 기본값·명시 활성화·GENOS 환경 프로필·도구 탐색/회수 양쪽의
질문→작성→반환 연결을 검사한다. 기본 경로에서 review 물리 호출이 없고 작성 문장과
출처·실제 한계가 보존되는지, 검토 생략이 통과로 기록되지 않는지 확인한다.
기존 검토·번호 매핑·프롬프트·서빙·구 v3/v4 계약도 회귀 검사한다.
실제 모델 품질·GENOS 지연은 측정하지 않는다.

로컬 확인 결과: 계약·회귀 검사 **312개 통과**. 기본/명시 활성화 v5, 번호 매핑,
답변·출처 반환, GENOS 환경 결속·팀 범위·워크플로우 SSE, 구 v3/v4와 실패 경로를 포함한다.
현재 엔진 manifest 26개·고유 결속 파일 178개와 MAIN v5 프로필 결속을 검증했고,
코드/manifest/schema 해시 불일치 0건, 기존 데이터 pin 6개 일치, Python 3.11 문법과
`git diff --check` 통과를 확인했다. 처음 실행의 bounded 모의 문장 기대값과 기존
워크플로우 테스트의 JSON 모의 응답을 각각 실제 작성 문장·현재 SSE 계약에 맞춰 수정했다.
최종 통과 결과는 수정 뒤 실행한 검사다. 기존 TestClient/httpx 사용 중단 예정 경고
1건은 이 변경과 무관하며 테스트 실패는 아니다.

이 변경은 MAIN 작업 코드까지다. 로컬 활성 frozen 릴리스에는 자동 적용되지 않는다.
GENOS에서는 변경 코드로 새 코드서빙 리비전을 배포한 뒤 워크플로우 테스트 화면의
새 질문으로 확인해야 한다. 데이터 재구축과 워크플로우 Python 수정은 필요 없다.
현재 세션에서 GENOS 반입·Git push·코드서빙 리비전 배포는 수행하지 않았다.

부분 패치 인계본은 `08_DEPLOYMENT/GENOS/patches/GENOS_FINAL_REVIEW_OFF_20260928_R1.zip`과
같은 이름의 `_APPLY.txt`다. 코드·설정 5개만 백업 적용하고 설치된 엔진·프로필 pin을
갱신한다. 전체 코드 ZIP은 전달하지 않는다. 별도 모의 Git checkout에서 TXT의
check·apply·재실행·commit 후 코드 ZIP gate·원복과 미지원 코드의 적용 전 거부를
확인했다. 상세 영수증은 `final_review_disabled_20260928_r1/LOCAL_VALIDATION.json`에 보존한다.

## 복구

명시 v5 프로필에 `final_review_enabled=true`를 설정하고 해당 파일을 소비하는
engine/PIPELINE 프로필 해시를 함께 다시 결속해 기존 검토를 활성화할 수 있다.
전체 수정 원복 시에도 코드·설정과 engine/PIPELINE 해시를 함께 복구한다.
GENOS 리비전 변경 및 현장 실행 확인, 로컬 활성 릴리스 교체는 각각 별도다.
