# 판단 오류 수정 기능의 MAIN 반영

2026-09-29 사용자 지시 `메인 파이프라인에 반영해줘`로 검증한 형식·판단 오류 수정 기능을
새 immutable 릴리스로 만들어 로컬 MAIN에 활성화했다.

- 릴리스: `legal-agent-structure-catalogue-pecab-repair-20260929-r1`
- 활성 포인터: generation31
- 이전 릴리스: `legal-agent-structure-catalogue-pecab-20260929-r1`, generation30
- 데이터: 기존 `pecab-only-public-main-20260929-v1/generation` 유지
- 사용자 지시 전환: `USER_DIRECTED_CUTOVER`, `quality_certified=false`

`service.py`가 활성 포인터의 코드·manifest를 검증한 뒤 해당 frozen Pipeline을 로드한다.
`ServingLegalAgent` → `BoundedSourceSession.structured` → `ModelGateway`에서 잘못된 JSON,
스키마, 질문 참조 충돌·누락·중복, 선별 후보·이유, 추천과 검색의 교차 필드 조건을 검증한다.
오류 내용과 이전 출력 일부를 같은 입력 view에서 재요청하고, 검증에 성공한 응답으로 진행한다.
기본 `max_schema_repairs=1`이며 원래 호출 예산·deadline을 사용한다. 정상 판단에는 추가 호출이 없다.
서버·통신·저장소 장애를 형식 오류로 재시도하지 않는다. 진행 표시에는 수정 상태를 전달한다.
세부 동작은 [판단 오류 수정 계약](MODEL_DECISION_REPAIR_20260929.md)을 따른다.

변경한 runtime 파일은 `bounded_source_session.py`, `gateway.py`, `progress.py` 3개다.
이에 결속한 엔진 manifest26개와 PIPELINE 해시를 함께 동결했다.
구조 원문 우선·문서 현황·PeCab·답변 SSE, 로컬 Gemma 공개 scope와 GENOS 내부 모델 설정을 유지한다.
실험의 Qwen 설정과 ADR0557 결과를 제품 설정이나 품질 통과 근거로 승격하지 않는다.

새 frozen 코드에서 오류 복구·MAIN 요청 분기 계약42개가 통과했다.
현재 로컬 서비스 진입점에서도 모의 잘못된 판단 → 오류 전달 → 수정 응답 → 답변 발행을 확인한다.
실제 외부 모델 호출은 없다. 기존 질문 배경 분리·초기 쟁점 병합 검사2개의 실패는
이전 frozen MAIN에서도 재현됐으며 미해결 상태를 보존한다. 이 전환은 법률 답변 품질 인증이 아니다.

활성화 권한, 이전 포인터, 원본 코드/해시 비교, frozen 검사, 실제 서비스 결속과 적용 영수증은
[MAIN 반영 감사](../../../../09_ARTIFACTS/AUDITS/20260929-model-decision-repair-main)에 둔다.
기존 릴리스와 activation receipt를 보존해 이전 PeCab 코드·데이터 쌍으로 복구할 수 있다.
일반 rollback은 저장소의 `semantic_runtime.control rollback --confirm-main` 절차를 따른다.
동시 작업의 이후 코드·포인터를 임의로 덮어쓰지 않는다.

Git main 브랜치 병합·GENOS 코드서빙 리비전 배포는 이번 로컬 MAIN 활성화와 별도다.
GENOS에 직접 접속하거나 내부 모델을 호출하지 않았다. 현장에 반영하려면 새 작업 코드와
엔진 pin을 함께 배포해야 하며 현장 질문·SSE 확인은 워크플로우 테스트 화면에서 한다.
이 기능 자체는 데이터 재구축이나 워크플로우 Python 교체를 요구하지 않는다.

## 현장 사진에 맞춘 후속 인계

R1 적용 메일은 통합판의 bounded 파일을 기준으로 했고, 현장 사진의 프롬프트 정리·SSE·진행
표시 조합에서는 첫 파일 해시 검사로 중단했다. 소스 변경 전 실패다. 해당 세 파일의 정확한
보관 바이트를 확인해 오류 수정만 함수 단위로 적용하는 R2 ZIP/TXT를 별도로 발송했다.
다른 코드 메일의 대체 선택 적용기와 실제 검증 범위는
[사진 기준 인계·메일 호환성](GENOS_SELECTIVE_MAIL_COMPATIBILITY_20260929.md)을 따른다.
기존 R1·frozen 릴리스·MAIN 포인터와 완료된 기록은 변경하지 않는다.
