"""사내 서빙을 부르는 창구 하나 — GenOS 게이트웨이와 직결 endpoint 를 같은 모양으로 다룬다.

**한눈에 보기.** 이 파일은 "어디로, 어떤 머리말을 달고 부르는가" 만 안다. 무엇을
물을지와 답을 어떻게 읽을지는 부르는 쪽이 정한다. 상품 카드를 뽑는 LLM(`core/llm.py`)과
질의·적재의 임베딩(`core/storage/vdb/embedder.py`)이 이 창구를 같이 쓴다.

**왜 이렇게 나눴나.** 온프렘 GenOS 에서는 모델을 직접 부르지 않는다. GenOS 가 앞에
게이트웨이를 두고, 우리는 **서빙 번호와 토큰**으로 그 뒤의 모델을 부른다.

    {GENOS_URL}/api/gateway/rep/serving/{serving_id}/chat/completions
                                        └ GenOS 에 등록하면 받는 번호
    Authorization: Bearer {token}

그런데 개발 중에는 GenOS 밖에서도 부른다 — 맥에서 시험할 때의 Gemini, 게이트웨이를
거치지 않는 사내 GPU 서버가 그렇다. 부르는 곳마다 URL 조립과 재시도를 따로 적어 두면
같은 버그를 두 번 고치게 된다. 그래서 **접속 지점을 값 하나(`Endpoint`)로 만들고**,
게이트웨이든 직결이든 그 값만 바꿔 끼운다.

```text
core/llm.py · core/storage/vdb/config.py   어느 접속 지점을 쓸지 정한다
        ↓ Endpoint
core/genos.py                              부른다 — 머리말·재시도·타임아웃
        ↓ OpenAI 호환 응답(dict)
core/llm.py                                답을 텍스트로 읽는다
core/storage/vdb/embedder.py               답을 벡터 목록으로 읽는다
```

나중에 게이트웨이 규약이 바뀌거나 이 계층을 통째로 떼어내야 할 때 고칠 곳이 여기
하나가 되도록 둔 것이다. 그래서 이 파일은 **환경변수를 읽지 않는다** — 설정은 부르는
쪽이 읽고, 여기에는 완성된 값이 넘어온다.

SDK 를 쓰지 않고 표준 라이브러리(urllib)로 REST 를 직접 부른다. 사내망 반입 시
의존성을 하나 더 통과시키지 않으려는 판단이다(07-issuance-note 와 같다).
"""
from __future__ import annotations

import contextvars
import json
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from . import obs

_log = obs.bind(obs.get_logger("serving"))

# 429(쿼터·혼잡)와 5xx(일시 장애)는 다시 걸어 본다. 그 밖의 4xx 는 **요청이 잘못된
# 것이라 즉시 던진다** — 같은 요청을 다시 보내도 같은 답이 온다. 예전 GeminiClient 는
# 4xx 를 "재시도 무의미" 라고 적어 놓고도 넓은 except 로 다시 잡아 세 번 걸었다.
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

# GenOS 게이트웨이에서 서빙 하나를 가리키는 경로. 이 뒤에 OpenAI 규약의 경로가 붙는다
# (`/chat/completions`, `/embeddings`, `/models`) — 즉 이 주소가 OpenAI 로 치면 `/v1` 자리다.
_SERVING_PATH = "/api/gateway/rep/serving/{serving_id}"

