"""GENOS 채팅 워크플로우 Python 단계.

GENOS 워크플로우 편집기에 이 파일 전체를 붙여 넣고 ``run``을 진입점으로
사용한다. 질문은 코드서빙의 ``LEGAL_AGENT``로 전달하고, 검증된 RAG 답변은
다시 생성하지 않고 화면의 ``text``로 반환한다. 본문의 숫자 각주 표기는
표시 단계에서 제거하며 원장과 문서·조문 출처는 보존한다.
"""

import json
import asyncio
from concurrent.futures import TimeoutError as FutureTimeout
import inspect
import hashlib
import os
import re
import time
import threading
import traceback
import urllib.error
import urllib.request
import uuid


WORKFLOW_REVISION = "rag-v6-progress-20261002-r1"
PROGRESS_DISPLAY_REVISION = "reasoner-display-v6-20261002-r1"
ANSWER_DISPLAY_REVISION = "answer-reference-display-20260929-r1"
HTTP_ERROR_DIAGNOSTICS_REVISION = "http-error-origin-20260928-r1"
QUESTION_KEYS = ("question", "query", "chatInput", "input", "message", "prompt", "text")
META_KEYS = frozenset(
    {
        "team_id",
        "TEAM_ID",
        "scope",
        "document_ids",
        "use_llm",
        "API_TYPE",
        "request_id",
        "channel",
        "chatId",
        "chat_id",
        "sessionId",
        "session_id",
        "socketIOClientId",
        "userInfo",
        "user_id",
        "userId",
        "botType",
        "bot_type",
        "apiKey",
        "api_key",
        "token",
        "Authorization",
        "history",
        "chatHistory",
        "overrideConfig",
    }
)
_UNSAFE_ID = re.compile(r"[^A-Za-z0-9_.:-]")
_BARE_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _log_event(event, level="INFO", **fields):
    """GENOS가 수집하는 stdout에 1줄 1 JSON 이벤트를 남긴다."""
    forbidden = ("TOKEN", "KEY", "PASSWORD", "SECRET", "AUTHORIZATION")
    safe = {}
    for key, value in fields.items():
        if any(part in key.upper() for part in forbidden):
            continue
        if isinstance(value, str):
            token = (os.getenv("GENOS_CODESERVING_TOKEN") or os.getenv("GENOS_CODE_KEY") or "")
            safe[key] = value.replace(token, "[REDACTED]") if token else value
        else:
            safe[key] = value
    print(
        json.dumps(
            {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "level": level,
                "logger": "genos.workflow.rag_chat",
                "event": event,
                "workflow_revision": WORKFLOW_REVISION,
                **safe,
            },
            ensure_ascii=False,
            default=str,
        ),
        flush=True,
    )


def _extract_question(data):
    data = data if isinstance(data, dict) else {}
    for key in QUESTION_KEYS:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    found = []
    _walk(data, found)
    return max(found, key=len).strip() if found else ""


def _walk(value, found):
    if isinstance(value, dict):
        for key in QUESTION_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                found.append(candidate)
        for key, nested in value.items():
            if key not in META_KEYS and isinstance(nested, (dict, list, tuple)):
                _walk(nested, found)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _walk(nested, found)


def _safe_id(value, fallback):
    cleaned = _UNSAFE_ID.sub("-", str(value or "")).strip("-")[:64]
    return cleaned or fallback


def _ad_channel(data):
    override=data.get('overrideConfig') or {}
    nested=(override.get('vars') or {}).get('genosUserInfo') if isinstance(override,dict) else None
    return 'genos-studio' if nested or any(data.get(k) for k in ('endpoint','workflow_id','applied_fields','persona')) else 'genos'


def _session_id(data):
    return _safe_id(
        data.get("chatId") or data.get("chat_id") or data.get("sessionId") or data.get("session_id"),
        "sess-anonymous",
    )


def _user_id(data):
    info = data.get("userInfo")
    if not isinstance(info, dict):
        info = {}
    value = data.get("user_id") or data.get("userId") or info.get("user_id") or info.get("userId")
    return _safe_id(value, "anonymous")


def _settings():
    """환경변수를 실행 시점에 읽어 워크플로우 리비전 설정을 즉시 반영한다."""
    base = os.getenv("GENOS_BASE_URL", "").strip().rstrip("/")
    serving_id = os.getenv("GENOS_CODESERVING_ID", "").strip()
    token = (os.getenv("GENOS_CODESERVING_TOKEN") or os.getenv("GENOS_CODE_KEY") or "").strip()
    try:
        timeout = float(os.getenv("GENOS_CODESERVING_TIMEOUT_SECONDS", "2100"))
    except ValueError:
        timeout = 2100.0
    if not base:
        raise EnvironmentError("GENOS_BASE_URL이 필요합니다.")
    if not base.startswith(("http://", "https://")):
        raise EnvironmentError("GENOS_BASE_URL은 http:// 또는 https://로 시작해야 합니다.")
    if not serving_id:
        raise EnvironmentError("GENOS_CODESERVING_ID가 필요합니다.")
    if _UNSAFE_ID.search(serving_id):
        raise EnvironmentError("GENOS_CODESERVING_ID 형식이 잘못되었습니다.")
    if not token:
        raise EnvironmentError("GENOS_CODESERVING_TOKEN이 필요합니다.")
    endpoint = f"{base}/api/gateway/code_serving/{serving_id}/json"
    return endpoint, token, max(1.0, timeout)


