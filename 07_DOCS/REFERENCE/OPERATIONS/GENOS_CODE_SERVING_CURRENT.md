# GENOS 코드 서빙 배포 — 현재 통합 패키지 기준

> GENOS 질문은 [GENOS.md](../../../GENOS.md)를 먼저 읽는다. 아래에는 여러 날짜의 설치본 이력이 함께 있다.
> 명령은 대상 설치본/배포 방식과 일치할 때만 사용한다. 현장 V1.8.6과 데모의 워크플로우 반환 규약 및
> 코드서빙 라우팅은 다를 수 있다. `/json`, 빈 시작 커맨드, 계정 비밀번호 인증을 모든 환경의 고정 규칙으로 보지 않는다.
> 코드스페이스 Python 3.11.15와 워크플로우 Python 3.10은 서로 다른 실행 환경의 기록이다.
> 최신 환경별 근거는 [현장 지식 보관본](../GENOS_UPSTREAM/7b42bc4cbf9b/knowledge.md)을 함께 확인한다.


## 2026-09-10 DOC/실패 건너뛰기 후속 패치

`genos-doc-skip-20260910.zip`은 최신 data-e2e 패치 위에 DOC 변환과 문서별 실패 격리를
추가한다. 기본 결과는 단일 generation이 아닌 `batch-result.json` + 문서별 DRAFT다.
이 catalog는 운영 CURRENT로 지정하지 않는다. DOC에는 현장 LibreOffice가 필요하다.
설치·실행·입력/E2E 비율·재개: [GENOS_DOC_SKIP.md](GENOS_DOC_SKIP.md).
OQL/답변/자동 서비스 전환은 포함하지 않는다. 이전 단일 빌드는 `--fail-fast`로 유지한다.

## 2026-09-10 데이터 적재 E2E 최신 인계

`genos-data-e2e-20260910.zip` + `genos_apply_data_e2e.sh.b64.txt`는 최신 Qwen 응답 수정과
이전 안전 설치본을 보존한다. `genos_data_e2e.sh`는 내규·외규 데이터 구축만 수행한다.
기본/--check-only는 입력 점검, --execute는 구조화·추출/검토·임베딩·DRAFT 적재다.
OQL/질문답변/운영 전환은 포함하지 않는다. 자세한 명령은 [GENOS_DATA_E2E_CURRENT.md](GENOS_DATA_E2E_CURRENT.md).

## 2026-09-10 최신 메일 기준 설치 호환성 (아래 과거 안내보다 우선)

`genos-all-corpus-compatible-20260910.zip` + `genos_apply_compatible.sh.b64.txt`는
최근 발송 `genos-semantic-backend-hash-fix-20260910.zip`의 코드/엔진 해시를 보존하면서
내규·외규 전체 빌드 CLI를 설치한다. 이전 `genos-all-corpus-20260909.zip`을 그 위에 적용하면
로깅된 app.py(`bc10f25f…`)를 미등록 현장 수정으로 거절하므로 구 설치기를 재실행하지 않는다.

- 코드 루트 `/home/genos/DEV`, 첨부 `/home/genos/DEV/TRANSFER`.
- 기존 `genos.py`는 보존한다. URL/키/원본/Git/CURRENT는 변경하지 않는다.
- 스키마/엔진 해시는 설치 전 전체 확인하며, 알 수 없는 수정은 한꺼번에 보고하고 중단한다.
- 런타임 로그 helper와 최신 engine manifest가 요구하는 정확한 dependency를 포함한다.
- 상세 설치·실행·로그·재개 명령: [GENOS_LATEST_COMPATIBLE.md](GENOS_LATEST_COMPATIBLE.md).
- 실제 현장 모델 호출·전수 데이터 실행 검증은 별도다. 서비스 적용은 커밋/push/재배포가 필요하다.

## 2026-09-09 브랜치 전송 패치 (아래 초기 ZIP 안내보다 우선)

`genos_branch_hotfix.sh`는 `fde/seungho/integration@87a28a18`의
`02-els-qa/core/genos.py` 호출 계약을 참고한다. 현장 연결 성공은 아직 미확인이다.

- URL·포트·키·서빙 ID는 사용자가 관리하며 패치가 변경하지 않는다.
- 게이트웨이는 `/serving/<ID>/models`, `/chat/completions`, `/embeddings`를 쓰며
  `/v1`을 자동 추가하지 않는다. 기존 `GENOS_LLM_API_PREFIX`/`GENOS_EMBED_API_PREFIX`는
  직결 서버용으로 보존한다. 게이트웨이 prefix는 `GENOS_GATEWAY_API_PREFIX`(기본 `none`)다.
