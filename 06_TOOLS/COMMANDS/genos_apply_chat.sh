#!/usr/bin/env bash
set -euo pipefail

dev_root="${GENOS_DEV_ROOT:-/home/genos/DEV}"
script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [[ -d "$script_dir/08_DEPLOYMENT" ]]; then
  payload_root="$script_dir"
else
  payload_root="$(CDPATH= cd -- "$script_dir/../.." && pwd)"
fi
service_file="$dev_root/service.py"
service_source="$payload_root/service.py"
workflow_rel="08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py"
doc_rel="07_DOCS/REFERENCE/OPERATIONS/GENOS_CHAT_WORKFLOW.md"
python_bin="$(command -v python3 || command -v python || true)"

if [[ ! -f "$service_file" ]]; then
  echo "ERROR: $service_file 없음" >&2
  exit 1
fi
if [[ -z "$python_bin" ]]; then
  echo "ERROR: python3 또는 python 실행파일 없음" >&2
  exit 1
fi
if [[ ! -f "$payload_root/$workflow_rel" ]]; then
  echo "ERROR: 패치 파일 $payload_root/$workflow_rel 없음" >&2
  exit 1
fi
if [[ ! -f "$service_source" ]]; then
  echo "ERROR: 교체할 $service_source 없음" >&2
  exit 1
fi

backup="$(mktemp -d "$dev_root/.genos-chat-backup-XXXXXXXX")"
cp -p "$service_file" "$backup/service.py"

cp -p "$service_source" "$service_file"
echo "REPLACED: $service_file"

mkdir -p "$dev_root/$(dirname "$workflow_rel")" "$dev_root/$(dirname "$doc_rel")"
cp -p "$payload_root/$workflow_rel" "$dev_root/$workflow_rel"
cp -p "$payload_root/$doc_rel" "$dev_root/$doc_rel"

"$python_bin" -m py_compile "$service_file" "$dev_root/$workflow_rel"

echo "PASS: GENOS 채팅 패치 적용 완료"
echo "백업: $backup"
echo "다음: DEV 저장소에서 git diff 확인 → commit/push → 코드서빙 재배포"
