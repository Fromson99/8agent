# GENOS 문서 구축 — 단계별 실행과 성공 문서만 이어가기

2026-09-22 작업 코드. 기존 `pipeline.py` → `genos_data_stages` / `document_release`
경로를 사용한다. 신규 모델·파서·용어 스키마·임베딩 단계를 추가하지 않는다.
GENOS 현장 설치·내부 모델 실행은 별도 확인 대상이다.

## 현재 사진의 실행에서 이어가기

코드를 반입한 뒤 GENOS 프로젝트 루트에서 아래 명령을 순서대로 실행한다.
사진의 원래 실행은 `full-80k-002`, 후속 실행은 새 이름 `full-80k-002-success`다.
새 이름이 이미 다른 입력으로 사용되었다면 다른 새 run ID를 모든 명령에 동일하게 쓴다.
로컬 WSL에서는 `python3` 대신 저장소 `.venv/bin/python`을 사용한다.

```bash
# 1. 완료된 구조화만 선택. 실패/입력 제외 목록과 원래 상태는 보존한다.
python3 06_TOOLS/pipeline.py document-release select \
  --from-run-id full-80k-002 --run-id full-80k-002-success \
  --allow-incomplete --reason '구조화 실패 및 DOC 입력 제외 문서는 보류하고 성공 문서부터 진행'

# 2. 기본 사전과 지식 묶음의 준비 상태 점검
python3 06_TOOLS/pipeline.py glossary knowledge check

# 3. 선택 원문 통합: 모델 호출 없음
python3 06_TOOLS/pipeline.py document-release merge --run-id full-80k-002-success

# 4. 기존 미검토 후보 + 문서 정의 후보를 모아 검토 계획 작성: 모델 호출 없음
python3 06_TOOLS/pipeline.py document-release prepare --run-id full-80k-002-success

# 5. GENOS 내부 LLM으로 용어·정의 관계 검토. 아직 남으면 같은 명령으로 재개
python3 06_TOOLS/pipeline.py document-release review \
  --run-id full-80k-002-success --max-review-jobs 100

# 6. 검토 완료 후 문서–용어·정의·명시 참조 연결 / 색인 / 서빙 DRAFT 생성
#    이 명령은 검토 모델을 호출하지 않는다.
python3 06_TOOLS/pipeline.py document-release index --run-id full-80k-002-success

# 7. 서빙 후보의 해시·사전·검토 원장·제외 감사 기록 검증
python3 06_TOOLS/pipeline.py document-release verify \
  --release 01_DATA/TERM_RELEASES/full-80k-002-success
```

`select`가 보고한 `selected` / `omitted`를 확인한다. 사진 기준 예상치는 2,105 / 21이지만
명령은 숫자를 고정하지 않고 현장 원장과 완료 영수증을 읽어 결정한다. 완료된 구조화 캐시를
직접 재사용하며 파일 재파싱·VLM 재호출을 하지 않는다. 완료 결과 해시가 다르면 중단한다.

`review`가 exit 3 / `REVIEW_PENDING`이면 한 번의 작업 한도까지 처리한 것이다. 같은 명령으로
재개한다. 완료 검토는 재사용한다. 검토 종료 전 실패 작업의 재시도는 `--retry-review-failed`다.
검토 완료 후 재채점·재시도는 기존 결과를 덮어쓰지 않고 새 실행으로 진행한다.
`review_status=PARTIAL`은 미확인·실패·근거 부족을 보존한 검토 종료이며 품질 인증이 아니다.

진행 기록 확인:

```bash
python3 06_TOOLS/pipeline.py document-release status --run-id full-80k-002-success
```

`status`는 저장된 단계 산출물과 검토 집계를 읽는다. 프로세스 생존이나 파일 무결성 검증 결과를
뜻하지 않는다. 최종 무결성 검사는 `verify`다. 원래 실패 문서 표는 계속
`01_DATA/LOGS/full-80k-002/doc-status.html`에서 본다.

`index` 작업 코드의 진행 출력은 `RELEASE INDEX`(선택·통합·검토·최종 영수증),
`GENERATION`(용어 연결·원문 세대·서빙 자산·navigation 생성),
`Indexed documents N`(문서 색인 20건마다) 순서다. navigation 생성이 30초 이상
걸리면 `GENERATION compile-navigation.working`에 경과 시간, 완료되어 읽을 수 있는
문서 수, SQLite 파일 크기를 출력한다. 문서 수가 전부 차도 명시 참조·용어 근거 처리와
무결성 검사가 남을 수 있다. 이 숫자는 예상 완료 시간이 아니다.

