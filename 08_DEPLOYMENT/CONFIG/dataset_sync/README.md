# SourceSet release sync

`dataset-overlay-v1`의 파일 복사 방식은 v2 CUTOVER와 함께 폐기됐다. 데이터 이동 단위는
`DatasetPackage`, 선택 단위는 `SourceSet`, 배포 단위는 hash가 고정된 release다.

`profiles.json`은 대상별 SourceSet과 활성 release store만 선언한다. 내부 실데이터와 외부
mock을 같은 상대경로에 덮어쓰는 overlay는 더 이상 지원하지 않는다. 공개·내부 제한·실험
데이터는 각각 별도 SourceSet 정책으로 조합한다.

새 데이터 발행은 `06_TOOLS/MIGRATION/publish_v2_dataset.py`, CUTOVER 검증은
`06_TOOLS/MIGRATION/validate_v2_cutover.py`를 사용한다. 완료된 release와 generation은
내용을 고치지 않고 새 generation을 발행해 교체한다.
