# FEEDBACK

FeedbackEvent·Diagnosis·ChangeCandidate·reviewed QueryShortcut의 append-only
원장과 재생성 가능한 view를 둔다. 피드백은 canonical 지식을 바로
수정하지 않는다.

정식 흐름은 다음과 같다.

```text
RAG trace / 사용자 판정 / validator finding
  -> feedback-event-v1 (OBSERVED, hash 고정)
  -> change-candidate-v1 (INERT_UNTIL_REVIEW)
     -> QUERY_PROJECTION       : 동일 질문 유형의 검증된 착지 shortcut 후보
     -> DEFINITION_OBSERVATION : 충돌 surface를 정의 컴파일러로 보낼 관찰 후보
     -> DATA_CORRECTION        : 사람이 원본/구조 데이터를 고칠 검수 후보
     -> INGESTION_RULE         : 서로 다른 문서에서 반복된 detector 패턴의 rule 후보
```

`DATA_CORRECTED`는 기존 `DATA_ERROR`를 덮어쓰지 않고 `resolves_event_id`,
before/after hash, correction receipt를 가진 새 이벤트로 추가한다. 동일 detector
오류가 서로 다른 두 문서 이상에서 반복되어야 ingestion rule 후보가 생기며,
그 후보도 실험과 사람 승인 전에는 실행되지 않는다.

숏컷 상태 변경은 같은 ID의 `revision + previous_record_sha256` 연쇄로
추가한다. 선택 시 현재 세대뿐 아니라 사용자가 볼 수 있는 landing과
설치된 evidence receipt를 다시 확인하여 ACL을 우회하지 못한다.
