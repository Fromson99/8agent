# 과거 계약 오류와 보존해야 할 설계 이유

이 목록은 2026-10-14 설계를 위한 근거 인덱스다. 사건 수·운영 빈도의 전수 집계가 아니다. 읽은 README·운영 기록·코드의 hash는 [EVIDENCE.json](EVIDENCE.json)에 남긴다. 완료된 ADR의 판정·원출력·오류를 수정하거나 재채점하지 않았다.

## 공급자와 전송 표현

| 사건 | 직접 읽은 근거 | 관측과 적용 한계 | 설계에 남긴 결정 |
|---|---|---|---|
| H01 | [ADR0453](../../../../04_EXPERIMENTS/ADR/ADR-0453-gemini-schema-400-diagnosis/README.md), [ADR0457](../../../../04_EXPERIMENTS/ADR/ADR-0457-portable-synthesis-schema/README.md) | Gemini의 동일 합성 요청에서 전송 표현에 따라 400 수락 여부가 달라졌다. 당시 후보·모델의 소표본이며 현재 GENOS 한도 증거가 아니다 | 긴 실제 ID와 짧은 wire ID 분리, 원래 서버 제약 유지 |
| H02 | [ADR0464](../../../../04_EXPERIMENTS/ADR/ADR-0464-genos-proxy-schema-repair/README.md) | 대리 클라이언트의 strict 미준수 이후 스키마 프롬프트 병기 스모크 성공. 해당 성공 실행에서는 repair가 발동하지 않음 | strict와 복구의 실제 검증을 구분. 프롬프트 병기를 모든 경로에 무조건 추가하지 않고 역할별 입력 비용과 지원을 검증 |
| H07a | [ADR0668](../../../../04_EXPERIMENTS/ADR/ADR-0668-selection-provider-anyof/README.md) | 배타 행동 anyOf로 해당 공개 질문 완료. 일반 스키마에서 oneOf와 anyOf가 항상 동등하다는 근거가 아님 | 행동 const의 배타성을 검사하고 완전한 대안 객체를 유지 |
| H07b | [ADR0669](../../../../04_EXPERIMENTS/ADR/ADR-0669-reference-complete-action-schema/README.md), [ADR0670](../../../../04_EXPERIMENTS/ADR/ADR-0670-public-provider-schema-adapter/README.md) | 참조 단계의 완전한 출력 구조 수정만으로 공급자 호출은 실패했고, 후속 uniqueItems 전송 변환에서 해당 단계 수락. 전체 API 재실행 결과와 구분 | provider 투영과 원래 schema 검증을 분리. 제거한 제약은 runtime에서 유지 |
| H13 | [ADR0727](../../../../04_EXPERIMENTS/ADR/ADR-0727-navigation-input-binding/README.md), [ADR0729](../../../../04_EXPERIMENTS/ADR/ADR-0729-compact-branch-choice-contract/README.md), [ADR0730](../../../../04_EXPERIMENTS/ADR/ADR-0730-compact-choice-public-qualification/README.md) | 스키마 공유·축소의 합성 통과와 실제 공개 검증은 달랐다. 0730은 동결 기준 미충족으로 미승격 | 문자 절감만으로 후보 채택 금지. 구조 축소는 실제 완료·토큰·의미 검증과 함께 비교 |

## 조사 판단과 근거

