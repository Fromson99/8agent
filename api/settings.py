"""컨테이너에서 바꿀 수 있는 값만 여기 모은다.

배포처(코드스페이스·클라우드)마다 경로와 워커 수가 달라지므로 코드가 아니라
환경변수로 조정한다. 기본값은 이 저장소를 그대로 클론한 상태에서 동작한다.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _path(name: str, default: Path) -> Path:
    v = os.environ.get(name)
    return Path(v).expanduser().resolve() if v else default


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# --- 엔진 위치 -------------------------------------------------------------
# v1(온톨로지 기반)은 SPEC v2 재편 때 archive/ 로 옮겼다. 기존 API 는 그대로 동작한다.
PARSER_ROOT = _path("TRUST_PARSER_ROOT", REPO_ROOT / "archive" / "trust-parser-v1")
AGENT_ROOT = _path("FIRST_AGENT_ROOT", REPO_ROOT / "first-agent")
ONTOLOGY_PATH = os.environ.get("ONTOLOGY_PATH") or None
SNAPSHOT_PATH = os.environ.get("SNAPSHOT_PATH") or None

# --- 업로드 ----------------------------------------------------------------
MAX_UPLOAD_MB = _int("MAX_UPLOAD_MB", 40)
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
WORK_DIR = _path("WORK_DIR", Path(tempfile.gettempdir()) / "trust-api")

DOC_SUFFIXES = {".pdf", ".docx", ".pptx", ".html", ".htm", ".md", ".txt"}
CHUNKS_SUFFIXES = {".json"}
SUMMARY_SUFFIXES = {".pdf", ".md", ".markdown", ".txt"}

# --- 작업 큐 ---------------------------------------------------------------
# 파서는 CPU 바운드(도클링)라 2개까지 병렬.
# 에이전트는 스냅샷·용어집 파일을 공유하므로 **직렬**이 기본이다 — 동시에 쓰면 깨진다.
PARSER_WORKERS = _int("PARSER_WORKERS", 2)
AGENT_WORKERS = _int("AGENT_WORKERS", 1)
JOB_TTL_SECONDS = _int("JOB_TTL_SECONDS", 6 * 3600)
MAX_JOBS = _int("MAX_JOBS", 200)
MAX_WAIT_SECONDS = _int("MAX_WAIT_SECONDS", 240)

# --- 서버 ------------------------------------------------------------------
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
API_TOKEN = os.environ.get("API_TOKEN") or None      # 있으면 Bearer 인증 강제
SERVE_VIEWER = _flag("SERVE_VIEWER", True)
