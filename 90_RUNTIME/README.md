# 90_RUNTIME

재생성 가능하거나 환경에만 존재하는 `LOGS/`, `OUT/`, `PYTEST_CACHE/`를 둔다.
임시 폴더는 사용 시 생성하고 빈 자리표시자는 남기지 않는다. `GENERATIONS/`와
`LEGACY_VAR/`는 기존 activation·rollback receipt가 참조하므로 이름과 내용을 보존한다.
Git 정본이 아니다.
