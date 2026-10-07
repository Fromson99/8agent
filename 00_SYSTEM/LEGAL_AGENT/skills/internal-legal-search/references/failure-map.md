# 실패 기록과 설계 출처

2026-09-22 읽기 전용 종합. 아래 기록은 서로 다른 날짜·코드·모델·조건의 결과이며 합산 정확도를 계산하지 않는다. 과거 관측을 현행 v5의 동일한 결함으로 단정하지 않는다. 사례별 정답·원문을 런타임 스킬에 복사하지 않았다.

## 내부 실패 → 반영 규칙

| 기록 | 확인된 실패·한계 | 최종 스킬 반영 | 남는 책임·상태 |
|---|---|---|---|
| [ADR0428](../../../../../04_EXPERIMENTS/ADR/ADR-0428-reverse-match-structural-path/README.md) | 당시 핵심 원문 후보 75/75, 초기 8개 보유 후 21/75. 구조 우선 정렬로 본문 후보 소실 | 역매칭 유지, 구조/본문 함께 보고 관련 원문 읽기 | 과거 8개 제한 결과. 현재 v5에도 동일 수치를 적용하지 않음. 순위는 서버 개선 대상 |
| [ADR0474 감사](../../../../../07_DOCS/REFERENCE/REPORTS/ADR-0474_PHASE0_TRAJECTORY_AUDIT_20260920.md) | 새 경로에서 결정 조문 노출 4/12, 읽기 2/12. 장부·형식·도구 연결 문제 | v5 기존 계획만 재사용, 추가 장부·계획 전용 호출 제외 | 당시 v1 경로 결과. 현재 정확도 아님 |
| [CM003 반복](../../../../../07_DOCS/REFERENCE/REPORTS/CM003_TOOL_LOOP_DIAGNOSIS_20260921.md) | 다른 호의 정의·'이하' 연결로 이동, 같은 관계 반복 | 출발 구절·대상과 요구 대조, 관계의 새 정보 없으면 반복 중단 | 현재 메뉴에는 표제어 보강이 있음. 과거 표시 결함과 해석 실패를 구분 |
| [v4 E01·E15·E16](../../../../../07_DOCS/REFERENCE/REPORTS/SOURCE_TIERS_EDGE_CASES_20260921/README.md) | 새 후보 뒤 조기 종료, 서버 읽기 후 모델 제시 누락 | 후보→읽기→전달 상태 구분, 미확인 범위 표시 | 모델 지침만으로 서버 조기 종료·packing 실패 해결 불가 |
| 같은 원장 E02·E03·E07·E09 | 제목 0건, 약칭/좌표 혼선, 변경 검색에 과거 커서, 루트 READ | 문서 식별 후 locate, 새 검색 cursor=null, 제공된 read_action | 40개 항목은 관측+코드 점검이며 실패 40회가 아님 |
| [Qwen 행동 진단](../../../../../07_DOCS/REFERENCE/REPORTS/RAG_SOURCE_WORKFLOW_IMPLEMENTATION_20260921/QWEN_BEHAVIOR_DIAGNOSIS.md) | 후보 120개 READ0, 주제만 비슷한 원문 선택, 미선택 E 인용, 예외 누락 | 읽기 우선 전환, 규율 대상·행위 대조, 전달 후 선택, 예외 확보 | 입력 설계·순위 영향과 모델 판단 영향을 분리해야 함 |
| [Gemma 7문항 기록](../../../../../07_DOCS/REFERENCE/REPORTS/GEMMA_OBLIGATION_PROBE_20260922/README.md) | 요구문 한 글자, 번호/문장 혼동, 평가자 원문 왜곡. 최종 비교 불충분 | 구체적인 짧은 문장, 종류별 번호 사용, 원문 대조 | 최소 길이·스키마 수정은 기존 코드 책임. 자동 점수로 스킬 효능 주장 안 함 |
| [ADR0506](../../../../../04_EXPERIMENTS/ADR/ADR-0506-gemma-v5-main-three-case-probe/README.md) | 요구문 정상화 이후에도 일반 차감/별도 조정 혼동, AND 조건 누락, 최종0/3 | 직접 요구 답변, AND/OR·범위·일반/예외 대조 | 형식 성공과 실제 답변 품질은 다름. 최종 정답률 미측정 |
| [ADR0507](../../../../../04_EXPERIMENTS/ADR/ADR-0507-v5-priority-reverse-matching/README.md) | 우선순위 단서를 추가해도 두 arm 모두 필수 원문 READ0, 반환 계약 오류 | 현행 output_schema 유지, 계획 재전송 최소화, 생성될 핸들 예측 금지 | 좌표·순위 기능과 실행 가능한 명령은 별도. 스키마 제거를 경량화로 채택하지 않음 |
| [ADR0508 CM003](../../../../../04_EXPERIMENTS/ADR/ADR-0508-v5-maximal-reference-context/CASE_REVIEW.md) | 필수 근거1/2, 요구 누락·draft_quote 변형으로 최종 미완료 | 원질문 전체 검토, 정확 문자열 복사, 미확보 예외 탐색 | 스킬의 복사 지시만으로 실모델 준수 입증 안 됨 |
| [ADR0508 CM018](../../../../../04_EXPERIMENTS/ADR/ADR-0508-v5-maximal-reference-context/CASE_REVIEW.md) | 좌표는 해소됐지만 필수 원문1/2, 관계 출발·대상 미확보 | 실제 의존 관계의 양쪽 원문 확보, 없으면 해당 주장 유보 | 관계 선언 삭제로 검증 우회하지 않음 |
| [ADR0508 CM038](../../../../../04_EXPERIMENTS/ADR/ADR-0508-v5-maximal-reference-context/CASE_REVIEW.md) | 필수 원문 전달1/1, 선택0/1, 예산 소진·미선택 인용 거부 | 읽은 적합 원문 즉시 선택, 작성 예산 보존, 인용 허용 집합 확인 | '찾았으므로 답변 성공'이라는 지표 해석 배제 |

