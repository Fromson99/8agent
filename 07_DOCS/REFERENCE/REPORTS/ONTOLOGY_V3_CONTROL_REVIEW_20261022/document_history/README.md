# 문서 분리 전 원문 보존

2026-10-22 사용자 요청에 따라 통합 문서를 주제별로 분리했다. 아래 파일은 분리 직전 문서와 완료된 검사 도구·결과를 원래 UTF-8 바이트와 SHA-256으로 보존한 gzip JSON이다.

- [분리 전 원문](20261022_before_split.json.gz)
- [분리 구성표](../../../ARCHITECTURE/ONTOLOGY_V3/DOCUMENT_MAP.json)
- [현재 전체 목차](../../../ARCHITECTURE/ONTOLOGY_V3.md)

압축 안 files의 각 키는 저장소 상대 경로이며 content와 sha256을 포함한다. 복원 검토는 저장소 Python의 gzip/json으로 읽어 별도 임시 경로에 기록하고 SHA-256을 대조한다. 현재 문서나 원문 정본에 자동 덮어쓰지 않는다.

기존 EVIDENCE.json과 database/VALIDATION.json은 당시 사실·검사 기록으로 그대로 보존한다. 그 문서 hash는 분리 전 버전의 hash이며 현재 파일의 hash와 같다는 뜻이 아니다. DOCUMENT_MAP.json과 REORGANIZATION_VALIDATION.json도 최초 분리 시점의 기록으로 보존하며 후속 편집의 현재 hash 목록으로 사용하지 않는다.

## 공통 클러스터·온톨로지 구성·질문 매칭 반영

2026-10-22 후속 대화를 기존 주제 문서와 두 개의 새 주제 문서에 통합했다. 이전 문서의 공통 확인 규칙을 사용자용 클러스터·표현 틀과 원문별 의미 관계로 구체화하고, 생성→게시→질문/원문 조회→적용 흐름을 연결했다. 기대 효과와 완료된 CM 연구 결과, 작업 코드와 선택 MAIN의 경계를 구분했다.

- [갱신 직전 원문 9개](20261022_before_clustering_matching.json.gz): files의 content·sha256으로 UTF-8 내용을 보존한다. unchanged_evidence는 이번 작업에서 보존할 코드·완료 기록·활성 포인터의 갱신 전 hash다.
- [갱신 검사와 현재 문서 목록](20261022_clustering_matching_validation.json): 변경·추가 문서 hash, 로컬 링크·anchor 검사, 기존 anchor 보존, 보존 대상의 hash 대조 결과와 검사 범위.
- [온톨로지 구성](../../../ARCHITECTURE/ONTOLOGY_V3/CLUSTERING_AND_CONSTRUCTION.md) · [질문·원문 매칭](../../../ARCHITECTURE/ONTOLOGY_V3/QUESTION_MATCHING.md).

새 압축본도 gzip/json으로 읽고 content를 별도 임시 경로에 UTF-8로 기록한 뒤 sha256을 대조하면 복원 내용을 검토할 수 있다. 기존 문서에 자동 덮어쓰지 않는다. 이번 변경은 문서 반영이며 기존 실험 결과·평가 기준·SQL·코드·MAIN 포인터는 변경하지 않았다.
