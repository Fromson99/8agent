"""T-A6.5 녹화/재생 — LLM 응답을 파일로 고정한다 (AGENT6 §9-6 대체).

lexicon 이 없어지면서 판정은 **전부 LLM 이** 한다. 그러면 테스트가 키 없이 돌던 길
(LLM-off 결정론 모드)이 사라진다. 그 길을 여기서 다시 낸다 — 실제 모델 응답을 한 번
녹화해 두고, 테스트는 재생만 한다. 재생은 결정론이고 키가 필요 없다.

    live    호출만 한다. 저장하지 않는다. (운영 기본)
    record  호출하고 응답을 `tests/agent6/fixtures/llm/{키}.json` 에 저장한다.
    replay  저장된 것만 쓴다. 없으면 **예외**를 던지고 무엇을 녹화해야 하는지 출력한다.

## 키를 무엇으로 잡는가

요청(kind + system + user + 응답 스키마)의 sha256 앞 16자다. 파일명에 프롬프트 전문을
넣으면 파일명이 못 쓰게 길어지고, 항목 id 만 넣으면 프롬프트가 바뀌어도 같은 녹화가
재생되어 **바뀐 프롬프트를 시험하지 못한다**. 대신 파일 *안에* 무엇의 녹화인지를 적는다
(kind · 항목 id 목록 · 프롬프트 앞머리 · 모델 · 녹화 시각).

`kind` 에 자기일관성 **회차**(#1·#2·#3)가 들어 있는 것이 중요하다. 같은 프롬프트를 k번
부르는 것이 자기일관성인데 회차를 키에서 빼면 k번이 전부 같은 응답으로 재생되어
**갈림 자체가 재현되지 않는다**. 회차를 키에 넣으면 "1회는 PASS, 2회는 UNCLEAR" 같은
실제 갈림까지 그대로 재생된다.

모델 이름은 키에서 뺀다 — 기계마다 `ANTHROPIC_MODEL` 이 달라 재생이 통째로 깨지기
때문이다. 대신 녹화 파일에 적어 두고, 다른 모델의 녹화를 재생하면 경고를 남긴다.

## 실패는 녹화하지 않는다

호출이 실패(None)했을 때 그것을 녹화하면, 재생에서 그 항목은 영원히 "판정 실패"가 된다.
실패는 그때그때의 사정이지 고정할 사실이 아니다. 그래서 성공한 응답만 저장하고, 실패는
경고로 남긴다(§0 조용한 실패 금지).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_CACHE_DIR = ROOT / "tests" / "agent6" / "fixtures" / "llm"

MODES = ("live", "record", "replay")

# 키 길이. 16자(64비트)면 이 저장소가 낼 수 있는 녹화 수에서 충돌 확률이 무시할 만하고,
# 파일명을 눈으로 구별할 수 있는 길이다.
KEY_CHARS = 16

# 파일 안에 남기는 프롬프트 앞머리 — 사람이 열어 보고 "무엇의 녹화인가"를 알기 위한 것이지
# 재생 판단에 쓰이지 않는다(판단은 키가 한다).
HEAD_CHARS = 240


class CacheMiss(RuntimeError):
    """replay 인데 녹화가 없다. **조용히 넘어가지 않는다** — 무엇을 녹화해야 하는지 말한다."""


class LLMUnavailable(RuntimeError):
    """LLM 클라이언트를 열지 못했다(키 없음·SDK 없음). 판정 국면이 이것을 시끄럽게 보고한다."""


def request_key(kind: str, system: str, user: str, schema: Any) -> str:
    """요청 하나의 지문. 프롬프트가 한 글자라도 바뀌면 다른 키다(그래야 녹화가 낡지 않는다)."""
    h = hashlib.sha256()
    for part in (kind, system, user, json.dumps(schema, ensure_ascii=False, sort_keys=True)):
        h.update(str(part).encode("utf-8"))
        h.update(b"\x00")                     # 경계 없이 이으면 서로 다른 조합이 같은 해시가 된다
    return h.hexdigest()[:KEY_CHARS]


@dataclass
class CacheStats:
    """이 실행에서 무슨 일이 있었는지. CLI 가 그대로 출력한다."""
    calls: int = 0                            # 요청 수 (재생 포함)
    live: int = 0                             # 실제 API 호출
    recorded: int = 0                         # 새로 저장한 녹화
    replayed: int = 0                         # 파일에서 재생
    failed: int = 0                           # 호출했으나 응답을 못 받음

    def text(self) -> str:
        return (f"요청 {self.calls}회 (실호출 {self.live} / 재생 {self.replayed} / "
                f"신규녹화 {self.recorded} / 실패 {self.failed})")


class RecordingClient:
    """LLM 클라이언트 래퍼. 판정기는 **언제나 이것과만** 이야기한다.

    live 모드에서도 감싸는 이유: 호출 수·재생 수를 세는 자리를 한 곳으로 두기 위해서다.
    모드마다 다른 객체를 쓰면 "실제로 몇 번 불렀나"를 모드별로 따로 세게 되고, 그 수가
    리포트에 실리는 순간 어느 쪽이 맞는지 알 수 없게 된다.
    """

    def __init__(self, inner: Any, *, mode: str = "live",
                 cache_dir: str | Path = DEFAULT_CACHE_DIR):
        if mode not in MODES:
            raise ValueError(f"llm_mode 는 {MODES} 중 하나여야 합니다 (받은 값 '{mode}')")
        if mode != "replay" and inner is None:
            raise LLMUnavailable(f"{mode} 모드에는 실제 LLM 클라이언트가 필요합니다")
        self.inner = inner
        self.mode = mode
        self.cache_dir = Path(cache_dir)
        self.stats = CacheStats()
        self.warnings: list[str] = []
        self.misses: list[dict[str, Any]] = []

    # --- 판정기가 부르는 것 --------------------------------------------------
    def structured(self, kind: str, system: str, user: str, schema: dict,
                   *, summary: Sequence[str] = (), **kw) -> Optional[dict]:
        """core.llm.LLM.structured 와 같은 계약. `summary` 는 녹화 파일에만 실린다."""
        key = request_key(kind, system, user, schema)
        self.stats.calls += 1
        path = self.cache_dir / f"{key}.json"

        if self.mode == "replay":
            return self._replay(path, key, kind, summary)

        payload = self.inner.structured(kind=kind, system=system, user=user,
                                        schema=schema, **kw)
        self.stats.live += 1
        if payload is None:
            self.stats.failed += 1
            self.warnings.append(f"{kind}: 응답을 받지 못해 녹화하지 않았습니다")
            return None
        if self.mode == "record":
            self._write(path, key, kind, system, user, summary, payload)
            self.stats.recorded += 1
        return payload

    # --- 재생 ---------------------------------------------------------------
    def _replay(self, path: Path, key: str, kind: str,
                summary: Sequence[str]) -> dict:
        if not path.exists():
            self.misses.append({"key": key, "kind": kind, "items": list(summary),
                                "path": str(path)})
            raise CacheMiss(self._miss_text(path, key, kind, summary))
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CacheMiss(f"녹화 파일을 읽지 못했습니다: {path} — {exc}. "
                            f"파일을 지우고 --llm-mode record 로 다시 녹화하세요") from exc
        if not isinstance(data, dict) or data.get("response") is None:
            raise CacheMiss(f"녹화 파일에 response 가 없습니다: {path} — "
                            f"--llm-mode record 로 다시 녹화하세요")
        recorded_model = str(data.get("model") or "")
        want = getattr(self.inner, "model", None)
        if want and recorded_model and recorded_model != want:
            self.warnings.append(
                f"{kind}: 녹화는 모델 '{recorded_model}' 로 만들어졌습니다(지금 설정은 '{want}')")
        self.stats.replayed += 1
        return data["response"]

    def _miss_text(self, path: Path, key: str, kind: str,
                   summary: Sequence[str]) -> str:
        have = len(list(self.cache_dir.glob("*.json"))) if self.cache_dir.exists() else 0
        items = ", ".join(summary) or "(항목 미상)"
        return (
            f"녹화가 없습니다 — replay 모드에서는 판정할 수 없습니다.\n"
            f"  키    {key}\n"
            f"  요청  kind={kind}  항목={items}\n"
            f"  파일  {path}  (이 디렉터리의 녹화 {have}건)\n"
            f"  녹화  같은 입력으로 `--llm-mode record` 를 한 번 돌리면 이 파일이 생깁니다.\n"
            f"        프롬프트(항목 스펙·전사·근거 발췌)가 바뀌면 키도 바뀝니다 — "
            f"낡은 녹화를 재생하지 않기 위한 것이며, 다시 녹화해야 합니다.")

    # --- 녹화 ---------------------------------------------------------------
    def _write(self, path: Path, key: str, kind: str, system: str, user: str,
               summary: Sequence[str], payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {
            "key": key,
            "kind": kind,
            "items": list(summary),
            "model": getattr(self.inner, "model", ""),
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "system_head": system[:HEAD_CHARS],
            "user_head": user[:HEAD_CHARS],
            "user_chars": len(user),
            "response": payload,
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)                      # 중간에 죽어도 반쪽 녹화가 남지 않는다

    # --- 계정 ---------------------------------------------------------------
    @property
    def log(self) -> list:
        return list(getattr(self.inner, "log", []) or [])

    def totals(self) -> dict[str, Any]:
        """토큰·호출 합계. 재생분은 토큰을 쓰지 않았으므로 0 으로 잡힌다(사실 그대로)."""
        base: dict[str, Any] = {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                                "errors": 0}
        if self.inner is not None and hasattr(self.inner, "totals"):
            try:
                base.update(self.inner.totals())
            except Exception as exc:            # 통계 실패로 판정을 잃지 않는다
                self.warnings.append(f"LLM 통계를 읽지 못했습니다: {type(exc).__name__}: {exc}")
        base.update({"mode": self.mode, "requests": self.stats.calls,
                     "replayed": self.stats.replayed,
                     "recorded": self.stats.recorded,
                     "failed": self.stats.failed})
        return base


def open_client(mode: str = "live", *, model: Optional[str] = None,
                cache_dir: str | Path = DEFAULT_CACHE_DIR) -> RecordingClient:
    """모드에 맞는 클라이언트를 연다.

    replay 는 **API 키를 요구하지 않는다** — 이 모드에 실제 클라이언트가 필요 없다는 것이
    녹화/재생의 요점이다. live·record 는 열지 못하면 `LLMUnavailable` 을 올린다.
    """
    if mode not in MODES:
        raise ValueError(f"llm_mode 는 {MODES} 중 하나여야 합니다 (받은 값 '{mode}')")
    if mode == "replay":
        return RecordingClient(None, mode=mode, cache_dir=cache_dir)
    try:
        from core.llm import LLM
    except Exception as exc:
        raise LLMUnavailable(f"core.llm 을 불러오지 못했습니다: "
                             f"{type(exc).__name__}: {exc}") from exc
    try:
        inner = LLM(model)
    except Exception as exc:                    # 대개 ANTHROPIC_API_KEY 없음
        raise LLMUnavailable(f"LLM 을 열지 못했습니다: {type(exc).__name__}: {exc} — "
                             f"first-agent/.env 의 ANTHROPIC_API_KEY 를 확인하세요") from exc
    return RecordingClient(inner, mode=mode, cache_dir=cache_dir)


def wrap(client: Any, *, mode: str = "live",
         cache_dir: str | Path = DEFAULT_CACHE_DIR) -> RecordingClient:
    """이미 만들어진 클라이언트(테스트의 가짜 포함)를 같은 계약으로 감싼다."""
    if isinstance(client, RecordingClient):
        return client
    return RecordingClient(client, mode=mode, cache_dir=cache_dir)


def index(cache_dir: str | Path = DEFAULT_CACHE_DIR) -> list[dict[str, Any]]:
    """녹화 목록 — 사람이 "무엇이 녹화돼 있나"를 볼 때 쓴다."""
    d = Path(cache_dir)
    out: list[dict[str, Any]] = []
    for p in sorted(d.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            out.append({"key": p.stem, "kind": "(읽을 수 없음)", "items": []})
            continue
        out.append({"key": data.get("key", p.stem), "kind": data.get("kind", ""),
                    "items": data.get("items", []), "model": data.get("model", ""),
                    "recorded_at": data.get("recorded_at", "")})
    return out
