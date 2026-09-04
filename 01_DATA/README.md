# 01_DATA

`DatasetPackage → SourceSet → UnifiedCorpusView`의 canonical 데이터 영역이다.
현재 실데이터는 v1 `data/`에 있으며 중앙 경로 계약을 통해 단계적으로
이행한다. 신규 패키지는 `EXTERNAL`, `INTERNAL`을 물리적으로 구분하되
같은 `dataset-package-v2` 계약을 사용한다.

Target: `CONTRACTS/`, `CATALOG/`, `PACKAGES/`, `SOURCE_SETS/`, `ACTIVE/`,
`INDEXES/`, `FEEDBACK/`, `QUARANTINE/`, `BACKUPS/`.