| 사건 | 직접 읽은 근거 | 관측과 설계 이유 | 설계에 남긴 결정 |
|---|---|---|---|
| H03/H04 | [ADR0661](../../../../04_EXPERIMENTS/ADR/ADR-0661-law-navigation-state-contract-probe/README.md), [ADR0663](../../../../04_EXPERIMENTS/ADR/ADR-0663-law-navigation-one-repair-probe/README.md) | 제외 이유를 가진 선택의 채택 문제가 출발점. 새 READ/DEFER 충돌은 수정 호출에서도 반복 | 읽기와 판단을 분리하고 이유·명시 상태·행동을 일치시킴. 보류 행을 일괄 삭제하지 않음 |
| H05 | [ADR0664](../../../../04_EXPERIMENTS/ADR/ADR-0664-law-navigation-patch-repair-probe/README.md), [ADR0676](../../../../04_EXPERIMENTS/ADR/ADR-0676-investigation-reinspection-repair/README.md), [현재 correction_schema](../../../../02_BACKEND/semantic_runtime/legal_agent/law_navigation.py) | partial 출력 복구 성공 뒤 행동/근거가 따로 교체되는 위험이 드러남. 현재 control 경로는 full decision을 사용 | 과거 성공을 근거로 sparse merge를 무조건 재도입하지 않음 |
| H06 | [ADR0665](../../../../04_EXPERIMENTS/ADR/ADR-0665-selection-tool-contract-fixes/README.md), [동결 설계](../../../../04_EXPERIMENTS/ADR/ADR-0665-selection-tool-contract-fixes/artifacts/design/frozen-design.json), [ADR0666](../../../../04_EXPERIMENTS/ADR/ADR-0666-selection-schema-provider-closure/README.md), [ADR0667](../../../../04_EXPERIMENTS/ADR/ADR-0667-selection-original-basis-closure/README.md) | 읽기 자동 채택, 법령 정렬, 불가능한 메뉴, branch 소유 근거 등 여러 결함을 수정. 합성 계약 통과만으로 실제 요청 완료에 도달하지 못한 이력 | guard·메뉴·동작 계약은 모두 보존하고 공급자 호환을 별도로 다룸 |
| H08 | [ADR0696](../../../../04_EXPERIMENTS/ADR/ADR-0696-structured-decision-wire-repair/README.md) | 본문 없는 메뉴의 DECIDE, 허용 근거의 중복 표기 요구를 수정 | 조건·예외·사실을 바꾸지 않는 정규화만 허용 |
| H12a | [ADR0702](../../../../04_EXPERIMENTS/ADR/ADR-0702-exception-state-wire-contract/README.md) | 예외 목록을 작성하면서 NOT_ESTABLISHED를 반복. 빈 목록을 예외 없음으로 추정하지 않음 | 예외 상태와 목록을 함께 제약하며 의미를 만들어 채우지 않음 |
| H12b | [ADR0746](../../../../04_EXPERIMENTS/ADR/ADR-0746-source-span-norm-contract/README.md), [현재 completion_v8](../../../../02_BACKEND/semantic_runtime/legal_agent/completion_v8.py) | source_quote 재작성 대신 source_ref로 정확 원문을 결속. 예전 v5~v7 history 보존 | 간결 출력의 기준 사례. 원문 의미·규범 역할의 미확인을 함께 유지 |
| H14 | [실패 복구 지침](../../OPERATIONS/AGENT_FAILURE_RECOVERY_POLICY.md), [ADR0774](../../../../04_EXPERIMENTS/ADR/ADR-0774-assessment-gap-action-main/README.md) | 현장 source gap/REQUEST_FACT 충돌과 좁은 자동 보정. MAIN60 반영은 전역 복구 완성 아님 | 기존 source gap 보정 유지. MISSING_FACT 의미 재분류는 별도 판단 |
| H15 | 이번 대화의 사진 1·2, [현재 validate](../../../../02_BACKEND/semantic_runtime/legal_agent/law_navigation.py), [현재 deduplicate_decision](../../../../02_BACKEND/semantic_runtime/legal_agent/request_repair.py) | 사진에서 두 원인이 같은 문구. 앞선 로컬 합성 재현은 같은 ID/다른 사유, 공백 사유 모두 schema 통과 뒤 ProposalError. 현장 원본과 버전은 미확정 | 오류를 분리·위치화하고 중복 생성 예방 후보를 검증. 완전 동일 항목 이외의 임의 합치기 금지 |

