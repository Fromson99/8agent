#!/usr/bin/env bash
# Fixed onsite layout. setup copies validated external RAW packages, never LLM data.
set -euo pipefail
umask 077
GENOS_DATA_CODE_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd -P)"
cd -- "$GENOS_DATA_CODE_ROOT"
GENOS_DATA_PYTHON=python3
if [[ -x .venv/bin/python ]]; then GENOS_DATA_PYTHON="$GENOS_DATA_CODE_ROOT/.venv/bin/python"; fi
export PYTHONUNBUFFERED=1
case "${1:-paths}" in
  setup)
    "$GENOS_DATA_PYTHON" - "$GENOS_DATA_CODE_ROOT" <<'PY'
from pathlib import Path
import sys
data = Path(sys.argv[1]) / 'data'
ignore = data / '.gitignore'
if data.is_symlink() or ignore.is_symlink():
    raise SystemExit('data 또는 data/.gitignore가 심볼릭 링크입니다. 변경하지 않았습니다.')
data.mkdir(exist_ok=True)
if not ignore.exists():
    with ignore.open('x') as stream:
        stream.write('*\n!.gitignore\n')
else:
    print('기존 data/.gitignore 유지: 원본/결과가 Git에서 제외되는지 확인하세요.')
PY
    "$GENOS_DATA_PYTHON" 06_TOOLS/COMMANDS/genos_unified_pipeline.py --data-root "$GENOS_DATA_CODE_ROOT/data" bootstrap-external
    "$GENOS_DATA_PYTHON" - "$GENOS_DATA_CODE_ROOT" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
target = root / 'data/corpus/internal'
if any(p.is_symlink() for p in [target, *target.parents] if p != root):
    raise SystemExit('내규 위치에 심볼릭 링크가 있습니다. 변경하지 않았습니다.')
target.mkdir(parents=True, exist_ok=True)
print('내규 폴더를 넣을 위치:', target)
print('외규 원본 위치:', root / 'data/corpus')
print('기존 GENOS_DATA/원본/Git/환경변수/배포는 변경하지 않았습니다.')
PY
    ;;
  build)
    shift
    # Explicit fixed path wins over stale GENOS_INPUT_ROOT/GENOS_UPLOAD_ROOT.
    exec "$GENOS_DATA_PYTHON" 06_TOOLS/COMMANDS/genos_unified_pipeline.py build --execute \
      --input-root "$GENOS_DATA_CODE_ROOT/data/corpus/internal" "$@"
    ;;
  paths)
    printf '내규: %s/data/corpus/internal\n외규: %s/data/corpus/{law,krx,kofia,expc,fsc,moleg,prec}\n결과 권장: %s/data/builds/새실행이름\n' "$GENOS_DATA_CODE_ROOT" "$GENOS_DATA_CODE_ROOT" "$GENOS_DATA_CODE_ROOT"
    ;;
  *) printf '사용법: bash 06_TOOLS/COMMANDS/genos_data.sh {setup|paths|build [빌드 옵션]}\n' >&2; exit 2 ;;
esac
