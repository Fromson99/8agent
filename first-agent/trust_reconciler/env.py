"""`.env` 로더 — 표준 라이브러리만, 정규표현식 없음.

python-dotenv 를 쓰지 않는 이유: docling 이 끌고 온 전이 의존이라
언제 사라질지 모르는 것에 비밀값 로딩을 걸어 두고 싶지 않다. 필요한 기능은 20줄이다.

동작
  - 프로젝트 루트의 `.env` 를 읽어 os.environ 에 넣는다.
  - **이미 환경에 있는 값은 덮어쓰지 않는다.** CI·셸에서 준 값이 파일보다 우선이다.
  - 값이 비어 있으면(`KEY=`) 넣지 않는다. 빈 문자열 키로 API 호출이 나가면
    "인증 실패" 대신 엉뚱한 에러가 나서 원인을 찾기 어렵다.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

_loaded = False


def _strip_quotes(value: str) -> str:
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def parse_env(text: str) -> dict[str, str]:
    """KEY=VALUE 줄들을 dict 로. 주석·빈 줄·`export ` 접두사·따옴표를 처리한다."""
    out: dict[str, str] = {}
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key = key.strip()
        if not key:
            continue
        out[key] = _strip_quotes(value)
    return out


def load(path: str | Path | None = None, override: bool = False) -> list[str]:
    """`.env` 를 환경에 반영하고, 새로 설정된 키 이름 목록을 돌려준다.

    값은 절대 반환하거나 로그에 남기지 않는다 — 키 이름만 다룬다.
    """
    global _loaded
    p = Path(path) if path else DEFAULT_ENV_PATH
    if not p.exists():
        _loaded = True
        return []

    applied: list[str] = []
    for key, value in parse_env(p.read_text(encoding="utf-8")).items():
        if not value:
            continue                      # 빈 값은 무시 (아직 안 채운 자리표시자)
        if not override and os.environ.get(key):
            continue                      # 셸/CI 가 준 값이 우선
        os.environ[key] = value
        applied.append(key)
    _loaded = True
    return applied


def ensure_loaded() -> None:
    """프로세스당 한 번만 읽는다. 라이브러리 진입점에서 호출한다."""
    if not _loaded:
        load()


def has_api_key() -> bool:
    ensure_loaded()
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
