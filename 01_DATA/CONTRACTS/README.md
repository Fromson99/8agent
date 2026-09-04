# CONTRACTS

기계 검증 정본은 `00_SYSTEM/SCHEMAS/`에 있다. 이 폴더는 데이터
배포물이 같은 스키마 버전을 지칭하는 카탈로그 영역이다.

`lawrag.datasets.load_package()`는 기본으로 manifest의 모든 artifact
SHA-256을 실제 파일과 대조한다. 파일 없는 순수 계약 테스트에서만
`package_from_mapping()`을 사용한다.
