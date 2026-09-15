# CONTRACTS

새 법률 의미 데이터는 `00_SYSTEM/LEGAL_SCHEMA.json`에 고정된 `legal-semantic-v2`를 사용한다. `LEGAL_SEMANTIC_V2/`의 여섯 프로필은 합성 예시이며 승인 데이터가 아니다. 아래의 기존 projection 예시는 legacy 호환 자료다.

기계 검증 정본은 `00_SYSTEM/SCHEMAS/`에 있다. 이 폴더는 데이터
배포물이 같은 스키마 버전을 지칭하는 카탈로그 영역이다.

`lawrag.datasets.load_package()`는 기본으로 manifest의 모든 artifact
SHA-256을 실제 파일과 대조한다. 파일 없는 순수 계약 테스트에서만
`package_from_mapping()`을 사용한다.

현재 예시 계약:

- `definition-projection-v1.example.json`: 여러 canonical 규칙을 일반화해
  KG 전체를 다시 순회하지 않고 개념 포함 여부를 판정하는 Projection 예시.
  기계 검증 정본은 `00_SYSTEM/SCHEMAS/definition-projection-v1.schema.json`이다.

## 다섯 단계 스키마

[단계별 정의](../../00_SYSTEM/STAGE_SCHEMAS.md)와 [합성 예시](PIPELINE_STAGES/README.md)를 함께 관리한다.
새 원문 보정·검토·적재 묶음·다중 카드·피드백 계약은 기존 legal-semantic-v2 의미 필드를 참조한다.
`PIPELINE.json`이 단계별 계약 목록과 파일 해시를 고정한다. 이 예시는 운영 데이터나 승인 기록이 아니다.
