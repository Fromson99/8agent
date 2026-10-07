# GENOS v5 환경변수·색인 로그·공유 세대 패치노트

작성일: 2026-09-22. 이 문서는 코드스페이스와 코드서빙에 반입할 작업 코드의 변경 사항이다.
외부 WSL에서 계약 테스트를 통과했으며, 망분리 GENOS 배포와 내부 모델 답변은 현장 검증 전이다.

## 바뀐 동작

- `GENOS_GENERATION`으로 명시한 GENOS 세대의 `legal-agent-tools-v5`는 코드서빙 환경변수로 모델을 메모리에서 결속한다. `LEGAL_AGENT_PROFILE` JSON 파일은 선택 사항이며, 파일 경로와 SHA256을 둘 다 지정했다면 기존 파일 결속이 우선한다. 로컬 활성 릴리스의 고정 프로필은 변경하지 않는다.
- 색인 실행에는 이미 `RELEASE INDEX`·`GENERATION` 단계 로그, 문서 20건마다 `Indexed documents N`, navigation 생성 중 30초마다 `compile-navigation.working`이 있다. 30초 로그는 경과 시간, SQLite에 확정된 문서 수, 파일 크기를 보여준다. 문서 수가 전부 차도 참조·용어 연결과 검증이 남을 수 있으므로 완료율이나 ETA로 해석하지 않는다. 이 로그는 새로 시작한 프로세스에서만 보인다.
- `document-release publish-shared`는 완료된 reviewed 또는 unreviewed release를 검증한 뒤 generation만 지정한 공유 볼륨에 복사한다. 전체 파일 해시와 서빙 자산을 확인하고, 기존 결과를 덮어쓰거나 `CURRENT`를 바꾸지 않는다. 검토 보류 세대와 검토 완료 세대는 별도 경로를 쓴다.

## 먼저: 코드와 데이터 확인

패치 ZIP을 기존 r2 코드가 설치된 코드스페이스 `~/DEV/TRANSFER`에 업로드한다.
기존 코드 파일을 백업한 뒤 `~/DEV` 루트에서 압축을 푼다. ZIP 항목은 루트 상대 경로다.

```bash
cd -P ~/DEV
backup="TRANSFER/backup-env-nfs-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup"
cp --parents -p service.py 02_BACKEND/lawrag/pipeline/document_release.py \
  02_BACKEND/lawrag/pipeline/term_generation.py "$backup"/
python3 -m zipfile -e TRANSFER/8agent-genos-v5-env-nfs-patch-20260922.zip .
python3 -m py_compile service.py 02_BACKEND/lawrag/pipeline/document_release.py
```

Jupyter 셸의 환경변수는 코드서빙에 자동 전달되지 않는다. `01_DATA`와 `.env`는 ZIP에 포함되지 않는다. 기존 색인 프로세스는 구 코드를
계속 사용하므로 새 로그가 필요하면 새 실행으로 시작해야 한다. 코드 해시가 결속된 미완료
run의 `index`를 새 코드로 이어 실행하면 계획 불일치가 날 수 있다. 기존 프로세스는 먼저
상태·PID·최근 로그를 확인하고, 새 코드를 쓰는 새 색인은 새 run ID로 실행한다.

기존 smoke release가 완성됐다면 모델 호출이나 재색인 없이 NFS 발행부터 시험할 수 있다. `--shared-root`는 코드스페이스와 코드서빙 양쪽에서 같은 경로로 읽히는 기존 디렉터리여야 한다. 아래 경로는 이전 현장 관찰에 근거한 예시이며 쓰기·읽기 권한은 현장에서 확인한다.

```bash
python3 06_TOOLS/pipeline.py document-release verify \
  --release 01_DATA/TERM_RELEASES/smoke-20260922-150608/serving-unreviewed
python3 06_TOOLS/pipeline.py document-release publish-shared \
  --release 01_DATA/TERM_RELEASES/smoke-20260922-150608/serving-unreviewed \
  --shared-root /nfs-root/diamo/8-agent/term-releases
```

출력의 `generation_path`를 코드서빙의 `GENOS_GENERATION`에 지정한다. `ls -ld`와 `ls -l`로 코드서빙에서 `manifest.json`을 읽을 수 있는지 확인한다. 이 경로는 기존 수동 사본 경로와 다를 수 있으며, 출력값을 그대로 쓴다. `published:true`는 NFS 복사·검증 결과이며 코드서빙 배포 성공이나 워크플로우 답변 성공이 아니다.

## 코드서빙 모델 설정과 워크플로우 smoke

