"""raw 등록부 — `01_DATA/INBOX/AUTHORING/corpus/` 가 원본층(raw)이다. 들어오는 길이 무엇이든 원본은
여기 한 번 남고, 출처별 `manifest.json` 한 줄이 그 원본의 등록이다.

수집기(collect)는 처음부터 이 규약으로 쓴다(law·krx·kofia·expc…). 이 모듈은
**수집기 밖**으로 들어오는 원본 — 화면 업로드, inbox, 손으로 둔 파일(서식·내규)
— 에 같은 규약을 적용한다:

    01_DATA/INBOX/AUTHORING/corpus/<source>/<파일>                    원본 사본 (불변)
    01_DATA/INBOX/AUTHORING/corpus/<source>/manifest.json             {"source", "collected_at", "items": [...]}
    항목  name · kind · status "ok" · body_file(저장소 뿌리 상대) · body_sha256 ·
          body_format(hwp5(ole)|docx|pdf|xml|html) · collected_at · folder · via · orig_filename

왜: 구조 스토어(01_DATA/INBOX/AUTHORING/structure)는 **파생**이다 — 규칙이 바뀌면 다시 만든다. 그 안의
source.* 만이 원본이면 스토어를 비우는 순간 원본이 사라지고, 계보 원장(lineage)은
"수집 밖에서 들어온 것"으로만 본다. 원본은 파생과 다른 층에 있어야 하고, 한 줄의
등록이 있어야 "무엇을 갖고 있나"를 셀 수 있다(배치 라인업·원장이 이걸 읽는다).

조인 키는 **본문 sha256** — 구조 스토어 doc_id 가 sha 앞 16자리라 이름 없이 이어진다.
이미 어느 manifest 에 있는 sha 는 다시 등록하지 않는다(사본도 안 만든다) —
배치가 manifest 항목을 투입할 때 uploads 에 또 쌓이지 않게.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from lawrag.platform.paths import data_path, repository_root

log = logging.getLogger("lawrag.core.rawstore")

UPLOADS = "uploads"
FORMAT_BY_EXT = {".hwp": "hwp5(ole)", ".hwpx": "hwpx", ".docx": "docx", ".pdf": "pdf",
                 ".xml": "xml", ".html": "html", ".htm": "html", ".doc": "doc", ".md": "md"}


def corpus_dir() -> Path:
    return Path(os.environ.get("CORPUS_DIR") or data_path("INBOX", "AUTHORING", "corpus"))


def corpus_for(store: Optional[Path]) -> Path:
    """스토어 옆의 raw 층 — glossary·embeddings 와 같은 '스토어 부모' 규약. CORPUS_DIR
    가 명시되면 그것이 이긴다. 시험이 tmp 스토어로 돌 때 실제 01_DATA/INBOX/AUTHORING/corpus 에 등록이
    새지 않게 하는 규칙이기도 하다."""
    if os.environ.get("CORPUS_DIR"):
        return Path(os.environ["CORPUS_DIR"])
    if store is not None:
        return data_path("INBOX", "AUTHORING", "corpus")
    return corpus_dir()


def _repo_root_for(corpus: Path) -> Path:
    """manifest 의 body_file 은 저장소 뿌리 상대 경로 — lineage._manifest_root 와 같은 규칙."""
    c = corpus.resolve()
    try:
        c.relative_to(data_path().resolve())
    except ValueError:
        pass
    else:
        return repository_root()
    if c.name == "corpus" and c.parent.name == "data":
        return c.parent.parent
    return c.parent


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_of(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


# ------------------------------------------------------------------ 읽기
_cache: dict = {}


def known_shas(corpus: Optional[Path] = None) -> dict[str, dict]:
    """모든 출처 manifest 의 본문 sha256 → {source, name}. mtime 캐시."""
    corpus = corpus or corpus_dir()
    if not corpus.is_dir():
        return {}
    paths = sorted(corpus.glob("*/manifest.json"))
    sig = tuple((str(p), p.stat().st_mtime_ns) for p in paths)
    if _cache.get("sig") == sig and _cache.get("corpus") == str(corpus):
        return _cache["shas"]
    out: dict[str, dict] = {}
    for p in paths:
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = m.get("items", []) if isinstance(m, dict) else m
        src = (m.get("source") if isinstance(m, dict) else None) or p.parent.name
        for it in items:
            sha = it.get("body_sha256")
            if not sha:
                for a in it.get("attachments", []):
                    if a.get("role") == "body" and a.get("sha256"):
                        sha = a["sha256"]
                        break
            if sha:
                out.setdefault(sha, {"source": src, "name": it.get("name")})
    _cache.update(sig=sig, corpus=str(corpus), shas=out)
    return out


def load_manifest(source: str, corpus: Optional[Path] = None) -> dict:
    corpus = corpus or corpus_dir()
    p = corpus / source / "manifest.json"
    if p.exists():
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(m, dict):
                m.setdefault("items", [])
                return m
        except Exception:
            pass
    return {"source": source, "collected_at": "", "items": []}


def save_manifest(source: str, m: dict, corpus: Optional[Path] = None) -> Path:
    corpus = corpus or corpus_dir()
    d = corpus / source
    d.mkdir(parents=True, exist_ok=True)
    m["collected_at"] = m.get("collected_at") or time.strftime("%Y-%m-%d %H:%M:%S")
    m["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    p = d / "manifest.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    _cache.clear()
    return p


# ------------------------------------------------------------------ 등록
_SAFE = re.compile(r"[^\w.\-()\[\]가-힣 ]+")


def _safe_name(name: str) -> str:
    return _SAFE.sub("_", name).strip() or "file"


def _storage_name(sha: str, filename: str) -> str:
    """Keep ordinary paths; bound the copy's basename without losing its source name."""
    name = _safe_name(Path(filename or "file").name)
    candidate = f"{sha[:16]}__{name}"
    if len(os.fsencode(candidate)) <= 255:
        return candidate
    # Source bytes and orig_filename remain unchanged in the manifest. A full
    # content hash identifies the stored copy when the readable name is too long.
    suffix = Path(name).suffix
    return sha + (suffix if len(os.fsencode(suffix)) <= 16 else "")


