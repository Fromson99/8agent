"""LLM 호출 래퍼 — **컴파일 국면 전용** (SPEC §0 핵심원칙 1).

stochastic 은 컴파일 타임에 가둔다. 이 모듈은 형식 유도(T4)와 후보 제안에만 쓰이고,
런타임(구조화·비교)에서는 **import 조차 되지 않는다.**

기록: 모든 요청·응답을 그대로 남긴다. 무엇을 물었고 무엇이 왔는지 사람이 볼 수 있어야
형식을 신뢰할 수 있다.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# 2026-08-11 사용자 결정: 전 경로 하이쿠 — 판정·합성 모두 싼 모델로 충분한지
# 벤치로 확인하는 국면이다. effort 는 하이쿠가 안 받으므로 structured() 가
# 하이쿠일 때 키를 뺀다 — 호출부는 모델을 모른 채 effort 를 계속 말해도 된다.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
ROOT = Path(__file__).resolve().parent.parent

log = logging.getLogger("core.llm")


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
    dur_ms: int = 0
    # 첫 글자가 나온 시각(ms) — 스트리밍으로 잰다. 사용자가 체감하는 지연은
    # 총 시간이 아니라 이 값이다(그 뒤로는 흘러나온다).
    ttft_ms: int = 0

    def dump(self) -> dict:
        return {"kind": self.kind, "at": self.at, "model": self.model,
                "usage": self.usage, "stop_reason": self.stop_reason,
                "images": self.images, "dur_ms": self.dur_ms,
                "ttft_ms": self.ttft_ms,
                "system": self.system, "user": self.user,
                "raw_response": self.raw_response, "error": self.error}


class LLM:
    def __init__(self, model: Optional[str] = None):
        load_env()
        import anthropic

        self.model = model or os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL
        # timeout 없이는 멈춘 스트림이 영원히 매달린다 — 벤치 실측(2026-08-11):
        # 응답이 안 오는 호출 하나가 5분을 통째로 먹었다. httpx 의미론으로 float
        # 는 연결·읽기 모두에 걸리고, 스트리밍 읽기는 **청크 사이** 간격이다.
        # 스트림은 생성이 되는 동안엔 ping 이 계속 와서 무소식이 아니다.
        #
        # 30 → 120 (2026-08-17). 30초로도 죽은 연결은 잡혔지만, **첫 글자 전
        # 침묵**까지 같이 잘랐다: 입력을 다 읽는 동안(prefill)은 보낼 것이 없어
        # 조용하고, 판정 프롬프트는 회수한 조문 **전문**을 싣는다(pipeline
        # section_text cap=10**9). 벡터 채널이 조문을 늘린 뒤 혼합 골든에서
        # ReadTimeout 이 36.9초·35.1초에 났다 — 죽은 연결이 아니라 긴 prefill 을
        # 죽었다고 오판한 것이다. 죽은 연결 감지라는 목적은 120초로도 선다
        # (5분을 통째로 먹던 그 실패는 여전히 잡힌다).
        self._client = anthropic.Anthropic(timeout=120.0)
        self.log: list[Exchange] = []

    def structured(self, kind: str, system: str, user: str, schema: dict,
                   max_tokens: int = 16000, effort: Optional[str] = "high",
                   images: Optional[list[str]] = None,
                   model: Optional[str] = None) -> Optional[dict]:
        """structured output 으로 JSON 을 받는다 (§2.3 "structured output").

        temperature 는 보내지 않는다 — 이 모델 계열에서 제거되어 400 이 난다.
        결정성은 스키마 고정으로 얻고(effort 는 호출자가 정한다 — 컴파일 경로는
        high 를 쓴다), 어차피 결과는 사람이 확정한다(§2.4).

        `images` 를 주면 **같은 호출에 그림을 함께 보낸다**(VLM). 쓰는 자리는 하나다:
        결정론이 **글자로는 볼 수 없는 축**을 물을 때. 마커 없는 제목은 크고 굵고 위가
        트여 있어서 제목인데, 그 판단의 근거가 픽셀에 있다. 텍스트만 보내면 모델도
        우리와 똑같이 못 본다.

        받는 형식은 `data:image/png;base64,...` (뷰어가 이미 그 형태로 페이지를 렌더한다).
        """
        use = model or self.model      # 호출마다 다른 모델을 쓸 수 있다 —
                                       # 가르기만 하는 판정은 싼 모델로 충분하다
        ex = Exchange(kind=kind, system=system, user=user, model=use,
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
        # `effort` 는 모델 계열마다 지원이 갈린다 — haiku 는 400 을 낸다.
        # 여기서 모델을 보고 키를 빼 준다 — 호출부는 effort 를 계속 말해도 된다.
        cfg: dict = {"format": {"type": "json_schema", "schema": schema}}
        if effort and "haiku" not in use:
            cfg["effort"] = effort
        t0 = time.perf_counter()
        try:
            # 스트리밍 — 첫 글자 시각(ttft)을 재기 위해서다. 결과는 똑같이
            # 한 덩어리 JSON 으로 파싱한다.
            with self._client.messages.stream(
                model=use,
                max_tokens=max_tokens,
                system=system,
                output_config=cfg,
                messages=[{"role": "user", "content": content}],
            ) as stream:
                text = ""
                for chunk in stream.text_stream:
                    if not text and chunk:
                        ex.ttft_ms = int((time.perf_counter() - t0) * 1000)
                    text += chunk
                resp = stream.get_final_message()
            ex.stop_reason = resp.stop_reason or ""
            ex.usage = {"input_tokens": resp.usage.input_tokens,
                        "output_tokens": resp.usage.output_tokens}
            if resp.stop_reason == "refusal":
                ex.error = "모델이 요청을 거절했습니다 (stop_reason=refusal)"
                return None
            ex.raw_response = text
            if resp.stop_reason == "max_tokens":
                # 잘린 JSON 은 파싱 오류로 나가는데, 원인은 예산이다 — 이름을 바로
                # 붙여야 호출부가 max_tokens 를 올린다(실측 2026-08-16: 소넷5 는
                # 사고 토큰이 출력 예산을 먹어 600 에서 절반 넘게 잘렸다).
                ex.error = (f"출력이 max_tokens={max_tokens} 에서 잘림 "
                            f"(out {resp.usage.output_tokens}) — 예산을 올려라")
                return None
            ex.parsed = json.loads(text)
            return ex.parsed
        except Exception as exc:                       # 호출·파싱 실패를 삼키지 않는다
            ex.error = f"{type(exc).__name__}: {exc}"
            return None
        finally:
            ex.dur_ms = int((time.perf_counter() - t0) * 1000)
            self.log.append(ex)
            if ex.error:
                log.error("%s [%s] 실패 %dms — %s", kind, use, ex.dur_ms, ex.error)
            else:
                log.info("%s [%s] %dms — in %d, out %d 토큰%s",
                         kind, use, ex.dur_ms,
                         ex.usage.get("input_tokens", 0),
                         ex.usage.get("output_tokens", 0),
                         f", 그림 {ex.images}장" if ex.images else "")

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
