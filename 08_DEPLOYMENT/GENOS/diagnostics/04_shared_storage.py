#!/usr/bin/env python3
"""Check code-space read access and recent files on the shared report path."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat

from trace_common import DEFAULT_ROOT, output, paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    root = args.root
    if not root.exists():
        output({'root': str(root), 'exists': False,
                'note': '코드스페이스에서 경로가 보이지 않습니다. 코드서빙 쓰기 여부는 별도 확인.'})
        return 2
    info = root.stat()
    try:
        recent = paths(root)[:5]
    except ValueError:
        recent = []
    output({'root': str(root), 'exists': True, 'is_directory': root.is_dir(),
            'code_space_can_read': os.access(root, os.R_OK | os.X_OK),
            'mode': oct(stat.S_IMODE(info.st_mode)), 'uid': info.st_uid, 'gid': info.st_gid,
            'recent_files': [{'path': str(path), 'bytes': path.stat().st_size,
                              'code_space_can_read': os.access(path, os.R_OK)} for path in recent],
            'note': '이 검사는 코드스페이스 권한만 확인합니다. 코드서빙 쓰기는 shared_report.written/failed 로그로 확인.'})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
