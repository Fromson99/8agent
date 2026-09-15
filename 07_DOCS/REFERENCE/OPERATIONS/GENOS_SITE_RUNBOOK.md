# GenOS 코드 서빙 현장 실행 가이드

> 2026-09-08 통합 패키지(service.py standalone) 배포는 [현재 코드 서빙 절차](GENOS_CODE_SERVING_CURRENT.md)를 먼저 따른다. 아래 구형 구조화 서비스/데이터 경로/스크립트는 현재 인계본에 그대로 적용하지 않는다.

이 문서의 목표는 GenOS 사이트에서 내부 Gitea 코드 서빙을 만들고, 반입한
코드 ZIP을 `main` 브랜치에 올린 뒤, `service.py`를 배포하여 `ping` 호출까지
한 번에 성공시키는 것이다.

> 핵심: GenOS 코드 서빙은 웹 화면에 ZIP을 직접 업로드해 실행하는 방식으로
> 문서화되어 있지 않다. 화면에서 코드 서빙과 내부 Gitea 저장소를 만든 뒤,
> 코드 스페이스 터미널에서 ZIP을 풀고 `git push origin main` 한 커밋을 배포한다.

공식 참조:

- [GenOS 코드 서빙](https://genos-docs.gitbook.io/default/basic-tutorials/guides/development/code_serving)
- [코드 서빙 생성](https://genos-docs.gitbook.io/default/basic-tutorials/guides/development/code_serving/create_code_serving)
- [코드 서빙 배포](https://genos-docs.gitbook.io/default/basic-tutorials/guides/development/code_serving/deploy_code_serving)
- [코드 서빙 활용](https://genos-docs.gitbook.io/default/basic-tutorials/guides/development/code_serving/usage_code_serving)

## 0. 현장에서 먼저 받을 값

GenOS 관리자 또는 배포 승인자에게 다음을 확인한다.

| 항목 | 예시/용도 |
|---|---|
| 코드 서빙 ID | 게이트웨이 URL에 사용 |
| 내부 Gitea clone URL | 코드 ZIP을 push할 저장소 |
| Python 이미지 | Python 3.11 또는 3.12 CPU |
| 인스턴스 타입 | 첫 배포는 CPU, 1 replica |
| 코드 서빙 인증키 | 배포 후 JSON 호출에 사용 |
| 영속 볼륨 경로 | 예: `/mnt/8-agent` |
| LLM/Embedding 서빙 ID·키 | 검색 후 답변 생성에 사용 |
| 배포 승인자 | 배포 신청을 실제 승인할 사람 |

LLM·Embedding·데이터가 아직 없어도 `ping` 과 `health`는 먼저 확인할 수 있다.

## 1. 반입 코드 ZIP 만들기

외부 개발 환경의 저장소 루트에서 실행한다.

```bash
python scripts/genos_preflight.py source

CODE_ZIP="var/out/ship/8agent-genos-$(date +%Y%m%d-%H%M).zip"
python scripts/code_ship.py pack --out "$CODE_ZIP"
python scripts/code_ship.py verify "$CODE_ZIP"
sha256sum "$CODE_ZIP" > "$CODE_ZIP.sha256"
```

`genos_preflight.py source --strict`는 Git 작업판이 깨끗하지 않으면 멈춘다. 반출할
미커밋 변경을 포함하려면 먼저 검토·커밋한 후 다음을 최종 관문으로 사용한다.

```bash
python scripts/genos_preflight.py source --strict
```

코드 ZIP은 `.env`, 인증키, 원문 PDF/HWP/DOCX, ADR 문서·산출물을 싣지 않는다.
정본 데이터는 `scripts/data_ship.sh` 묶음으로 별도 반입한다.

## 2. GenOS 화면에서 코드 서빙 생성

1. GenOS에 로그인한다.
2. `서빙 > 코드 서빙 > + 코드 서빙 생성`으로 이동한다.
3. 저장소 유형은 `내부 Gitea`를 선택한다.
4. 서빙 이름과 설명을 입력하고 생성한다.
5. 상세 화면에서 다음을 복사해 따로 보관한다.
   - Gitea clone URL
   - 코드 서빙 ID
   - 인증키 발급/확인 위치

외부 Git 연결은 현장망에서 URL·ID·PAT 검증이 된 경우에만 사용한다.

## 3. 코드 스페이스에서 ZIP을 Gitea에 push

GenOS 코드 스페이스 터미널을 열고, 반입한 ZIP의 절대경로와 Gitea URL을 넣는다.

```bash
export GENOS_GIT_URL='<코드 서빙 상세의 Gitea clone URL>'
export CODE_ZIP='<반입된 8agent-genos-*.zip 절대경로>'

python3 -m zipfile -t "$CODE_ZIP"
git clone "$GENOS_GIT_URL" 8-agent
python3 -m zipfile -e "$CODE_ZIP" 8-agent
cd 8-agent
chmod +x scripts/*.sh scripts/*.py

python3 scripts/genos_preflight.py source
git add .
git commit -m 'Deploy 8-AGENT to GenOS'
git push origin HEAD:main
git rev-parse HEAD
```

마지막 40자 커밋 해시를 복사한다. 배포 화면에서 이 해시를 선택해야 한다.

`git clone`한 디렉터리가 비어 있지 않으면 기존 내용을 삭제하지 말고 새 디렉터리에
clone한다. 기존 배포를 갱신하는 경우에는 직전 성공 커밋을 롤백 해시로 메모한다.

## 4. 데이터를 영속 볼륨에 복원

`ping` 만 먼저 보려면 이 단계를 배포 후로 미뤄도 된다. 검색·답변까지 보려면
데이터 ZIP 조각을 코드 스페이스의 한 디렉터리에 모은 뒤 실행한다.

```bash
export DATA_ZIP_DIR='<data_ship ZIP 조각을 모은 디렉터리>'
export PERSIST_ROOT='/mnt/8-agent'

scripts/data_ship.sh verify "$DATA_ZIP_DIR"
scripts/data_ship.sh unpack "$DATA_ZIP_DIR" --root "$PERSIST_ROOT" --dry-run
scripts/data_ship.sh unpack "$DATA_ZIP_DIR" --root "$PERSIST_ROOT"
```

코드 스페이스와 코드 서빙 인스턴스가 같은 볼륨을 보는지는 배포 후 `ls` 호출로
반드시 확인한다.

## 5. 배포 설정

코드 서빙 상세의 `배포`에서 다음을 입력한다.

| 화면 항목 | 설정 |
|---|---|
| 커밋 | 3단계의 `git rev-parse HEAD` 40자 해시 |
| 이미지 | Python 3.11 또는 3.12 CPU |
| 인스턴스 | CPU, 첫 배포 1개 |
| GPU | 없음. LLM/Embedding은 별도 서빙 사용 |
| 빌드 커맨드 | `python -m pip install -r requirements-serving.txt` |
| 시작 커맨드 | 비움. GenOS가 `service.py` 함수를 적재 |
| HA/자동 확장 | 첫 카나리에서 끔 |

### 최소 환경변수: `ping`/`health`만 확인

최소 기동은 기본 경로를 사용하므로 모델 키 없이도 가능하다. 다만 재배포 후
데이터를 보존하려면 처음부터 영속 경로를 넣는 것을 권장한다.

```text
STRUCTURE_STORE=/mnt/8-agent/data/structure
STRUCTURE_CUSTOM_DIR=/mnt/8-agent/data/custom
GLOSSARY_STORE=/mnt/8-agent/data/glossary.json
RAG_LINKS_STORE=/mnt/8-agent/data/links.json
RAG_LOG_DIR=/mnt/8-agent/data/rag
RAG_RULES_DIR=/mnt/8-agent/data/rules
RAG_VECTOR_STORE=/mnt/8-agent/data/embeddings/sections
OPS_DIR=/mnt/8-agent/data/ops
```

### 검색 + 답변 생성 환경변수

GenOS 환경 설정 탭에서 `*_KEY`는 잠금/비밀 값으로 넣는다.

```text
LLM_BACKEND=genos
GENOS_LLM_URL=https://<GenOS>/api/gateway/rep/serving/<LLM_ID>
GENOS_LLM_KEY=<LLM 서빙 인증키>
GENOS_LLM_MODEL=claude-haiku-4-5-20251001
GENOS_LLM_JSON_MODE=json_schema
GENOS_LLM_SCHEMA_PROFILE=reduced
GENOS_LLM_TEMPERATURE=0

EMBED_BACKEND=genos
GENOS_EMBED_URL=https://<GenOS>/api/gateway/rep/serving/<EMBED_ID>
GENOS_EMBED_KEY=<Embedding 서빙 인증키>
GENOS_EMBED_BATCH=64
```

GenOS LLM 서빙이 다른 모델 ID만 제공하면 연결 점검은 할 수 있지만, 제품 답변과
제품 context를 만드는 경로에는 사용하지 않는다.

## 6. 배포 신청·승인

1. 설정값과 커밋 해시를 다시 확인한다.
2. `배포 신청`을 누른다.
3. 승인 권한자가 `승인 > 승인`에서 해당 배포를 승인한다.
4. 상태가 운영/활성으로 바뀐 뒤 코드 서빙 인증키를 발급한다.
5. 컨테이너 로그에서 `service.py` import 오류와 pip 설치 실패가 없는지 확인한다.

## 7. 배포 즉시 확인

코드 스페이스 터미널 또는 GenOS 게이트웨이에 접근 가능한 PC에서 실행한다.

```bash
export GENOS_CODE_URL='https://<GenOS>/api/gateway/code_serving/<CODE_ID>/json'
read -rsp 'Code serving key: ' GENOS_CODE_KEY
export GENOS_CODE_KEY
echo

scripts/genos_call.sh ping
scripts/genos_call.sh health
scripts/genos_call.sh ls /mnt/8-agent/data
```

합격 기준:

- `ping`: `service` 값이 `8-AGENT`
- `health`: 밖의 `status=200`, 안의 `json.status=ok`
- `ls`: `exists=false`가 아니고 `structure`, `rag`, `embeddings` 등이 보임

데이터·Embedding·LLM까지 준비됐으면 이어서 실행한다.

```bash
scripts/genos_call.sh search '설명의무의 법적 근거'
scripts/genos_call.sh ask '신탁업자가 고유재산과 신탁재산을 구분해야 하는 근거는?'
```

합격 기준:

- `search`: 밖의 `ok=true`, hit/ref 1개 이상
- `ask`: 밖의 `ok=true`, `answer`가 비어 있지 않고 `refs`가 있음

GenOS 인스턴스 터미널에 접근할 수 있으면 상류 서빙까지 직접 점검한다.

```bash
python scripts/genos_preflight.py runtime --strict --probe-upstreams
```

## 8. 프론트 없이 작은 파일 카나리

JSON/base64 부풀림과 게이트웨이 한계 때문에 500KB 이하 파일만 쓴다.

```bash
scripts/genos_call.sh upload ./sample.pdf '현장-카나리'
scripts/genos_call.sh search '샘플 문서의 핵심 용어'
```

큰 파일은 게이트웨이로 보내지 말고 `data_ship.sh`, 영속 공유 볼륨 또는 코드
스페이스에서 `scripts/onsite.sh process <경로>`를 사용한다.

## 9. 현황 보고서·백업

```bash
scripts/genos_call.sh report | python3 -c \
  'import json,sys; print(json.load(sys.stdin)["html"])' > genos-status.html
```

공유 볼륨에 배포 전 스냅샷을 남긴다.

```bash
cat > snapshot.json <<'JSON'
{"op":"snapshot_to","path":"/mnt/8-agent/backups/before-deploy.tar.gz"}
JSON
scripts/genos_call.sh file snapshot.json
```

## 10. 실패할 때 보는 순서

| 현상 | 우선 확인 |
|---|---|
| 빌드 실패 | Python 버전, `requirements-serving.txt`, 사내 wheel index, CPU torch/docling 이미지 |
| `service.py` 적재 실패 | 저장소 루트에 `service.py` 존재, 최상위 `async service(config, data)` |
| 401/403 | 코드 서빙 키와 LLM 서빙 키를 혼동하지 않았는지 |
| `ping` 성공, `health` 실패 | FastAPI/docling/PyMuPDF/python-multipart import 로그 |
| `ls`에서 볼륨 안 보임 | 코드 스페이스와 서빙 인스턴스의 마운트 경로 불일치 |
| 검색 0건 | `STRUCTURE_STORE`, `RAG_VECTOR_STORE`, 데이터 ZIP 복원 위치 |
| Embedding 401/400 | 전용 키, `/v1/models`, `/v1/embeddings` 계약, 색인·질의 모델 일치 |
| LLM 401/400 | 전용 키, 모델 ID, `GENOS_LLM_JSON_MODE=prompt` 강등 필요 여부 |
| 요청 timeout | `GENOS_CALL_TIMEOUT`, LLM 서빙 로그, 문서 파싱 크기 |

코드 장애는 직전 성공 커밋을 다시 배포해 롤백한다. 데이터 스키마 변경이
포함된 배포는 반드시 먼저 `snapshot_to`를 실행한다.

## 현장 종료 전 체크리스트

- [ ] 배포 커밋 40자 해시 기록
- [ ] 코드 ZIP·데이터 ZIP SHA-256 기록
- [ ] `ping`, `health`, `ls` 응답 저장
- [ ] 검색·답변 카나리 응답 저장
- [ ] 직전 성공 커밋(롤백 대상) 기록
- [ ] 영속 볼륨 마운트 경로 기록
- [ ] 인증키·`.env`·LLM 요청/응답 로그가 반출물에 없음
