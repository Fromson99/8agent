# GenOS 반입·가동 — 복붙용 1장

GenOS 사이트의 화면 순서, Gitea push, 배포 필드, 트러블슈팅까지 현장에서
차례로 따라하려면 [GENOS_SITE_RUNBOOK.md](GENOS_SITE_RUNBOOK.md)를 먼저 본다.
최초 배포 뒤의 코드 갱신은 [GENOS_PATCH_UPDATE.md](GENOS_PATCH_UPDATE.md)를 따른다.

## 결론

- **코드 ZIP을 GenOS에 바로 배포하는 것은 아니다.** ZIP 반입 → 코드 스페이스에서
  내부 Gitea 저장소에 push → 코드 서빙 화면에서 그 커밋을 배포한다.
- 코드 ZIP에는 실행 코드만 있다. 검색 문서·색인은 `data_ship.sh` ZIP으로 따로 반입한다.
- `.env`, 인증키, `.git`, 가상환경, 원문 PDF/HWP/DOCX는 코드 ZIP에서 자동 제외된다.

## 1. 밖에서 반입 파일 만들기

저장소 루트에서 그대로 실행한다.

```bash
python scripts/genos_preflight.py source
CODE_ZIP="var/out/ship/8agent-code-$(date +%Y%m%d-%H%M).zip"
python scripts/code_ship.py pack --out "$CODE_ZIP"
python scripts/code_ship.py verify "$CODE_ZIP"
sha256sum "$CODE_ZIP"
```

검색 데이터도 필요하면 별도로 만든다.

```bash
scripts/data_ship.sh list
scripts/data_ship.sh pack
```

반입 신청에는 다음을 서로 구분해 첨부한다.

1. `8agent-code-*.zip` — 코드
2. `var/out/ship/8agent-data-*/*.zip` — 문서·검색 데이터
3. 각 파일의 SHA256

코드 ZIP만 넣어도 `ping`과 `health`는 확인할 수 있지만, 데이터 ZIP/영속 볼륨이 없으면
검색 결과가 비거나 답변 근거가 나오지 않는다.

## 2. GenOS 코드 스페이스에서 Git에 올리기

GenOS 화면에서 `서빙 > 코드 서빙 > 코드 서빙 생성 > 내부 Gitea`로 저장소를 먼저 만든다.
ZIP과 저장소 URL을 받은 뒤 실행한다.

```bash
export GENOS_GIT_URL='<코드 서빙 상세의 저장소 URL>'
export CODE_ZIP='<반입된 8agent-code-*.zip 절대경로>'

python -m zipfile -t "$CODE_ZIP"
git clone "$GENOS_GIT_URL" 8-agent
python -m zipfile -e "$CODE_ZIP" 8-agent
cd 8-agent
chmod +x scripts/*.sh scripts/*.py
python scripts/genos_preflight.py source
git add .
git commit -m 'Deploy 8-AGENT to GenOS'
git push origin HEAD:main
git rev-parse HEAD
```

마지막 `git rev-parse HEAD`의 40자리 해시를 배포 화면에서 선택한다.

## 3. 데이터 ZIP 풀기

공유/영속 볼륨이 `/mnt/8-agent`인 예시다. 실제 경로로 바꾼다.

```bash
export DATA_ZIP_DIR='<data_ship ZIP을 한곳에 모은 디렉터리>'
scripts/data_ship.sh verify "$DATA_ZIP_DIR"
scripts/data_ship.sh unpack "$DATA_ZIP_DIR" --root /mnt/8-agent --dry-run
scripts/data_ship.sh unpack "$DATA_ZIP_DIR" --root /mnt/8-agent
```

## 4. 코드 서빙 환경 설정

- 언어: Python 3.11 또는 3.12 CPU
- 빌드 커맨드: `python -m pip install -r requirements-serving.txt`
- 시작 커맨드: 비움 (`service.py` 함수 서빙)
- 첫 배포: 인스턴스 1개, HA/자동 확장 끔

필수 환경변수는 GenOS 화면에서 잠금 값으로 입력한다.

```text
LLM_BACKEND=genos
GENOS_LLM_URL=https://<GenOS>/api/gateway/rep/serving/<LLM_ID>
GENOS_LLM_KEY=<LLM 인증키>
EMBED_BACKEND=genos
GENOS_EMBED_URL=https://<GenOS>/api/gateway/rep/serving/<EMBED_ID>
GENOS_EMBED_KEY=<Embedding 인증키>
STRUCTURE_STORE=/mnt/8-agent/data/structure
STRUCTURE_CUSTOM_DIR=/mnt/8-agent/data/custom
GLOSSARY_STORE=/mnt/8-agent/data/glossary.json
RAG_LINKS_STORE=/mnt/8-agent/data/links.json
OPS_DIR=/mnt/8-agent/data/ops
```

