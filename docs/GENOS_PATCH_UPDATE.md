# GenOS 코드 업데이트 — `push → Gmail ZIP → 적용 → 배포`

이 문서는 최초 반입이 끝난 뒤의 **코드만** 업데이트하는 절차다. 데이터는 다시 보내거나
Git에 넣지 않는다. 데이터·벡터·`.env`·인증키는 기존 GenOS 영속 경로에 그대로 둔다.

## 흐름

```text
개발 PC에서 commit/push
        ↓ (성공한 push만)
Gmail로 증분 코드 ZIP 수신
        ↓
GenOS Jupyter에서 검증·백업·코드 적용
        ↓
내부 Gitea에 commit/push
        ↓
코드 서빙 화면에서 새 commit 배포
```

## 1. 개발 PC: 한 번만 자동 발송 설정

WSL의 저장소 루트에서 실행한다. 값은 Git이나 소스에 저장하지 않고 현재 터미널의
환경변수로만 준다.

```bash
cd /home/jin/8-AGENT
export PATCH_MAIL_REMOTE=origin
export PATCH_MAIL_REF=refs/heads/main
export PATCH_MAIL_TO='받을_Gmail_주소'
export GMAIL_USERNAME='보내는_Gmail_주소'
read -rsp 'Gmail 앱 비밀번호: ' GMAIL_APP_PASSWORD; export GMAIL_APP_PASSWORD; echo
bash scripts/install_push_patch_mail.sh "$PATCH_MAIL_TO"
```

`GMAIL_APP_PASSWORD`에는 일반 Gmail 비밀번호가 아니라 Google 계정의 **앱 비밀번호**를
입력한다. 터미널을 닫으면 이 환경변수는 사라진다. 매번 입력하기 싫다면 기존 Windows
자격 증명 관리자 방식도 [LOCAL_PUSH_PATCH_MAIL.md](LOCAL_PUSH_PATCH_MAIL.md)를 따른다.

그 다음부터는 평소와 동일하다.

```bash
git add <바뀐_파일>
git commit -m '설명'
git push origin main
```

push가 실제로 성공한 뒤에만 메일이 발송된다. ZIP에는 변경된 코드만 들어가며,
JavaScript 파일은 Gmail 통과를 위해 ZIP 안에서 임시 이름으로 바뀌었다가 GenOS 적용
도구가 원래 이름으로 복원한다.

## 2. GenOS Jupyter: ZIP 적용

Gmail에서 받은 `8agent-patch-*.zip`을 Jupyter 파일 목록에서 예를 들어
`~/DEV/patch-inbox/`에 올린다. 아래는 현재 코드 작업판이 `~/DEV/8-agent-new`인 경우다.

```bash
cd "$HOME/DEV/8-agent-new"
export PATCH_ZIP="$HOME/DEV/patch-inbox/8agent-patch-받은파일명.zip"

# 1) ZIP만 검증
python3 scripts/genos_patch_apply.py verify "$PATCH_ZIP"

# 2) 실제 변경 전 적용 목록 확인 (파일은 아직 안 바뀜)
python3 scripts/genos_patch_apply.py apply "$PATCH_ZIP" --root "$PWD"

# 3) 실제 적용: 기존 코드 사본은 var/patch-backups/ 아래 자동 보관
python3 scripts/genos_patch_apply.py apply "$PATCH_ZIP" --root "$PWD" --apply
```

도구는 아래 항목이 ZIP에 들어 있으면 바로 중단한다.

- `data/` 및 벡터/원문 데이터
- `.env`, `.env.local`, 인증서·키 파일
- PDF/HWP/DOCX/XLSX 같은 문서·압축 파일
- 심볼릭 링크, `..` 경로, ZIP 해시 불일치

Git 작업판에 직접 수정한 파일이 있으면 실수 방지를 위해 적용하지 않는다. 먼저
`git status`로 확인하고 commit 또는 stash한다. 정말 의도된 경우에만 `--allow-dirty`를
붙인다.

## 3. 내부 Gitea에 반영하고 배포

적용이 끝나면 변경만 확인하고 내부 저장소에 commit/push한다.

```bash
cd "$HOME/DEV/8-agent-new"
git status
git diff --stat
python3 scripts/genos_preflight.py source
git add .
git commit -m 'Apply code patch'
git push origin HEAD:main
git rev-parse HEAD
```

마지막 해시가 코드 서빙의 커밋 목록에 보이면, GenOS **코드 서빙 상세 → 배포**에서 그
새 커밋을 선택해 배포 신청/승인한다. 배포 후에는 다음만 다시 확인하면 된다.

```bash
scripts/genos_call.sh ping
scripts/genos_call.sh health
```

데이터 ZIP을 다시 풀거나 환경변수를 다시 입력할 필요는 없다. 단, 데이터 구조나
임베딩 모델을 변경한 업데이트만 별도의 데이터 반입·색인 절차가 필요하다.

## 4. 한 번에 동작 확인

배포가 끝난 뒤 코드 서빙 URL과 키를 넣고 아래 한 명령을 실행한다. `--all`은 연결,
health, 영속 데이터, 일반 RAG 검색, Vector DB 검색, LLM 답변 생성을 순서대로 확인한다.

```bash
cd "$HOME/DEV/8-agent-new"
export GENOS_CODE_URL='https://<GenOS>/api/gateway/code_serving/<CODE_ID>/json'
read -rsp 'Code serving key: ' GENOS_CODE_KEY; export GENOS_CODE_KEY; echo
export GENOS_DATA_ROOT='/workspace/8-agent-runtime/data'
bash scripts/genos_smoke.sh --all
```

마지막 출력에서 `5/6 Vector DB 검색`의 `vector_hits` 또는 `refs`, `6/6 LLM 답변 생성`의
`answer`와 `refs`가 있으면 두 연결이 정상이다. 질문을 바꾸려면 실행 전에
`GENOS_SMOKE_SEARCH`, `GENOS_SMOKE_ASK` 환경변수만 바꾸면 된다.

## 롤백

적용 전 코드 사본은 `var/patch-backups/<시간>-<커밋앞12자리>/`에 있다. 더 간단하고
권장되는 롤백은 코드 서빙 화면에서 직전 정상 **커밋**을 다시 선택해 재배포하는 것이다.
GenOS Jupyter 작업판도 해당 커밋으로 되돌려야 한다면 팀의 Git 절차에 따라 별도 revert
커밋을 만들어 push한다. 데이터와 `.env`는 이 과정에서 변경되지 않는다.
