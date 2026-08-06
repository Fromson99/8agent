"""파싱된 문서 보관소 — 채팅이 "어느 계약서 얘기냐"를 알 수 있게 한다.

GenOS 채팅은 텍스트 한 줄만 준다. 그런데 이 엔진의 질의·대사는 **어떤 문서의**
chunks 인지가 있어야 답할 수 있다. 그래서 파싱 결과를 id 로 붙들어 두고,
대화 세션마다 활성 문서를 기억한다.

문서는 두 곳에서 온다.

    1. `POST /v1/parser/parse` 결과 — 파싱하면 자동 등록된다
    2. 디스크의 `out/*.chunks.json`, `data/golden_pairs/*/contract.chunks.json`
       — 컨테이너에 이미 있는 것들. 첫 조회 때 한 번 훑는다.

메모리에만 둔다. 재시작하면 1번은 사라지고 2번은 다시 훑는다.
"""
from __future__ import annotations

import json
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import settings


@dataclass
class Document:
    doc_id: str
    name: str
    source: str                       # upload | disk
    chunks: dict = field(repr=False, default_factory=dict)
    path: Optional[str] = None
    registered_at: float = field(default_factory=time.time)

    def summary(self) -> dict:
        chunks = self.chunks.get("chunks") or []
        articles = sorted({c.get("article") for c in chunks if c.get("article")})
        return {"doc_id": self.doc_id, "name": self.name, "source": self.source,
                "document": self.chunks.get("document"),
                "source_pdf": self.chunks.get("source_pdf"),
                "chunks": len(chunks), "articles": len(articles),
                "path": self.path, "registered_at": self.registered_at}


def _slug(text: str) -> str:
    """파일명 → 사람이 채팅에 칠 수 있는 id. 한글은 그대로 두고 공백만 정리한다."""
    t = unicodedata.normalize("NFC", text).strip()
    out = []
    for ch in t:
        if ch.isalnum() or ch in "-_.":
            out.append(ch)
        elif ch in " \t/\\":
            out.append("-")
    s = "".join(out).strip("-.") or "doc"
    return s[:48]


class DocumentStore:
    def __init__(self) -> None:
        self._docs: dict[str, Document] = {}
        self._lock = threading.Lock()
        self._scanned = False

    # --- 등록 -------------------------------------------------------------
    def register(self, name: str, chunks: dict, source: str = "upload",
                 path: Optional[str] = None) -> Document:
        base = _slug(Path(name).stem.replace(".chunks", ""))
        with self._lock:
            doc_id, n = base, 2
            while doc_id in self._docs:
                doc_id = f"{base}-{n}"
                n += 1
            doc = Document(doc_id=doc_id, name=name, source=source,
                           chunks=chunks, path=path)
            self._docs[doc_id] = doc
        return doc

    # --- 조회 -------------------------------------------------------------
    def get(self, doc_id: str) -> Optional[Document]:
        self._ensure_scanned()
        doc = self._docs.get(doc_id)
        if doc:
            return doc
        # 대소문자·부분 일치까지 봐준다 — 채팅에서 id 를 정확히 치기 어렵다
        low = doc_id.lower()
        hits = [d for d in self._docs.values() if low in d.doc_id.lower()]
        return hits[0] if len(hits) == 1 else None

    def list(self) -> list[Document]:
        self._ensure_scanned()
        return sorted(self._docs.values(), key=lambda d: -d.registered_at)

    def latest(self) -> Optional[Document]:
        docs = self.list()
        return docs[0] if docs else None

    def delete(self, doc_id: str) -> bool:
        with self._lock:
            return self._docs.pop(doc_id, None) is not None

    # --- 디스크 -----------------------------------------------------------
    def rescan(self) -> int:
        """디스크의 chunks.json 을 다시 훑는다. 업로드본은 건드리지 않는다."""
        with self._lock:
            for i in [i for i, d in self._docs.items() if d.source == "disk"]:
                self._docs.pop(i, None)
            self._scanned = False
        self._ensure_scanned()
        return sum(1 for d in self._docs.values() if d.source == "disk")

    def _ensure_scanned(self) -> None:
        if self._scanned:
            return
        with self._lock:
            if self._scanned:
                return
            self._scanned = True
        root = settings.PARSER_ROOT
        for f in sorted(root.glob("out/*.chunks.json")) + \
                sorted(root.glob("data/golden_pairs/*/*.chunks.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue                  # 깨진 파일 하나가 목록 전체를 막지 않는다
            if not isinstance(data, dict) or "chunks" not in data:
                continue
            name = f.parent.name if f.name.startswith("contract") else f.stem
            self.register(name, data, source="disk", path=str(f.relative_to(root)))


STORE = DocumentStore()
