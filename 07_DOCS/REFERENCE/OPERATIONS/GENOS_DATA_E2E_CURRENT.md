# GENOS 내규·외규 데이터 구축 E2E

이번 E2E는 **데이터 적재까지**입니다. OQL·질문답변·운영 전환은 포함하지 않습니다.
기존 전체 구축 알고리즘은 그대로 사용하며 명시적인 실행 진입점과 최신 호환 설치본을 제공합니다.

## 설치

첨부 ZIP과 `genos_apply_data_e2e.sh.b64.txt`를 `/home/genos/DEV/TRANSFER`에 저장하세요.
기존 코드/데이터 폴더를 삭제하지 않습니다. 이전 설치기를 다시 실행하지 않습니다.

```bash
(
  set -e
  cd /home/genos/DEV/TRANSFER
  base64 -d genos_apply_data_e2e.sh.b64.txt > genos_apply_data_e2e.sh
  GENOS_SCHEMA_BUILD_ROOT=/home/genos/DEV bash genos_apply_data_e2e.sh
)
```

unzip 불필요. 최신 Qwen 응답 처리·엔진 해시는 유지하고 기존 `genos.py` 연결 설정은 보존합니다.
알 수 없는 수정은 덮어쓰지 않고 설치 전 모두 보고합니다. 기존 .env·원본·Git·CURRENT는 그대로입니다.

## 원본 위치

- 내규: `/home/genos/DEV/data/corpus/internal/` 아래 중첩 폴더. 폴더 경로와 문서제목이 함께 저장됩니다.
- 외규: `/home/genos/DEV/data/corpus/` 아래 `law`, `krx`, `kofia`, `expc`, `fsc`, `moleg`, `prec`.
  기존 외규 manifest에 등록된 본문/첨부를 처리합니다. ZIP은 먼저 풀어야 합니다.
- 파일의 등록 태그/형식에 맞는 파서를 사용합니다. 지원하지 않는 형식/파서 누락은 숨기지 않고 중단합니다.

## 1. 입력 점검 — 모델 호출 없음

```bash
cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id data-e2e-001 --check-only
```

파일/manifest/hash/등록 태그 검사입니다. 실제 파싱이나 모델 연결 성공까지 뜻하지 않습니다.
오류가 있으면 출력된 inventory JSON의 `errors`를 확인하세요.

## 2. 전체 구축 — 실제 모델 호출

```bash
cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id data-e2e-001 --execute --embed-batch-size 64 --max-calls 10000
```

`--build-dir`은 자동 지정됩니다. 기존 GENOS LLM·임베딩 URL/키/모델 설정을 유지하세요.
`GENOS_LLM_REVISION`에는 실제 배포 리비전이 필요합니다. 서빙 ID 226을 임의로 대신 넣지 않습니다.
순서: 전체 원본 확인 → 구조화 → 정본 스키마에 맞는 LLM 추출/검토/필요 시 재추출 →
임베딩 **64개씩 모든 청크 처리** → 원문/스키마 번들/벡터를 SQLite 기반 DRAFT 세대에 적재·재검증.
실패한 추출을 성공으로 간주하지 않습니다. 호출 예산/재시도 한도와 문서량에 따라 미완료될 수 있습니다.

## 3. 진행·오류 확인

```bash
tail -n 100 -f /home/genos/DEV/data/logs/data-e2e-001/progress.log
```

- 단계/오류/대기 기록: `data/logs/data-e2e-001/{progress.log,events.jsonl,attempt-*.json}`
- 모델 요청/응답/사용량/실제 모델 ID: `data/builds/data-e2e-001/provider/`, `models.json`
- 추출/검토 상태: `authoring-status.json`, `queue/queue.sqlite`
- 최종 결과: `data/builds/data-e2e-001/result.json`, 적재 세대 `generation/`
- **프로세스 종료 코드 0 + result.json의 ok:true**여야 적재 완료입니다.
  데이터는 DRAFT이며, 법률 의미의 사람 승인이나 서비스 활성화를 뜻하지 않습니다.
로그에는 내부 문서가 포함될 수 있으니 외부로 공유하지 마세요.

## 중단 후 재개

실제 `data/builds/data-e2e-001/plan.json`이 생성된 후 중단됐고 원본/코드/스키마/모델이 같을 때:

```bash
cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id data-e2e-001 --execute --resume --embed-batch-size 64 --max-calls 10000
```

입력 점검에서만 실패했다면 --resume 없이 재실행합니다. 코드/스키마/원본/모델을 바꿨다면
기존 결과를 지우지 말고 `data-e2e-002`처럼 새 run-id를 사용하세요.
이번 패치 설치 뒤 이전 코드로 시작한 빌드를 재개하지 말고 새 run-id를 사용하세요.
# 2026-09-10 DOC/실패 건너뛰기 패치 이후 우선 안내

최신 기본값은 문서별 실패 격리/건너뛰기이며 결과는 `batch-result.json`과 문서별 DRAFT다.
아래 과거 단일 generation 안내는 `--fail-fast` 모드에 해당한다.
설치·통과율·원본 DOC 변환·재개는 [GENOS_DOC_SKIP.md](GENOS_DOC_SKIP.md)를 따른다.
# 리비전 입력 조건 제거 (최신)

`genos-no-revision-20260910.zip` 적용 후 `GENOS_LLM_REVISION`을 요구하지 않는다.
설치·실행은 [GENOS_NO_REVISION.md](GENOS_NO_REVISION.md)를 따른다.
