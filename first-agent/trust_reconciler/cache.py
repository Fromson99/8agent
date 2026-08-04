"""스냅샷 저장소 — LLM 호출을 입력 해시로 기록·재생한다.

## 왜 필요한가

문서 해석을 LLM 이 하면 같은 입력에 다른 답이 나올 수 있다.
금융 대사에서 "어제는 일치였는데 오늘은 불일치"는 그 자체로 사고다.

    1회차  키가 있을 때 실행 → 모든 호출이 스냅샷에 기록됨
    2회차  스냅샷을 재생 → 결과가 고정. API 키 없이도 동일 리포트가 나온다.
    감사   사람이 스냅샷 JSON 을 열어 잘못된 판정을 고치면 그게 정답이 된다.

## 해시에 들어가는 것

호출 종류 + 입력 페이로드 전체 + 프롬프트 내용.
프롬프트를 고치면 해시가 달라져 자동으로 다시 호출된다 — 낡은 판정이 남지 않는다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional


def _stable(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class SnapshotStore:
    def __init__(self, path: str | Path, prompt_fingerprint: str = ""):
        self.path = Path(path)
        self.prompt_fingerprint = prompt_fingerprint
        self._data: dict[str, dict] = {}
        self._dirty = False
        self._hits = 0
        self._misses = 0
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._data = raw.get("entries", {})

    # --- 키 -------------------------------------------------------------
    def key(self, kind: str, payload: dict) -> str:
        h = hashlib.sha256()
        h.update(kind.encode())
        h.update(b"\0")
        h.update(self.prompt_fingerprint.encode())
        h.update(b"\0")
        h.update(_stable(payload).encode())
        return f"{kind}:{h.hexdigest()[:24]}"

    # --- 조회 / 기록 -----------------------------------------------------
    def get(self, kind: str, payload: dict) -> Optional[dict]:
        entry = self._data.get(self.key(kind, payload))
        if entry is None:
            self._misses += 1
            return None
        self._hits += 1
        return entry.get("result")

    def put(self, kind: str, payload: dict, result: dict) -> None:
        self._data[self.key(kind, payload)] = {
            "kind": kind,
            # 사람이 열어 볼 때 무슨 호출이었는지 알 수 있게 요약을 같이 남긴다
            "input_summary": _summarize(kind, payload),
            "result": result,
        }
        self._dirty = True

    def save(self) -> bool:
        if not self._dirty:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            {"prompt_fingerprint": self.prompt_fingerprint, "entries": self._data},
            ensure_ascii=False, indent=2), encoding="utf-8")
        self._dirty = False
        return True

    @property
    def stats(self) -> dict:
        return {"hits": self._hits, "misses": self._misses, "entries": len(self._data)}


def _summarize(kind: str, payload: dict) -> str:
    if kind == "tag_blocks":
        return f"{payload.get('doc_role')} blocks={len(payload.get('blocks') or [])}"
    if kind == "extract_elements":
        return f"{payload.get('doc_role')} tag={payload.get('tag')}"
    if kind == "pair_sections":
        return f"candidates={len(payload.get('candidates') or [])}"
    if kind == "compare_values":
        return f"{payload.get('tag')}.{payload.get('element_id')}"
    if kind == "doc_meta":
        return str(payload.get("file_name", ""))
    return ""


def prompt_fingerprint() -> str:
    """프롬프트 5종의 내용 해시. 프롬프트가 바뀌면 스냅샷이 자동 무효화된다."""
    from .llm.client import CALLS, load_prompt

    h = hashlib.sha256()
    for name in CALLS:
        h.update(name.encode())
        h.update(load_prompt(name).encode())
    return h.hexdigest()[:16]
