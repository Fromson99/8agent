# GENOS 데이터 ZIP만 생성 — R2

R1 대신 `GENOS_DATA_ZIP_ONLY_20261007_R2.txt` 한 개를 GENOS의 `~/DEV/TRANSFER`에 저장하고, `~/DEV` 터미널에서 실행한다.

```bash
bash TRANSFER/GENOS_DATA_ZIP_ONLY_20261007_R2.txt
```

검증한 도구가 TXT에 내장되어 있으며 `python3` 3.11 이상을 사용한다. 기본 generation은 `/nfs-root/diamo/8-agent/term-releases/financial-risk-success-20261005-schema-r2/generation`, runtime은 `/nfs-root/diamo/8-agent/runtime`이다. 선택한 generation의 상위 폴더와 runtime만 목록 검사한다. 코드 설치·Git 변경·push·배포는 실행하지 않는다.

완성 ZIP과 SHA256 파일은 `~/DEV/TRANSFER`에 생긴다. 터미널에 출력하는 실행 폴더의 `SOURCE_CHANGES.txt`와 `SOURCE_CHANGES.json`에서 추가·삭제·수정 경로 및 읽기 누락을 확인한다. 두 보고서는 ZIP 안에도 포함된다. 첫 목록은 `SOURCE_BEFORE.json.gz`에 보존한다. TXT 실행 시작 로그와 종료 상태는 TXT 옆 `data-zip-only-logs/run-*`에 남는다.

사진의 R1은 압축 후 입력 목록 변경을 발견하여 완성 ZIP을 발행하지 않았다. 그 로그에는 변경된 경로가 없어 실제 변경 위치는 아직 미확인이다. R2는 변경 경로를 기록하고 계속 압축한다. 실행 중 삭제되거나 읽기 권한이 없는 파일은 누락 경로와 오류 종류를 기록하며, 처음 목록을 만든 뒤 추가된 파일은 변경 보고서에만 남는다. 일반 파일은 열었을 때의 크기까지 읽어 계속 늘어나는 로그를 따라가지 않는다. 변경 판정은 경로·크기·수정 시각·inode·권한을 비교하며, 원본 전체를 다시 해시 검사하지 않는다.

계속 쓰는 SQLite는 읽기 전용 연결의 online backup으로 커밋된 DB 사본을 만들어 압축한다. 원본에 SQL 쓰기나 checkpoint를 하지 않는다. 해당 DB의 WAL·SHM·journal은 함께 복사하지 않는다. DB별 백업은 기본 60초 제한이며 실패하면 해당 DB를 누락으로 표시하고 ZIP은 완성한다. 선택 generation의 DB는 sidecar가 없으면 원래 바이트로 복사한다. manifest와 내부 해시는 다시 쓰지 않는다.

이 ZIP은 전체 파일이 한 시점의 상태라는 보장이 없다. ZIP 완성과 데이터 일관성·현장 배포 검증은 별도다. 보고서와 manifest에 이를 표시하며, 새 형식 `genos-rag-data-live-v2`를 사용한다. 복원 도구는 보고서 확인을 뜻하는 `--accept-live-archive`를 추가로 요구하고, 읽기 누락·목록 검사 오류·generation 해시 불일치가 있으면 복사를 시작하지 않는다. 현장 ZIP 생성만 요청된 작업이므로 TXT는 복원을 실행하지 않는다.

모의 데이터 계약 26개와 첨부 TXT 실제 실행 4개가 통과했다. 실제 파일의 동시 추가·수정·삭제와 SQLite WAL 커밋이 있는 상태에서 ZIP 완성, 경로 보고, DB 백업의 무결성을 확인했다. 기존 Git HEAD·스테이징 수정은 보존했다. `HANDOFF.json`은 TXT 및 내장 코드의 SHA256을 고정하며, `VALIDATION.json`은 검증 범위를 기록한다. 현재 Codex에서는 망분리 GENOS에 접근하지 않았으며 R2 현장 실행 결과는 미확인이다.