## 요청 수명과 실제 소비자

| 사건 | 직접 읽은 근거 | 관측과 설계 이유 | 설계에 남긴 결정 |
|---|---|---|---|
| H09a | [ADR0678](../../../../04_EXPERIMENTS/ADR/ADR-0678-investigation-contract-completion/README.md), [ADR0679](../../../../04_EXPERIMENTS/ADR/ADR-0679-investigation-completion-qualification/README.md) | HTTP200/length 오분류로 후보 거절. 후속에서도 최신 consumer 변경 미포함 때문에 직접 MAIN 적용 불가 | 완료·전송 분리와 최신 소비자를 포함한 같은 코드 검증 |
| H09b | [현장 스트림 사진 기록](../../../../09_ARTIFACTS/AUDITS/20261013-model-stream-photo/FINDINGS.json), [입력 계측 R1 원인 기록](../../../../08_DEPLOYMENT/GENOS/handoffs/model_input_metrics_20261014_r1/FINDINGS_UTF8.txt) | 종료 정보 부재와 출력 length의 별도 현장 사례. 컨텍스트 초과인지 단정할 수 없고 최종 실패 로그 누락도 존재 | 진단을 JSON 오류 하나로 합치지 않음. actual usage·종료·원장 연결 |
| H10/H11 | [MAIN50 27개 문제 계획](../MAIN50_CM51_REPAIR_IMPLEMENTATION_PLAN_20261009/PLAN.md), [ADR0718](../../../../04_EXPERIMENTS/ADR/ADR-0718-main50-request-repair-integration/README.md), [ADR0723](../../../../04_EXPERIMENTS/ADR/ADR-0723-source-target-recovery-complete/README.md), [ADR0724](../../../../04_EXPERIMENTS/ADR/ADR-0724-source-recovery-boundary-fix/README.md), [MAIN51 반영](../../../../04_EXPERIMENTS/ADR/ADR-0725-source-recovery-public-qualification/MAIN_RESULT.md) | stale retry, 동일 부족의 반복, 다른 조문으로 부재 처리, 부분 읽기 재개. 후속 실제 MAIN 연결 기록 존재 | 이미 통합된 정확 대상·원문 재사용·부분 재개를 회귀 기준으로 유지. 옛 계획을 아직 전부 미구현으로 설명하지 않음 |
| H17 | [BL-010](../../../BACKLOG.md), [ADR0679](../../../../04_EXPERIMENTS/ADR/ADR-0679-investigation-completion-qualification/README.md), 이번 대화의 이전 테스트 출력 | 구 fixture·SQL·consumer 기대 불일치와 실제 배선 누락 | 검사 실패를 삭제해 통과시키지 않고 보장할 사용자 동작을 현행 API에서 검사 |
| 보조 이력 | [ADR0593](../../../../04_EXPERIMENTS/ADR/ADR-0593-rag-chain-native-kind-repair/README.md), [ADR0594](../../../../04_EXPERIMENTS/ADR/ADR-0594-rag-chain-strict-contracts/README.md), [ADR0595](../../../../04_EXPERIMENTS/ADR/ADR-0595-rag-chain-command-repair/README.md), [ADR0601](../../../../04_EXPERIMENTS/ADR/ADR-0601-rag-chain-empty-state-guards/README.md), [ADR0606](../../../../04_EXPERIMENTS/ADR/ADR-0606-native-memory-command-verifier-repair/README.md) | 격리 chain의 단계·정정·이력 결속 오류, 초기 state 없음, 모델 호출 전 set 직렬화 실패. 현재 MAIN과 다른 프로토타입도 포함 | 모델 오류, runtime 코드 오류, 평가 runner 오류를 분리. 프로토타입 점수를 현재 서비스로 전용하지 않음 |

## AD와 구축

