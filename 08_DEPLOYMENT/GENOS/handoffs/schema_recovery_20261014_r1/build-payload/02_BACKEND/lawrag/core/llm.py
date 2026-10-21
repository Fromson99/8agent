"""LLM 호출 래퍼 — **컴파일 국면 전용** (SPEC §0 핵심원칙 1).

stochastic 은 컴파일 타임에 가둔다. 이 모듈은 형식 유도(T4)와 후보 제안에만 쓰이고,
런타임(구조화·비교)에서는 **import 조차 되지 않는다.**

기록: 모든 요청·응답을 그대로 남긴다. 무엇을 물었고 무엇이 왔는지 사람이 볼 수 있어야
형식을 신뢰할 수 있다.

백엔드는 넷이다 — anthropic(개발망) · local(온프레미스 OpenAI 호환 서빙) ·
genos(폐쇄망, GenOS LLM 서빙) · openrouter(외부 OpenAI 호환 API). 고르는 규칙과 환경변수는 `backend()` 머리,
계약은 `LLM.structured()` 하나로 같다.
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

from lawrag.platform.paths import repository_root

# 2026-08-11 사용자 결정: 전 경로 하이쿠 — 판정·합성 모두 싼 모델로 충분한지
# 벤치로 확인하는 국면이다. effort 는 하이쿠가 안 받으므로 structured() 가
# 하이쿠일 때 키를 뺀다 — 호출부는 모델을 모른 채 effort 를 계속 말해도 된다.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"
OPENROUTER_URL = "https://openrouter.ai/api"
OPENROUTER_MODEL = "qwen/qwen3.8-27b"
ROOT = repository_root()

log = logging.getLogger("lawrag.core.llm")

# ── 백엔드 둘 ────────────────────────────────────────────────────────────
# anthropic — 개발망. Anthropic SDK, structured output(json_schema) 네이티브.
# genos     — 폐쇄망. GenOS 의 LLM 서빙은 OpenAI 호환 REST 다 (실측:
#             genos-docs v1.9.0 "LLM 서빙 API 사용"):
#                 {GENOS_LLM_URL}/v1/models             모델 이름 조회
#                 {GENOS_LLM_URL}/v1/chat/completions   Authorization: Bearer <인증키>
#             GENOS_LLM_URL 은 https://<GenOS>/api/gateway/rep/serving/<서빙ID>.
#             그 뒤의 엔진(vLLM 계열)이 json_schema 를 받으면 그대로 쓰고, 400 을
#             내면 스키마를 프롬프트에 싣는 길로 **한 번 내려가 그 세션 내내** 그
#             길로 간다. 호출부(structured 의 계약)는 어느 쪽인지 모른다.
# openrouter — 개발망의 OpenAI 호환 REST. 사용자 환경의 `OPEN_ROUTER` 키를
#             그대로 받고, 별도 모델 지정이 없으면 Qwen3.8 27B 를 쓴다.
#
# 고르는 규칙: LLM_BACKEND 가 있으면 그것. 없으면 GENOS_LLM_URL 이 있을 때
# genos, 아니면 anthropic. 둘 다 있으면 genos — URL 을 적은 건 그쪽을 쓰겠다는
# 뜻이다(폐쇄망엔 어차피 anthropic 키가 없다).
BACKENDS = ("disabled", "anthropic", "local", "genos", "openrouter")


def _sealed() -> bool:
    return os.environ.get("LAWRAG_SERVING_SEALED", "").strip().casefold() in {
        "1", "true", "yes", "on",
    }


def _require_product_model(model: str | None) -> str:
    selected = str(model or DEFAULT_MODEL).strip()
    if _sealed() and selected != DEFAULT_MODEL:
        raise RuntimeError(
            f"sealed product LLM must be {DEFAULT_MODEL}, not {selected!r}"
        )
    return selected


def anthropic_client(*, timeout: float, max_retries: int = 2):
    """Construct the fixed product endpoint without ambient proxy/base overrides."""

    import anthropic

    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if _sealed() and not key:
        raise RuntimeError("sealed Anthropic backend requires ANTHROPIC_API_KEY")
    ambient_base = os.environ.get("ANTHROPIC_BASE_URL", "").strip()
    endpoint = "https://api.anthropic.com"
    if _sealed() and ambient_base and ambient_base.rstrip("/") != endpoint:
        raise RuntimeError("sealed Anthropic base URL conflicts with release binding")
    transport = anthropic.DefaultHttpxClient(
        timeout=timeout,
        trust_env=False,
        follow_redirects=False,
    )
    return anthropic.Anthropic(
        api_key=key or None,
        base_url=endpoint,
        max_retries=max_retries,
        http_client=transport,
    )


def _genos_llm_url() -> str:
    """직접 URL 또는 GenOS 기본 주소 + 서빙 ID로 완성한 LLM endpoint."""
    direct = (os.environ.get("GENOS_LLM_URL") or "").strip()
    if direct:
        return direct.rstrip("/")
    serving_id = os.environ.get("GENOS_LLM_SERVING_ID", "").strip()
    base = (os.environ.get("GENOS_BASE_URL") or "").strip().rstrip("/")
    if not base or not serving_id or not serving_id.isdigit():
        return ""
    return f"{base}/api/gateway/rep/serving/{serving_id}"


def _genos_llm_key() -> str:
    return os.environ.get("GENOS_LLM_KEY", "").strip()


def _genos_llm_model() -> str:
    return os.environ.get("GENOS_LLM_MODEL", "").strip()


def backend() -> str:
    load_env()
    b = (os.environ.get("LLM_BACKEND") or "").strip().lower()
    if b in BACKENDS:
        return b
    if _sealed():
        raise RuntimeError("sealed product LLM requires an explicit backend")
    if os.environ.get("LOCAL_LLM_URL"):
        return "local"
    return "genos" if _genos_llm_url() else "anthropic"


def available() -> bool:
    """LLM 을 쓸 수 있는가 — 호출부는 키 이름을 몰라도 된다. 없으면 검색까지만
    내려가는 것이 전 경로의 규약이다."""
    b = backend()
    if b == "disabled":
        return False
    if b == "local":
        return bool(os.environ.get("LOCAL_LLM_URL"))
    if b == "genos":
        return bool(_genos_llm_url())
    if b == "openrouter":
        return bool(os.environ.get("OPEN_ROUTER") or
                    os.environ.get("OPENROUTER_API_KEY"))
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# 없을 때 사람에게 보여 줄 한 줄 — 어느 변수를 채워야 하는지.
MISSING_HINT = ("LOCAL_LLM_URL(온프레미스 OpenAI 호환), ANTHROPIC_API_KEY(개발망), "
                "GENOS_LLM_URL·GENOS_LLM_KEY 또는 GENOS_BASE_URL·서빙 프로필(GenOS), "
                "또는 OPEN_ROUTER(OpenRouter)")


def load_env() -> None:
    """`.env` 를 읽어 환경에 넣는다. 이미 있는 값은 덮지 않는다."""
    if _sealed():
        # Deployment configuration is the only operational authority.  A
        # packaged or adjacent authoring .env file cannot change product calls.
        return
    for candidate in (ROOT / ".env",):
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
    # Exact decoded provider events, before content selection/JSON extraction.
    provider_response: list[dict] = field(default_factory=list)
    provider_usage: dict = field(default_factory=dict)
    requested_thinking: Optional[bool] = None
    parsed: Any = None
    model: str = ""
    usage: dict = field(default_factory=dict)
    stop_reason: str = ""
    at: str = ""
    error: str = ""
    output_contract: dict = field(default_factory=dict)
    normalizations: list[dict] = field(default_factory=list)
    physical_calls: int | None = None
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
                "raw_response": self.raw_response, "error": self.error,
                "output_contract":self.output_contract,"physical_calls":self.physical_calls,
                "normalizations":self.normalizations,
                "provider_response": self.provider_response,
                "provider_usage": self.provider_usage,
                "requested_thinking": self.requested_thinking}


class LLM:
    def __init__(self, model: Optional[str] = None):
        load_env()
        if model is not None:
            _require_product_model(model)
        self.backend = backend()
        self.log: list[Exchange] = []
        if self.backend == "disabled":
            raise RuntimeError("product LLM backend is disabled")
        if self.backend in ("local", "genos", "openrouter"):
            self._init_genos(model)
            return
        import anthropic

        configured_model = os.environ.get("ANTHROPIC_MODEL")
        if _sealed() and configured_model:
            _require_product_model(configured_model)
        self.model = _require_product_model(model or configured_model or DEFAULT_MODEL)
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
        self._client = anthropic_client(timeout=120.0)

    # ── GenOS(OpenAI 호환) ────────────────────────────────────────────────
    def _init_genos(self, model: Optional[str]) -> None:
        import requests

        if self.backend == "openrouter":
            self._genos_url = (os.environ.get("OPENROUTER_URL") or
                               OPENROUTER_URL).rstrip("/")
            if _sealed() and os.environ.get("OPEN_ROUTER", ""):
                raise RuntimeError("sealed OpenRouter forbids fallback credential names")
            self._genos_key = (
                os.environ.get("OPENROUTER_API_KEY", "")
                if _sealed()
                else (os.environ.get("OPEN_ROUTER") or
                      os.environ.get("OPENROUTER_API_KEY", ""))
            )
            self._genos_user = ""
            json_mode = os.environ.get("OPENROUTER_JSON_MODE")
            temperature = os.environ.get("OPENROUTER_TEMPERATURE")
            configured_model = os.environ.get("OPENROUTER_MODEL")
            default_model = OPENROUTER_MODEL
            self._backend_label = "OpenRouter"
        elif self.backend == "local":
            self._genos_url = os.environ["LOCAL_LLM_URL"].rstrip("/")
            self._genos_key = os.environ.get("LOCAL_LLM_KEY", "")
            self._genos_user = ""
            json_mode = os.environ.get("LOCAL_LLM_JSON_MODE")
            temperature = os.environ.get("LOCAL_LLM_TEMPERATURE")
            configured_model = os.environ.get("LOCAL_LLM_MODEL")
            default_model = ""
            self._backend_label = "Local LLM"
        else:
            self._genos_url = _genos_llm_url()
            if not self._genos_url:
                raise RuntimeError("GENOS_LLM_URL 또는 GENOS_BASE_URL·서빙 ID가 필요합니다")
            self._genos_key = _genos_llm_key()
            self._genos_user = os.environ.get("GENOS_USER_ID", "")
            json_mode = os.environ.get("GENOS_LLM_JSON_MODE")
            temperature = os.environ.get("GENOS_LLM_TEMPERATURE")
            configured_model = _genos_llm_model()
            default_model = ""
            self._backend_label = "GenOS"
        if _sealed():
            if configured_model:
                _require_product_model(configured_model)
            if temperature not in (None, "", "0", "0.0"):
                raise RuntimeError("sealed product LLM temperature must be zero")
            default_model = DEFAULT_MODEL
        # json 을 받는 방식 — json_schema(엔진이 스키마 강제) → prompt(스키마를
        # 시스템 프롬프트에 싣고 파싱). 400 이 나면 자동으로 한 단계 내려간다.
        self._json_mode = (json_mode or "json_schema").lower()
        self._temperature = float(temperature or "0")
        self._session = requests.Session()
        self._session.trust_env = False
        self._session.headers.update({"Content-Type": "application/json"})
        if self._genos_key:
            self._session.headers["Authorization"] = f"Bearer {self._genos_key}"
        if self._genos_user:
            self._session.headers["x-genos-user-id"] = self._genos_user
        if self.backend == "openrouter":
            referer = os.environ.get("OPENROUTER_HTTP_REFERER", "")
            app_name = os.environ.get("OPENROUTER_APP_NAME", "8-AGENT")
            if referer:
                self._session.headers["HTTP-Referer"] = referer
            if app_name:
                self._session.headers["X-Title"] = app_name
        # 모델 이름 — 환경이 말하면 그것, 아니면 서빙에 물어 첫 모델(문서의 예시
        # 절차 그대로: /v1/models 의 data[0].id). 실패는 첫 호출로 미룬다.
        self.model = model or configured_model or default_model
        if _sealed():
            self.model = _require_product_model(self.model)
        if not self.model:
            try:
                r = self._session.get(
                    self._genos_url + "/v1/models",
                    timeout=15,
                    allow_redirects=False,
                )
                r.raise_for_status()
                self.model = r.json()["data"][0]["id"]
            except Exception as exc:                  # 첫 호출 때 다시 시도한다
                log.warning("%s /v1/models 실패 — %s", self._backend_label, exc)

    @staticmethod
    def _extract_json(text: str) -> str:
        """Remove only a complete outer JSON fence; never salvage prose or thinking."""
        import re
        t=text.strip()
        fence=re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```",t,flags=re.S)
        return fence.group(1).strip() if fence else t


    def _require_openai_attestation(self, response) -> None:
        """Verify GenOS/local serving revision on every sealed response."""

        if not _sealed() or self.backend not in {"genos", "local"}:
            return
        prefix = "GENOS_LLM" if self.backend == "genos" else "LOCAL_LLM"
        expected = {
            "x-lawrag-model-revision": os.environ.get(
                f"{prefix}_MODEL_REVISION", ""
            ),
            "x-lawrag-model-sha256": os.environ.get(
                f"{prefix}_MODEL_SHA256", ""
            ),
            "x-lawrag-credential-binding-id": os.environ.get(
                f"{prefix}_CREDENTIAL_BINDING_ID", ""
            ),
            "x-lawrag-credential-binding-version": os.environ.get(
                f"{prefix}_CREDENTIAL_BINDING_VERSION", ""
            ),
            "x-lawrag-trust-policy-id": os.environ.get(
                f"{prefix}_TRUST_POLICY_ID", ""
            ),
        }
        if any(not value for value in expected.values()) or any(
            response.headers.get(key) != value for key, value in expected.items()
        ):
            raise RuntimeError(
                "sealed product LLM response lacks exact serving attestation"
            )

    def _call_genos(self, ex: Exchange, system: str, user: str, schema: dict,
                    max_tokens: int, images: Optional[list[str]], t0: float,
                    model: str = "", enable_thinking: Optional[bool] = None) -> tuple[str, str]:
        """(text, stop_reason) 을 돌려준다. stop_reason 은 anthropic 어휘로
        정규화한다 — 호출부의 max_tokens·refusal 처리를 같이 쓰기 위해서다."""
        if not model:
            if not self.model:                        # 생성 때 못 물었으면 지금
                r = self._session.get(
                    self._genos_url + "/v1/models",
                    timeout=15,
                    allow_redirects=False,
                )
                r.raise_for_status()
                self.model = r.json()["data"][0]["id"]
            model = self.model
        content: Any = user
        if images:
            blocks = [{"type": "image_url", "image_url": {"url": str(u)}}
                      for u in images if "," in str(u)]
            content = blocks + [{"type": "text", "text": user}]
            ex.images = len(blocks)
        ex.model = model
        temperature = self._temperature

        def _payload(mode: str) -> dict:
            sys_text = system
            if mode == "prompt":
                sys_text = (system + "\n\n[출력 형식] 아래 JSON Schema 를 만족하는 "
                            "JSON 객체 **하나만** 출력한다. 설명·머리말·코드 울타리 없이 "
                            "JSON 만.\n" + json.dumps(schema, ensure_ascii=False))
            body = {"model": model, "temperature": temperature,
                    "max_tokens": max_tokens, "stream": True,
                    "messages": [{"role": "system", "content": sys_text},
                                 {"role": "user", "content": content}]}
            if enable_thinking is not None:
                # Same serving option already used by GENOS's inference check.
                # Retain the explicit thinking option in every configured output mode.
                body["chat_template_kwargs"] = {"enable_thinking": enable_thinking}
            if mode == "json_schema":
                from semantic_runtime.legal_agent.model_contract import genos_wire_schema
                body["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": ex.kind.replace(".", "_"),
                                    "schema": genos_wire_schema(schema), "strict": True}}
                body["stream_options"] = {"include_usage": True}
            elif mode == "json_object":
                body["response_format"] = {"type": "json_object"}
            return body

        mode = self._json_mode
        while True:
            ex.physical_calls = (ex.physical_calls or 0) + 1
            resp = self._session.post(self._genos_url + "/v1/chat/completions",
                                      json=_payload(mode), stream=True,
                                      timeout=(15, 120), allow_redirects=False)
            self._require_openai_attestation(resp)
            if resp.status_code == 400 and mode != "prompt":
                from semantic_runtime.legal_agent.output_contract import OutputContractError,issue
                raise OutputContractError('provider rejected the configured structured request mode',
                    [issue('REQUEST_SCHEMA_UNSUPPORTED',repairable=False)],
                    category='REQUEST_SCHEMA_UNSUPPORTED',repairable=False)
            resp.raise_for_status()
            break

        text, finish = "", ""
        response_model_seen = False
        done = False
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                done = True
                break
            try:
                chunk = json.loads(payload)
            except json.JSONDecodeError as exc:
                from semantic_runtime.legal_agent.output_contract import OutputContractError,issue
                raise OutputContractError('invalid model stream event',
                    [issue('MODEL_STREAM_FRAME_INVALID',repairable=False)],
                    category='OUTPUT_INCOMPLETE',repairable=False) from exc
            ex.provider_response.append(chunk)
            response_model = chunk.get("model")
            if response_model is not None:
                response_model_seen = True
                if (self.backend=='genos' or _sealed()) and response_model != model:
                    from semantic_runtime.legal_agent.errors import ContractError
                    raise ContractError('product LLM response names another model')
            if chunk.get("usage"):
                u = chunk["usage"]
                ex.provider_usage = u
                ex.usage = {"input_tokens": u.get("prompt_tokens", 0),
                            "output_tokens": u.get("completion_tokens", 0)}
            for ch in chunk.get("choices") or []:
                piece = (ch.get("delta") or {}).get("content") or ""
                if piece:
                    if not text:
                        ex.ttft_ms = int((time.perf_counter() - t0) * 1000)
                    text += piece
                    ex.raw_response = text
                if ch.get("finish_reason"):
                    finish = ch["finish_reason"]
        if (self.backend=='genos' or _sealed()) and not response_model_seen:
            from semantic_runtime.legal_agent.errors import ContractError
            raise ContractError('product LLM response has no model identity')
        if not done:
            from semantic_runtime.legal_agent.output_contract import OutputContractError,issue
            raise OutputContractError('model stream ended without its completion marker',
                [issue('MODEL_STREAM_INCOMPLETE',repairable=False)],category='OUTPUT_INCOMPLETE',repairable=False)
        if finish not in ('','stop','length','content_filter'):
            from semantic_runtime.legal_agent.output_contract import OutputContractError,issue
            raise OutputContractError('unsupported model completion reason',
                [issue('MODEL_FINISH_REASON_INVALID',repairable=False)],category='OUTPUT_INCOMPLETE',repairable=False)
        stop = {"stop": "end_turn", "length": "max_tokens",
                "content_filter": "refusal"}.get(finish, finish or "end_turn")
        if mode != "json_schema":
            original = text
            text = self._extract_json(text)
            if text != original:
                from hashlib import sha256
                ex.normalizations.append({'rule':'complete_outer_json_fence_or_whitespace',
                    'raw_sha256':sha256(original.encode()).hexdigest(),
                    'normalized_sha256':sha256(text.encode()).hexdigest()})
        return text, stop

    def structured(self, kind: str, system: str, user: str, schema: dict,
                   max_tokens: int = 16000, effort: Optional[str] = "high",
                   images: Optional[list[str]] = None,
                   model: Optional[str] = None,
                   enable_thinking: Optional[bool] = None) -> Optional[dict]:
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
        # GENOS product calls share one output budget, including callers that
        # still pass a smaller historical per-task value.
        # Structure recipe records its own budget in a durable journal, so it
        # supplies the same 80k value through its dedicated configuration.
        if self.backend == "genos" and not kind.startswith("structure_recipe_"):
            max_tokens = 80000
        use = model or self.model      # 호출마다 다른 모델을 쓸 수 있다 —
                                       # 가르기만 하는 판정은 싼 모델로 충분하다
        if _sealed():
            use = _require_product_model(use)
        ex = Exchange(kind=kind, system=system, user=user, model=use,
                      at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        content: Any = user
        if images and self.backend not in ("local", "genos", "openrouter"):
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
        if enable_thinking is not None and type(enable_thinking) is not bool:
            raise ValueError("enable_thinking must be bool or None")
        ex.requested_thinking = enable_thinking
        t0 = time.perf_counter()
        try:
            if self.backend in ("local", "genos", "openrouter"):
                # 그림 블록은 백엔드마다 형식이 다르다 — genos 쪽이 다시 만든다.
                text, stop = self._call_genos(ex, system, user, schema,
                                              max_tokens, images, t0,
                                              model=use, enable_thinking=enable_thinking)
                use = ex.model
            else:
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
                stop = resp.stop_reason or ""
                if _sealed() and getattr(resp, "model", None) != use:
                    raise RuntimeError(
                        "sealed Anthropic response names another product model"
                    )
                ex.usage = {"input_tokens": resp.usage.input_tokens,
                            "output_tokens": resp.usage.output_tokens}
            ex.stop_reason = stop
            if stop == "refusal":
                ex.error = "모델이 요청을 거절했습니다 (stop_reason=refusal)"
                return None
            if self.backend not in ("local", "genos", "openrouter"):
                ex.raw_response = text
            if stop == "max_tokens":
                # 잘린 JSON 은 파싱 오류로 나가는데, 원인은 예산이다 — 이름을 바로
                # 붙여야 호출부가 max_tokens 를 올린다(실측 2026-08-16: 소넷5 는
                # 사고 토큰이 출력 예산을 먹어 600 에서 절반 넘게 잘렸다).
                ex.error = (f"출력이 max_tokens={max_tokens} 에서 잘림 "
                            f"(out {ex.usage.get('output_tokens', '?')}) — 원응답·추론 사용량과 서버 설정 확인")
                return None
            from semantic_runtime.legal_agent.output_contract import strict_json
            ex.parsed = strict_json(text)
            return ex.parsed
        except Exception as exc:                       # 호출·파싱 실패를 삼키지 않는다
            from semantic_runtime.legal_agent.output_contract import diagnostics
            ex.output_contract = diagnostics(exc)
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
