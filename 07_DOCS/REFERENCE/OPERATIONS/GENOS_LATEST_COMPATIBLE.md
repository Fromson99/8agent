# 최신 메일 기준 전체 빌드 호환 패치

2026-09-10 발송한 `genos-semantic-backend-hash-fix-20260910.zip`을 기준으로 합니다.
기존 전체 빌드 ZIP은 로깅된 app.py를 알 수 없는 수정으로 판단하고 중단했습니다.
이번 패치는 최신 app.py/provider.py/pipeline.py/로깅 및 엔진 해시를 같은 버전으로 묶습니다.
최신 메일에 포함된 파일은 그대로 사용하며 알고리즘을 새로 바꾸지 않았습니다.
이미 같은 파일이면 유지합니다. genos.py는 현장에서 연결에 성공한 파일을 보존합니다.
키·URL·원본·Git·CURRENT는 변경하지 않습니다. 새 실행 코드를 추가해도 모델은 자동 호출하지 않습니다.

## 설치

두 첨부를 `/home/genos/DEV/TRANSFER`에 저장합니다.

```bash
(
  set -e
  cd /home/genos/DEV/TRANSFER
  base64 -d genos_apply_compatible.sh.b64.txt > genos_apply_compatible.sh
  GENOS_SCHEMA_BUILD_ROOT=/home/genos/DEV bash genos_apply_compatible.sh
)
```

unzip 불필요. 전체 대상과 엔진 해시를 확인한 뒤 백업/설치합니다.
알 수 없는 수정은 경로·해시를 한꺼번에 표시하고 코드 변경 전 중단합니다. 강제 덮어쓰기 옵션은 없습니다.
백업과 설치 영수증은 `runtime/patch-backups/genos-compatible-*`에 저장됩니다.
원본/환경변수는 그대로 유지하세요. 변경된 코드서빙 파일의 적용은 이후 커밋·push·재배포가 별도 필요합니다.

## 입력 점검 (모델 호출 없음)

```bash
cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_build_all.sh --run-id full-002 --check-only
```

내규는 `data/corpus/internal` 아래 하위 폴더까지, 외규는 `law,krx,kofia,expc,fsc,moleg,prec`의
manifest에 등록된 본문·첨부를 처리합니다. ZIP은 먼저 풀어야 합니다.

## 전체 실행

```bash
cd /home/genos/DEV
bash 06_TOOLS/COMMANDS/genos_build_all.sh --run-id full-002 --embed-batch-size 64 --max-calls 10000
```

`GENOS_LLM_REVISION`은 기존 실제 배포 리비전으로 설정돼 있어야 합니다. 모델/서빙 ID를 임의로 대신 넣지 않습니다.
GENOS LLM/임베딩 연결 환경변수는 기존 값을 유지합니다. 코드서빙 답변 백엔드는 최신 메일대로
`SEMANTIC_LLM_BACKEND=genos`를 사용합니다. 이 전체 빌드 명령은 명시적 GENOS 오프라인 빌드입니다.
순서: 입력 점검 → 전체 구조화 → LLM 스키마 추출·검토·재추출 → 임베딩 64개씩 → SQLite DRAFT 적재.
`--build-dir`은 자동 지정합니다. 이전 패치의 `full-001` 결과는 삭제하지 말고 새 ID로 실행하세요.

## 진행/오류 로그와 재개

```bash
tail -n 100 -f /home/genos/DEV/data/logs/full-002/progress.log
```

결과는 `data/builds/full-002/result.json`과 `generation/`입니다. `ok: true`여야 완료입니다.
LLM 개별 요청/응답은 `provider/`, 작업 실패는 `queue/queue.sqlite`에 남습니다.
로그에는 내부 문서가 포함될 수 있으니 외부 공유하지 마세요.

```bash
bash /home/genos/DEV/06_TOOLS/COMMANDS/genos_build_all.sh --run-id full-002 --resume --embed-batch-size 64 --max-calls 10000
```

실제 빌드가 시작된 후 중단됐을 때만 --resume을 사용합니다. 입력 점검에서만 실패했다면 일반 명령으로 재실행합니다.
원본·스키마·코드·모델 변경은 새 실행 ID가 필요합니다. 호출 예산/재시도 한도에 도달하면 오류를 확인하세요.
기존 서비스/CURRENT는 자동 교체하지 않습니다. 실제 현장 전체 데이터의 성공·품질은 로컬 테스트로 보장하지 않습니다.
