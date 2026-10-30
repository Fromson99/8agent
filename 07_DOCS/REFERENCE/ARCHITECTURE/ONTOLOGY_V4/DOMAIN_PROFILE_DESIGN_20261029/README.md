# 도메인 설정·업무 설정·실험 계획의 비활성 설계 예시

**2026-10-29 작업 코드 구현:** [사용 안내](../../../OPERATIONS/DOMAIN_PROFILE_WORKFLOW_20261029.txt) · [구현·검증 결과](../../../../../09_ARTIFACTS/AUDITS/20261029-domain-profile-implementation/구현과_검증결과.txt). 아래 파일은 비활성 설계 원본으로 보존한다. 제품 템플릿은 `00_SYSTEM/ONTOLOGY_PROFILES/`에 별도로 두며, 실모델 E1/E2·MAIN 승격·현장 배포는 미수행이다.

[전체 구현·실험 설계](../DOMAIN_PROFILE_IMPLEMENTATION_PLAN_20261029.md)의 부속 데이터다. 제품 설정 위치에 등록하지 않았고 runtime_enabled는 false다. 프로필 생성기·LLM 구조화기·새 컴파일러·실험 runner는 이 파일로 구현된 것이 아니다.

| 파일 | 역할 |
|---|---|
| [domain-profile.example.json](domain-profile.example.json) | 법률 기본 틀: 의미 유형·typed slot·관계·검토·조립 목적 |
| [domain-profile.design.schema.json](domain-profile.design.schema.json) | 위 설계 예시의 JSON Schema. 문법 검증용이며 의미 정답을 판정하지 않음 |
| [business-profile.example.json](business-profile.example.json) | 기본 틀의 exact hash를 고정한 업무별 선택. 용어·정의를 복제하지 않음 |
| [business-profile.design.schema.json](business-profile.design.schema.json) | 업무별 선택 예시의 JSON Schema |
| [experiment-plan.example.json](experiment-plan.example.json) | ADR 예약·입력/코드/판정 동결 전에 검토할 실험 설계. 실행 결과 아님 |

프로필의 required_review_slots는 검토해야 할 필드다. 원본에 없으면 NOT_RECORDED 등 해당 상태를 남기고 값을 만들어 넣지 않는다. `PRESENT` 값의 원본 연결, 조건부 타입, enum, 관계 및 원문 지지는 실제 구현의 검증 계획에 따른다. 등록 연산자 이름은 제안이며 현재 실행 가능하다는 뜻이 아니다.

업무 예시의 selected_concept_refs가 비어 있는 이유는 실제 용어집 ID를 임의로 선택하지 않았기 때문이다. 업무 생성 시 인증된 작업의 glossary snapshot을 조회해 참조한다. glossary 선택·문서 범위·형식 설명은 권한을 늘리거나 공통 검증을 완화할 수 없다.

기본 프로필 파일을 바꾸면 업무 프로필의 부모 hash도 새 검토 판본으로 갱신해야 한다. 이 예시의 부모 hash는 저장된 파일 byte의 SHA256이며, 운영에서 사용할 canonical JSON hash 규약은 제품 계약에서 별도로 고정한다.
