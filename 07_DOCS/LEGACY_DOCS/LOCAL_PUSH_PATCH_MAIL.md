# 로컬 `git push` 증분 ZIP Gmail 발송

이 방식은 GitHub Actions나 Codex 주기 작업을 사용하지 않는다. 이 PC의 저장소에서
`git push infocz feature/legal_RAG`를 실행할 때 로컬 `pre-push` 훅이 작업자를 시작하고,
작업자가 회사 원격의 SHA가 실제로 갱신된 것을 확인한 뒤에만 증분 ZIP을 발송한다.

> Git에는 클라이언트 `post-push` 훅이 없다. 따라서 훅은 push 전에 백그라운드 작업을
> 예약하며, 작업자가 최대 180초 동안 원격 SHA를 확인한다. push가 실패하면 메일도 보내지 않는다.

## 1. 훅 설치

WSL 저장소 루트에서 실행한다. 수신 주소를 생략하면 발신 Gmail 본인에게 보낸다.

```bash
bash scripts/install_push_patch_mail.sh
```

온사이트 기본 수신 주소를 지정하려면 다음처럼 설치하거나 나중에 Git 로컬 설정만 바꾼다.

```bash
bash scripts/install_push_patch_mail.sh onsite@example.internal
git config --local patchmail.to onsite@example.internal
```

이 설정은 저장소의 `.git/config`에만 저장되며 커밋되지 않는다.

## 2. Gmail 자격 증명 1회 등록

Google 계정에서 2단계 인증을 켠 뒤 **앱 비밀번호**를 만든다. 일반 Gmail 로그인
비밀번호를 사용하지 않는다. Windows PowerShell에서 다음 명령을 실행하고 Gmail 주소와
앱 비밀번호를 프롬프트에 입력한다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "\\wsl.localhost\Ubuntu\home\jin\8-AGENT\scripts\push_patch_credential.ps1" `
  -Mode Set
```

자격 증명은 `8-AGENT Gmail SMTP`라는 Generic Credential로 Windows 자격 증명 관리자에만
저장된다. Git, `.env`, GitHub Secrets에는 들어가지 않는다. 삭제 명령은 다음과 같다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File "\\wsl.localhost\Ubuntu\home\jin\8-AGENT\scripts\push_patch_credential.ps1" `
  -Mode Delete
```

## 3. 평소 사용

추가 명령 없이 평소처럼 회사 원격으로 push한다.

```bash
git push infocz feature/legal_RAG
```

터미널에는 `patch-mail: push 성공 확인 후 ...`가 표시된다. 메일 작업은 push와 분리되어
백그라운드에서 실행되며, 로그는 `var/patch-mail/logs/<SHA>.log`, ZIP은
`var/out/ship/local-mail/`에 저장된다. 두 경로는 `.gitignore`의 `var/` 규칙으로 제외된다.

## 적용 범위와 안전장치

- 이 로컬 clone에서 `infocz`의 `feature/legal_RAG`로 push할 때만 발송한다.
- 다른 PC나 다른 사용자의 push에는 반응하지 않는다.
- 원격 SHA가 새 SHA와 일치해야만 발송한다. push 실패나 timeout이면 발송하지 않는다.
- Git commit blob만 패키징하며 로컬 미커밋 파일은 포함하지 않는다.
- `.env`, key/certificate, ADR, `data/`, 원문 corpus, 생성 산출물과 문서 바이너리를 제외한다.
- 삭제·rename·제외 항목은 ZIP의 `PATCH_MANIFEST.json`에 기록한다.
- 단일 파일 12MB 초과는 제외하며 ZIP이 18MB를 넘으면 발송하지 않는다.
- 메일 실패는 이미 성공한 Git push를 되돌리지 않는다. 로그를 확인한 뒤 재발송해야 한다.

GitHub의 `Mail push patch ZIP` 워크플로우는 제거되며 이 로컬 방식과 동시에 실행되지 않는다.
