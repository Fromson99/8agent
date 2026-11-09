# 05_TESTS

- `SMOKE/`: cutover·activation 최소 검증
- `REGRESSION/`: 기존 기능 전체 회귀 스위트
- `GENERATIONS/`: receipt-bound 불변 테스트 세대

`REGRESSION` 아래의 소문자 폴더는 Python import namespace이므로 그대로 유지한다.

## 빠르게 돌리기 (2026-11-06)

측정(같은 머신, 다른 세션 병행 중): 101파일·1,905검사 회귀 묶음은 기존 직렬 1,495초 → 직렬 234초 →
`run_tests.py` 7프로세스 66~73초. 기본 전체 스위트(847파일·10,412검사)는 같은 묶음 기준 기존 conftest 612초 →
363초(7프로세스). 결과는 101파일 1,905건 모두 같았고, 전체 스위트 차이는 아래 두 종류뿐이었다.

- `python -m pytest ...`로 실행하면 `conftest.py`가 pytest를 한 번 `libeatmydata` 아래에서 다시 시작해
  fsync를 없앤다. 테스트용 SQLite·파일은 그대로 쓰이고 PRAGMA 값·`os.fsync` 호출·파일 내용은 같으며,
  WSL 디스크의 fsync 대기만 사라진다(한 파일 기준 40초→4초). 실제 fsync가 필요하면 `LAWRAG_TEST_KEEP_FSYNC=1`.
  `pytest.main()`을 직접 부르는 스크립트는 다시 시작하지 않으므로 `eatmydata python 스크립트.py`로 실행한다.
- 실험 도구 폴더(`06_TOOLS/EXPERIMENTS` 아래 약 1,400개)는 sys.path에 한 칸(`EXPERIMENT_PATH_SLOT`)으로만
  들어가고, 그 폴더들에 있는 이름만 원래 순서대로 찾는다(모듈 이름 2,655개의 연결 파일이 이전과 같음을 확인).
  폴더를 sys.path에 하나씩 다시 넣지 않는다. 넣으면 모든 import와 `importlib.metadata.version()`이 그 폴더들을
  훑고(버전 조회 1회 60ms), 프로세스 풀 자식(forkserver)은 `adr_0928/inspect.py`가 표준 `inspect`를 가려 죽는다
  (`test_genos_meaning_recovery.py`·`test_pipeline_unit_fulltext.py`·`test_genos_request_summary.py`의 BrokenProcessPool
  3건이 이 때문에 늘 실패했고 이제 통과한다). 대신 그런 자식 프로세스에서는 실험 도구 모듈을 이름으로 바로 import할 수 없다.
- 여러 파일은 병렬 실행기로 돌린다. 파일 단위로 나눠 각자 별도 pytest 프로세스·basetemp에서 실행하고,
  남은 메모리를 보고 프로세스 수를 정한다(기본 최대 8, 여유 2.5GB 유지). 이 머신에서는 11개로 늘려도 CPU가 차서
  빨라지지 않았다.

  ```
  .venv/bin/python 06_TOOLS/maintenance/run_tests.py --files-from 목록.txt --output 90_RUNTIME/OUT/이름
  .venv/bin/python 06_TOOLS/maintenance/run_tests.py --files-from 목록.txt --output 90_RUNTIME/OUT/이름2 \
      --compare 90_RUNTIME/OUT/이름/result.json
  ```

  `--compare`는 이전 결과와 같은 묶음 구성으로 돌려 결과가 바뀐 검사만 보여 준다. 같은 프로세스에서 앞서 실행된
  테스트에 따라 결과가 달라지는 검사가 있으므로(예: `test_genos_team_selection.py::test_current_generation_boot_and_team_search`는
  101파일 직렬에서만 503) 변경 전후 비교는 같은 묶음으로 한다. Windows PowerShell을 부르는 `test_zip_parts_*`는
  WSL 연동 시간 초과(`UtilAcceptVsock accept4 failed 110`)로 실행마다 결과가 바뀔 수 있다.
  파일별 소요 시간은 `90_RUNTIME/PYTEST_CACHE/file-durations.json`에 쌓여 다음 묶음 나누기에 쓰인다.
- 릴리스·stage 코드로 돌릴 때는 `--code-root 08_DEPLOYMENT/RELEASES/<id>/code`(또는 stage 폴더). 감사 폴더마다
  `pytest_contracts.py`를 만들어 `pytest.main()`을 한 프로세스에서 직렬로 부르지 않는다(병렬·fsync 제거가 안 된다).
  제품 패키지는 그 코드에서, 검사·도구는 작업 폴더에서 읽고, 코드 해시·엔진 핀·격리를 확인한다. 결과는 그 코드의
  기준 결과(`90_RUNTIME/TEST_BASELINES/`)로 저장되어 다음 MAIN 반영에서 이전 MAIN을 다시 돌리지 않는다.
  MAIN 반영 전체 순서는 [MAIN_RELEASE.md](../07_DOCS/REFERENCE/OPERATIONS/MAIN_RELEASE.md)(`main_release.py`).
- 전체 스위트의 남은 시간은 대부분 GENOS·Dataiku 인계 설치기를 하위 프로세스로 실제 실행하는 검사
  (`test_genos_cm_*_handoff.py` 등, 한 건 10~38초)와 제품 코드의 JSON 스키마 검사(`jsonschema` `$ref` 해석)다.
