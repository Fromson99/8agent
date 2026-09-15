#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
target_dir="${1:-/home/genos/DEV}"
manifest="$script_dir/parts-manifest.json"
b64_last="$script_dir/genos-unified-dev-root-20260908.zip.part017.b64.txt"
raw_last="$script_dir/genos-unified-dev-root-20260908.zip.part017"

if [[ ! -f "$manifest" ]]; then
  echo "오류: parts-manifest.json이 없습니다: $manifest" >&2
  exit 2
fi

if [[ ! -f "$raw_last" ]]; then
  if [[ ! -f "$b64_last" ]]; then
    echo "오류: 마지막 조각이 없습니다: $b64_last" >&2
    exit 2
  fi
  python3 - "$b64_last" "$raw_last" <<'PY'
import base64
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
try:
    decoded = base64.b64decode(source.read_bytes(), validate=True)
except Exception as exc:
    raise SystemExit(f"마지막 조각 Base64 복원 실패: {exc}") from exc
target.write_bytes(decoded)
print(f"마지막 조각 복원 완료: {target.name}")
PY
fi

mkdir -p -- "$target_dir"

python3 - "$manifest" "$script_dir" "$target_dir" <<'PY'
import hashlib
import json
import os
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

manifest_path = Path(sys.argv[1]).resolve()
parts_dir = Path(sys.argv[2]).resolve()
target = Path(sys.argv[3]).resolve()
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

if target == Path("/") or target.is_symlink():
    raise SystemExit(f"안전하지 않은 대상 경로입니다: {target}")
if manifest.get("schema_version") != "split-archive-v1":
    raise SystemExit("지원하지 않는 parts-manifest 형식입니다")

extras = sorted(path.name for path in target.iterdir() if path.name != "TRANSFER")
if extras:
    raise SystemExit(
        "대상 DEV가 비어 있지 않습니다. TRANSFER 외 항목을 먼저 확인하세요: "
        + ", ".join(extras[:10])
    )

archive_name = str(manifest["archive"])
archive = parts_dir / archive_name
partial = parts_dir / (archive_name + ".partial")
digest = hashlib.sha256()
total = 0

try:
    with partial.open("wb") as output:
        for row in manifest["parts"]:
            part = parts_dir / str(row["name"])
            if not part.is_file() or part.is_symlink():
                raise SystemExit(f"분할파일 없음 또는 심볼릭 링크: {part.name}")
            raw = part.read_bytes()
            actual = hashlib.sha256(raw).hexdigest()
            if len(raw) != int(row["bytes"]) or actual != row["sha256"]:
                raise SystemExit(f"분할파일 검증 실패: {part.name}")
            output.write(raw)
            digest.update(raw)
            total += len(raw)
    if total != int(manifest["archive_bytes"]):
        raise SystemExit("전체 ZIP 크기가 manifest와 다릅니다")
    if digest.hexdigest() != manifest["archive_sha256"]:
        raise SystemExit("전체 ZIP SHA-256이 manifest와 다릅니다")
    os.replace(partial, archive)
finally:
    partial.unlink(missing_ok=True)

with zipfile.ZipFile(archive) as bundle:
    damaged = bundle.testzip()
    if damaged:
        raise SystemExit(f"손상된 ZIP 항목: {damaged}")
    for info in bundle.infolist():
        path = PurePosixPath(info.filename)
        mode = (info.external_attr >> 16) & 0o170000
        if path.is_absolute() or ".." in path.parts or mode == stat.S_IFLNK:
            raise SystemExit(f"안전하지 않은 ZIP 경로: {info.filename}")
    bundle.extractall(target)

(target / "GENOS_DATA" / "runtime").mkdir(parents=True, exist_ok=True)
print(f"설치 완료: {target}")
print(f"전체 ZIP: {archive}")
print(f"SHA-256: {digest.hexdigest()}")
PY

cat <<EOF

다음 명령:
  cd '$target_dir'
  python3.11 -m venv .venv
  .venv/bin/pip install -r requirements-pipeline.txt

환경값:
  GENOS_DATA_ROOT=$target_dir/GENOS_DATA
  GENOS_RUNTIME_DIR=$target_dir/GENOS_DATA/runtime
  GENOS_UPLOAD_ROOT=/nfs-root
EOF
