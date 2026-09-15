# GENOS 내규·외규 전체 데이터화 + 로그

코드는 `/home/genos/DEV`에 설치합니다. URL·인증키는 기존 환경변수를 사용합니다.
이 명령은 원본을 삭제하지 않고 새 DRAFT 데이터를 만듭니다. 서비스 배포·CURRENT 교체는 하지 않습니다.

## 입력 위치

- 내규: `/home/genos/DEV/data/corpus/internal/` 아래 모든 하위 폴더의 문서.
- 외규: `/home/genos/DEV/data/corpus/` 아래 `law`, `krx`, `kofia`, `expc`, `fsc`, `moleg`, `prec`의 manifest 등록 원본과 첨부.
- 내규 ZIP은 먼저 풀어 놓아야 합니다. ZIP 자체는 처리하지 않습니다.
- 폴더 이름과 문서 제목은 메타데이터에 함께 저장합니다. 같은 원본의 별도 폴더 이름도 별칭으로 보존합니다.
- 외규 HTML/HWP가 같은 본문의 대체 표현이면 선택한 본문만 처리하며 제외 사유를 기록합니다. 미등록 원본 문서는 오류로 보고합니다.
- PDF/DOCX는 기존 Docling, HWP/HWPX는 기존 전용 파서, 등록 태그는 기존 형식 라우터를 사용합니다. 필요한 의존성이 설치되어 있어야 합니다.

## 1. 입력 점검만 (모델 호출 없음)

```bash
cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_build_all.sh --run-id full-001 --check-only
```

파일 존재, 원본 해시, 등록 태그를 확인합니다. 실제 파싱 성공이나 모델 연결을 보장하는 점검은 아닙니다.
오류가 있으면 출력된 `inventory-*.json`의 `errors`를 먼저 해결하세요.

## 2. 전체 실행

`GENOS_LLM_REVISION`에는 실제 배포 버전 식별자를 설정해 두세요. 서빙 경로의 226이나
`/models`의 모델 ID를 임의로 배포 리비전으로 쓰지 않습니다. 이 값은 재개 시 동일 모델 배포를 확인하는 기록입니다.
이미 설정했다면 다시 바꿀 필요 없습니다. 아래 명령을 한 번 실행합니다.

```bash
cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_build_all.sh --run-id full-001 --embed-batch-size 64 --max-calls 10000
```

순서: 입력 점검 → 전체 원본 구조화 → LLM 스키마 추출·검토·필요 시 재추출 → 임베딩 64개씩 → SQLite 적재·검증.
159개 청크면 64 + 64 + 31로 처리합니다. 64개만 처리하고 끝내는 옵션이 아닙니다.
원문 구조화 오류가 있으면 문서별 오류를 모은 뒤 LLM 호출 전에 중단합니다.
LLM 검토에 통과하지 않은 작업이 남으면 전체 완료로 표시하거나 부분 적재하지 않습니다.
작업당 재시도는 기본 3회, 실행당 LLM 호출 예산은 10,000회입니다. 전체 문서 처리에는 시간·모델 자원이 많이 들 수 있습니다.

## 3. 진행 상황과 오류

다른 터미널에서:

```bash
tail -n 100 -f /home/genos/DEV/data/logs/full-001/progress.log
```

- `data/logs/full-001/progress.log`: 시간, 단계, Python 출력/오류, traceback, 30초 생존 표시, 종료 상태.
- 같은 폴더 `events.jsonl`: 기계 판독용 이벤트. 재개해도 기존 로그에 이어 씁니다.
- 같은 폴더 `inventory-*.json`: 선택 문서·제외 사유·중복 별칭·입력 오류.
- 같은 폴더 `attempt-*.json`: 시도별 시작/종료/종료 코드. 성공은 `COMPLETED`, 실패는 `FAILED`.
- `data/builds/full-001/structure-errors.json`: 문서별 파싱 오류.
- `data/builds/full-001/authoring-status.json`, `queue/queue.sqlite`: LLM 작업 상태와 시도별 실패 기록.
- `data/builds/full-001/provider/`: 모델 요청·응답·사용량 기록. 문서 원문을 포함할 수 있으므로 외부 공유하지 마세요.

기록은 실행 사용자 전용 권한으로 생성하며 알려진 환경변수의 키·토큰·비밀번호를 가립니다.
강제 종료(SIGKILL), 전원/디스크 장애나 네이티브 라이브러리의 직접 출력은 완전한 종료 로그를 보장하지 않습니다.
`RUNNING` 기록만 남아 있으면 완료가 아닙니다. SSH 종료 방지가 필요하면 운영 환경의 세션 유지 도구를 사용하세요.

## 4. 중단 후 재개

```bash
cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_build_all.sh --run-id full-001 --resume --embed-batch-size 64 --max-calls 10000
```

성공한 LLM 작업/임베딩 배치는 재사용합니다. 재시도 한도를 이미 소진한 실패는 오류 원인을 먼저 해결해야 합니다.
입력·태그·스키마·코드·모델 배포가 바뀌면 재개를 거부합니다. 그때는 `--run-id full-002`처럼 새 ID로 실행하세요.
입력 점검에서만 실패해 `plan.json`이 생성되지 않았다면 `--resume` 없이 다시 실행합니다.

## 5. 완료 결과

`/home/genos/DEV/data/builds/full-001/result.json`에 `ok: true`와 생성 수가 기록됩니다.
실제 결과는 `generation/store.sqlite`, `generation/vectors.sqlite`, `generation/manifest.json`입니다.
외부 Vector DB는 필요 없습니다. 이 작업은 데이터 생성까지이며 사용자 질문 답변이나 서비스 활성화를 자동 실행하지 않습니다.

로컬 검증은 합성 문서·가짜 모델 기반 기능 테스트입니다. GENOS 현장 데이터 전체의 성공이나 추출 품질은 아직 검증하지 않았습니다.