- 전송은 `httpx`이고 환경 프록시/CA를 반영하며 리다이렉트는 추적하지 않는다. TLS 검증은 유지한다.
- 게이트웨이 `check(execute=True)`는 모델 목록 사전 조회 없이 POST하며,
  model은 기존 설정값 또는 브랜치처럼 `genos`를 사용한다. 제품 RAG 모델 정책은 변경하지 않는다.
- 알려진 ZIP/이전 requests 패치본의 함수 지문을 검증하고 원본을 백업한다.
  기본 실행은 패치 뒤 GET 모델 목록 점검만 한다. `--patch-only`는 네트워크 호출 없이 패치한다.
  기존 독립 점검 파일 대신 이번 패치에 내장된 httpx 점검을 사용한다.
- 원래 ZIP을 다시 만들거나 Git push/코드 서빙 재배포를 하지는 않는다.

상태: 2026-09-08 공식 문서와 ADR0259 인계 코드 확인. 현장 Python **3.11.15** 사용자 확인. GENOS 현장 배포 미실행.
적용: genos-integrated-20260908.zip, genos_install.sh.txt, service(config, data) 방식.
이 문서는 새 통합 패키지 배포의 시작점이다. 과거 MAIN/structure_app/data_ship 절차와 혼용하지 않는다.

## 1. 저장소 URL과 인증키의 역할

| 화면/정보 | 사용처 | 설정/행동 |
|---|---|---|
| 기본 정보 > 저장소 URL | 배포할 코드의 Git 저장소 | GENOS_GIT_URL, git clone/push |
| 내부 Gitea Git 인증 | 저장소 읽기/쓰기 | 공식 안내 기준 GENOS 로그인 ID·비밀번호; 현장 SSO/관리정책이 다르면 현장 방식 확인 |
| 외부 Git ID·크레덴셜(PAT) | 외부 Git 저장소 접근 | 생성/수정 화면에서 저장소 URL·ID·PAT 검증 |
| 인증 키 탭 | 배포된 코드 서빙 API 호출 | GENOS_CODE_KEY, Authorization: Bearer |
| 코드 서빙 ID | 호출할 앱 식별 | GENOS_CODE_URL의 code_serving/<ID>/json |
| Qwen/Gemma 모델 인증키 | 앱→LLM 요청 | GENOS_LLM_KEY |
| KURE 모델 인증키 | 앱→임베딩 요청 | GENOS_EMBED_KEY |

'인증키'라는 글자만으로 Git 비밀번호라고 판단하지 않는다. **인증 키 탭의 키는 코드 API 호출용**이다.
저장소 URL에 모델키/코드키를 붙이지 않는다. 실제 저장소 URL과 코드서빙 ID는 상세 화면 값을 쓴다.
ID226/325/19는 모델 서빙 ID이고, 앱의 코드 서빙 ID는 별도다.

## 2. 배포 흐름과 폴더

```text
메일 첨부파일 모음
 → genos_install.sh.txt: 합치기/해시/압축해제/설치/소량접속점검
 → genos-installed/genos-authoring (전체 인계본, 데이터·실행큐 보관)
 → 코드 파일만 내부 Git clone 폴더로 복사
 → git commit / push
 → 코드 서빙 화면: 해당 커밋 배포 신청/승인
 → GENOS_CODE_URL + GENOS_CODE_KEY로 ping/connections 확인
```

**코드 스페이스에 압축을 푸는 것만으로 배포 코드가 바뀌지 않는다.**
GENOS가 읽는 것은 연결된 Git 저장소의 선택한 커밋이다.
저장소 루트에 service.py와 requirements-serving.txt가 있어야 한다.
`repo/genos-authoring/service.py`처럼 한 단계 안쪽에 넣지 않는다.

```text
영속 인계/실행 폴더                     Git clone 폴더
 genos-installed/genos-authoring/       genos-code/
   service.py                           service.py
   data/structured-prellm.sqlite         requirements-serving.txt
   runs/authoring/                       02_BACKEND/, 00_SYSTEM/, ...
   runs/generations/draft-001/            (.env/SQLite/실행큐/가상환경 제외)
   .env (현장 키)
```

코드 스페이스와 코드 서빙 인스턴스는 서로 다른 파일시스템일 수 있다.
데이터 세대는 양쪽에서 보이는 영속 볼륨에 놓거나 코드서빙의 영속 볼륨으로 따로 복사한다.
코드 스페이스의 경로를 그대로 환경변수에 넣는 것만으로 공유되지는 않는다.

## 3. 인계본 압축 해제

첨부파일 전부와 설치SH를 한 폴더에 모은 뒤 실행한다.

```bash
bash genos_install.sh.txt
```

접속/패키지설치 전 압축만 풀려면 `--unpack-only`를 사용한다.
이 스크립트는 Git push 또는 플랫폼 배포 신청은 하지 않는다.
소량 접속검사는 LLM 1회/임베딩 1회이며 전수 authoring은 별도다.

