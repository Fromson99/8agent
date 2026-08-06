"""LLM 호출 래퍼 — 기본 off, 플래그 뒤에서만 동작 (§6 T6, §C8 T17).

원칙
    · 고정 enum + structured output(JSON) 만 요구한다 (§6 T6)
      temperature 는 이 모델 계열이 받지 않아 생략한다 — 실측 400 오류로 확인
    · **판정에는 관여하지 않는다** — 태깅 보강과 공리 후보 추출까지만 (§B3-3, §B11-5)
    · 모든 요청·응답을 그대로 기록한다. 무엇을 물었고 무엇이 왔는지 사람이 볼 수 있어야 한다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DEFAULT_MODEL = "claude-sonnet-5"
ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """`.env` 를 읽어 환경에 넣는다. 이미 있는 값은 덮지 않는다."""
    for candidate in (ROOT / ".env", ROOT.parent / "first-agent" / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").split("\n"):
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, v = s.partition("=")
            k, v = k.strip(), v.strip().strip("'\"")
            if v and not os.environ.get(k):
                os.environ[k] = v


@dataclass
class Exchange:
    """한 번의 호출 기록 — 프롬프트와 원문 응답을 그대로 남긴다."""
    kind: str
    system: str
    user: str
    raw_response: str = ""
    parsed: Any = None
    model: str = ""
    usage: dict = field(default_factory=dict)
    stop_reason: str = ""
    at: str = ""
    error: str = ""


class LLM:
    def __init__(self, model: Optional[str] = None):
        load_env()
        import anthropic

        self.model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
        self._client = anthropic.Anthropic()
        self.log: list[Exchange] = []

    def call(self, kind: str, system: str, payload: dict,
             max_tokens: int = 8192) -> Optional[dict]:
        user = json.dumps(payload, ensure_ascii=False, indent=2)
        ex = Exchange(kind=kind, system=system, user=user, model=self.model,
                      at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        try:
            # SPEC §6 T6 은 "temperature 낮게" 를 요구하지만, 이 모델 계열은
            # temperature 를 아예 받지 않는다(400: `temperature` is deprecated).
            # 결정성은 모델 기본 동작에 맡기고, 재현성은 llm_log 기록으로 확보한다.
            msg = self._client.messages.create(
                model=self.model, max_tokens=max_tokens,
                system=system, messages=[{"role": "user", "content": user}])
            ex.raw_response = "".join(b.text for b in msg.content
                                      if getattr(b, "type", "") == "text")
            ex.stop_reason = getattr(msg, "stop_reason", "") or ""
            ex.usage = {"input": msg.usage.input_tokens, "output": msg.usage.output_tokens}
            if ex.stop_reason == "max_tokens":
                ex.error = f"응답이 max_tokens({max_tokens})에서 잘렸습니다"
            else:
                ex.parsed = _extract_json(ex.raw_response)
                if ex.parsed is None:
                    ex.error = "응답에서 JSON 을 찾지 못했습니다"
        except Exception as e:                       # 호출 실패가 파이프라인을 죽이지 않게
            ex.error = f"{type(e).__name__}: {e}"
        self.log.append(ex)
        return ex.parsed

    def call_multimodal(self, kind: str, system: str, content: list[dict],
                        max_tokens: int = 8192) -> Optional[dict]:
        """이미지 + 텍스트를 함께 보낸다 (VLM 1차 스캔).

        별지는 병합 셀·체크박스라 텍스트만으로는 구조가 깨진다 — 실측으로 확인됐다.
        페이지 이미지를 함께 주면 표 배치가 보인다.
        """
        summary = json.dumps(
            [{"type": c["type"], "bytes": len(c.get("source", {}).get("data", ""))}
             if c["type"] == "image" else {"type": "text", "len": len(c.get("text", ""))}
             for c in content], ensure_ascii=False)
        ex = Exchange(kind=kind, system=system, user=summary, model=self.model,
                      at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        try:
            msg = self._client.messages.create(
                model=self.model, max_tokens=max_tokens, system=system,
                messages=[{"role": "user", "content": content}])
            ex.raw_response = "".join(b.text for b in msg.content
                                      if getattr(b, "type", "") == "text")
            ex.stop_reason = getattr(msg, "stop_reason", "") or ""
            ex.usage = {"input": msg.usage.input_tokens, "output": msg.usage.output_tokens}
            if ex.stop_reason == "max_tokens":
                ex.error = f"응답이 max_tokens({max_tokens})에서 잘렸습니다"
            else:
                ex.parsed = _extract_json(ex.raw_response)
                if ex.parsed is None:
                    ex.error = "응답에서 JSON 을 찾지 못했습니다"
        except Exception as e:
            ex.error = f"{type(e).__name__}: {e}"
        self.log.append(ex)
        return ex.parsed

    def dump_log(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            [{"kind": e.kind, "at": e.at, "model": e.model, "usage": e.usage,
              "stop_reason": e.stop_reason, "error": e.error,
              "system": e.system, "user_payload": e.user,
              "raw_response": e.raw_response, "parsed": e.parsed}
             for e in self.log], ensure_ascii=False, indent=2), encoding="utf-8")
        return p

    def totals(self) -> dict:
        return {
            "calls": len(self.log),
            "input_tokens": sum(e.usage.get("input", 0) for e in self.log),
            "output_tokens": sum(e.usage.get("output", 0) for e in self.log),
            "errors": sum(1 for e in self.log if e.error),
        }


def _extract_json(text: str) -> Optional[dict]:
    """코드펜스·앞뒤 문장을 견디고 균형 잡힌 { } 를 꺼낸다. 정규식 없음."""
    s = (text or "").strip()
    if s.startswith("```"):
        nl = s.find("\n")
        s = s[nl + 1:] if nl >= 0 else s[3:]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
        s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    depth, start, in_str, esc = 0, -1, False, False
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    return json.loads(s[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None
