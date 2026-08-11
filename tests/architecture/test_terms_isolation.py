"""용어층 컴파일 국면의 격리 — 검색 런타임은 core/terms 를 모른다.

결정 변경 기록 (2026-08-10, 사용자 결정): 질의 시점 벡터 단이 **허용**됐다
(하이브리드 — core/rag/vector.py). 그래도 두 격리는 남는다:

  1. core/rag 는 여전히 core.terms 를 import 하지 않는다 — 벡터 컴파일
     (embed_sections)과 벡터 검색(vector.py)은 파일(npz)로만 만난다.
  2. 무거운 의존(torch·sentence-transformers)은 **모듈 수준에서 import
     금지** — 지연 로드만. 모델 없는 환경에서 검색 서비스가 떠야 하고,
     벡터 단은 조용히 빠져야 한다.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
RAG = ROOT / "core" / "rag"
TERMS = ROOT / "core" / "terms"

HEAVY = {"sentence_transformers", "torch", "numpy", "sklearn", "scipy",
         "gensim", "kiwipiepy"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def _module_level_imports(path: Path) -> set[str]:
    """함수 안이 아니라 **모듈 수준**의 import 만 — 지연 로드는 허용이다."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
    return out


def test_검색_런타임은_용어층_컴파일을_import_하지_않는다():
    for py in RAG.glob("*.py"):
        bad = {m for m in _imports(py) if m == "core.terms" or m.startswith("core.terms.")}
        assert not bad, f"{py.name} 가 컴파일 국면을 런타임으로 끌어왔다: {bad}"


def test_검색_런타임의_무거운_의존은_지연_로드만():
    """core/rag 와 core/embedding 을 import 하는 것만으로 torch 가 뜨면 안
    된다 — 모델 없는 컨테이너에서도 렉시컬 검색은 살아야 한다."""
    targets = list(RAG.glob("*.py")) + [ROOT / "core" / "embedding.py"]
    for py in targets:
        bad = {m for m in _module_level_imports(py) if m.split(".")[0] in HEAVY}
        assert not bad, f"{py.name} 모듈 수준에 무거운 의존: {bad} — 함수 안으로 내려라"


def test_용어층은_임베딩_계열을_transcribe_에서_쓰지_않는다():
    """Tier 1 은 정규식 전사다 — 임베딩·형태소·torch 가 여기 들어오면
    '비용 0·신뢰도 최고'라는 층의 정체성이 깨진다. (Phase 1 모듈은 별도 파일)"""
    heavy = {"sentence_transformers", "torch", "numpy", "kiwipiepy",
             "sklearn", "scipy", "gensim"}
    for name in ("transcribe.py", "__init__.py", "__main__.py"):
        p = TERMS / name
        if not p.exists():
            continue
        bad = {m for m in _imports(p) if m.split(".")[0] in heavy}
        assert not bad, f"core/terms/{name} 에 무거운 의존이 들어왔다: {bad}"
