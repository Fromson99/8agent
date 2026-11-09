# 로컬 MAIN 반영 절차 — `main_release.py` (2026-11-06)

작업 코드 수정을 지금 선택된 로컬 MAIN 위에 얹어 다음 MAIN으로 선택할 때 쓴다.
감사 폴더마다 `stage.py`·`apply_fix.py`·`pin_code.py`·`pytest_contracts.py`·`compare.py`·
`prepare_release.py`·`activate.py`·`entry_check.py`를 새로 만들지 않는다
(11월 6일 하루에만 `pin_code.py` 16벌, `prepare_release.py` 11벌이 있었다).

## 순서

```bash
OUT=09_ARTIFACTS/AUDITS/20261106-<이름>
T=06_TOOLS/maintenance/main_release.py

# 1. 선택된 MAIN을 그대로 복사하고 바꾼 파일만 넣는다. 핀·PIPELINE·SQL 계획 메타는 자동 갱신.
.venv/bin/python $T stage --out $OUT --product 02_BACKEND/semantic_runtime/a.py \
    --product 02_BACKEND/semantic_runtime/b.py=$OUT/b.clean.py   # 작업 폴더에 남의 수정이 섞였을 때
# $OUT/staged-diff.patch 로 들어간 변경만 있는지 확인한다.

# 2. 관련 검사: 후보(OUT/staged)만 돌리고, 지금 MAIN의 결과는 저장된 기준을 쓴다.
.venv/bin/python $T test --out $OUT --files-from $OUT/tests.txt

# 3. 변경별 확인(실제 로컬 Oracle 서비스, 현장 재현 시나리오 등)은 $OUT/staged 로 따로 돌려 결과 파일을 남긴다.

# 4. 릴리스 준비(아직 MAIN 그대로)
.venv/bin/python $T prepare --out $OUT --release-id <영문-날짜-r1> \
    --reason "<왜 바꿨는지>" --authorization-text "<사용자 지시 원문>" \
    --evidence oracle=$OUT/service-oracle.json --limit "<검증하지 않은 것>"

# 5. MAIN 선택 + Gold 연결 이동 + 진입 확인. 하나라도 실패하면 자동으로 되돌린다.
.venv/bin/python $T activate --out $OUT [--extra-check $OUT/check_this_change.py]

.venv/bin/python $T status --out $OUT      # 단계별 상태
.venv/bin/python $T rollback --out $OUT    # 이 반영 되돌리기(아직 선택된 MAIN일 때만)
```

## 단계별로 하는 일과 멈추는 경우

| 단계 | 하는 일 | 멈추는 경우 |
|---|---|---|
| stage | MAIN 파일 536개를 해시 확인하며 복사 → product만 교체 → 탐색 호환 등록(탐색 컴파일러 3파일을 바꾼 경우) → `prepare_oracle_queries` → 엔진 핀·PIPELINE 갱신 → 엔진 preflight | MAIN 파일 해시 불일치, product가 MAIN과 같음, SQL 계획이 바뀜(`--allow-sql-change` 없이), 탐색 3파일 변경인데 `--navigation-source` 없음, 핀/PIPELINE/계획 외의 예상 못 한 변경 |
| test | `run_tests.py --code-root OUT/staged`(병렬·격리) → 지금 MAIN의 같은 파일 결과를 저장된 기준에서 읽고, 없는 파일만 MAIN 코드로 실행 → 결과가 다른 검사는 그 파일만 양쪽에서 단독 재실행해 확인 | 새 실패(단독 재실행에서도 후보만 실패), 후보에서 사라진 검사, 끝나지 않은 묶음, 실행 중 코드 변경, 격리 위반 |
| prepare | 변경 목록·사유(`integration.json`), `authorization.json`, `validation.json` 작성 → `rag_main_promotion.py prepare` → 준비된 릴리스가 stage 파일과 바이트 동일한지 확인 | test 미통과, stage 이후 staged/작업 폴더 product 변경, 선언 안 된 변경, 릴리스 배치에 안 들어가는 새 파일 |
| activate | `rag_main_promotion.py apply` → Gold 연결(`gold_connection_engine_r12/binding.json`)을 새 엔진으로 → 진입 확인(실제 root service 해석, 다음 세대, 데이터 세대·manifest 불변, 작업 폴더 product = 선택본, 이전 MAIN 롤백 포인터, 매핑이 이전 MAIN과 같음, 예전 탐색 버전 유지, Gold 연결기 같은 엔진) → `--extra-check` | 위 확인 중 하나라도 실패 → MAIN·Gold 연결 자동 되돌림 |

### 새 워크플로우를 처음 넣을 때 (2026-11-07 추가)

`PIPELINE.json`과 엔진 핀은 파생 파일이라 `--product`로 넣을 수 없다. 새 워크플로우 패키지는 stage 옵션으로 등록한다.

```bash
.venv/bin/python $T stage --out $OUT --product …(새 패키지 파일과 manifest 포함) \
    --register-workflow 02_BACKEND/workflow/<새_패키지>/manifest.json \
    --workflow-entrypoint "/v1/rag/ask:<화면 조회 방식 이름>" \
    --engine-pin 02_BACKEND/semantic_runtime/<새 워크플로우가 import하는 새 모듈>.py
```