최신 [ADR0508 요약](../../../../../04_EXPERIMENTS/ADR/ADR-0508-v5-maximal-reference-context/README.md)은 형식 오류0건·필수 원문 전달3/5·읽은 증거24개 보존이지만 최종 검토 완료 답변0/3이다. 여러 변경과 입력 상한을 함께 바꾼 단회 in-sample 실행이므로 개별 개선 효과를 확정하지 않는다. 그 격리 후보의 좌표·응답 계약을 현재 MAIN으로 설명하지 않는다.

## 공개 자료 → 채택·제외

공개 코드를 붙여 넣거나 여러 SKILL.md를 연결하지 않고, 아래 일반 절차를 우리 도구 계약과 내부 관측에 맞춰 새로 작성했다. 공개 벤치마크 점수를 내부 법률 성능으로 이전하지 않는다.

| 출처 | 채택한 아이디어 | 제외·한계 |
|---|---|---|
| [Anthropic search-strategy](https://github.com/anthropics/knowledge-work-plugins/blob/main/enterprise-search/skills/search-strategy/SKILL.md) | 질문 단서에 맞는 검색 경로, 미발견 시 방법 전환 | 모든 커넥터 병렬 실행, 날짜·범위 필터 일괄 제거, 일반 업무용 출처 서열을 법률에 적용하지 않음 |
| [QMD skill](https://github.com/tobi/qmd/blob/main/skills/qmd/SKILL.md) | 후보 검색→전체 근거 읽기→출처 있는 답변, 미리보기는 단서 | QMD 설치·별도 인덱스·HyDE·새 query 필드 제외. 작은 임베딩 모델이 작은 에이전트의 성공 증거는 아님 |
| [Google 검색 grounding](https://ai.google.dev/gemini-api/docs/google-search), [Deep Research 소개](https://blog.google/innovation-and-ai/technology/developers-tools/deep-research-agent-gemini-api/) | 질문에 필요한 검색과 결과 확인을 반복하는 방식 참고 | Gemini의 검색 성능을 프롬프트 한 장으로 복제할 수 있다고 가정하지 않음. 외부 검색 API는 내부 원문 경로에 연결하지 않음 |
| [SKILLER GAIA skill](https://github.com/DANG-ai/SKILLER/blob/main/gaia/skills/ours_x4p3/SKILL.md) | 짧은 행동 지침·증거 확인·멈춤 조건이라는 연구 방향 | [PolyForm Noncommercial 라이선스](https://github.com/DANG-ai/SKILLER/blob/main/LICENSE). 원문·템플릿·코드를 복제/번역/동봉하지 않음. 인용 생략·고정 턴 수·GAIA 파일 절차 제외 |
| [Microsoft SkillOpt](https://www.microsoft.com/en-us/research/blog/skillopt-agent-skills-as-trainable-parameters/), [저장소](https://github.com/microsoft/SkillOpt) | 실패 궤적에 근거한 작은 지침 수정, 별도 검증 후 채택 | 자동 수정·자동 승격 제외. 이번 스킬은 SkillOpt 실행 결과가 아님 |
| [Microsoft local-ai-agents](https://github.com/microsoft/ai-agents-for-beginners/blob/main/.agents/skills/local-ai-agents/SKILL.md) | 모델이 짧은 선택을 하고 도구가 실제 작업을 수행하는 구성 참고 | 특정 로컬 모델 예제를 내부 법률 품질 검증으로 취급하지 않음 |
| [daymade deep-research](https://github.com/daymade/claude-code-skills/blob/main/deep-research/SKILL.md) | 근거 부족 지점 확인 | 장문 보고서 과정·추가 조사 단계·고정 출처 수 제외 |
| [Search-R1](https://github.com/PeterGriffinJin/Search-R1), [Agent Distillation](https://github.com/Nardien/agent-distillation) | 도구 사용이 모델 능력·학습에 좌우된다는 연구 참고 | 학습된 가중치를 가져와야 하는 접근을 설치 가능한 검색 skill로 포장하지 않음 |

## 수정 시 구분할 것

- 지침으로 줄일 오류: 불필요한 계획 재작성, 검색어만 바꾸는 반복, 잘못된 커서 재사용, 근거 선택 누락, 복사할 인용의 의역.
- 도구·서버 수정이 필요한 오류: 보이지 않는 검색 영수증, 미전달 원문, 불충분한 페이지 재개, 후보 정렬, 선택/인용 집합 불일치, 조기 종료.
- 모델 검증이 필요한 오류: AND/OR 보존, 개념 구분, 사안 적용, 지침·번호·수정 지시의 안정적 준수.

어느 범주의 오류도 문서 작성만으로 해결 완료라고 표시하지 않는다.
