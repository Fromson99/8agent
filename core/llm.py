"""LLM 호출 래퍼 — **컴파일 국면 전용** (SPEC §0 핵심원칙 1).

stochastic 은 컴파일 타임에 가둔다. 이 모듈은 형식 유도(T4)와 후보 제안에만 쓰이고,
런타임(구조화·비교)에서는 **import 조차 되지 않는다.**

기록: 모든 요청·응답을 그대로 남긴다. 무엇을 물었고 무엇이 왔는지 사람이 볼 수 있어야
형식을 신뢰할 수 있다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

DEFAULT_MODEL = "claude-opus-5"
ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """`.env` 를 읽어 환경에 넣는다. 이미 있는 값은 덮지 않는다."""
    for candidate in (ROOT / ".env", ROOT / "first-agent" / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, v = s.partition("=")
            k, v = k.strip(), v.strip().strip("'\"")
            if v and not os.environ.get(k):
                os.environ[k] = v


@dataclass
class Exchange:
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
    # 이 호출에 함께 보낸 그림의 **개수**. 픽셀 자체는 로그에 남기지 않는다 —
    # 감사 로그가 base64 로 뒤덮이면 사람이 못 읽는다. 몇 장을 보고 답했는지는 남는다.
    images: int = 0

    def dump(self) -> dict:
        return {"kind": self.kind, "at": self.at, "model": self.model,
                "usage": self.usage, "stop_reason": self.stop_reason,
                "images": self.images,
                "system": self.system, "user": self.user,
                "raw_response": self.raw_response, "error": self.error}


class LLM:
    def __init__(self, model: Optional[str] = None):
        load_env()
        import anthropic

        self.model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
        self._client = anthropic.Anthropic()
        self.log: list[Exchange] = []

    def structured(self, kind: str, system: str, user: str, schema: dict,
                   max_tokens: int = 16000, effort: str = "high",
                   images: Optional[list[str]] = None) -> Optional[dict]:
        """structured output 으로 JSON 을 받는다 (§2.3 "structured output").

        temperature 는 보내지 않는다 — 이 모델 계열에서 제거되어 400 이 난다.
        결정성은 스키마 고정과 낮은 effort 로 얻고, 어차피 결과는 사람이 확정한다(§2.4).

        `images` 를 주면 **같은 호출에 그림을 함께 보낸다**(VLM). 쓰는 자리는 하나다:
        결정론이 **글자로는 볼 수 없는 축**을 물을 때. 마커 없는 제목은 크고 굵고 위가
        트여 있어서 제목인데, 그 판단의 근거가 픽셀에 있다. 텍스트만 보내면 모델도
        우리와 똑같이 못 본다.

        받는 형식은 `data:image/png;base64,...` (뷰어가 이미 그 형태로 페이지를 렌더한다).
        """
        ex = Exchange(kind=kind, system=system, user=user, model=self.model,
                      at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        content: Any = user
        if images:
            blocks: list[dict] = []
            for uri in images:
                head, _, b64 = str(uri).partition(",")
                if not b64:
                    continue
                media = head[len("data:"):].split(";")[0] or "image/png"
                blocks.append({"type": "image",
                               "source": {"type": "base64", "media_type": media,
                                          "data": b64}})
            # 그림을 **먼저**, 물음을 나중에 둔다 — 무엇을 보고 답할지가 정해진 뒤에
            # 질문이 와야 모델이 그림을 근거로 삼는다.
            content = blocks + [{"type": "text", "text": user}]
            ex.images = len(blocks)
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                output_config={"format": {"type": "json_schema", "schema": schema},
                               "effort": effort},
                messages=[{"role": "user", "content": content}],
            )
            ex.stop_reason = resp.stop_reason or ""
            ex.usage = {"input_tokens": resp.usage.input_tokens,
                        "output_tokens": resp.usage.output_tokens}
            if resp.stop_reason == "refusal":
                ex.error = "모델이 요청을 거절했습니다 (stop_reason=refusal)"
                return None
            text = next((b.text for b in resp.content if b.type == "text"), "")
            ex.raw_response = text
            ex.parsed = json.loads(text)
            return ex.parsed
        except Exception as exc:                       # 호출·파싱 실패를 삼키지 않는다
            ex.error = f"{type(exc).__name__}: {exc}"
            return None
        finally:
            self.log.append(ex)

    def totals(self) -> dict:
        return {
            "calls": len(self.log),
            "input_tokens": sum(e.usage.get("input_tokens", 0) for e in self.log),
            "output_tokens": sum(e.usage.get("output_tokens", 0) for e in self.log),
            "errors": sum(1 for e in self.log if e.error),
        }

    def dump_log(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps([e.dump() for e in self.log], ensure_ascii=False, indent=2),
                     encoding="utf-8")
        return p
