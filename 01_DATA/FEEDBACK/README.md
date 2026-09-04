# FEEDBACK

FeedbackEvent·Diagnosis·ChangeCandidate·reviewed QueryShortcut의 append-only
원장과 재생성 가능한 view를 둔다. 피드백은 canonical 지식을 바로
수정하지 않는다.

숏컷 상태 변경은 같은 ID의 `revision + previous_record_sha256` 연쇄로
추가한다. 선택 시 현재 세대뿐 아니라 사용자가 볼 수 있는 landing과
설치된 evidence receipt를 다시 확인하여 ACL을 우회하지 못한다.
