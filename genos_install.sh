#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
target_dir="${1:-/home/genos/DEV}"
manifest="$script_dir/parts-manifest.json"

if [[ ! -f "$manifest" ]]; then
  echo "parts-manifest.json이 없습니다: $manifest" >&2
  exit 2
fi
mkdir -p -- "$target_dir"
if [[ ! -w "$target_dir" ]]; then
  echo "대상 폴더에 쓰기 권한이 없습니다: $target_dir" >&2
  exit 2
fi

python3 - "$manifest" "$script_dir" "$target_dir" <<'PY'
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path, PurePosixPath

manifest_path = Path(sys.argv[1]).resolve()
parts_dir = Path(sys.argv[2]).resolve()
target = Path(sys.argv[3]).resolve()
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
archive = target / ".genos-unified-raw-handoff.zip.partial"
digest = hashlib.sha256()
with archive.open("wb") as output:
    for row in manifest["parts"]:
        part = parts_dir / row["name"]
        raw = part.read_bytes()
        if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise SystemExit(f"분할 파일 검증 실패: {part.name}")
        output.write(raw)
        digest.update(raw)
if archive.stat().st_size != manifest["archive_bytes"]:
    raise SystemExit("합친 ZIP 크기가 다릅니다")
if digest.hexdigest() != manifest["archive_sha256"]:
    raise SystemExit("합친 ZIP SHA-256이 다릅니다")
with zipfile.ZipFile(archive) as bundle:
    for info in bundle.infolist():
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts:
            raise SystemExit(f"안전하지 않은 ZIP 경로: {info.filename}")
    bundle.extractall(target)
archive.unlink()
print(f"설치 완료: {target}")
PY

echo "권장 환경값: GENOS_DATA_ROOT='$target_dir/GENOS_DATA' GENOS_RUNTIME_DIR='$target_dir/GENOS_DATA/runtime'"
echo "다음: cd '$target_dir' && .venv/bin/python 06_TOOLS/COMMANDS/genos_unified_pipeline.py --data-root \"\$GENOS_DATA_ROOT\" external"
echo "처리 후 발행: .venv/bin/python 06_TOOLS/COMMANDS/genos_unified_pipeline.py --data-root \"\$GENOS_DATA_ROOT\" publish"
