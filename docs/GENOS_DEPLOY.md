# GenOS 코드 서빙 배포 런북

바로 반입·배포하거나 curl 명령을 복사하려면 먼저
[GENOS_QUICKSTART.md](GENOS_QUICKSTART.md)를 본다. 이 문서는 선택 이유와 운영 상세를
설명하는 확장판이다.

이 문서는 저장소의 현재 구현을 GenOS에 처음 올리고, 데이터·모델 연결·카나리·
롤백까지 한 번에 수행하는 실행 순서다. 망분리 상태·스냅샷·아웃박스의 상세 규약은
[OPS_TRANSPORT.md](OPS_TRANSPORT.md)가 정본이다.

공식 문서 기준:

- [코드 서빙 생성](https://genos-docs.gitbook.io/default/basic-tutorials/guides/development/code_serving/create_code_serving)
- [코드 서빙 배포](https://genos-docs.gitbook.io/default/basic-tutorials/guides/development/code_serving/deploy_code_serving)
- [코드 서빙 활용](https://genos-docs.gitbook.io/default/basic-tutorials/guides/development/code_serving/usage_code_serving)
- [컨테이너 서비스](https://genos-docs.gitbook.io/default/basic-tutorials/guides/development/code_serving/container_service)
- [실행 확장(HA)](https://genos-docs.gitbook.io/default/basic-tutorials/guides/development/code_serving/ha-autoscale)

## 0. 이번 배포의 모드

첫 배포는 **GenOS 단일 JSON 게이트웨이 모드**로 한다. 저장소 루트의
`service.py`가 `async def service(config, data)`를 제공하고, 그 한 문에서 내부
FastAPI 앱을 ASGI로 호출한다.

```
GenOS gateway /code_serving/<ID>/json
        └─ service.py
             └─ op=call → lawrag.api.structure_app 전체 라우터
```

이 모드에서는 `scripts/serve.sh`나 별도 uvicorn 프로세스를 시작하지 않는다. GenOS가
`service.py` 함수를 적재한다. 브라우저 UI·Swagger·임의 HTTP path는 이 게이트웨이로
직접 노출되지 않는다.

GenOS의 워크플로우/전처리기/MCP **컨테이너 서비스**로 노출할 때는 별도 단계로 한다.
그 경우 시작 커맨드는 다음 앱을 가리킬 수 있지만, `/chat` 등 GenOS 타입별 요청·응답
어댑터를 먼저 검증해야 한다.

```bash
uvicorn lawrag.api.structure_app:app --host 0.0.0.0 --port "$PORT"
```

## 1. 소스 판 확정

```bash
cd <저장소>
python scripts/genos_preflight.py source
git status --short
```

`--strict`는 경고도 실패로 판정한다. 배포할 변경만 검토·stage·commit한다. 원본 은행
문서가 포함된 내부 전용 브랜치를 공개 원격에 push하지 않는다. strict 최종 점검은 아래
GenOS 원격을 등록한 뒤 실행한다.

```bash
git rev-parse HEAD       # 이 40자리 커밋을 배포 신청에 사용
```

## 2. GenOS 코드 서빙 생성과 Git

1. `서빙 > 코드 서빙 > 코드 서빙 생성`으로 들어간다.
2. 폐쇄망 본선은 **내부 Gitea**를 우선한다. 외부 Git이면 URL·ID·PAT 검증을 통과한다.
3. 생성된 저장소 주소를 별도 remote로 등록한다. `GENOS_GIT_URL`에는 UI가 보여 준
   실제 주소를 넣는다.

```bash
git remote add genos "$GENOS_GIT_URL"       # 이미 있으면 set-url
python scripts/genos_preflight.py source --strict
git push genos <배포브랜치>
```

현재 로컬의 `origin` 이름을 재사용하지 않는다. 어느 원격에 무엇을 보냈는지 분리해서
공개 저장소 오발송을 막는다.

## 3. 환경 설정

### 빌드

- 언어/이미지: Python 3.11 또는 3.12 계열 CPU 이미지
- 빌드 커맨드:

```bash
python -m pip install --upgrade pip && python -m pip install -r requirements-serving.txt
```

`requirements-serving.txt`는 GenOS LLM·임베딩을 외부 서빙으로 호출하는 판이다.
`anthropic`, 로컬 `sentence-transformers`, pytest와 수집·컴파일 전용 패키지를 싣지
않는다. 문서 업로드/파싱 때문에 docling은 포함하며, docling의 PDF 레이아웃 모델은
torch를 끌 수 있다. 일반 PyPI의 GPU/CUDA 휠을 그대로 받으면 이미지가 매우 커지므로
GenOS 관리자가 제공하는 CPU torch/docling 이미지 또는 사내 CPU wheel index를 우선한다.

### 비밀·모델 변수

환경 설정 탭에서 다음을 등록한다. `*_KEY` 값은 잠금 처리하며 Git에 넣지 않는다.

| 변수 | 값 |
|---|---|
| `LLM_BACKEND` | `genos` |
| `GENOS_LLM_URL` | `https://<GenOS>/api/gateway/rep/serving/<LLM ID>` |
| `GENOS_LLM_KEY` | LLM 서빙 인증키 — 코드 서빙 키와 별개 |
| `GENOS_LLM_MODEL` | 선택. 비우면 `/v1/models` 첫 모델 |
| `GENOS_LLM_JSON_MODE` | 우선 `json_schema`; 400이면 코드가 prompt로 강등 |
| `GENOS_LLM_SCHEMA_PROFILE` | 법률 조사 selector의 Qwen schema projection. 기본 `reduced`; engine이 전체 JSON Schema를 검증하면 `native` |
| `GENOS_LLM_TEMPERATURE` | `0` |
| `GENOS_USER_ID` | 선택. 이용 로그 사용자 ID |
| `EMBED_BACKEND` | `genos` |
| `GENOS_EMBED_URL` | `https://<GenOS>/api/gateway/rep/serving/<Embedding ID>` |
| `GENOS_EMBED_KEY` | 임베딩 서빙 인증키 |
| `GENOS_EMBED_MODEL` | 선택. 비우면 `/v1/models` 첫 모델 |
| `GENOS_EMBED_BATCH` | 우선 `64` |

### 영속 볼륨 변수

아래 `/mnt/8-agent`는 예시다. 코드 스페이스와 코드 서빙 컨테이너에 **같이 마운트된
실제 경로**로 바꾼다.

| 변수 | 예시 |
|---|---|
| `STRUCTURE_STORE` | `/mnt/8-agent/data/structure` |
| `STRUCTURE_CUSTOM_DIR` | `/mnt/8-agent/data/custom` |
| `GLOSSARY_STORE` | `/mnt/8-agent/data/glossary.json` |
| `RAG_LINKS_STORE` | `/mnt/8-agent/data/links.json` |
| `OPS_DIR` | `/mnt/8-agent/data/ops` |

영속 변수를 생략하면 저장소 안 `data/`를 쓰므로 첫 기동은 될 수 있어도 재배포 시
상태가 사라질 수 있다.

## 4. 데이터 반입

코드는 Git이 나르지만 `data/structure`, `glossary.json`, `links.json`, RAG 관측·규칙은
Git에서 제외된다. 보내는 쪽에서 현재 목록과 크기를 먼저 확인한다.

```bash
scripts/data_ship.sh list
scripts/data_ship.sh pack
# 결과: var/out/ship/8agent-data-<시각>/
```

받는 GenOS 코드 스페이스에서 첨부 zip을 한 폴더에 모은 뒤:

```bash
scripts/data_ship.sh verify <받은폴더>
scripts/data_ship.sh unpack <받은폴더> --root <영속볼륨의 저장소 뿌리> --dry-run
scripts/data_ship.sh unpack <받은폴더> --root <영속볼륨의 저장소 뿌리>
```

임베딩 벡터는 기본 반입하지 않는다. 색인과 질의 임베딩이 반드시 같은 모델이어야
하므로 GenOS 코드 스페이스에서 해당 서빙으로 다시 만든다.

```bash
export STRUCTURE_STORE=/mnt/8-agent/data/structure
export RAG_VECTOR_STORE=/mnt/8-agent/data/embeddings/sections
export GENOS_EMBED_URL='https://<GenOS>/api/gateway/rep/serving/<Embedding ID>'
export GENOS_EMBED_KEY='<인증키>'
python -m lawrag.core.terms embed-sections
```

## 5. 배포 신청

1. 코드 서빙 상세에서 **배포**를 누른다.
2. Python 이미지, CPU 인스턴스, 위에서 확정한 커밋 해시를 선택한다.
3. 처음에는 GPU 없이 인스턴스 1개로 시작한다. LLM·Embedding 계산은 별도 서빙이 한다.
4. 승인 권한자가 `승인 > 승인`에서 배포를 승인한다.
5. 컨테이너 로그에서 빌드·import 오류가 없는지 확인한다.

첫 배포에서는 HA를 고정 1개로 둔다. LLM 호출·문서 변환은 오래 걸릴 수 있고,
큐 기반 자동 확장은 요청/응답 1MB 및 처리 시간 제한이 있으므로 카나리 전에 켜지 않는다.
부하 시험 뒤 고정 복제본 또는 CPU 신호 자동 확장을 선택한다.

## 6. 배포 후 카나리

코드 서빙 상세의 인증 키를 발급한다. 호출하는 코드 스페이스/터미널에서만 다음 값을
설정한다.

```bash
export GENOS_CODE_URL='https://<GenOS>/api/gateway/code_serving/<코드서빙 ID>/json'
export GENOS_CODE_KEY='<코드 서빙 인증키>'
```

순서를 건너뛰지 않는다.

```bash
scripts/genos_call.sh ping
scripts/genos_call.sh health
scripts/genos_call.sh search '설명의무의 법적 근거'
scripts/genos_call.sh ask '신탁업자가 고유재산과 신탁재산을 구분해야 하는 근거는?'
```

합격 기준:

| 단계 | 합격 |
|---|---|
| `ping` | `service=8-AGENT`, 배포 커밋과 대응하는 rev/상태 |
| `health` | 바깥 `status=200`, 안쪽 `json.status=ok`, `fitz/docling=ok` |
| `search` | `ok=true`, 문서 수와 hit/ref가 1개 이상 |
| `ask` | `ok=true`, `answer` 비어 있지 않음, `refs` 존재, LLM 오류 없음 |

GenOS 런타임 터미널 접근이 가능하면 환경·모델 연결까지 한 번에 확인한다.

```bash
python scripts/genos_preflight.py runtime --strict --probe-upstreams
```

키 없이도 검색은 동작하지만 답변 합성은 동작하지 않는다. `ping`만 성공하고 `health`가
실패하면 대개 `fastapi`/`python-multipart`/문서 파서 의존성 문제다.

## 7. 운영과 롤백

- 코드 변경: 새 커밋 push → 해당 커밋으로 재배포 → 위 카나리 4단계 반복.
- 데이터 변경: 스냅샷/아웃박스 절차는 [OPS_TRANSPORT.md](OPS_TRANSPORT.md)를 따른다.
- 장애 롤백: 직전 성공 커밋(리비전)을 다시 배포하고, 영속 볼륨 데이터는 그대로 둔다.
- 데이터 스키마 변경이 섞인 배포는 배포 직전 `snapshot_to`로 볼륨에 스냅샷을 남긴다.
- 인증키는 로그·명령 인자·Git에 남기지 않고 GenOS 잠금 환경변수로만 관리한다.

## 외부 작업이 필요한 값

아래 값은 저장소에서 알아낼 수 없으므로 GenOS UI에서 확보해야 한다.

- 코드 서빙 저장소 URL과 코드 서빙 ID
- 사용할 Python 이미지/인스턴스 타입 이름
- 영속/공유 볼륨의 실제 마운트 경로
- LLM 서빙 ID·인증키
- Embedding 서빙 ID·인증키
- 코드 서빙 인증키
- 배포 승인자