배포 화면에서 CPU 이미지·인스턴스·커밋 해시를 선택해 신청하고 승인받는다.

## 5. 프론트 없이 curl로 확인·운영

공통값을 먼저 넣는다. 키는 명령행에 직접 적지 않는다.

```bash
export GENOS_CODE_URL='https://<GenOS>/api/gateway/code_serving/<CODE_ID>/json'
read -rsp 'Code serving key: ' GENOS_CODE_KEY; export GENOS_CODE_KEY; echo
```

### 기동 확인

```bash
curl --fail-with-body --silent --show-error --max-time 60 \
  "$GENOS_CODE_URL" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $GENOS_CODE_KEY" \
  --data-binary '{"op":"ping"}' | jq .
```

### 애플리케이션·파서 확인

```bash
curl --fail-with-body --silent --show-error --max-time 120 \
  "$GENOS_CODE_URL" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $GENOS_CODE_KEY" \
  --data-binary '{"op":"call","method":"GET","path":"/health"}' | jq .
```

### 영속 볼륨 확인

```bash
curl --fail-with-body --silent --show-error --max-time 60 \
  "$GENOS_CODE_URL" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $GENOS_CODE_KEY" \
  --data-binary '{"op":"ls","path":"/mnt/8-agent/data"}' | jq .
```

### 문서 목록

```bash
curl --fail-with-body --silent --show-error --max-time 120 \
  "$GENOS_CODE_URL" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $GENOS_CODE_KEY" \
  --data-binary '{"op":"call","method":"GET","path":"/v1/structure/documents"}' | jq .
```

### 검색만 실행 — LLM 불필요

```bash
export QUESTION='설명의무의 법적 근거'
jq -nc --arg q "$QUESTION" \
  '{op:"call",method:"GET",path:"/v1/rag/search",params:{q:$q,mode:"auto"}}' | \
curl --fail-with-body --silent --show-error --max-time 300 \
  "$GENOS_CODE_URL" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $GENOS_CODE_KEY" \
  --data-binary @- | jq .
```

### 답변 생성 — LLM 필요

```bash
export QUESTION='신탁재산을 고유재산과 구분해야 하는 근거는?'
jq -nc --arg q "$QUESTION" \
  '{op:"call",method:"POST",path:"/v1/rag/ask",json:{question:$q,mode:"vector"}}' | \
curl --fail-with-body --silent --show-error --max-time 600 \
  "$GENOS_CODE_URL" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $GENOS_CODE_KEY" \
  --data-binary @- | jq .
```

### 작은 문서 업로드

JSON 게이트웨이/HA 크기 제한 때문에 **500KB 이하 카나리 파일만** 이 방법을 쓴다.
큰 문서는 데이터 ZIP이나 공유 볼륨으로 반입한다.

```bash
export FILE='<업로드할 PDF/HWP/HWPX/DOCX/XML 경로>'
export FOLDER='내규'
export FILE_B64="$(base64 < "$FILE" | tr -d '\n')"

jq -nc --arg filename "$(basename "$FILE")" --arg file_b64 "$FILE_B64" --arg folder "$FOLDER" \
  '{op:"upload",filename:$filename,file_b64:$file_b64,form:{folder:$folder,use_llm:false}}' | \
curl --fail-with-body --silent --show-error --max-time 600 \
  "$GENOS_CODE_URL" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $GENOS_CODE_KEY" \
  --data-binary @- | jq .

unset FILE_B64
```

### 정적 현황 리포트 저장

```bash
curl --fail-with-body --silent --show-error --max-time 300 \
  "$GENOS_CODE_URL" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $GENOS_CODE_KEY" \
  --data-binary '{"op":"report"}' | jq -r '.html' > genos-status.html
```

### 배포 전 상태 스냅샷을 공유 볼륨에 저장

```bash
curl --fail-with-body --silent --show-error --max-time 300 \
  "$GENOS_CODE_URL" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $GENOS_CODE_KEY" \
  --data-binary '{"op":"snapshot_to","path":"/mnt/8-agent/backups/before-deploy.tar.gz"}' | jq .
```

합격 기준은 `ping.service=8-AGENT`, `health.status=200`, `health.json.status=ok`, 검색의
`ok=true`다. `jq`가 없으면 각 명령의 마지막 `| jq .`만 제거한다.