def _redact_http_error(value, question=""):
    """Project an error excerpt without credentials or the current question."""
    value = str(value)
    if question:
        value = value.replace(question, "[QUESTION_OMITTED]")
        value = value.replace(json.dumps(question, ensure_ascii=True)[1:-1], "[QUESTION_OMITTED]")
    for name, secret in os.environ.items():
        if secret and re.search(r"TOKEN|KEY|PASSWORD|SECRET|CREDENTIAL|AUTHORIZATION", name, re.I):
            value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+", r"\1 [REDACTED]", value)
    value = re.sub(r'''(?ix)(["']?(?:authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret|cookie|set-cookie)["']?\s*[:=]\s*)("[^"]*"|'[^']*'|[^\s,;}]+)''', r"\1[REDACTED]", value)
    value = re.sub(r"(https?://)[^/\s@]+@", r"\1[REDACTED]@", value)
    value = re.sub(r'''(https?://[^\s?'"<>]+)\?[^\s'"<>]*''', r"\1?[REDACTED]", value)
    return "".join(c for c in value if c in "\n\t" or ord(c) >= 32 and ord(c) != 127)


def _http_error_diagnostics(exc, raw, question=""):
    """Keep the received HTTP error visible in workflow results, without retrying."""
    text = raw.decode("utf-8", "replace")
    allowed = {"server", "via", "content-type", "x-request-id", "x-correlation-id",
               "x-envoy-upstream-service-time", "x-error-code", "x-error-type"}
    headers = {str(key).lower(): _redact_http_error(value, question)[:200]
               for key, value in (getattr(exc, "headers", None) or {}).items()
               if str(key).lower() in allowed}
    try:
        data = json.loads(text)
        body_format = "json"
    except ValueError:
        data, body_format = None, "text" if text else "empty"
    messages, identifiers = [], {}
    def collect(value, depth=0):
        if not isinstance(value, dict) or depth > 4:
            return
        for key in ("code", "type", "error_type"):
            item = value.get(key)
            if type(item) is int or isinstance(item, str) and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,80}", item):
                identifiers.setdefault(key, _redact_http_error(item, question))
        for key in ("message", "detail", "error", "errMsg", "reason"):
            item = value.get(key)
            if isinstance(item, str):
                # Some gateways echo the complete request inside their error.
                if not re.search(r'''["'](?:question|messages|prompt|answer|documents|sources)["']\s*:''', item, re.I):
                    messages.append(_redact_http_error(item, question)[:1000])
        for key in ("body", "error", "detail", "data", "cause"):
            collect(value.get(key), depth + 1)
    collect(data)
    if body_format == "json":
        excerpt = "\n".join(dict.fromkeys(messages))[:1500]
    elif re.search(r'''["'](?:question|messages|prompt|answer|documents|sources)["']\s*:''', text, re.I):
        excerpt = "[REQUEST_OR_SOURCE_CONTENT_OMITTED]"
    else:
        excerpt = _redact_http_error(text, question)[:1500]
    try:
        _, _, wait = _settings()
    except Exception:
        wait = None
    hints = ("timeout", "timed out", "deadline", "aiohttp", "asyncio", "nginx", "envoy", "upstream", "gunicorn")
    return {
        "revision": HTTP_ERROR_DIAGNOSTICS_REVISION,
        "response_headers": headers,
        "body_format": body_format,
        "captured_body_bytes": len(raw),
        "capture_limit_reached": len(raw) >= 16384,
        "captured_body_sha256": hashlib.sha256(raw).hexdigest(),
        "error_fields": identifiers,
        "error_body_excerpt": excerpt,
        "error_hints": [hint for hint in hints if hint in text.lower()],
        "socket_timeout_seconds": wait,
        "proxy_environment_present": {name: bool(os.getenv(name)) for name in (
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
            "http_proxy", "https_proxy", "all_proxy", "no_proxy")},
    }


def _workflow_settings(data):
    """Inspect the deployed workflow without HTTP, model calls, or secret output."""
    _, _, timeout = _settings()
    mode = os.getenv("GENOS_RAG_PROGRESS_UI", "socketio-final").strip().lower()
    settings = {
        "workflow_revision": WORKFLOW_REVISION,
        "progress_display_revision": PROGRESS_DISPLAY_REVISION,
        "http_error_diagnostics_revision": HTTP_ERROR_DIAGNOSTICS_REVISION,
        "json_socket_timeout_seconds": timeout,
        "stream_socket_timeout_seconds": timeout,
        "progress_mode": mode,
        "transport_mode": "sse",
        "route_with_socket_id": "/stream",
        "route_without_socket_id": "/stream",
        "json_fallback_http_statuses": [404, 405],
    }
    _log_event("workflow.settings", request_id=data["request_id"], **settings)
    return {
        "text": "워크플로우 설정 확인\n" + json.dumps(settings, ensure_ascii=False, indent=2),
        "answer_status": "diagnostics",
        "request_id": data["request_id"],
        "workflow_settings": settings,
    }


def unwrap(payload):
    """GENOS 게이트웨이의 중첩 응답을 실제 RAG 결과 dict로 푼다."""
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            return {}
    if not isinstance(payload, dict):
        return {}

    # service.py의 정상 응답은 {status, body}, 다른 GENOS 리비전은 {code, data}다.
    for key in ("body", "data", "result"):
        if key in payload and isinstance(payload[key], (dict, str)):
            inner = unwrap(payload[key])
            if inner:
                if "_gateway_status" not in inner and isinstance(payload.get("status"), int):
                    inner["_gateway_status"] = payload["status"]
                return inner
    return dict(payload)