코드서빙 환경 설정에 `GENOS_GENERATION`과 다음 값을 넣고 새 리비전을 배포한다.

```text
SEMANTIC_LLM_BACKEND=genos
GENOS_BASE_URL=<현장 내부 게이트웨이 주소>
GENOS_LLM_SERVING_ID=<현장 내부 서빙 ID>
GENOS_LLM_KEY=<현장 내부 인증키; 비밀값으로 등록>
GENOS_LLM_MODEL=<선택 사항; /models에 여러 모델이 있을 때 명시>
GENOS_RAG_MAX_OUTPUT_TOKENS=<선택; v5 모델 호출 1회당 max_tokens, 기본 6400>
```

`GENOS_RAG_IMPLEMENTATION`은 설정하지 않는다. 현재 MAIN의 `00_SYSTEM/PIPELINE.json`이 `legal-agent-tools-v5`를 선택한다. 예전 override 값이 남아 있다면 코드서빙 환경에서 제거한다. `GENOS_LLM_URL`을 쓰는 직접 접속이면 BASE_URL·SERVING_ID 대신 그 URL을 설정한다. `GENOS_LLM_PROFILE`은 현행 v5가 읽지 않는다. 환경변수 결속을 쓰려면 기존 `LEGAL_AGENT_PROFILE`과 `LEGAL_AGENT_PROFILE_SHA256`은 둘 다 제거한다. 서비스 시작 시 `/models`로 선택 모델의 게시 상태를 확인한다. `GENOS_LLM_MAX_INPUT_BYTES`는 필요 없으며, 입력 크기 보호값은 v5 프로필에서 코드가 계산한다. 이 값은 실제 모델의 토큰 문맥 한도 검증을 대신하지 않는다.

워크플로우 테스트 창에서 먼저 `{"question":"자료 목록","use_llm":false}`로 공유 세대 검색을 확인하고, 그 뒤 작은 근거 질문에 `use_llm:true`를 지정한다. 첫 요청이 200이어도 의미 답변 E2E는 두 번째 요청 결과·코드서빙 로그에서 확인해야 한다. 모델/토큰 제한·게이트웨이 오류가 나오면 같은 리비전의 코드서빙 로그를 남긴다.

## 야간 전체 색인

이미 준비한 run이 구 코드로 진행 중이면 무조건 중단하지 않는다. 새 코드로 새 run ID를 준비한 뒤 `document-release index`를 실행하고, 완료 후 `verify` → `publish-shared` 순서로 진행한다. 검토를 보류한다면 기존 `--skip-meaning-review --skip-review-reason` 계약을 사용하고 `SKIPPED`, `canonical_approval:false`, `quality_certified:false` 상태를 유지한다. 새 세대는 워크플로우 테스트가 끝날 때까지 기존 코드서빙 `GENOS_GENERATION`과 CURRENT를 자동 교체하지 않는다. 진행 출력은 별도 파일로 보존할 수 있다.

```bash
RUN_ID='new-prepared-run-id'
mkdir -p 01_DATA/LOGS
set -o pipefail
python3 -u 06_TOOLS/pipeline.py document-release index \
  --run-id "$RUN_ID" --skip-meaning-review \
  --skip-review-reason '의미 검토 보류' 2>&1 | tee "01_DATA/LOGS/${RUN_ID}-index.log"
python3 06_TOOLS/pipeline.py document-release verify \
  --release "01_DATA/TERM_RELEASES/${RUN_ID}/serving-unreviewed"
python3 06_TOOLS/pipeline.py document-release publish-shared \
  --release "01_DATA/TERM_RELEASES/${RUN_ID}/serving-unreviewed" \
  --shared-root /nfs-root/diamo/8-agent/term-releases
```

`RUN_ID`는 실제 새 선택·통합·준비가 끝난 ID로 바꿔야 한다. 준비 없이 index만 호출하면 거절된다. 검토 완료 경로는 `--skip-meaning-review`를 빼고 release 인자를 `01_DATA/TERM_RELEASES/$RUN_ID`로 바꾼다.

## 검증과 원복

외부 WSL에서 관련 계약 테스트 86개가 통과했다. NFS 복사본 손상·재실행·기존 세대 유지 계약을 테스트했다. 실제 현장 NFS 권한·모델 호출·워크플로우 결과는 미확인이다. 원복은 코드서빙을 이전 코드 리비전과 이전 `GENOS_GENERATION` 값으로 되돌려 재배포한다. 공유 경로와 이전 세대는 삭제하지 않는다.
