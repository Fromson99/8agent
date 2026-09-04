#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

use_shell_credentials=0
if [[ -n "${GMAIL_USERNAME:-}" || -n "${GMAIL_APP_PASSWORD:-}" ]]; then
    [[ -n "${GMAIL_USERNAME:-}" && -n "${GMAIL_APP_PASSWORD:-}" ]] || {
        echo "오류: GMAIL_USERNAME과 GMAIL_APP_PASSWORD는 함께 설정해야 합니다." >&2
        exit 2
    }
    use_shell_credentials=1
elif ! command -v powershell.exe >/dev/null 2>&1; then
    echo "오류: Gmail 환경변수를 설정하거나 WSL의 Windows PowerShell을 사용할 수 있어야 합니다." >&2
    exit 2
fi

git config --local core.hooksPath .githooks
git config --local patchmail.remote "${PATCH_MAIL_REMOTE:-infocz}"
git config --local patchmail.ref "${PATCH_MAIL_REF:-refs/heads/feature/legal_RAG}"
if [[ -n "${1:-}" ]]; then
    git config --local patchmail.to "$1"
fi

chmod +x .githooks/pre-push scripts/local_push_mail.py

echo "로컬 push 메일 훅을 설치했습니다."
echo "remote: $(git config --local --get patchmail.remote)"
echo "ref: $(git config --local --get patchmail.ref)"
recipient="$(git config --local --get patchmail.to 2>/dev/null || true)"
echo "recipient: ${recipient:-Gmail 발신자 본인}"
if [[ "$use_shell_credentials" == 1 ]]; then
    echo "이번 터미널의 Gmail 환경변수를 사용합니다. 터미널을 닫으면 다시 설정해야 합니다."
else
    echo "다음으로 Windows PowerShell에서 자격 증명을 한 번 등록하세요:"
    echo "  powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"$(wslpath -w "$repo_root/scripts/push_patch_credential.ps1")\" -Mode Set"
fi