완료·검증된 세대를 코드서빙이 읽는 공유 NFS에 적재하려면 별도 발행 단계를 실행한다.
`--shared-root`는 코드스페이스와 코드서빙 양쪽에서 같은 경로로 보이는 **기존 디렉터리**여야 한다.
예시는 현장 관찰에 나온 NFS 경로이며 권한과 코드서빙의 접근성은 현장에서 확인한다.

```bash
python3 06_TOOLS/pipeline.py document-release publish-shared \
  --release 01_DATA/TERM_RELEASES/<run-id>/serving-unreviewed \
  --shared-root /nfs-root/diamo/8-agent/term-releases
```

검토 완료 release라면 `--release 01_DATA/TERM_RELEASES/<run-id>`를 사용한다.
명령은 `verify_release`를 먼저 실행하고 generation 전체를 임시 폴더에 복사해 파일 해시와
서빙 자산을 재검증한 뒤 최종 경로로 이름을 바꾼다. 출력의 `generation_path`를 해당
코드서빙의 `GENOS_GENERATION`으로 설정한다. 검토 보류 결과는
`<shared-root>/<run-id>/unreviewed/generation`, 검토 완료 결과는
`<shared-root>/<run-id>/reviewed/generation`에 분리된다. 기존 결과가 같으면 검증 후
재사용하고, 달라졌으면 덮어쓰지 않고 중단한다. 데이터 CURRENT·MAIN은 바꾸지 않는다.
Jupyter 셸의 `export`는 코드서빙 환경 설정에 자동 전달되지 않으므로 배포 리비전을
업데이트하고 워크플로우에서 확인한다.

실행 중인 프로세스는 기존 코드를 계속 사용하므로 코드 반입만으로 새 로그가 나오지 않는다.
현재 `build_generation`은 임시 폴더 전체를 검증한 뒤에만 `serving/generation`을 확정한다.
중단 후 색인 이후만 재개하는 명령은 없다. `release.json`이 없는 실행은 완료로 보지 않으며,
프로세스를 중단하기 전에 마지막 로그·PID·임시 산출물 상태를 확인한다. 새 코드에서
시작한 실행은 `index` 명령을 다시 호출해 완료 결과를 재사용할 수 있지만, 색인 도중
중단했다면 색인 생성은 다시 수행한다. 코드 해시가 결속된 기존 run을 새 코드로 재사용할
때는 계획 불일치가 발생할 수 있으므로 코드 변경 이행에는 새 run ID를 쓴다.

## 단계 계약과 실행 순서

| 단계 / 명령 | 입력 | 출력 / 다음 소비자 | 모델 호출 |
|---|---|---|---|
| `build-data-stages --stage raw` | 등록 RAW·전처리 설정 | 입력 목록·준비 영수증 → structure | PDF 변환 서비스 설정에 따름 |
| `build-data-stages --stage structure` | 명시 RAW 범위 | `STRUCTURE/<fingerprint>/source.sqlite` + 선택 영수증 → select/merge | PDF 전처리·VLM 경로에 따름 |
| `document-release select` | 종료된 구조화 실행·문서 상태 원장·완료 영수증 | 새 `LOGS/<run>/structure-selection.json` + 제외 감사 → merge | 없음 |
| `document-release merge` | 검증된 선택·명시 기존 세대·제외 ID·선택 사전 결속 | `TERM_RELEASES/<run>/plan.json`, `sources/store.sqlite` → prepare | 없음 |
| `document-release prepare` | 통합 원문·선택 사전·지식 묶음 | `glossary-draft`, `review/review.sqlite` → review | 없음 |
| `document-release review` | 준비된 초안·검토 계획 | `glossary-reviewed`, `review/completion.json` → index | GENOS 내부 LLM |
| `document-release index` | 완료 검토·통합 원문 | `serving/generation`, `release.json` → verify / 서비스 | 없음 |
| `document-release verify` | 완성된 release | 무결성 검증 결과 → 별도 활성화 | 없음 |

`prepare`는 기존 호환성을 위해 통합 원문이 없으면 merge도 수행한다. `review`는 prepare가 없으면
멈추고, `index`는 review가 완료되지 않았으면 멈춘다. 색인의 연결·생성과 서빙 묶음 생성은
기존 `term_generation.build_generation`의 같은 계약으로 함께 수행한다.
후속 단계의 반복 실행은 입력·결과 해시를 재검증하고 완료 결과를 재사용한다.

`document-release build --run-id <후속ID>`는 merge → prepare → review → index의 자동 실행이다.
기존 `build-all`은 RAW에서 시작하는 전체 자동 실행이며 실패 무시 기능으로 바뀌지 않는다.
`select`로 고정한 후속 run ID를 `build-all` / `build-data-stages`에 넣으면 원래 범위가
다시 들어오는 일을 막기 위해 거부한다. 후속 실행은 `document-release`로만 이어간다.

