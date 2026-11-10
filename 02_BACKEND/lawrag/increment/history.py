"""증분 상태와 업데이트 기록 — 새 DB 표 대신 Dataiku 관리 폴더(또는 로컬 폴더)에 JSON.

  state.json                 지금 세대(검색 게시 ID)·지금 원문 ZIP 이름/해시·파일별 판단·작업 기록
  structured/<sha>.json.gz   떨어진 파일의 구조화 결과 (같은 파일을 다시 구조화하지 않게)
  runs/<run>/decide.json     실행별 판단, previews/<문서>.html 대비표
  updates/<NNNN>/update.json 반영 한 번의 변경 내용(채널 전/후·문서별 조문 변경·원문 ZIP 전/후)
  updates/<NNNN>/old/…       바꿔치기 전 원문 파일 (되돌릴 때 다시 끼운다)

업데이트 기록은 최근 KEEP(3)개만 둔다. Gold 세대도 지금 것 + 이전 2개(합 3개)만 남긴다.
"""
from __future__ import annotations

import gzip
import io
import json
from pathlib import Path, PurePosixPath

KEEP = 3


class Store:
    """경로 기반 저장소. LocalStore(로컬 폴더)와 DataikuStore(관리 폴더)가 같은 모양."""

    def get(self, path: str) -> bytes | None: ...
    def put(self, path: str, data: bytes) -> None: ...
    def list(self, prefix: str = "") -> list[str]: ...
    def delete(self, path: str) -> None: ...
    def download(self, path: str, local) -> bool: ...
    def upload_file(self, path: str, local) -> None: ...

    def get_json(self, path: str, default=None):
        data = self.get(path)
        return default if data is None else json.loads(data.decode("utf-8"))

    def put_json(self, path: str, value) -> None:
        self.put(path, json.dumps(value, ensure_ascii=False, indent=1, sort_keys=True).encode("utf-8"))

    def get_gz_json(self, path: str):
        data = self.get(path)
        return None if data is None else json.loads(gzip.decompress(data).decode("utf-8"))

    def put_gz_json(self, path: str, value) -> None:
        self.put(path, gzip.compress(json.dumps(value, ensure_ascii=False).encode("utf-8"), mtime=0))


class LocalStore(Store):
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, path: str) -> Path:
        rel = PurePosixPath(path)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("저장 경로")
        return self.root.joinpath(*rel.parts)

    def get(self, path):
        p = self._p(path)
        return p.read_bytes() if p.is_file() else None

    def put(self, path, data):
        p = self._p(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)

    def list(self, prefix=""):
        return sorted(str(p.relative_to(self.root).as_posix()) for p in self.root.rglob("*")
                      if p.is_file() and str(p.relative_to(self.root).as_posix()).startswith(prefix))

    def delete(self, path):
        p = self._p(path)
        if p.is_file():
            p.unlink()

    def download(self, path, local):
        p = self._p(path)
        if not p.is_file():
            return False
        import shutil
        shutil.copyfile(p, local)
        return True

    def upload_file(self, path, local):
        import shutil
        p = self._p(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local, p)


class DataikuStore(Store):
    def __init__(self, folder):
        self.folder = folder

    def get(self, path):
        if path not in self.list(path):
            return None
        with self.folder.get_download_stream(path) as stream:
            return stream.read()

    def put(self, path, data):
        self.folder.upload_stream(path, io.BytesIO(data))

    def list(self, prefix=""):
        return sorted(p.lstrip("/") for p in self.folder.list_paths_in_partition() if p.lstrip("/").startswith(prefix))

    def delete(self, path):
        self.folder.delete_path(path)

    def download(self, path, local):
        if path not in self.list(path):
            return False
        with self.folder.get_download_stream(path) as stream, open(local, "wb") as out:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                out.write(chunk)
        return True

    def upload_file(self, path, local):
        with open(local, "rb") as f:
            self.folder.upload_stream(path, f)


# ------------------------------------------------------------------ 상태

def state(store: Store) -> dict:
    return store.get_json("state.json", {"schema": "increment-state-v1", "current_query": "", "corpus": {},
                                         "files": {}, "jobs": {}, "seq": 0})


def save_state(store: Store, value: dict) -> None:
    store.put_json("state.json", value)


# ------------------------------------------------------------------ 업데이트 기록

def updates(store: Store) -> list[dict]:
    seqs = sorted({p.split("/")[1] for p in store.list("updates/") if p.endswith("/update.json")})
    return [store.get_json(f"updates/{s}/update.json") for s in seqs]


def write_update(store: Store, record: dict, old_files: dict[str, bytes]) -> dict:
    st = state(store)
    seq = int(st.get("seq", 0)) + 1
    name = f"{seq:04d}"
    for member, data in old_files.items():
        store.put(f"updates/{name}/old/{member}", data)
    record = {**record, "seq": seq, "status": record.get("status", "ACTIVE"),
              "old_files": sorted(old_files)}
    store.put_json(f"updates/{name}/update.json", record)
    st["seq"] = seq
    save_state(store, st)
    trim(store)
    return record


def trim(store: Store, keep: int = KEEP) -> list[str]:
    """오래된 업데이트 기록부터 지워 최근 keep개만 남긴다."""
    seqs = sorted({p.split("/")[1] for p in store.list("updates/") if p.endswith("/update.json")})
    removed = seqs[:-keep] if len(seqs) > keep else []
    for s in removed:
        for p in store.list(f"updates/{s}/"):
            store.delete(p)
    return removed


def mark(store: Store, seq: int, status: str, **extra) -> None:
    path = f"updates/{seq:04d}/update.json"
    record = store.get_json(path)
    record.update(status=status, **extra)
    store.put_json(path, record)


def old_files(store: Store, seq: int, members: list[str]) -> dict[str, bytes]:
    out = {}
    for member in members:
        data = store.get(f"updates/{seq:04d}/old/{member}")
        if data is None:
            raise ValueError(f"되돌릴 옛 파일 없음: {member}")
        out[member] = data
    return out


def keep_queries(store: Store, current_query: str, keep: int = KEEP) -> list[str]:
    """남길 Gold 세대: 지금 것 + 최근 활성 업데이트들의 이전 세대 (합 keep개)."""
    out = [current_query] if current_query else []
    for record in reversed(updates(store)):
        before = (record.get("channel_before") or {}).get("query_id")
        if before and before not in out:
            out.append(before)
        if len(out) >= keep:
            break
    return out[:keep]