def ensure(raw: bytes, filename: str, *, source: str = UPLOADS, name: str = "",
           kind: str = "", folder: str = "", via: str = "upload",
           extra: Optional[dict] = None, corpus: Optional[Path] = None) -> dict:
    """원본 한 건을 등록한다 — 이미 어느 manifest 에 있는 sha 면 그 기록을 돌려주고
    끝(사본 없음). 없으면 corpus/<source>/ 에 사본을 쓰고 manifest 한 줄을 더한다.
    반환 {"sha256", "new": bool, "source", "path"|None, "item"|None}."""
    corpus = corpus or corpus_dir()
    sha = sha256_of(raw)
    have = known_shas(corpus).get(sha)
    if have is not None:
        return {"sha256": sha, "new": False, "source": have["source"], "path": None,
                "item": None, "name": have.get("name")}
    ext = Path(filename or "").suffix.lower()
    sub = datetime.now().strftime("%Y-%m")
    rel_dir = corpus / source / sub if source == UPLOADS else corpus / source
    rel_dir.mkdir(parents=True, exist_ok=True)
    dest = rel_dir / _storage_name(sha, filename)
    if not dest.exists():
        dest.write_bytes(raw)
    root = _repo_root_for(corpus)
    try:
        rel = str(dest.resolve().relative_to(root))
    except ValueError:
        rel = str(dest)
    item = {"source": source, "name": name or Path(filename or "").stem,
            "kind": kind or "", "status": "ok", "via": via,
            "orig_filename": Path(filename or "").name,
            "body_file": rel, "body_sha256": sha,
            "body_format": FORMAT_BY_EXT.get(ext, ext.lstrip(".") or "bin"),
            "body_bytes": len(raw), "collected_at": _now(), "doc_id": sha[:16]}
    if folder:
        item["folder"] = folder
    if extra:
        item.update({k: v for k, v in extra.items() if v not in (None, "")})
    m = load_manifest(source, corpus)
    m["items"].append(item)
    save_manifest(source, m, corpus)
    log.info("raw 등록 — %s/%s ← %s (%s)", source, dest.name, via, kind or "?")
    return {"sha256": sha, "new": True, "source": source, "path": str(dest), "item": item,
            "name": item["name"]}


def register_files(paths: list[Path], *, source: str, kind: str = "",
                   names: Optional[dict] = None, move: bool = True,
                   sidecars: bool = True, extra: Optional[dict] = None,
                   corpus: Optional[Path] = None) -> dict:
    """손으로 둔 파일 묶음을 corpus/<source>/ 로 옮기고(또는 복사) manifest 를 만든다.

    names: sha16 → 표시 이름 (구조 스토어 meta.name 과 맞추고 싶을 때).
    sidecars: 같은 이름의 `.md`(hwp 변환 사이드카)도 함께 옮긴다 — 계보 원장의
    '변환 완료' 가 그대로 이어진다.
    같은 sha 가 이미 어느 manifest 에 있으면 건너뛴다(dup 목록으로 보고)."""
    corpus = corpus or corpus_dir()
    dest_dir = corpus / source
    dest_dir.mkdir(parents=True, exist_ok=True)
    m = load_manifest(source, corpus)
    known = known_shas(corpus)
    root = _repo_root_for(corpus)
    added, dup, moved = [], [], []
    for p in paths:
        p = Path(p)
        if not p.is_file():
            continue
        raw = p.read_bytes()
        sha = sha256_of(raw)
        if sha in known:
            dup.append({"file": p.name, "source": known[sha]["source"]})
            continue
        dest = dest_dir / p.name
        if dest.exists() and sha256_of(dest.read_bytes()) != sha:
            dest = dest_dir / f"{sha[:16]}__{p.name}"
        if move:
            shutil.move(str(p), str(dest))
        else:
            shutil.copy2(str(p), str(dest))
        moved.append(str(dest))
        if sidecars:
            sc = p.with_name(p.name + ".md")
            if sc.exists():
                (shutil.move if move else shutil.copy2)(str(sc), str(dest_dir / sc.name))
        ext = dest.suffix.lower()
        item = {"source": source, "name": (names or {}).get(sha[:16]) or dest.stem,
                "kind": kind, "status": "ok", "via": "register",
                "orig_filename": p.name,
                "body_file": str(dest.resolve().relative_to(root)),
                "body_sha256": sha, "body_format": FORMAT_BY_EXT.get(ext, ext.lstrip(".")),
                "body_bytes": len(raw), "collected_at": _now(), "doc_id": sha[:16]}
        if extra:
            item.update(extra)
        m["items"].append(item)
        known[sha] = {"source": source, "name": item["name"]}
        added.append(item)
    if added:
        save_manifest(source, m, corpus)
    return {"added": added, "dup": dup, "moved": moved, "manifest": str(dest_dir / "manifest.json")}