새 RAW부터 각각 실행하려면:

```bash
python3 06_TOOLS/pipeline.py build-data-stages --run-id new-documents-001 --stage raw --execute
python3 06_TOOLS/pipeline.py build-data-stages --run-id new-documents-001 --stage structure --execute
```

전체 구조화가 성공했으면 그 run ID로 `merge`부터 실행할 수 있다. 일부 실패는 `select`로
성공분을 새 run ID에 고정한다. RAW 변환·내부 모델 환경변수는 기존
[팀별 입력 안내](GENOS_TEAM_RAW.md), [구조화 안내](GENOS_RECIPE_VLM.md), `.env.genos.example`을 따른다.

## 범위와 재개 조건

- 원래 구조화 실행의 `completed=false`, 오류, DOC 입력 제외, RAW 파일은 수정하지 않는다.
- 부분 선택에는 `--allow-incomplete`와 `--reason`이 필요하다. 실행 중·원장 불일치·저장소 전체
  오류·성공 0건·완료 결과 변조는 이 옵션으로 우회할 수 없다.
- 새 선택의 `completed=true`는 선택한 성공 문서 범위에만 해당한다. 원래 범위의 누락은
  `coverage=PARTIAL`, `omitted_count`, 문서별 사유로 기록하고 최종 release에도 전달한다.
- 부모 실행의 선택 JSON과 상태 원장을 JSON 스냅샷으로 고정한다. 부모를 나중에 재시도해도
  후속 실행에 성공 문서가 자동 추가되지 않는다. 추가 반영은 새 선택·새 릴리스로 한다.
- `select`의 스냅샷은 `structure-selection-v1`에 `origin_sha256`를 추가한다.
  `selection-origin.json`은 `structure-selection-origin-v1`이며 완료 원문 스키마는 바뀌지 않는다.
  이전 전체 완료 선택과 `document-release-v1`은 계속 읽는다. 새 부분 선택의 소비자는 이번 코드다.
- 기존 서빙 문서를 유지하려면 **merge/prepare/review/index/build 모두** 같은
  `--base-generation <기존 세대>`를 지정한다. 기본 CURRENT나 최신 폴더를 자동 선택하지 않는다.
  `--exclude-document`는 통합 원문 중 특정 버전 ID를 제외하는 기존 옵션이며 실패 우회가 아니다.
- 기존 검토 사전 재사용은 `--glossary-dir <완료 사전>`을 모든 후속 단계에 동일하게 지정한다.
  `--reference-review-state`를 선택할 때도 모든 단계에 같은 완료 state를 유지한다.
- 사전·입력·코드·참조 검토 결속이 바뀌면 새 run ID를 사용한다. 새 코드는 기존 완료 세대를
  바꾸지 않으며, 이번 변경 이전에 시작한 후속 release 계획은 기존 코드로 재개하거나 새 ID로 만든다.

## 활성화·반입·복구

구축과 검증은 MAIN/CURRENT를 바꾸지 않는다. 최종 GENOS 활성화·프로세스 재시작·롤백은
[기존 document-release 계약](GENOS_DOCUMENT_CONNECTIONS.md#활성화롤백)을 따른다.
서빙은 `service.py`가 선택한 세대의 원문·사전·navigation 색인을 소비한다.

변경 실행 파일은 `lawrag/pipeline/document_release.py`, 신규 `structure_selection.py`,
`06_TOOLS/COMMANDS/genos_data_stages.py`다. `pipeline.py document-release`의 기존 배선을 사용하며
추가 Python 의존성은 없다. 현장에서는 같은 코드 묶음·requirements와 `.env` 설정 이름을 보존한다.
[전체 코드 ZIP](GENOS_FULL_CODE_ZIP.md)의 manifest가 반입 코드의 파일별 해시를 고정한다.

원복 시 신규 후속 명령을 중지하고 이전 코드 백업을 사용한다. 원래 RAW/STRUCTURE/LOGS와
활성 포인터를 바꾸지 않았으므로 원래 구조화 상태와 서빙 세대는 그대로 남는다.
생성된 새 LOGS/TERM_RELEASES는 감사 이력으로 보존하고 다른 입력으로 덮어쓰지 않는다.

## 검증 범위

`test_document_release_stages.py`는 모의 XML의 실제 구조화 → 일부 실패 → 성공분 선택 →
단계별 검토/색인 → release 무결성 검사를 연결한다. 부모 보존, 제외 사유, 잠금, 변조 거부,
선행 단계 차단, 모델 없는 색인, 완료 검토 재사용, CLI 종료 코드도 확인한다.
실제 2,105건 처리 시간·GENOS 내부 LLM 품질·현장 코드 반입 성공은 이 검증에 포함하지 않는다.
