"""두 엔진을 한 프로세스에 올린다.

`trust-parser/src` 는 플랫 모듈 배치다(`import ontology`). 그래서 CLI 와 **똑같이**
sys.path 맨 앞에 넣는다 — `src/cli.py` 가 이미 도클링과 같은 프로세스에서 검증한 구성이라
여기서 다른 방식을 쓰면 검증되지 않은 임포트 순서를 새로 만드는 셈이다.
`first-agent` 는 `trust_reconciler` 패키지라 디렉토리만 올리면 된다.

## 왜 지연 임포트인가

도클링은 torch 를 끌고 오고 최초 실행 시 레이아웃 모델을 내려받는다(수백 MB, 네트워크 필요).
그걸 모듈 상단에서 임포트하면 **서버가 뜨는 데 수십 초**가 걸리고, 모델 다운로드가 실패하면
헬스체크조차 못 받는다. 그래서 실제로 PDF 를 먹는 순간에만 임포트한다.
도클링이 아예 없어도 서버는 뜨고, 파싱 엔드포인트만 503 을 낸다
— 대사·질의는 순수 파이썬이라 그대로 돌아간다.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
import threading
from functools import lru_cache

from . import settings

_lock = threading.Lock()
_ready = False


def bootstrap() -> None:
    """sys.path 를 한 번만 손본다."""
    global _ready
    if _ready:
        return
    with _lock:
        if _ready:
            return
        for p in (settings.AGENT_ROOT, settings.PARSER_ROOT / "src"):
            s = str(p)
            if s not in sys.path:
                sys.path.insert(0, s)      # 파서 src 가 결국 맨 앞 — cli.py 와 동일
        _ready = True


def parser(name: str):
    """trust-parser 의 플랫 모듈 하나를 가져온다."""
    bootstrap()
    return importlib.import_module(name)


def agent(name: str = "main"):
    """first-agent 의 `trust_reconciler.<name>` 을 가져온다."""
    bootstrap()
    return importlib.import_module(f"trust_reconciler.{name}")


@lru_cache(maxsize=4)
def ontology(path: str | None = None):
    """온톨로지는 읽기 전용이라 프로세스당 한 번만 읽어 공유한다."""
    onto = parser("ontology")
    return onto.load(path or settings.ONTOLOGY_PATH
                     or onto.default_path(settings.PARSER_ROOT))


def has_docling() -> bool:
    return importlib.util.find_spec("docling") is not None


def has_anthropic_key() -> bool:
    try:
        return bool(agent("env").has_api_key())
    except Exception:
        import os
        return bool(os.environ.get("ANTHROPIC_API_KEY"))