# 게이트웨이를 거치지 않는 OpenAI 호환 서버(vLLM 등)는 `/v1` 이 그 자리다.
_DIRECT_PATH = "/v1"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """리다이렉트를 따라가지 않는다 — 3xx 는 그대로 실패로 본다.

    urllib 은 기본으로 따라가는데, POST 를 받은 301·302 를 GET 으로 바꿔 다시 건다.
    게이트웨이 주소를 잘못 적었을 때 엉뚱한 페이지가 200 으로 돌아오면 원인이
    가려진다. 예전 httpx 도 따라가지 않았다.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_open = urllib.request.build_opener(_NoRedirect).open


def _send(url: str, headers: dict[str, str], data: bytes | None,
          timeout: float) -> tuple[int, bytes]:
    """한 번 보내고 (상태 코드, 본문)을 돌려준다. 4xx·5xx 도 예외가 아니라 값으로 온다.

    urllib 은 400 이상을 `HTTPError` 로 던진다. 재시도할지(429·5xx) 바로 멈출지는
    상태 코드로 가르므로, 여기서 값으로 바꿔 부르는 쪽이 한 갈래로 보게 한다.
    연결 실패·타임아웃은 그대로 던진다.
    """
    request = urllib.request.Request(url, data=data, headers=headers,
                                     method="GET" if data is None else "POST")
    try:
        with _open(request, timeout=timeout) as res:
            return res.status, res.read()
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read()
        except Exception:                       # noqa: BLE001 — 본문을 못 읽어도 상태 코드는 남긴다
            body = b""
        return exc.code, body


def _text(body: bytes) -> str:
    return body.decode("utf-8", "replace")


class ServingError(RuntimeError):
    """서빙을 부르지 못했다. 부르는 쪽이 잡아 각자의 예외로 바꿔 던진다."""


class DeadlineExceeded(ServingError):
    """요청 전체에 걸린 마감 시간이 지났다 — 더 부르지 않는다."""


# ── 요청 마감 시간 ───────────────────────────────────────────
#
# 호출 하나의 타임아웃(`Endpoint.timeout`)만으로는 요청 전체가 얼마나 걸릴지 못 막는다.
# 질의 1건은 임베딩·LLM·인용 재생성을 차례로 부르고, 각 호출이 재시도까지 하므로
# 30초 × 3회 + 대기가 겹치면 워크플로우(60초)가 먼저 끊긴다. 그래서 질의 쪽이 마감
# 시각을 한 번 걸어 두면, 이 창구를 지나는 모든 호출이 **남은 시간만큼만** 기다리고
# 남은 시간이 없으면 다시 걸지 않는다. 적재는 마감을 걸지 않으므로 그대로다.
_DEADLINE: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "genos_deadline", default=None)


@contextmanager
def deadline(seconds: float) -> Iterator[None]:
    """이 안에서 부르는 모든 서빙 호출에 `seconds` 뒤의 마감을 건다."""
    token = _DEADLINE.set(time.monotonic() + seconds)
    try:
        yield
    finally:
        _DEADLINE.reset(token)


def remaining() -> float | None:
    """마감까지 남은 초. 마감이 없으면 None."""
    end = _DEADLINE.get()
    return None if end is None else end - time.monotonic()


@dataclass(frozen=True)
class Endpoint:
    """부를 수 있는 접속 지점 하나.

    `label` 은 로그에 그대로 쓴다. 붙지 못했을 때 **어디에 붙으려 했는지**가 보이지
    않으면, 설정이 안 들어간 것인지 서버가 죽은 것인지 구분할 수 없다. 토큰은 담지
    않는다 — 로그에 새지 않게 하려는 것.
    """

    root: str                                   # OpenAI 로 치면 `/v1` 에 해당하는 주소
    label: str
    timeout: float = 120.0
    max_retries: int = 3
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def chat_url(self) -> str:
        return f"{self.root}/chat/completions"

    @property
    def embeddings_url(self) -> str:
        return f"{self.root}/embeddings"

    @property
    def models_url(self) -> str:
        return f"{self.root}/models"


def genos_endpoint(base_url: str, serving_id: str, token: str, *,
                   timeout: float = 120.0, max_retries: int = 3) -> Endpoint:
    """GenOS 게이트웨이 뒤의 서빙 하나를 가리킨다."""
    root = base_url.rstrip("/") + _SERVING_PATH.format(serving_id=serving_id)
    return Endpoint(
        root=root,
        label=f"genos:{serving_id}",
        timeout=timeout,
        max_retries=max_retries,
        headers={"Authorization": f"Bearer {token}"},
    )


def direct_endpoint(base_url: str, *, timeout: float = 120.0,
                    max_retries: int = 3, token: str = "") -> Endpoint:
    """게이트웨이를 거치지 않는 OpenAI 호환 서버를 가리킨다.

    주소가 이미 `/v1` 로 끝나면 덧붙이지 않는다 — 설정에 어느 쪽으로 적어 두든
    같은 곳을 가리켜야 한다.
    """
    root = base_url.rstrip("/")
    if not root.endswith(_DIRECT_PATH):
        root += _DIRECT_PATH
    return Endpoint(
        root=root,
        label=root,
        timeout=timeout,
        max_retries=max_retries,
        headers={"Authorization": f"Bearer {token}"} if token else {},
    )


def chat(endpoint: Endpoint, body: dict[str, Any]) -> dict[str, Any]:
    """OpenAI 규약의 `/chat/completions` 를 부르고 응답 dict 를 그대로 돌려준다.

    답을 어떻게 읽을지는 부르는 쪽이 정한다 — 여기서 미리 풀어 주면 채팅과 임베딩
    중 한쪽에는 맞지 않는다.
    """
    return post(endpoint, endpoint.chat_url, body)


def embeddings(endpoint: Endpoint, body: dict[str, Any]) -> dict[str, Any]:
    """OpenAI 규약의 `/embeddings` 를 부르고 응답 dict 를 그대로 돌려준다."""
    return post(endpoint, endpoint.embeddings_url, body)


def post(endpoint: Endpoint, url: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST 하고 JSON 을 돌려준다. 끊기거나 밀리면 잠깐 쉬고 다시 건다.

    쉬는 시간을 점점 늘린다(2·4초). 여러 요청을 동시에 던지면 서버가 잠깐 밀리는데
    (429·503), 곧바로 다시 걸면 밀린 상태 그대로라 같은 답이 온다.

    `url` 을 따로 받는 이유는 Gemini 때문이다 — 주소가 OpenAI 모양이 아니라
    (`/models/{model}:generateContent`) `Endpoint.root` 로 조립할 수 없다. 그래도
    머리말·타임아웃·재시도는 같은 규칙을 쓰게 하려는 것.
    """
    headers = {"Content-Type": "application/json", **endpoint.headers}
    try:
        data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except ValueError as exc:
        raise ServingError(f"{endpoint.label} 요청 본문을 JSON 으로 만들지 못했다: {exc}") from exc
    last: str = ""

    for attempt in range(1, endpoint.max_retries + 1):
        left = remaining()
        if left is not None and left <= 0:
            raise DeadlineExceeded(
                f"{endpoint.label} 요청 마감 시간 초과(timeout) — 시도 {attempt - 1}회"
                + (f", 마지막: {last}" if last else ""))
        timeout = endpoint.timeout if left is None else min(endpoint.timeout, left)
        sent = time.monotonic()
        try:
            status, raw = _send(url, headers, data, timeout)
        except Exception as exc:                # noqa: BLE001 — 네트워크·일시 장애 흡수
            last = f"{type(exc).__name__}: {exc}"
            _attempt_failed(endpoint, attempt, timeout, sent, last)
        else:
            if status < 400:
                try:
                    return json.loads(raw)
                except Exception as exc:        # noqa: BLE001 — 본문이 JSON 이 아니다
                    raise ServingError(
                        f"{endpoint.label} 응답을 읽지 못했다: {exc} ({_text(raw)[:200]})") from exc
            detail = _text(raw)[:300]
            if status not in RETRY_STATUS:
                # 요청 자체가 틀렸다 — 다시 보내도 같은 답이 온다.
                raise ServingError(f"{endpoint.label} HTTP {status}: {detail}")
            last = f"HTTP {status}: {detail}"
            _attempt_failed(endpoint, attempt, timeout, sent, last)

        if attempt == endpoint.max_retries:
            break
        pause = 2.0 * attempt                   # 선형 백오프
        left = remaining()
        if left is not None and left <= pause:
            raise DeadlineExceeded(
                f"{endpoint.label} 요청 마감 시간 초과(timeout) — 시도 {attempt}회, 마지막: {last}")
        time.sleep(pause)

    raise ServingError(f"{endpoint.label} 호출 실패({endpoint.max_retries}회): {last}")