def _request_body(question, data):
    request_id = str(data.get("request_id") or uuid.uuid4().hex)
    request_body = {
        "API_TYPE": "LEGAL_AGENT",
        "question": question,
        "channel": "genos-chat",
        "session_id": _session_id(data),
        "user_id": _user_id(data),
        "request_id": request_id,
    }
    for key in ("team_id", "scope", "document_ids", "use_llm"):
        if key in data:
            request_body[key] = data[key]
    # A workflow revision can bind a team independently of chat payloads.
    # Read on each request; an explicitly invalid setting must not widen scope.
    if "TEAM_ID" in os.environ:
        team_id = os.environ["TEAM_ID"].strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+_team", team_id):
            raise ValueError("TEAM_ID에 risk_team 같은 실제 팀 폴더명을 설정해 주세요.")
        request_body["team_id"] = team_id
    if os.environ.get("GENOS_MEMORY_ENABLED", "0").strip().lower() in {"1", "true", "on"}:
        import hashlib, hmac
        key = os.environ.get("GENOS_MEMORY_SIGNING_KEY", "")
        if len(key) < 32:
            raise ValueError("멀티턴용 신뢰 연결 설정이 없습니다.")
        if "TEAM_ID" not in os.environ:
            raise ValueError("멀티턴 워크플로우의 TEAM_ID를 고정해야 합니다.")
        if request_body["user_id"] == "anonymous" or request_body["session_id"] == "sess-anonymous":
            raise ValueError("멀티턴에는 스튜디오 사용자와 대화 식별자가 필요합니다.")
        # Preserve full stable identity; sanitizing/truncating must not merge users or sessions.
        info = data.get("userInfo") if isinstance(data.get("userInfo"), dict) else {}
        raw_user = data.get("user_id") or data.get("userId") or info.get("user_id") or info.get("userId")
        raw_session = data.get("chatId") or data.get("chat_id") or data.get("sessionId") or data.get("session_id")
        request_body["user_id"] = "u-" + hashlib.sha256(str(raw_user).encode()).hexdigest()
        request_body["session_id"] = "s-" + hashlib.sha256(str(raw_session).encode()).hexdigest()
        request_body["memory"] = True
        if "scope" in request_body:
            raise ValueError("멀티턴 문서 범위는 TEAM_ID와 document_ids로 지정합니다.")
        for name in ("expected_revision", "public_question"):
            if name in data:request_body[name] = data[name]
        stamp = int(time.time())
        canonical = json.dumps({"issued_at": stamp, "request": {k:v for k,v in request_body.items() if k not in {"API_TYPE", "channel", "memory_authorization"}}},
                               sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
        request_body["memory_authorization"] = {"issued_at": stamp, "signature": hmac.new(key.encode(), canonical, hashlib.sha256).hexdigest()}
    request_body['ad_session_id']=str(data.get('chatId') or data.get('chat_id') or data.get('sessionId') or data.get('session_id') or '')
    request_body['ad_channel']=_ad_channel(data)
    return request_body


def call_code_serving(question, data):
    request_body = _request_body(question, data)
    return _post_code_serving(request_body)


def _post_code_serving(request_body):
    endpoint, token, timeout = _settings()
    request_id = request_body["request_id"]
    encoded = json.dumps(request_body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(endpoint, data=encoded, method="POST")
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Content-Type", "application/json")
    started = time.perf_counter()
    _log_event(
        "code_serving.request.started",
        request_id=request_id,
        endpoint=endpoint,
        timeout_seconds=timeout,
        request_bytes=len(encoded),
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        _log_event(
            "code_serving.response.received",
            request_id=request_id,
            http_status=response.status,
            response_bytes=len(raw),
            content_type=response.headers.get("Content-Type", ""),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return unwrap(json.loads(raw.decode("utf-8")))


async def _workflow_warmup(operation, data):
    """Explicit workflow test operation; never turn metadata into a question."""
    request_id = data['request_id']
    try:
        body = await asyncio.to_thread(_post_code_serving, {
            'API_TYPE': operation, 'request_id': request_id,
        })
        state = body.get('state')
        if state not in {'NOT_STARTED', 'RUNNING', 'READY', 'FAILED'}:
            raise ValueError('WARMUP 응답 계약 불일치: 코드서빙 리비전을 확인해 주세요.')
        if body.get('_gateway_status', 200) >= 400:
            raise ValueError('WARMUP 요청 실패: 코드서빙 로그를 확인해 주세요.')
        messages = {
            'NOT_STARTED': '자료 준비를 아직 시작하지 않았습니다.',
            'RUNNING': '자료를 준비하고 있습니다. WARMUP_STATUS로 상태를 확인해 주세요.',
            'READY': '이 프로세스의 자료 준비가 완료되었습니다.',
            'FAILED': '자료 준비에 실패했습니다. warmup.failed 로그를 확인해 주세요.',
        }
        text = messages[state] + '\nworker_id: ' + str(body.get('worker_id', ''))
        if body.get('generation_path'):
            text += '\ngeneration: ' + str(body['generation_path'])
        _log_event('workflow.warmup.finished', request_id=request_id,
                   operation=operation, state=state, worker_id=body.get('worker_id'))
        return {'text': text, 'answer_status': 'warmup', 'request_id': request_id,
                'warmup': body}
    except Exception as exc:
        _log_event('workflow.warmup.failed', level='ERROR', request_id=request_id,
                   operation=operation, error_type=type(exc).__name__, error_message=str(exc)[:500])
        return {'text': '자료 준비 상태를 가져오지 못했습니다. 코드서빙 리비전과 워크플로우 로그를 확인해 주세요.',
                'answer_status': 'failed', 'request_id': request_id}


class _ChatProgress:
    """Render scoped read labels and committed decision summaries as Markdown."""

    def __init__(self, data):
        self.sid = str(data.get("socketIOClientId") or "")
        self.blocks = []
        self.emit = None
        mode = os.getenv("GENOS_RAG_PROGRESS_UI", "socketio-final").strip().lower()
        self.enabled = mode in {"socketio-final", "socketio", "socketio-inline"} and bool(self.sid)
        self.show_progress = mode in {"socketio", "socketio-inline"}
        self.show_inline_progress = mode == "socketio-inline"
        self.primed = False
        self.last_heartbeat = -30000
        self.last_status = ""
        self.last_body_status = ""
        self.last_body_label = ""
        self.last_body_elapsed = -5000
        self.visible_steps = 0
        self.last_wait_label = None
        self.answer_raw = ''
        self.answer_sent = ''
        self.answer_seq = 0
        self.transport = {"requested_route": "/stream", "route": "/stream",
                          "opened": False, "progress_events": 0, "heartbeat_events": 0,
                          "answer_events": 0}

    async def _send(self, event, value):
        if not self.enabled:
            return
        try:
            if self.emit is None:
                from main_socketio import sio_server
                self.emit = sio_server.emit
            sent = self.emit(event, value, room=self.sid)
            if inspect.isawaitable(sent):
                await sent
        except Exception as exc:
            self.enabled = False
            _log_event("workflow.progress.socket_failed", level="WARNING", error_type=type(exc).__name__)

    async def progress(self, event):
        if not self.show_progress or self.answer_seq:
            return
        if not isinstance(event, dict) or event.get("schema_version") != "rag-progress-v1":
            return
        kind = event.get("kind")
        label = event.get("label")
        if kind not in {"phase", "candidate", "reading", "read_complete", "selected", "revised", "review", "decision", "model_wait", "heartbeat", "overflow"}:
            return
        if not isinstance(label, str) or len(label) > 140:
            return
        if label in {"내부 모델 응답을 받음", "모델 결과 형식을 검증함"}:
            return
        details = event.get("details", [])
        details = [" ".join(row.split()) for row in details[:8]
                   if isinstance(row, str) and 0 < len(row) <= 300] if isinstance(details, list) else []
        elapsed = event.get("elapsed_ms", 0)
        elapsed = elapsed if type(elapsed) is int and elapsed >= 0 else 0
        count = event.get("count")
        message = label + (f" · {count}건" if type(count) is int and 0 <= count <= 100000 else "")
        if kind == "heartbeat":
            if elapsed - self.last_heartbeat < 30000:
                return
            self.last_heartbeat = elapsed
            # A heartbeat is a connection signal, not a new processing stage.
            message = (self.last_status or "요청 처리 중") + f" · 요청 경과 {elapsed // 1000}초"
        else:
            if kind == "model_wait" and label == self.last_wait_label and not details:
                return
            if kind == "model_wait":
                self.last_wait_label = label
            else:
                self.last_wait_label = None
            signature = message + "\n" + "\n".join(details)
            if signature == self.last_body_status:
                return
            self.last_status = message
        # GENOS token append is the channel the user can already see. Forward
        # actual stage changes there as well as to the optional Reasoner panel.
        # Same-stage numeric updates are limited to one every five seconds.
        show_body = (bool(details) or kind == "heartbeat" or not self.primed or
                     label != self.last_body_label or elapsed - self.last_body_elapsed >= 5000)
        signature = message + "\n" + "\n".join(details)
        visible = message + ("\n" + "\n".join(details) if details else "")
        if self.show_inline_progress and self.enabled and show_body and signature != self.last_body_status:
            # A single newline is a Markdown soft break. Blank lines make each
            # stage a real paragraph in the GENOS chat renderer.
            prefix = "**에이전트 진행 상황**\n\n" if not self.primed else ""
            if kind == "heartbeat":
                body = "대기 · " + self._plain(message) + "\n\n"
            else:
                self.visible_steps += 1
                title = {"candidate": "검색", "reading": "열람", "read_complete": "열람 결과",
                         "selected": "근거 선택", "revised": "선택 변경", "decision": "판단",
                         "review": "검토", "model_wait": "현재 단계"}.get(kind, "진행")
                body = f"**{self.visible_steps}. {title}** · {self._plain(message)}\n\n"
                if details:
                    body += "\n".join("- " + self._plain(row) for row in details) + "\n\n"
            await self._send("token", prefix + body)
            self.primed = True
            self.last_body_status, self.last_body_label = signature, label
            self.last_body_elapsed = elapsed
        if not self.show_inline_progress:
            if not show_body or signature == self.last_body_status:
                return
            self.last_body_status, self.last_body_label = signature, label
            self.last_body_elapsed = elapsed
        # GENOS expects a cumulative node list and JSON in data.output.content.
        # Preserve the first 79 entries; refresh the last node at the UI limit.
        index = min(len(self.blocks) + 1, 80)
        block = {"nodeId": f"rag-progress-{index}",
                 "nodeLabel": "Visible Reasoner", "status": "FINISHED",
                 "data": {"output": {"content": json.dumps(
                     {"visible_rationale": f"[{label}]\n{visible}"}, ensure_ascii=False)}}}
        if len(self.blocks) < 80:
            self.blocks.append(block)
        else:
            self.blocks[-1] = block
        await self._send("agentFlowExecutedData", list(self.blocks))

    @staticmethod
    def _plain(value):
        # Source labels and model-authored summaries are plain text, never
        # user-supplied Markdown links, HTML or formatting instructions.
        value = " ".join("".join(c if c.isprintable() else " " for c in value).split())
        value = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        for char in ("\\", "`", "*", "_", "[", "]", "#", "!"):
            value = value.replace(char, "\\" + char)
        return value

    async def answer_delta(self, event):
        if not isinstance(event, dict) or event.get('schema_version') != 'rag-answer-delta-v1':
            return
        seq, value = event.get('seq'), event.get('text')
        if type(seq) is not int or seq != self.answer_seq + 1 or not isinstance(value, str):
            raise ValueError('invalid answer stream sequence')
        self.answer_seq = seq
        self.answer_raw += value
        # Wait for newline boundaries before expanding Markdown soft breaks.
        # This makes chunked rendering identical to completed answer rendering.
        text = _for_markdown(_without_inline_reference_numbers(self.answer_raw, final=False).strip())
        if not text.startswith(self.answer_sent):
            raise ValueError('answer stream prefix changed')
        delta = text[len(self.answer_sent):]
        if delta:
            if not self.answer_sent and self.primed:
                await self._send('token', '---\n\n**최종 답변**\n\n')
            await self._send('token', delta)
            self.answer_sent = text

    async def finish(self, text):
        if not self.enabled:
            return
        # GENOS still validates the final dict.  Token streaming is the chat
        # rendering channel; final text remains the same verified answer.
        if self.answer_sent:
            if text.startswith(self.answer_sent):
                text = text[len(self.answer_sent):]
            else:
                text = '\n\n---\n\n**답변 작성 결과**\n\n' + text
        elif self.primed:
            text = "---\n\n**최종 답변**\n\n" + text
        for start in range(0, len(text), 160):
            await self._send("token", text[start:start+160])
        await self._send("end", "end")


async def _stream_code_serving(question, data, display, *, probe=False):
    endpoint, token, configured_timeout = _settings()
    stream_endpoint = endpoint[:-5] + "/stream"
    body = ({"API_TYPE": "SSE_CHECK", "request_id": data["request_id"]}
            if probe else _request_body(question, data))
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue(maxsize=128)
    reader_closed = threading.Event()

    def enqueue(kind, value):
        async def deliver():
            if kind == 'progress' and queue.full():
                return
            while not reader_closed.is_set():
                try:
                    await asyncio.wait_for(queue.put((kind, value)), timeout=0.25)
                    return
                except asyncio.TimeoutError:
                    continue
        if reader_closed.is_set():
            return
        future = asyncio.run_coroutine_threadsafe(deliver(), loop)
        while not reader_closed.is_set():
            try:
                future.result(timeout=0.25)
                return
            except FutureTimeout:
                continue
        future.cancel()

    def read_stream():
        request = urllib.request.Request(stream_endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"), method="POST")
        request.add_header("Authorization", f"Bearer {token}")
        request.add_header("Content-Type", "application/json")
        request.add_header("Accept", "text/event-stream")
        started = time.perf_counter()
        _log_event("code_serving.stream.request.started", request_id=body["request_id"],
                   endpoint=stream_endpoint,
                   socket_timeout_seconds=configured_timeout,
                   configured_json_timeout_seconds=configured_timeout,
                   request_bytes=len(request.data))
        try:
            with urllib.request.urlopen(request, timeout=configured_timeout) as response:
                _log_event("code_serving.stream.response.opened", request_id=body["request_id"],
                           http_status=getattr(response, "status", None),
                           content_type=response.headers.get("Content-Type", ""),
                           duration_ms=int((time.perf_counter() - started) * 1000))
                if "text/event-stream" not in response.headers.get("Content-Type", ""):
                    raise ValueError("code serving did not return SSE")
                enqueue("opened", {"opened": True,
                    "server_revision": response.headers.get("X-Genos-SSE-Revision", "")[:100],
                    "progress_revision": response.headers.get("X-Genos-Progress-Revision", "")[:100],
                    "answer_revision": response.headers.get("X-Genos-Answer-Revision", "")[:100]})
                for raw in response:
                    if reader_closed.is_set():
                        return
                    if len(raw) > 1048576:
                        raise ValueError("SSE frame too large")
                    if not raw.startswith(b"data:"):
                        continue
                    frame = json.loads(raw[5:].decode("utf-8"))
                    if isinstance(frame, dict) and frame.get("event") in ("progress", "answer_delta", "result"):
                        enqueue(frame["event"], frame.get("data"))
                        if frame["event"] == "result":
                            _log_event("code_serving.stream.result.received", request_id=body["request_id"],
                                       duration_ms=int((time.perf_counter() - started) * 1000))
                            return
                raise ConnectionError("SSE ended without result")
        except urllib.error.HTTPError as exc:
            _log_event("code_serving.stream.request.failed", level="ERROR", request_id=body["request_id"],
                       http_status=exc.code, error_type=type(exc).__name__,
                       fallback=not probe and exc.code in (404, 405),
                       duration_ms=int((time.perf_counter() - started) * 1000))
            enqueue("fallback" if not probe and exc.code in (404, 405) else "error", exc)
        except Exception as exc:
            _log_event("code_serving.stream.request.failed", level="ERROR", request_id=body["request_id"],
                       error_type=type(exc).__name__,
                       duration_ms=int((time.perf_counter() - started) * 1000))
            enqueue("error", exc)

    reader = asyncio.create_task(asyncio.to_thread(read_stream))
    try:
        while True:
            kind, value = await queue.get()
            if kind == "opened":
                display.transport.update(value)
            elif kind == "progress":
                if isinstance(value, dict) and value.get("request_id") == body["request_id"]:
                    display.transport["progress_events"] += 1
                    if value.get("kind") == "heartbeat":
                        display.transport["heartbeat_events"] += 1
                    await display.progress(value)
            elif kind == "result":
                return unwrap(value)
            elif kind == 'answer_delta':
                if not isinstance(value, dict) or value.get('request_id') != body['request_id']:
                    raise ValueError('answer stream request mismatch')
                await display.answer_delta(value)
                display.transport['answer_events'] += 1
            elif kind == "fallback":
                await reader
                display.transport.update(route="/json", fallback_http_status=value.code)
                return await asyncio.to_thread(call_code_serving, question, data)
            else:
                raise value
    finally:
        reader_closed.set()
        if reader.done():
            await reader


async def _workflow_sse_check(data):
    """Verify the actual SSE route without running a legal query or JSON fallback."""
    display = _ChatProgress({})
    try:
        body = await _stream_code_serving("", data, display, probe=True)
        ready = body.get("sse_ready") is True and display.transport["opened"]
        details = {"workflow_revision": WORKFLOW_REVISION,
                   "progress_display_revision": PROGRESS_DISPLAY_REVISION,
                   "answer_display_revision": ANSWER_DISPLAY_REVISION,
                   "sse_ready": ready, "transport": display.transport,
                   "stream_server_revision": body.get("stream_server_revision"),
                   "stream_startup_revision": body.get("stream_startup_revision"),
                   "stream_progress_revision": body.get("stream_progress_revision"),
                   "stream_answer_revision": body.get("stream_answer_revision"),
                   "heartbeat_seconds": body.get("heartbeat_seconds")}
        _log_event("workflow.sse_check.finished", request_id=data["request_id"], **details)
        return {"text": ("SSE 연결 확인 완료" if ready else "SSE 응답 계약을 확인하지 못했습니다.")
                       + "\n" + json.dumps(details, ensure_ascii=False, indent=2),
                "answer_status": "diagnostics" if ready else "failed",
                "request_id": data["request_id"], "sse_check": details}
    except Exception as exc:
        failure = {"sse_ready": False, "workflow_revision": WORKFLOW_REVISION,
                   "transport": display.transport, "error_type": type(exc).__name__}
        if isinstance(exc, urllib.error.HTTPError):
            failure["http_status"] = exc.code
            failure["http_error_diagnostics"] = _http_error_diagnostics(exc, exc.read(16384))
        _log_event("workflow.sse_check.failed", level="ERROR", request_id=data["request_id"], **failure)
        return {"text": "SSE 연결을 확인하지 못했습니다. 코드서빙의 SSE 시작 명령과 리비전을 확인해 주세요.",
                "answer_status": "failed", "request_id": data["request_id"], "sse_check": failure}


def _answer_text(body):
    answer = body.get("answer")
    if isinstance(answer, dict):
        return str(answer.get("text") or "").strip()
    return str(answer or "").strip()


def _public_answer_text(body):
    """Show v5 legal review notes; retain legacy diagnostic-only filtering."""
    text = _answer_text(body)
    answer = body.get('answer')
    if isinstance(answer, dict) and (answer.get('provider_receipt') or {}).get('final_review_policy') == 'advisory':
        return _without_inline_reference_numbers(text).strip()
    text = re.split(r"(?:^|\n)\s*확인 한계\s*:", text, maxsplit=1)[0]
    return _without_inline_reference_numbers(text).strip()


_ANSWER_NUMERIC_REFERENCE = re.compile(r"\[[ \t]*[1-9][0-9]*(?:[ \t]*[,，;、\-–][ \t]*[1-9][0-9]*)*[ \t]*\]")
_ANSWER_REFERENCE_PREFIX = re.compile(r"\[[0-9,，;、\-– \t]*")
_ANSWER_QUOTES = {'"': '"', '“': '”', '‘': '’', '「': '」', '『': '』'}


def _without_inline_reference_numbers(text, *, final=True):
    """Hide postfix numeric footnotes in prose, including split SSE fragments.

    Quotes, code, named brackets, line-leading list numbers and Markdown links
    remain literal. Pending brackets wait for their content and link suffix;
    emitted text therefore stays a prefix of the final rendering.
    """
    out, index, protected = [], 0, None
    while index < len(text):
        char = text[index]
        if char == "\\":
            if not final and index + 1 == len(text):
                break
            out.append(text[index:index+2]); index += 2
            continue
        if protected:
            if text.startswith(protected, index):
                out.append(protected); index += len(protected); protected = None
            else:
                out.append(char); index += 1
            continue
        if char == '`':
            end = index + 1
            while end < len(text) and text[end] == '`':
                end += 1
            protected = text[index:end]
            out.append(protected); index = end
            continue
        if char in _ANSWER_QUOTES:
            protected = _ANSWER_QUOTES[char]
            out.append(char); index += 1
            continue
        if char == '[':
            # Numeric brackets at the beginning of a line may be list labels.
            before = text[:index].rsplit('\n', 1)[-1].rstrip(' \t')
            postfix = bool(before and (before[-1].isalnum() or before[-1] in '.。!?;:)]"”’」』`*_'))
            if postfix:
                match = _ANSWER_NUMERIC_REFERENCE.match(text, index)
                if not final and (match and match.end() == len(text) or
                                  _ANSWER_REFERENCE_PREFIX.fullmatch(text[index:])):
                    break
                linked = bool(match and match.end() < len(text) and text[match.end()] == '(')
                if match and match.end() < len(text) and text[match.end()] == '[':
                    suffix = text[match.end():]
                    if not final and _ANSWER_REFERENCE_PREFIX.fullmatch(suffix):
                        break
                    linked = _ANSWER_NUMERIC_REFERENCE.match(suffix) is None
                if match and not linked:
                    while out and out[-1] in (' ', '\t'):
                        out.pop()
                    index = match.end()
                    continue
        out.append(char); index += 1
    return ''.join(out)


def _used_source_ids(body):
    answer = body.get("answer")
    if not isinstance(answer, dict):
        return set()
    used = set()
    for claim in answer.get("claims") or []:
        if isinstance(claim, dict):
            used.update(str(item) for item in (claim.get("evidence_ids") or []) if item)
            used.update(str(item) for item in (claim.get("source_ids") or []) if item)
    return used


def _source_label(item):
    name = item.get("document_name") or item.get("document_id") or "문서"
    ancestors = item.get("ancestors") or []
    titles = []
    for ancestor in ancestors:
        if isinstance(ancestor, dict):
            title = ancestor.get("title") or ancestor.get("label") or ancestor.get("name")
            if title:
                titles.append(str(title))
        elif isinstance(ancestor, str) and ancestor.strip():
            titles.append(ancestor.strip())
    location = " > ".join(titles[-2:])
    if not location and item.get("block_id"):
        location = str(item["block_id"])
    return f"- {name}" + (f" · {location}" if location else "")


def _tier_sources(bundle):
    from html import escape as html_escape
    def escape(value):
        return re.sub(r'([\\`*_{}\[\]()!])', r'\\\1', html_escape(str(value)))
    lines=[]
    seen=set()
    for c in sorted(bundle.get("sources",[]),
                    key=lambda item: isinstance(item,dict) and item.get("tier")!="CORE"):
        if not isinstance(c,dict) or c.get("tier") not in {"CORE","SUPPLEMENTAL"}:
            continue
        name=str(c.get("document_name") or "").strip()
        location=str(c.get("coordinate_label") or "").strip()
        if not name or (name,location) in seen:
            continue
        seen.add((name,location))
        tier="핵심" if c["tier"]=="CORE" else "보완"
        label=escape(name+(" · "+location if location else ""))
        # GENOS chat has no confirmed browser route for the RAG source API.
        # Markdown links to relative API paths can render as the raw path in chat.
        lines.append("- "+tier+" · "+label)
    return "**출처**\n"+"\n".join(lines) if lines else ""


def _sources(body):
    bundle=(body.get("assembly",{}).get("term_agent") or {}).get("source_bundle")
    if isinstance(bundle,dict) and bundle.get("schema_version")=="source-tiers-v4":
        return _tier_sources(bundle)
    assembly = body.get("assembly")
    contexts = assembly.get("context") if isinstance(assembly, dict) else []
    if not isinstance(contexts, list):
        contexts = []
    used = _used_source_ids(body)
    lines = []
    for item in contexts:
        if not isinstance(item, dict):
            continue
        # claims가 출처를 특정했다면 실제 사용된 근거만 표시한다.
        if used and str(item.get("id") or "") not in used:
            continue
        lines.append(_source_label(item))
    unique = list(dict.fromkeys(lines))
    return "**출처**\n" + "\n".join(unique) if unique else ""


def _has_found_source(body):
    assembly = body.get("assembly")
    if not isinstance(assembly, dict):
        return False
    if assembly.get("context"):
        return True
    agent = assembly.get("term_agent")
    if not isinstance(agent, dict):
        return False
    bundle = agent.get("source_bundle")
    if isinstance(bundle, dict) and bundle.get("sources"):
        return True
    exploration = agent.get("exploration_v3")
    return isinstance(exploration, dict) and bool((exploration.get("totals") or {}).get("evidence") or exploration.get("evidence_decisions"))


def render(body):
    if body.get('response_schema')=='ad-mode-v1':return body['text']
    status = body.get("_gateway_status")
    if isinstance(status, int) and status >= 400:
        if body.get("code") and body.get("detail"):
            return "실행 오류 (" + str(body["code"]) + "): " + str(body["detail"])[:1000]
        return "지금 답변을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."
    answer = _public_answer_text(body)
    source_text = _sources(body)
    if not answer and source_text:
        return "관련 원문은 찾았지만 답변을 완성하지 못했습니다.\n\n"+source_text
    if not answer:
        if _has_found_source(body):
            return "관련 원문은 찾았지만 답변 검토를 완료하지 못했습니다."
        return "관련 근거를 찾지 못해 답변을 만들지 못했습니다. 질문을 조금 더 구체적으로 입력해 주세요."
    text = f"{answer}\n\n{source_text}" if source_text else answer
    return text


def _for_markdown(text):
    text = re.sub(r"~", r"\\~", text)
    return re.sub(r"(?<!\n)\n(?!\n)", "\n\n", text)


async def _run_once(data):
    """질문 하나를 처리해 화면에 보낼 텍스트와 관측 필드를 만든다."""
    started = time.perf_counter()
    data = data if isinstance(data, dict) else {}
    request_id = str(data.get('request_id') or data.get('messageId') or uuid.uuid4().hex)
    data = {**data, "request_id": request_id}
    operation = str(data.get('API_TYPE') or '').strip().upper()
    if operation == 'SSE_CHECK':
        return await _workflow_sse_check(data)
    if operation == 'WORKFLOW_SETTINGS':
        return _workflow_settings(data)
    if operation in {'WARMUP', 'WARMUP_STATUS'}:
        return await _workflow_warmup(operation, data)
    question = _extract_question(data)
    if question:
        try:
            probe=unwrap(await asyncio.to_thread(_post_code_serving, {
                'API_TYPE':'AD_PROBE','question':question,'request_id':request_id,
                'ad_session_id':str(data.get('chatId') or data.get('chat_id') or data.get('sessionId') or data.get('session_id') or ''),
                'ad_channel':_ad_channel(data)}))
            if probe.get('response_schema')=='ad-mode-v1':return {**probe,'request_id':request_id}
        except Exception as exc:
            # Cannot establish the mode: do not risk sending an admin turn to RAG.
            return {'text':'AD_MODE_CHECK_FAILED: '+_redact_http_error(str(exc),question),'answer_status':'failed','request_id':request_id}
    if question.upper() == 'SSE_CHECK':
        return await _workflow_sse_check(data)
    if question.upper() == 'WORKFLOW_SETTINGS':
        return _workflow_settings(data)
    if question.upper() in {'WARMUP', 'WARMUP_STATUS'}:
        return await _workflow_warmup(question.upper(), data)
    session_id = _session_id(data)
    _log_event(
        "workflow.request.started",
        request_id=request_id,
        session_id=session_id,
        input_keys=sorted(str(key) for key in data),
        question_chars=len(question),
    )
    if not question or _BARE_UUID.fullmatch(question):
        reason = "question_is_uuid" if question else "question_missing"
        _log_event("workflow.request.invalid", level="WARNING", request_id=request_id, reason=reason)
        return {"text": "질문을 입력해 주세요.", "answer_status": "invalid_input", "request_id": request_id}
    display = _ChatProgress(data)
    try:
        body = await _stream_code_serving(question, data, display)
        call_seconds = time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        raw_error = exc.read(16384)
        detail = raw_error.decode("utf-8", "replace")[:2000]
        error_diagnostics = _http_error_diagnostics(exc, raw_error, question)
        try:
            failure = unwrap(json.loads(detail))
        except ValueError:
            failure = {}
        service_error = (isinstance(failure.get("code"), str)
                         and isinstance(failure.get("detail"), str))
        _log_event(
            "code_serving.request.failed",
            level="ERROR",
            request_id=request_id,
            http_status=exc.code,
            error_type=type(exc).__name__,
            detail=_redact_http_error(detail, question),
            http_error_diagnostics=error_diagnostics,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        failed = {
            "text": ("실행 오류 (" + failure["code"] + "): " + _redact_http_error(failure["detail"], question)[:1000]) if service_error else
                    f"지금 답변을 가져오지 못했습니다. (코드서빙 응답 {exc.code}, 추적 번호: {request_id})",
            "answer_status": "failed",
            "failure_kind": "http_error",
            "http_status": exc.code,
            "http_error_diagnostics": error_diagnostics,
            "code_serving_transport": dict(display.transport),
            "workflow_revision": WORKFLOW_REVISION,
            "tm_total": round(time.perf_counter() - started, 3),
            "session_id": session_id,
            "request_id": request_id,
        }
        await display.finish(failed["text"])
        if display.blocks:
            failed["agentFlowExecutedData"] = display.blocks
        return failed
    except Exception as exc:  # 채팅 단계 밖으로 예외를 내보내지 않는다.
        _log_event(
            "workflow.request.crashed",
            level="ERROR",
            request_id=request_id,
            error_type=type(exc).__name__,
            error_message=str(exc)[:500],
            traceback=traceback.format_exc()[-4000:],
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        failed = {
            "text": f"지금 답변을 가져오지 못했습니다. (추적 번호: {request_id})",
            "answer_status": "failed",
            "failure_kind": "client_exception",
            "error_type": type(exc).__name__,
            "workflow_revision": WORKFLOW_REVISION,
            "code_serving_transport": dict(display.transport),
            "tm_total": round(time.perf_counter() - started, 3),
            "session_id": session_id,
            "request_id": request_id,
        }
        await display.finish(failed["text"])
        if display.blocks:
            failed["agentFlowExecutedData"] = display.blocks
        return failed

    text = render(body) if body.get('response_schema')=='ad-mode-v1' else _for_markdown(render(body))
    answered = bool(_public_answer_text(body)) and not (
        isinstance(body.get("_gateway_status"), int) and body["_gateway_status"] >= 400
    )
    result = {
        "text": text,
        "answer_status": "answered" if answered else "failed" if isinstance(body.get("_gateway_status"), int) and body["_gateway_status"] >= 400 else "incomplete" if _has_found_source(body) else "not_found",
        "run_id": body.get("run_id"),
        "session_id": session_id,
        "request_id": request_id,
        "history": "not_persisted",
        "workflow_revision": WORKFLOW_REVISION,
        "answer_display_revision": ANSWER_DISPLAY_REVISION,
        "progress_display_revision": PROGRESS_DISPLAY_REVISION,
        "code_serving_transport": dict(display.transport),
        "tm_code_serving": round(call_seconds, 3),
        "tm_total": round(time.perf_counter() - started, 3),
    }
    await display.finish(text)
    if display.blocks:
        result["agentFlowExecutedData"] = display.blocks
    assembly = body.get("assembly") if isinstance(body, dict) else None
    contexts = assembly.get("context") if isinstance(assembly, dict) else []
    _log_event(
        "workflow.request.finished",
        request_id=request_id,
        session_id=session_id,
        run_id=body.get("run_id"),
        gateway_status=body.get("_gateway_status"),
        answer_status=result["answer_status"],
        answer_chars=len(_answer_text(body)),
        context_count=len(contexts) if isinstance(contexts, list) else 0,
        tm_code_serving=result["tm_code_serving"],
        tm_total=result["tm_total"],
    )
    return result


async def run(data):
    """GENOS 워크플로우 규약: 완성된 답변을 ``text`` dict로 한 번 반환한다.

    현장 GENOS 테스트 런타임은 async generator의 token/end 문자열을
    최종 워크플로우 결과로 해석하지 않는다. 기준 브랜치처럼 단일
    dictionary를 반환해 코드 서빙이 준 검증된 답변을 그대로 전달한다.
    """
    return await _run_once(data)
