"""수집된 HWP5 원문 → md 사이드카 — 정본은 lawrag/core/hwp5_md.py, 여기는 명령줄 문.

    python -m lawrag.pipeline.convert data/corpus/kofia            # 폴더째
    python -m lawrag.pipeline.convert 파일.hwp --force
"""
from __future__ import annotations

import sys

from lawrag.core.hwp5_md import main

if __name__ == "__main__":
    sys.exit(main())