## 4. 저장소 clone과 코드 복사

GENOS 코드 스페이스 터미널에서 실행한다. SRC는 실제 압축 해제된 경로로 바꾼다.

```bash
export GENOS_GIT_URL='<상세 화면의 실제 저장소 URL>'
export GENOS_SOURCE_DIR='/실제/경로/genos-installed/genos-authoring'
export GENOS_CODE_DIR="$PWD/genos-code"
git clone "$GENOS_GIT_URL" "$GENOS_CODE_DIR"
```

내부 Gitea에서 Username/Password를 묻는다면 GENOS 계정 인증을 사용한다.
코드 서빙 인증 키를 Git 비밀번호로 쓰지 않는다. 외부 Git은 해당 Git 서비스 계정/PAT를 쓴다.
처음에는 새 clone 폴더를 사용한다. 기존 저장소 갱신 시 기존파일 삭제/브랜치 변경을 임의로 하지 않는다.

다음은 패키지 manifest에 있는 코드만 복사하고 해당 파일만 stage한다. 키·데이터는 제외한다.

```bash
python3 - <<'PY'
import os, json, shutil, subprocess
from pathlib import Path, PurePosixPath
src=Path(os.environ['GENOS_SOURCE_DIR']).resolve()
dst=Path(os.environ['GENOS_CODE_DIR']).resolve()
if src==dst or src in dst.parents or dst in src.parents:
    raise SystemExit('인계 폴더와 Git 폴더는 서로 분리하세요.')
manifest=json.loads((src/'package-manifest.json').read_text())
paths=[]
for row in manifest['files']:
    rel=PurePosixPath(row['path'])
    if rel.is_absolute() or '..' in rel.parts:
        raise SystemExit('잘못된 manifest 경로')
    if rel.parts[0] in {'data','runs','.venv','.git'} or rel.name=='.env':
        continue
    source=src/rel; target=dst/rel
    target.resolve().relative_to(dst)
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)
    paths.append(str(rel))
subprocess.run(['git','-C',str(dst),'add','--',*paths],check=True)
PY
cd "$GENOS_CODE_DIR"
git diff --cached --stat
git commit -m 'Deploy GENOS semantic pipeline'
git push origin HEAD
git rev-parse HEAD
```

현재 branch와 push 결과를 확인하고 마지막 커밋 해시를 배포 화면에서 선택한다.
빈 저장소가 main을 요구하는 경우 현재 branch를 확인한 후 main으로 push한다. force push는 필요 없다.
Git에는 원문SQLite와 키를 올리지 않는다. 위 복사는 package-manifest.json 자체도 넣지 않으므로
Git checkout의 빌드는 아래 pip 명령을 사용한다. 전체 인계본용 setup.sh/verify_package.py는
원본 인계 디렉터리에서 실행한다.

## 5. 코드 서빙 화면 설정

| 항목 | 이번 패키지 설정 |
|---|---|
| 저장소 URL | 위 clone/push한 저장소 |
| 언어/이미지 | Python **3.11.15** (현장 확인) |
| 빌드 | python -m pip install -r requirements-serving.txt |
| 진입 계약 | 저장소 루트 service.py의 async service(config, data) |
| 시작 커맨드 | service 함수 방식의 플랫폼 기본 로더 사용. 별도 uvicorn 명령을 넣지 않음 |
| 배포 커밋 | 실제 push한 git rev-parse HEAD 값 |
| 승인 | 현장 승인 권한자가 처리 |

공식 환경 설정 화면은 범용 시작커맨드도 지원하지만, 이번 패키지는 service 함수 모드다.
현장 버전이 명시 시작커맨드를 요구하면 플랫폼의 Python service 기본값을 확인한다.
`python service.py`는 서버를 띄우는 명령이 아니다.

### 모델 접속용 환경변수/시크릿

```text
GENOS_BASE_URL=https://ai-platform-dev.ss.local:32154
GENOS_LLM_SERVING_ID=226
GENOS_LLM_KEY=<Qwen 모델 인증키>
GENOS_EMBED_SERVING_ID=19
GENOS_EMBED_KEY=<KURE 인증키>
```

Gemma든 Qwen이든 GENOS_LLM_SERVING_ID와 GENOS_LLM_KEY에 대상 서빙 값을 설정한다. 모델별 변수와 GENOS_LLM_PROFILE은 더 이상 사용하지 않는다.
MODEL이 비어 있으면 /v1/models의 모델이 하나인 경우만 자동 선택한다.
공식 경로는 `/v1`을 기본으로 한다. 현장 게이트웨이가 `/models`, `/chat/completions`,
`/embeddings`를 직접 노출한다고 확인된 경우에만 `GENOS_LLM_API_PREFIX=none`과
`GENOS_EMBED_API_PREFIX=none`을 설정한다.
코드 스페이스의 .env는 코드 서빙에 자동 전달되지 않는다. 플랫폼 환경변수에도 설정한다.
API 호출용 GENOS_CODE_KEY는 클라이언트에 둔다. 앱이 자신을 호출할 필요가 없다면 서버에 넣지 않는다.

