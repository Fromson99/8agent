"""Enforce the PDF-primary policy for legacy DOC. Never modify originals."""
from __future__ import annotations

import copy
from pathlib import Path


def prepare(row, directory, *, timeout=120, emit=print):
    if Path(row['path']).suffix.lower() != '.doc':
        return copy.deepcopy(row)
    raise ValueError('구형 DOC는 PDF를 주 입력으로 사용합니다. 같은 폴더에 같은 이름의 PDF를 반입하세요: ' + row['relative'])
