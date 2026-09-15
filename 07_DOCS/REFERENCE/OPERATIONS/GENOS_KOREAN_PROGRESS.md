# GENOS 한글 진행상황 로그

기본 터미널은 한글 요약이다. 원래 마스킹된 상세 로그/traceback은 삭제하지 않는다.
--verbose를 추가하면 터미널에도 원래 상세 로그를 출력한다.

- [문서 시작] 현재 문서 순번/파일. 순번은 완료율이 아니다.
- [청크] 해당 문서의 검토 통과/실패/미완료, 추출 또는 리뷰의 시도 횟수와 다음 상태.
- [문서 적재 집계] 최종 적재 통과/건너뜀/대기. 청크 리뷰 통과와 문서 적재는 다르다.
- [진행 확인] 마지막으로 관찰한 단계·문서·전체 경과시간·마지막 로그 이후 시간.
  heartbeat는 로컬 실행 확인이며 원격 모델 내부 진행률/정상 상태를 보장하지 않는다.
- 오류: 한글 원인 분류 + 확인할 조치. 원인을 확정 못하는 오류는 상세 로그 확인 안내.
- [종료] 성공/일부 건너뜀/실패/중단/입력 점검을 구분한다. 점검을 적재 완료로 표시하지 않는다.

## 설치

현재 파이프라인을 Ctrl+C로 중단하고 종료를 확인한 뒤 ZIP/설치 TXT를 TRANSFER에 둔다.

```bash
cd /home/genos/DEV/TRANSFER &&
base64 -d genos_apply_korean_progress.sh.b64.txt > genos_apply_korean_progress.sh &&
bash genos_apply_korean_progress.sh --install-only
```

이전 JSON/출력 길이/내규 제외 패치를 포함한다. URL/키/현장 genos.py/의존성/원본/Git/
CURRENT/과거 빌드를 보존한다. 알 수 없는 현장 수정은 설치 전에 거절한다.
백업은 runtime/patch-backups/genos-compatible-*이며 scoped 파일만 복구하여 롤백한다.

## 실행

코드 지문이 바뀌므로 이전 빌드에 --resume하지 말고 새 external-log-001을 사용한다.
이 ID도 기존에 사용했다면 다른 새 ID를 쓴다.

```bash
cd /home/genos/DEV &&
bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id external-log-001 --exclude-internal --check-only
```

```bash
cd /home/genos/DEV &&
bash 06_TOOLS/COMMANDS/genos_data_e2e.sh --run-id external-log-001 --exclude-internal --execute --segment-chars 1500 --max-tokens 8192 --max-output-tokens 32768 --embed-batch-size 64 --max-calls 10000
```

이번 버전으로 시작한 실행만 같은 명령에 --resume을 추가해 재개한다.
--verbose는 화면 표시만 바꾸며 입력/모델/검증/재시도 설정은 바꾸지 않는다.
32768 출력/컨텍스트 한도는 현장 모델 지원을 확인해야 한다. 이전 JSON 패치 가이드 참조.

## 다른 터미널에서 보기

한글 진행상황:

```bash
tail -f /home/genos/DEV/data/logs/external-log-001/console.log
```

현재 상태 한 번 보기 (DB 접속/모델 호출 없음):

```bash
python3 -m json.tool /home/genos/DEV/data/logs/external-log-001/current-status.json
```

상세 오류 마지막 100줄:

```bash
tail -n 100 /home/genos/DEV/data/logs/external-log-001/progress.log
```

events.jsonl은 기존 상세 로그 이벤트, attempt-*.json은 실행별 종료 기록이다.
current-status.json은 해당 run-id의 마지막 실행 시점 상태이며 이후 프로세스가 강제 종료되면
RUNNING으로 남을 수 있다. updated_at와 실제 프로세스 상태를 함께 확인한다.
로그에는 문서 제목/내용/내부경로가 포함될 수 있어 공유 전 확인한다.
모델 호출·검증 판단·실패 건너뜀·DRAFT 적재·운영 비활성 정책은 변경하지 않았다.