### 구축 후 검색용 데이터 경로

```text
GENOS_GENERATION=<코드 서빙에서 보이는 실제 published generation 절대경로>
GENOS_RUNTIME_DIR=<코드 서빙이 쓸 수 있는 영속 실행기록 경로>
```

GENOS_GENERATION은 structured-prellm.sqlite 파일이 아니라 publish 결과 디렉터리다.
ping/connections는 이 데이터 없이 가능하다. health와 검색은 해당 세대가 필요하다.
세대 manifest는 첫 health/검색 요청 때 검증한다. 경로가 없거나 계약이 맞지 않으면 프로세스를
죽이는 대신 세부 내부경로를 숨긴 분류된 503을 반환한다.
벡터색인 생성/연결과 RAG 답변용 SEMANTIC_LLM_ENDPOINT는 별도 단계이며 이번 접속설정만으로 완성되지 않는다.

## 6. 배포 후 코드 서빙 키로 호출

호출하는 코드 스페이스/터미널의 .env 또는 환경변수에 설정한다.

```bash
export GENOS_CODE_URL='https://ai-platform-dev.ss.local:32154/api/gateway/code_serving/<실제 코드 서빙 ID>/json'
read -rsp '코드 서빙 인증키: ' GENOS_CODE_KEY
export GENOS_CODE_KEY
printf '\n'
```

인계본 폴더에서 `bash genos_smoke.sh`를 실행하면 원격 코드 서빙을 통해 모델목록을 확인한다.
`bash genos_smoke.sh --execute`는 모델 생성/임베딩을 각1회 확인한다.
반환값은 `status`와 `body`이며 body.ok가 true인지 확인한다.
직접 호출할 때는 `{"op":"ping"}`, `{"op":"connections"}`를 사용한다. GENOS 화면의
표준 envelope가 필요한 경우 `{"API_TYPE":"PING"}`, `{"API_TYPE":"CONNECTIONS"}`도 동일하게 지원한다.
GENOS_CODE_URL이 비어 있으면 동일 service 함수를 로컬로 호출하므로 원격 배포 검증으로 보지 않는다.

## 7. 오류 분류

| 현상 | 우선 확인 |
|---|---|
| git clone/push 인증 실패 | Git URL, GENOS/Git 계정, PAT; 코드API키와 혼동 여부 |
| 배포 커밋이 없음 | 올바른 저장소와 branch에 push했는지 |
| service.py를 못 찾음 | Git 저장소 루트에 들어갔는지 |
| 게이트웨이401/403 | GENOS_CODE_KEY와 코드서빙 ID |
| body 안 llm/embed FAIL | 각각의 모델키, 모델 서빙ID, 내부주소, /models |
| 로컬은 성공하고 코드 서빙은 실패 | 배포환경 변수, 네트워크, 영속볼륨 차이 |
| health503 | GENOS_GENERATION 미설정/세대경로 접근실패/코드계약불일치 |

## 8. 근거와 유지 규칙

- [공식 코드 서빙 생성](https://genos-docs.gitbook.io/default/basic-tutorials/guides/development/code_serving/create_code_serving.md): 내부Git 인증, 외부PAT, 화면별 역할.
- [공식 코드 서빙 활용](https://genos-docs.gitbook.io/default/basic-tutorials/guides/development/code_serving/usage_code_serving.md): service 함수, push한커밋 배포, Bearer 호출.
- [공식 코드 서빙 배포](https://genos-docs.gitbook.io/default/basic-tutorials/guides/development/code_serving/deploy_code_serving.md): 커밋선택·승인.
- [ADR0259 인계](../../../04_EXPERIMENTS/ADR/ADR-0259-genos-split-mail-installer/README.md): 통합 패키지 및 설치 범위.

비밀번호·API키·PAT의 실제 값은 이 문서/위키/ZIP에 기록하지 않는다.
후속 agent는 GENOS 배포 질문에서 이 문서를 먼저 읽고, 실제 저장소URL/서빙ID를 추정하지 않는다.

## Python3.11.15 의존성 수정

ADR0263: 이전numpy2.5.1핀은Python>=3.12로현장과호환되지않았다. 기본설치는jsonschema/referencing/requests/python-dotenv/fastapi/httpx만사용한다. 로컬벡터용numpy/torch/sentence-transformers,단독서버uvicorn,외부AnthropicSDK는선택설치다.
