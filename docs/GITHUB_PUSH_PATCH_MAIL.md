# Git push 증분 ZIP Gmail 자동 발송

`.github/workflows/mail-push-patch.yml`은 모든 branch push마다 직전 SHA와 새 SHA 사이의
변경 파일만 ZIP으로 만들고 Gmail SMTP로 발송한다. push 이벤트는 입력창을 띄울 수
없으므로 수신 주소는 다음 우선순위를 따른다.

1. `Actions > Mail push patch ZIP > Run workflow`에서 입력한 `recipient`
2. GitHub Repository Variable `PATCH_MAIL_TO`
3. 둘 다 없으면 Secret `GMAIL_USERNAME`, 즉 발신자 본인 주소

## GitHub에 한 번만 설정할 값

저장소의 `Settings > Secrets and variables > Actions`에서 설정한다.

### Secrets

| 이름 | 값 |
|---|---|
| `GMAIL_USERNAME` | 발신 Gmail 전체 주소 |
| `GMAIL_APP_PASSWORD` | Google 2단계 인증 후 만든 16자리 앱 비밀번호 |

일반 Gmail 로그인 비밀번호를 넣지 않는다. 앱 비밀번호는 Git에 커밋하거나 Variable로
등록하지 않는다. Google Workspace 정책이나 Advanced Protection 때문에 앱 비밀번호가
허용되지 않으면 Workspace 관리자가 SMTP 사용을 허용해야 한다.

### Variables

| 이름 | 값 |
|---|---|
| `PATCH_MAIL_TO` | 기본 온사이트 수신 이메일. 생략하면 발신 Gmail로 보냄 |

온사이트 주소를 고정하려면 `PATCH_MAIL_TO`에 한 번만 등록한다. 특정 한 번만 다른 주소로
보내려면 Actions 화면의 `Run workflow`에서 `recipient`를 입력한다.

## 동작과 안전장치

- Git에 실제 push된 commit blob만 포함한다. 로컬 미커밋 파일과 `.env`는 들어가지 않는다.
- 삭제 및 rename은 `PATCH_MANIFEST.json`에 기록한다.
- `.env`, key/certificate, ADR 원장, PDF/HWP/DOCX/XLSX/PPTX 등 원문은 제외한다.
- `data/`와 agent6 원문 corpus는 메일 코드 패치에서 제외한다. 데이터 반입은
  `scripts/data_ship.sh`를 사용하며, 제외 경로는 manifest에 기록한다.
- `tmp/`와 `artifacts/`의 실험·렌더·사이트 생성 산출물도 코드 패치에서 제외한다.
- 단일 파일 12MB 초과는 제외 사유를 manifest에 남긴다.
- 최종 ZIP이 18MB를 넘으면 Gmail 첨부 한도를 고려해 발송하지 않고 Action을 실패시킨다.
- 수신 주소와 Gmail 자격증명이 없으면 조용히 건너뛰지 않고 Action을 실패시킨다.

## 로컬에서 ZIP만 검사

메일을 보내지 않고 현재 HEAD의 직전 commit 대비 ZIP을 만든다.

```bash
python scripts/push_patch_mail.py pack \
  --before HEAD^ --after HEAD \
  --out var/out/ship/local-patch.zip
```

직접 Gmail로 시험 발송할 때만 현재 셸에 값을 넣는다. 셸 history에 앱 비밀번호를 직접
쓰지 않는 것을 권장한다.

```bash
export GMAIL_USERNAME='sender@gmail.com'
read -rsp 'Gmail app password: ' GMAIL_APP_PASSWORD
export GMAIL_APP_PASSWORD
export PATCH_MAIL_TO='onsite@example.internal'
echo

python scripts/push_patch_mail.py run \
  --before HEAD^ --after HEAD \
  --out var/out/ship/local-patch.zip

unset GMAIL_APP_PASSWORD
```

## 수동 재발송

이미 만들어진 ZIP을 다른 주소로 다시 보낼 수 있다.

```bash
python scripts/push_patch_mail.py send var/out/ship/local-patch.zip \
  --to another-recipient@example.com
```

Actions 로그에는 앱 비밀번호를 출력하지 않는다. GitHub가 Secret을 마스킹하지만, 디버그
출력이나 `set -x`는 사용하지 않는다.