def _attempt_failed(endpoint: Endpoint, attempt: int, timeout: float, sent: float,
                    reason: str) -> None:
    """시도 하나가 실패할 때마다 바로 남긴다.

    실패는 재시도를 다 쓴 뒤 예외 하나로만 올라간다. 그런데 재시도 도중 워커가 통째로
    죽으면(gunicorn 워커 타임아웃) 그 예외가 영영 만들어지지 않아, 서빙이 503 을 냈는지
    응답 없이 매달렸는지 로그로 가를 수 없었다. 시도마다 대상·걸린 시간·사유를 적어 둔다.
    """
    _log.event("serving.attempt_failed", level=30, target=endpoint.label,
               attempt_no=attempt, max_retries=endpoint.max_retries,
               timeout=round(timeout, 1),
               elapsed_ms=int((time.monotonic() - sent) * 1000), reason=reason[:300])


def reachable(endpoint: Endpoint, *, timeout: float = 5.0) -> bool:
    """지금 이 서빙을 부를 수 있는가 — 모델 목록을 한 번 물어본다.

    부르는 쪽이 이 결과로 **그 경로가 없는 것처럼** 동작할지 정한다. 조용히
    느려지거나 요청 한복판에서 죽는 것보다, 처음부터 없는 셈 치는 편이 낫다.
    """
    try:
        status, _ = _send(endpoint.models_url, dict(endpoint.headers), None, timeout)
        return status == 200
    except Exception:                           # noqa: BLE001
        return False


__all__ = [
    "Endpoint",
    "ServingError",
    "RETRY_STATUS",
    "genos_endpoint",
    "direct_endpoint",
    "chat",
    "embeddings",
    "post",
    "reachable",
]