- `--register-workflow`: manifest의 id·version으로 `workflows.registered`에 추가하고, **그 패키지 폴더의 모든 파일을
  워크플로우 실행부(`02_BACKEND/workflow/registry.py`)를 고정한 엔진 manifest 전부에 핀으로 넣는다.**
  릴리스(`rag_main_promotion.py prepare`)는 `semantic_runtime` 폴더와 엔진이 고정한 파일만 복사하므로, 이 핀이 없으면
  prepare가 `integration delta differs … extra=[새 파일]`로 멈춘다(2026-11-07 문서 대사 MAIN173에서 실제 발생).
- `--engine-pin`: 새 워크플로우가 import하는 새 제품 파일(예: `basis_links/reading_groups.py`)도 같은 엔진에 고정한다.
- 이미 등록된 워크플로우 manifest의 버전·해시는 `pin()`이 manifest에서 다시 읽어 갱신한다.

모든 단계는 stage 때 본 MAIN 포인터와 지금 포인터를 비교한다. **다른 세션이 그 사이 MAIN을 바꿨으면
어느 단계든 멈추고 "stage again on top of the new MAIN"을 출력한다.** 새 `--out`(또는 같은 OUT에 새 `--name`)으로 다시 stage한다.
실패한 stage 폴더는 증거로 남고 재사용하지 않는다(SQL 계획 추가로 핀이 실패한 트리에서 다시 돌려 통과처럼 보이는 일을 막는다).

## 기준 결과 저장(이전 MAIN을 다시 돌리지 않는 방법)

- `run_tests.py --code-root DIR`은 끝까지 실행된 파일의 결과를 `90_RUNTIME/TEST_BASELINES/<코드 지문>/`에 파일별로 저장한다.
  코드 지문은 DIR 안 모든 파일(`__pycache__` 제외)의 해시 목록이다.
- stage 트리와 그것으로 만든 릴리스는 지문이 같다. 그래서 **후보를 검사한 결과가, 그 후보가 MAIN이 되면 다음 반영의 기준이 된다.**
  다음 반영에서는 후보만 돌린다.
- 검사 파일이나 `05_TESTS/conftest.py`·`pytest_code_root.py`가 바뀐 파일은 저장 결과를 쓰지 않고 MAIN 코드로 다시 돌린다.
  fixture·도구 모듈 변경으로 저장 결과가 낡을 수 있는데, 결과가 다른 검사는 항상 양쪽 단독 재실행으로 다시 판정하므로 새 실패로 잘못 세지 않는다.
- 저장 결과는 캐시라 지워도 된다. 의심되면 `test --rerun-baseline`.

측정(11월 6일, 다른 세션 병행 중, MAIN169의 관련 17파일·245검사):
예전 실행기 MAIN168 72초 + 후보 106초 → 새 도구 후보 56초 + MAIN170 57초(처음), 기준 재사용 시 59초.
결과는 245검사 모두 예전 실행기와 같았다. 예전 실행기는 검사 이름에서 파일 경로가 빠져 8건이 이름이 겹쳤다.

## 격리 실행(`run_tests.py --code-root`)

- 묶음마다 `pytest_code_root.py`가 실행된다: 제품 패키지는 DIR에서, 검사·fixture·도구는 작업 폴더에서 읽는다.
  `pytest.ini`(`pythonpath = 02_BACKEND .`)는 읽지 않고 `05_TESTS/conftest.py`는 plugin으로 한 번 읽는다(예전 감사 실행기와 같은 방식).
- 실행 전 DIR의 엔진 핀을 확인하고, 실행 전후 DIR의 파일 해시가 같은지 본다.
- `semantic_runtime` 모듈을 DIR 밖에서 읽으면 그 묶음은 실패한다. `lawrag`·`workflow` 중 DIR에 없는 모듈은 작업 폴더 것을 쓴다(기록만).
  DIR에 파일은 있지만 패키지 `__init__.py`가 없어(예: `lawrag/api/routers`) 작업 폴더 사본을 읽을 수밖에 없는 경우,
  두 사본이 같으면 기록만 하고 다르면 실패로 본다.

## 알려진 한계

- 일부 검사는 파일을 작업 폴더 경로로 직접 연다. 예를 들어 `test_rag_key_progress.py`는 `08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py`를 연다.
  이런 검사는 `--code-root`여도 작업 폴더 사본을 검사한다. 예전 감사 실행기도 같았다.
- prepare는 실제 `rag_main_promotion.py prepare`의 복사 규칙을 따른다. 그 규칙에 없는 위치에 새 파일을 넣으면 서빙에 포함되지 않아 prepare에서 멈춘다.
- GENOS 현장 전달본(ZIP·설치기·메일)은 이 도구 범위 밖이다. 현장 반입은 기존 handoff 절차로 한다.
- 변경별 확인(실제 Oracle 서비스, 재현 시나리오)은 자동으로 정해지지 않는다. 결과 파일을 `--evidence`로, 문자열·동작 확인은 `--extra-check`로 넘긴다.

## 검증 기록

[결과](../../../09_ARTIFACTS/AUDITS/20261106-main-release-tool/결과.txt):
실제 작업 폴더에서 격리 실행·기준 재사용·새 실패 검출을 확인했다.
하드링크 사본 작업 공간에서는 prepare → activate → 진입 확인 17/17 → rollback(MAIN·Gold 연결 바이트 복구)과
진입 확인 실패 시 자동 되돌림을 확인했다. 실제 MAIN은 바꾸지 않았다.
