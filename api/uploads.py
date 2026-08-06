"""업로드 파일 처리 — 확장자·크기를 먼저 막고, 스트리밍으로 디스크에 쓴다.

두 엔진 모두 **파일 경로**를 받는다(도클링·pdfplumber 가 경로를 요구한다).
그래서 메모리에 통째로 올리지 않고 작업 디렉토리에 흘려 쓴 뒤 경로를 넘긴다.
작업이 끝나면 `jobs._run` 의 finally 가 디렉토리째 지운다 — 계약서 원본을 남기지 않는다.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Iterable, Optional

from fastapi import HTTPException, UploadFile

from . import settings

CHUNK = 1024 * 1024


def new_workdir(prefix: str = "job") -> Path:
    d = settings.WORK_DIR / f"{prefix}-{uuid.uuid4().hex[:12]}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_name(name: Optional[str], fallback: str) -> str:
    base = Path(name or "").name.strip()
    return base or fallback


async def save(upload: UploadFile, dest_dir: Path, allowed: Iterable[str],
               fallback_name: str = "upload.bin") -> Path:
    """업로드 하나를 dest_dir 에 저장하고 경로를 돌려준다."""
    allowed = {s.lower() for s in allowed}
    name = _safe_name(upload.filename, fallback_name)
    suffix = Path(name).suffix.lower()
    if suffix not in allowed:
        raise HTTPException(415, detail={
            "message": f"지원하지 않는 형식입니다: '{suffix or name}'",
            "allowed": sorted(allowed)})

    path = dest_dir / name
    total = 0
    with path.open("wb") as fh:
        while True:
            block = await upload.read(CHUNK)
            if not block:
                break
            total += len(block)
            if total > settings.MAX_UPLOAD_BYTES:
                fh.close()
                path.unlink(missing_ok=True)
                raise HTTPException(413, detail={
                    "message": f"파일이 너무 큽니다 (상한 {settings.MAX_UPLOAD_MB}MB)",
                    "filename": name})
            fh.write(block)
    if total == 0:
        path.unlink(missing_ok=True)
        raise HTTPException(400, detail={"message": f"빈 파일입니다: {name}"})
    return path


def write_text(text: str, dest_dir: Path, name: str) -> Path:
    p = dest_dir / name
    p.write_text(text, encoding="utf-8")
    return p
