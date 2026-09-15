#!/usr/bin/env bash
set -euo pipefail

code_root="${GENOS_CODE_ROOT:-/home/genos/DEV}"
data_root="${GENOS_DATA_ROOT:-$code_root/GENOS_DATA}"
target="$code_root/02_BACKEND/lawrag/pipeline/genos_unified.py"
python_bin="$code_root/.venv/bin/python"

if [[ ! -f "$target" ]]; then
  echo "오류: 수정할 GENOS 코드가 없습니다: $target" >&2
  exit 2
fi
if [[ ! -x "$python_bin" ]]; then
  echo "오류: Python 가상환경이 없습니다: $python_bin" >&2
  exit 2
fi

"$python_bin" - "$target" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
start_marker = "def _source_hashes("
end_marker = "\n\ndef _build_source_store"
if start_marker not in text or end_marker not in text:
    raise SystemExit("오류: 수정할 함수 경계를 찾지 못했습니다")
start = text.index(start_marker)
end = text.index(end_marker, start)

fixed = '''def _source_hashes(root: Path) -> dict[str, str]:
    from lawrag.core import batch

    hashes: dict[str, str] = {}
    for target in batch.ingest_targets():
        body = Path(str(target["path"]))
        if body.is_symlink() or not body.is_file():
            raise ValueError(f"invalid ingested source body: {body}")
        sha256 = _sha(body)
        document_id = str(target["doc_id"])
        if len(sha256) != 64 or not sha256.startswith(document_id):
            raise ValueError(
                f"invalid ingested source coordinate: {body}: {document_id}"
            )
        previous = hashes.setdefault(document_id, sha256)
        if previous != sha256:
            raise ValueError(f"conflicting source hashes for {document_id}")
    return hashes
'''

path.write_text(text[:start] + fixed + text[end:], encoding="utf-8")
print(f"GENOS publish 코드 수정 완료: {path}")
PY

"$python_bin" -m py_compile "$target"
echo "Python 문법 검사 완료"

if [[ "${1:-}" == "--patch-only" ]]; then
  exit 0
fi
if [[ ! -d "$data_root/corpus" || ! -d "$data_root/structure" ]]; then
  echo "오류: external 결과를 찾을 수 없습니다: $data_root" >&2
  echo "현재 GENOS_DATA_ROOT를 확인하세요." >&2
  exit 3
fi

export PYTHONPATH="$code_root/02_BACKEND"
export GENOS_DATA_ROOT="$data_root"
export GENOS_RUNTIME_DIR="${GENOS_RUNTIME_DIR:-$data_root/runtime}"

"$python_bin" "$code_root/06_TOOLS/COMMANDS/genos_unified_pipeline.py" \
  --data-root "$data_root" publish

echo "GENOS publish 재실행 완료"
