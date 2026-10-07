# 야간 로그 기반 개념 구축

2026-10-05 작업 코드에 terminal v5/v6 요청의 `action-memory diagnose/propose/comparison-plan/compare`를
추가했다. 모델 호출 없이 실패·원문 열람·모델 전달 근거를 구분해 불변 진단과 실행되지 않는
수정 후보를 저장한다. 기존 야간 `build`와 예약 작업은 유지한다.
[입출력·실행·v6 평가·비교 판정](FAILURE_IMPROVEMENT.md).

2026-10-01 작업 코드에는 같은 구축 종료 시 조사 경험을 `legal_llm_wiki`로 저장하는
projection을 연결했다. 원자료·이유·개념 연결 이력을 보존하며 잘못된 연결/개념을
중단할 수 있다. 온라인 활성 RAG 소비·정답 검증은 별도다.
[저장·해제·검증 계약](LEGAL_LLM_WIKI.md).

현행 작업 코드의 입력은 `90_RUNTIME/semantic/legal-agent/runs/*/*/journal.sqlite`에 남은 **완료된 native 요청**이다. `06_TOOLS/pipeline.py action-memory build`가 같은 로그의 질문, 검색 계획 이유, 완독 원문, 원문 선별 이유와 feedback 해시를 확인해 episode를 만든다. 모델은 기존 이유를 묶어 조사 목적 개념과 `GUIDES_TO` 관계를 제안한다. 과거 답변은 정답으로 승격하지 않는다. 원문을 완독하지 않았거나 출처·세대 해시가 맞지 않는 로그는 사용하지 않는다.

실행 위치는 WSL `/home/jin/8-AGENT`다. 아래 명령은 한국시간 00:00 이상 06:00 미만에만 구축하며, 그 밖에서는 `OUTSIDE_WINDOW`를 기록하고 모델을 호출하지 않는다.

```bash
.venv/bin/python 06_TOOLS/pipeline.py action-memory build --root /home/jin/8-AGENT --max-seconds 120 --batch-size 8
.venv/bin/python 06_TOOLS/pipeline.py action-memory status --root /home/jin/8-AGENT
```

중복 실행은 `build.lock`으로 막고, 로그별 변경 서명과 episode ID로 재개·중복 방지를 한다. 한 번에 최대 8건, 모델 호출 1회, 전체 120초 이내로 자른다. 모델이 HTTP 응답을 계속 열어 두어도 별도 작업 프로세스를 종료한다. 승인되지 않은 비공개 질문은 `WAITING_AUTH`로만 저장하고 외부 모델에 전송하지 않는다. 공개 질문도 해당 원문 세대·문서 범위의 기존 반출 승인 기록을 **매 배치 다시 확인**한다. 모델 준비가 안 되면 `WAITING_MODEL`, 실패하면 `FAILED`를 남긴다. 다른 provider나 모델로 자동 대체하지 않는다.

Codex 앱의 현재 작업에 활성화한 heartbeat 자동화 `rag`가 매시간 이 CLI를 호출한다. 시간 범위는 앱 예약의 시간대 해석과 무관하게 `Asia/Seoul` 기준으로 **코드가 재검증**하며 00:00~06:00 밖에서는 즉시 종료한다. 앱이 꺼져 있거나 컴퓨터가 절전 상태면 로컬 자동 실행은 일어나지 않는다. 재개 시 cursor가 처리한 로그를 건너뛴다. 반복 상태가 같으면 별도 알림을 보내지 않고 신규 구축·실패만 알린다.

현황은 `90_RUNTIME/semantic/action-memory/STATUS.md`와 `status.json`에, 시간순 사건은 `build.jsonl`에, 개념·근거 관계와 intake cursor는 `memory.sqlite`에 남는다. `calls/<build-id>/`는 승인된 배치의 실제 모델 입출력을 보존한다. 이 디렉터리는 소유자 전용 접근으로 유지한다. `GUIDES_TO`는 조사 경험이며 법률 결론이 아니다. `EXCLUDES`의 `PROPOSED`는 검색 범위를 줄이지 않는다. 원문 인용·버전·독립 검증을 갖춘 `ACTIVE` 관계만 제약으로 컴파일할 수 있고, 모르는 목적·자료 세대 변경·근거 충돌 시 기존 허용 범위를 그대로 사용한다.

검증 계보: [ADR-0573](../../../04_EXPERIMENTS/ADR/ADR-0573-bounded-nightly-memory-worker/README.md)은 실제 승인된 native 로그 4건 중 2건에서 목적 개념 2개와 `GUIDES_TO` 21개를 생성하고, 미승인 1건 대기와 재실행 중복 방지를 확인했다. 다른 2건은 모델이 분류를 보류했다. [ADR-0575](../../../04_EXPERIMENTS/ADR/ADR-0575-native-schema-nightly-integration/README.md)의 온라인 전체 API 후보는 원문·인용 조건을 만족했지만 응답 지연이 증가해 **Rejected**다. 따라서 현재 로컬 활성 릴리스 generation 31은 이 DB를 요청 시 사용하지 않는다. 이 명령은 MAIN의 피드백 후처리 구축 단계에 연결된 작업 코드이며, 서빙 릴리스 활성화나 GENOS 배포가 아니다.