| 사건 | 직접 읽은 근거 | 관측과 적용 한계 | 설계에 남긴 결정 |
|---|---|---|---|
| H16a | [AD 요청 로그 R1](../../../../08_DEPLOYMENT/GENOS/handoffs/ad_request_logs_20261013_r1/GUIDE_UTF8.txt), [ad_model](../../../../02_BACKEND/semantic_runtime/ad_model.py), [ad_language](../../../../02_BACKEND/semantic_runtime/ad_language.py) | legal_agent에 있던 uniqueItems 전송 변환을 AD 공유 계약으로 연결한 이력. AD의 context 조회 loop는 schema repair loop가 아님 | 내부 모델 고정·명령 검증·SQL 트랜잭션 보존, 별도 owner와 총예산 |
| H16b | [ADR0389](../../../../04_EXPERIMENTS/ADR/ADR-0389-pdf-parent-template-schema/README.md), [recipe_runtime](../../../../02_BACKEND/lawrag/core/structure/recipe_runtime.py), [recipe_output](../../../../02_BACKEND/lawrag/core/structure/recipe_output.py) | 단순 parent-ID 형식으로 생성 문법을 바꿔도 최종 원문/구조 검수가 보류되는 사례. 현재 window review는 별도 owner | 원문·bbox·부모·cycle 검증 보존. RAG 완료 enum을 구축 승인 상태로 재사용하지 않음 |
| 현재 추가 경계 | [LLM](../../../../02_BACKEND/lawrag/core/llm.py), [genos_backend](../../../../02_BACKEND/semantic_runtime/genos_backend.py), [reference_resolution](../../../../02_BACKEND/lawrag/pipeline/reference_resolution.py) | 경로에 따라 schema prompt, structured output, 문법 fallback, gateway 사용이 다름. 파일명만으로 동일 적용을 가정할 수 없음 | P0에서 실제 선택 역할과 호출을 등록하고 숨은 physical call까지 집계 |

## 이번 코드 대조에서 확인한 선행 조건

- `unit_relations._navigate`의 후검증 교정과 `bounded_source_session.structured`의 gateway 설정을 함께 읽었다. 참조 선택은 법령 탐색의 repair 0 override에 포함되지 않는다. 이는 조건부 중첩 교정 가능성의 코드 근거이며 현장 호출 수 실측이 아니다.
- `NavigationReferences._map/schema`는 일반 객체 key를 변환하지 않는다. branch key 기반 후보를 도입하려면 `relations_repository.reserve_attempt`의 원장→wire 검증과 함께 codec을 바꿔야 한다.
- `workflow_tiers_policy.profile`은 알 수 없는 top-level key와 지원하지 않는 enum을 거절한다. 새 정책은 설정 파일만 추가해서 활성화할 수 없다.
- 현재 `model_contract.structured_value`와 gateway의 JSON 해석은 `json.loads`를 사용한다. 원시 중복 key 검사는 새 설계의 추가 경계이며 이번 현장 오류의 확인된 원인으로 주장하지 않는다.
- ADR0722 README에는 TODO가 남아 있다. 이를 완료된 qualification이나 승격 근거로 사용하지 않았다.

## 기록 보존과 다음 조사

이번에 읽은 문서의 역사적 수치를 합산해 현재 오류율을 만들지 않는다. 전체 빈도·원인 비중은 동일한 집계 정의와 현재 버전의 원장이 있어야 한다. 다음 P0에서 사건 목록을 완성할 때에는 읽은 자료, 읽지 못한 원본, 사진뿐인 사례, 미실행·실패한 검사도 각각 표시한다.

과거 결과를 다시 실행하거나 채점하는 작업은 새 ADR의 동결 조건을 따른다. 내부 CM·risk_cm의 질문·근거 후보를 외부 제품 context로 전송하지 않는다. 이번 설계의 일반적 교훈을 테스트하기 위해서는 공개 또는 명시적 합성 자료를 별도로 만든다.
