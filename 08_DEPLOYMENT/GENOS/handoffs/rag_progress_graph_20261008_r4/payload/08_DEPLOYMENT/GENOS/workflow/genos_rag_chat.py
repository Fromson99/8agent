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

try:
    from genos_diagnostics import install as _install_system_logging
except ModuleNotFoundError:
    # The standalone PASTE_ALL delivery embeds this exact stdlib-only module.
    # An older editor paste still keeps the original platform stdout behavior.
    _SYSTEM_LOGS = None
else:
    _SYSTEM_LOGS = _install_system_logging("workflow-python")


WORKFLOW_REVISION = "rag-v6-completion-20261007-r1"
PROGRESS_DISPLAY_REVISION = "rag-key-progress-20261007-r1"
ANSWER_DISPLAY_REVISION = "answer-reference-display-20260929-r1"
JUDGMENT_DISPLAY_REVISION = "judgment-knowledge-svg-20261008-r9"
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


def _raw_http_error(exc, request_id):
    raw = getattr(exc, "_genos_raw_error_body", None)
    if raw is None:
        raw = exc.read()
        exc._genos_raw_error_body = raw
        if _SYSTEM_LOGS is not None:
            _SYSTEM_LOGS.write("workflow.errors.raw.log", (
                "request_id=" + request_id + " HTTP " + str(exc.code) + "\n" + traceback.format_exc()
            ).encode("utf-8") + raw + b"\n")
    return raw


def _log_event(event, level="INFO", **fields):
    """GENOS가 수집하는 stdout에 1줄 1 JSON 이벤트를 남긴다."""
    if _SYSTEM_LOGS is not None:
        _SYSTEM_LOGS.write("workflow.events.raw.jsonl", (json.dumps(
            {"event": event, "level": level, **fields}, ensure_ascii=False, default=str) + "\n").encode("utf-8"))
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
                    messages.append(_redact_http_error(item, question))
        for key in ("body", "error", "detail", "data", "cause"):
            collect(value.get(key), depth + 1)
    collect(data)
    if body_format == "json":
        excerpt = "\n".join(dict.fromkeys(messages))
    elif re.search(r'''["'](?:question|messages|prompt|answer|documents|sources)["']\s*:''', text, re.I):
        excerpt = "[REQUEST_OR_SOURCE_CONTENT_OMITTED]"
    else:
        excerpt = _redact_http_error(text, question)
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
        "capture_limit_reached": False,
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
    mode = "off"
    settings = {
        "workflow_revision": WORKFLOW_REVISION,
        "progress_display_revision": PROGRESS_DISPLAY_REVISION,
        "judgment_display_revision": JUDGMENT_DISPLAY_REVISION,
        "http_error_diagnostics_revision": HTTP_ERROR_DIAGNOSTICS_REVISION,
        "json_socket_timeout_seconds": timeout,
        "stream_socket_timeout_seconds": timeout,
        "progress_mode": mode,
        "socketio_enabled": False,
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
        "ad_session_id": str(data.get('chatId') or data.get('chat_id') or data.get('sessionId') or data.get('session_id') or ''),
        "ad_channel": _ad_channel(data),
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
    if data.get('memory') is True or os.environ.get("GENOS_MEMORY_ENABLED", "0").strip().lower() in {"1", "true", "on"}:
        import hashlib
        if not re.fullmatch(r"[A-Za-z0-9_-]+_team", str(request_body.get('team_id', ''))):
            raise ValueError("멀티턴에는 TEAM_ID 또는 입력 team_id가 필요합니다.")
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
                   operation=operation, error_type=type(exc).__name__, error_message=str(exc),traceback=traceback.format_exc())
        return {'text': render_error({'request_id':request_id,'error_type':type(exc).__name__,
                   'detail':str(exc),'traceback':traceback.format_exc()}),
                'answer_status': 'failed', 'request_id': request_id}


class _ChatProgress:
    """Track SSE fragments for the final JSON without a Socket.IO emitter."""

    def __init__(self, data):
        self.sid = ""
        self.blocks = []
        self.flow_events = []
        self.emit = None
        self.enabled = False
        self.show_progress = False
        self.show_inline_progress = False
        self.primed = False
        self.last_heartbeat = -30000
        self.last_status = ""
        self.last_body_status = ""
        self.last_body_label = ""
        self.last_body_elapsed = -5000
        self.visible_steps = 0
        self.last_wait_label = None
        self.read_documents = {"reading": {}, "read_complete": {}}
        self.read_summary_indices = {}
        self.read_summary_signatures = {}
        self.inline_read_summaries = set()
        self.read_summary_emitted=set()
        self.read_summary_dirty=False
        self.answer_raw = ''
        self.answer_sent = ''
        self.answer_seq = 0
        self.transport = {"requested_route": "/stream", "route": "/stream",
                          "opened": False, "progress_events": 0, "heartbeat_events": 0,
                          "answer_events": 0}

    async def _send(self, event, value):
        if not self.enabled or self.emit is None:
            return
        try:
            sent = self.emit(event, value, room=self.sid)
            if inspect.isawaitable(sent):
                await sent
        except Exception as exc:
            self.enabled = False
            _log_event("workflow.progress.emitter_failed", level="WARNING", error_type=type(exc).__name__)

    async def progress(self, event):
        if not self.show_progress or self.answer_seq:
            return
        if not isinstance(event, dict) or event.get("schema_version") != "rag-progress-v1":
            return
        kind = event.get("kind")
        # Connection keep-alives never create a visible stage or waiting line.
        if kind in {"heartbeat", "model_wait"}:
            return
        label = event.get("label")
        if kind not in {"phase", "candidate", "reading", "read_complete", "selected", "revised", "review", "decision", "model_wait", "heartbeat", "overflow"}:
            return
        if not isinstance(label, str) or len(label) > 140:
            return
        if label in {"내부 모델 응답을 받음", "모델 결과 형식을 검증함"}:
            return
        details = event.get("details", [])
        full_error = (event.get('basis') or {}).get('detail_mode') == 'full_error'
        details = ([_redact_http_error(row) for row in details if isinstance(row,str)] if full_error else
                   [" ".join(row.split()) for row in details[:8]
                    if isinstance(row, str) and 0 < len(row) <= 300]) if isinstance(details, list) else []
        # Location-specific activity must remain visible in chronological order.
        # Older aggregate events still update the two existing summary cards.
        basis = event.get('basis') or {}
        read_summary = kind in self.read_documents and basis.get('detail_mode') != 'activity'
        if read_summary and details:
            documents = self.read_documents[kind]
            for row in details:
                state = "reported"
                for suffix, value in ((" · 열람 완료", "complete"),
                                      (" · 일부 열람, 나머지 확인 필요", "partial")):
                    if row.endswith(suffix):
                        row, state = row[:-len(suffix)], value
                        break
                document = row.split(" · ", 1)[0]
                locations = documents.setdefault(document, {})
                if locations.get(row) != "complete":
                    locations[row] = state
            label = "원문 열람 중" if kind == "reading" else "원문 확보 현황"
            details = []
            for document, locations in list(documents.items())[:4]:
                partial = sum(state == "partial" for state in locations.values())
                detail = f"{document} · {'열람 시작' if kind=='reading' else '확보 확인'} {len(locations)}개 범위"
                if partial:
                    detail += f" · 일부 열람 {partial}곳"
                details.append(detail)
                details.extend('  '+row.split(' · ',1)[-1] for row in list(locations)[-1:])
            if len(documents) > 4:
                details.append(f"그 외 {len(documents) - 4}개 문서")
        elapsed = event.get("elapsed_ms", 0)
        elapsed = elapsed if type(elapsed) is int and elapsed >= 0 else 0
        count = event.get("count")
        message = label + (f" · {count}건" if type(count) is int and 0 <= count <= 100000 else "")
        if read_summary and self.read_documents[kind]:
            documents = self.read_documents[kind]
            total = sum(len(locations) for locations in documents.values())
            message = f"{label} · 문서 {len(documents)}개 · {'열람 시작' if kind=='reading' else '확보 확인'} {total}개 범위"
        if read_summary:
            signature = message + "\n" + "\n".join(details)
            if self.read_summary_signatures.get(kind) == signature:
                return
            self.read_summary_signatures[kind] = signature
        signature = message + "\n" + "\n".join(details)
        if signature == self.last_body_status:
            return
        if len(self.flow_events) < 256 or full_error:
            self.flow_events.append({"label": message, "details": details,
                                     "kind": kind, "basis": dict(event.get('basis') or {})})
        self.last_status = message
        # GENOS token append is the channel the user can already see. Forward
        # actual stage changes there as well as to the optional Reasoner panel.
        # Same-stage numeric updates are limited to one every five seconds.
        show_body = (bool(details) or not self.primed or
                     label != self.last_body_label or elapsed - self.last_body_elapsed >= 5000)
        signature = message + "\n" + "\n".join(details)
        visible = message + ("\n" + "\n".join(details) if details else "")
        append_read_summary = not read_summary or kind not in self.inline_read_summaries
        if (self.show_inline_progress and self.enabled and show_body
                and signature != self.last_body_status and append_read_summary):
            # A single newline is a Markdown soft break. Blank lines make each
            # stage a real paragraph in the GENOS chat renderer.
            prefix = "**에이전트 진행 상황**\n\n" if not self.primed else ""
            self.visible_steps += 1
            title = {"candidate": "검색", "reading": "열람", "read_complete": "열람 결과",
                     "selected": "근거 선택", "revised": "선택 변경", "decision": "판단",
                     "review": "검토", "model_wait": "현재 단계"}.get(kind, "진행")
            stage_title = label.split(' · ', 1)[0]
            if stage_title in {'질문 이해','검색 계획','자료 검색','원문 확인','근거 선택','적용 판단','답변 작성'}:
                title = stage_title
            shown = message.removeprefix(title+' · ')
            body = f"**{self.visible_steps}. {title}** · {self._plain(shown)}\n\n"
            if full_error:
                body += render_error({'stage':label,'logs':details})+'\n\n'
            elif details:
                body += "\n\n".join("- " + self._plain(row) for row in details) + "\n\n"
            await self._send("token", prefix + body)
            if read_summary:
                self.inline_read_summaries.add(kind)
            self.primed = True
            self.last_body_status, self.last_body_label = signature, label
            self.last_body_elapsed = elapsed
        if not self.show_inline_progress:
            if not show_body or signature == self.last_body_status:
                return
            self.last_body_status, self.last_body_label = signature, label
            self.last_body_elapsed = elapsed
        # GENOS expects a cumulative node list and JSON in data.output.content.
        # Reads update two stable summaries instead of appending every unit.
        # Other stages retain the existing cumulative list and 80-node limit.
        existing = self.read_summary_indices.get(kind) if read_summary else None
        index = existing + 1 if existing is not None else min(len(self.blocks) + 1, 80)
        node_id = f"rag-error-{len(self.blocks) + 1}" if full_error else f"rag-progress-{index}"
        block = {"nodeId": node_id,
                 "nodeLabel": "Visible Reasoner", "status": "FINISHED",
                 "data": {"output": {"content": json.dumps(
                     {"visible_rationale": f"[{label}]\n{visible}"}, ensure_ascii=False)}}}
        if existing is not None:
            self.blocks[existing] = block
        elif len(self.blocks) < 80 or full_error:
            self.blocks.append(block)
            if read_summary and index < 80:
                self.read_summary_indices[kind] = index - 1
        else:
            if not self.blocks[-1]['nodeId'].startswith('rag-error-'):
                self.blocks[-1] = block
        # GENOS can append a new card even for an already sent nodeId. Keep the
        # final summaries in memory, but emit each read channel only once while
        # running; flush one final snapshot at completion.
        if read_summary:
            if kind in self.read_summary_emitted:
                self.read_summary_dirty=True
                return
            self.read_summary_emitted.add(kind)
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
        if self.read_summary_dirty:
            await self._send('agentFlowExecutedData',list(self.blocks))
            self.read_summary_dirty=False
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
            if _SYSTEM_LOGS is not None:
                _raw_http_error(exc, body["request_id"])
            _log_event("code_serving.stream.request.failed", level="ERROR", request_id=body["request_id"],
                       http_status=exc.code, error_type=type(exc).__name__,
                       fallback=not probe and exc.code in (404, 405),
                       duration_ms=int((time.perf_counter() - started) * 1000))
            enqueue("fallback" if not probe and exc.code in (404, 405) else "error", exc)
        except Exception as exc:
            if _SYSTEM_LOGS is not None:
                _SYSTEM_LOGS.write("workflow.errors.raw.log", (
                    "request_id=" + body["request_id"] + "\n" + traceback.format_exc()).encode("utf-8"))
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
            failure["http_error_diagnostics"] = _http_error_diagnostics(exc, _raw_http_error(exc, data["request_id"]))
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


def _ad_result(body):
    """Keep the exact Markdown fallback; prefer the server's escaped scroll table."""
    result=dict(body)
    if body.get('table_html') and os.environ.get('GENOS_AD_TABLE_FORMAT','html').lower()!='markdown':
        result['text_markdown']=body['text']
        result['text']=body['table_html']
    return result


def _judgment_view(body):
    """Read only the code-authored projection bound to this answer's route."""
    agent = (body.get('assembly') or {}).get('term_agent') or {}
    view, case = agent.get('judgment_view'), agent.get('case') or {}
    if not isinstance(view, dict) or view.get('schema_version') != 'judgment-view-v1':
        return None
    raw = {k: v for k, v in view.items() if k != 'content_sha256'}
    actual = hashlib.sha256(json.dumps(raw, ensure_ascii=False, sort_keys=True,
                                      separators=(',', ':')).encode()).hexdigest()
    if actual != view.get('content_sha256'):
        return None
    if (view.get('question_id'), view.get('question_revision'), view.get('route_id')) != (
            case.get('question_id'), case.get('revision'), case.get('route_id')):
        return None
    stages = view.get('stages')
    if not isinstance(stages, list) or [s.get('stage') for s in stages if isinstance(s, dict)] != [
            'INTENT', 'PLAN', 'RECALL', 'READ', 'SELECT', 'ASSESS', 'COMPOSE']:
        return None
    if any(s.get('judgment_ref') != case.get('judgment_refs', {}).get(s['stage']) for s in stages):
        return None
    return view


def _flow_text(value):
    """Plain, readable labels shared by the SVG and the judgment toggles."""
    text = ' '.join(str(value or '').split())
    words = {'CASE': '법령 조사', 'START': '새 질문 조사', 'DIRECT': '바로 안내',
             'RESEARCH': '추가 검색', 'FINISH': '조사 마무리', 'RETURN_TO': '이전 조사로 복귀',
             'SEARCH_STRUCTURE': '문서 구조 검색', 'OPEN_STRUCTURE': '조문 목차 열기',
             'NEXT_STRUCTURE': '다음 구조 목록', 'BROWSE_STRUCTURE': '현재 문서 목차 탐색',
             'OPEN_LAW': '적중 조문 목록 열기', 'NEXT_ARTICLES': '다음 적중 조문', 'NEXT_HITS': '다음 본문 적중',
             'FULLTEXT_SEARCH': '본문 검색', 'READ': '원문 확인', 'SELECT': '근거 선택',
             'SUCCEEDED': '처리 완료', 'ACCEPTED': '선택 완료', 'APPLIED': '실행 완료',
             'ADOPT': '근거 채택', 'EXCLUDE': '근거 제외', 'DEFER': '판단 보류',
             'READ_ARTICLES': '선택한 조문 읽기', 'READ_PARENT': '상위 원문 읽기',
             'READ_SCOPE': '선택한 원문 범위 읽기', 'VIEW_SAVED_SOURCE': '확보한 원문 다시 보기',
             'FOLLOW_CONNECTION': '연결 원문 확인', 'REQUEST_FACT': '추가 사실 확인',
             'CHOOSE_VERSION': '적용할 버전 선택', 'REFERENCE_CHOICES': '연결 원문 선택'}
    words.update({'GENERAL_RULE_EXPLANATION': '규정 내용 설명', 'LEGAL_INTERPRETATION': '법령 의미 확인'})
    return re.sub(r'\b(?:'+'|'.join(words)+r')\b', lambda match: words[match.group()], text)


def _flow_nodes(view, progress_events=None):
    """Prefer the actual displayed sequence, including re-entry, over a template."""
    nodes = []
    for event in progress_events or []:
        if not isinstance(event, dict) or event.get('kind') in {'heartbeat', 'model_wait'}:
            continue
        if not event.get('label'):
            continue
        nodes.append({'title': _flow_text(event['label']),
                      'details': [_flow_text(value) for value in event.get('details', []) if isinstance(value, str)],
                      'returned': event.get('kind') == 'revised'})
    if nodes:
        return nodes, 'request-progress'
    # Saved/reused answers can have no current progress. Retain their verified
    # execution labels rather than implying a new seven-stage investigation.
    for stage in view['stages']:
        details = [_flow_text(value) for value in stage.get('decisions', []) if value]
        if stage['stage'] == 'RECALL':
            details += ['읽을 원문 '+str(len(stage.get('data', [])))+'건']
        elif stage['stage'] == 'READ':
            details += list(dict.fromkeys(str(item.get('document_name', ''))+' · '+str(item.get('coordinate', ''))
                                         for item in stage.get('data', [])))
        elif stage['stage'] == 'SELECT':
            details += [law['name'] for law in stage.get('laws', [])]
        elif stage['stage'] in {'ASSESS', 'COMPOSE'}:
            details += list(dict.fromkeys(_flow_text(item['judgment']) for item in stage.get('data', []) if item.get('judgment')))
        nodes.append({'title': stage['label']+' · '+stage['status'],
                      'details': details, 'returned': False})
    return nodes, 'verified-judgment'


def _flow_graph(body, view, progress_events):
    """Entity/relationship view of existing records, without inferred law links."""
    import unicodedata
    def unique(values):
        seen, result = set(), []
        for value in values:
            text = ' '.join(unicodedata.normalize('NFC', str(value)).split())
            key = text.casefold()
            if text and key not in seen:
                seen.add(key); result.append(text)
        return result
    stages = {stage['stage']: stage for stage in view['stages']}
    nodes, edges = [], []
    def node(kind, title, details=()):
        key = 'G'+str(len(nodes)+1)
        nodes.append({'id': key, 'kind': kind, 'title': str(title), 'details': list(details)})
        return key
    def edge(left, right, label):
        edges.append({'from': left, 'to': right, 'label': label})
    issue = next((value for event in progress_events or []
                  if event.get('label', '').startswith('질문 이해')
                  for value in event.get('details', []) if isinstance(value, str)), None)
    question = node('question', issue or '현재 질문', stages['INTENT'].get('decisions', []) if not issue else [])
    queries = [str(value).removeprefix('검색어: ') for value in stages['PLAN'].get('decisions', [])]
    terms = []
    for event in progress_events or []:
        for detail in event.get('details', []):
            if detail.startswith('본문 검색에 사용한 단어: '):
                terms += detail.split(': ', 1)[1].split(' / ')
            elif detail.startswith('본문 검색어: '):
                queries.append(detail.split(': ', 1)[1])
    concepts = [str(value) for value in stages['INTENT'].get('concepts', []) if not str(value).startswith('system:')]
    terms, concepts, queries = unique(terms), unique(concepts), unique(queries)
    term_keys = {value.casefold() for value in terms}
    # Exact phrases remain in progress/PLAN details. Avoid repeating the same
    # words in concept cards, query cards and a second search-word list.
    search_details = ['검색 표현 '+str(len(queries))+'개'] if queries else []
    if not terms: search_details += queries
    numbers = [value for value in terms if value.isdigit()]
    if numbers: search_details.append('숫자 조건: '+' / '.join(numbers))
    search = node('search', '원문 본문 검색', search_details)
    # These are the recorded search words, not newly inferred legal concepts.
    # Keep numeric search operands in the search node's exact list.
    concept_rows = [{'concept': value, 'usage': '본문 검색' if value.casefold() in term_keys else '질문 검토'}
                    for value in unique(terms+concepts) if not value.isdigit()]
    if concept_rows:
        term = node('term', '검색 개념')
        nodes[-1]['rows'] = concept_rows
        edge(question, term, '검토한 개념')
        if any(row['usage']=='본문 검색' for row in concept_rows):
            edge(term, search, '검색에 사용')
    if not any(row['usage']=='본문 검색' for row in concept_rows):
        edge(question, search, '자료 탐색')
    law_ids = {}
    names = [law['name'] for law in stages['SELECT'].get('laws', [])]
    for event in progress_events or []:
        if event.get('basis', {}).get('kind') == 'LAW_FULLTEXT_DIRECTORY':
            names += event.get('details', [])
    selected = {item.get('source_id') for item in stages['SELECT'].get('data', []) if item.get('action') == '답변 근거 채택'}
    used = selected | {item.get('source_id') for stage in ('ASSESS', 'COMPOSE') for item in stages[stage].get('data', [])}
    originals = {item['source_id']: item for item in stages['READ'].get('data', [])
                 if item.get('source_id') and (not used or item['source_id'] in used)}
    names += [item['document_name'] for item in originals.values() if item.get('document_name')]
    for name in dict.fromkeys(names):
        law_ids[name] = node('law', name)
        edge(search, law_ids[name], '확인한 법령')
    source_ids = {}
    for source_id, item in originals.items():
        source_ids[source_id] = node('source', item.get('coordinate') or '확인한 원문',
                                     [item.get('document_name', ''), '답변 근거 채택' if source_id in selected else '열람한 원문'])
        if item.get('document_name') in law_ids: edge(law_ids[item['document_name']], source_ids[source_id], '포함하는 원문')
    claims = {}
    for item in stages['ASSESS'].get('data', []):
        if item.get('source_id') not in source_ids or not item.get('judgment'): continue
        key = (item['source_id'], item['judgment'])
        if key not in claims: claims[key] = node('claim', item['judgment'])
        edge(source_ids[item['source_id']], claims[key], '판단 근거')
    answer_text = _public_answer_text(body)
    answer = node('answer', answer_text or '현재 판단과 출처를 담은 답변')
    composed = {(item.get('source_id'), item.get('judgment')) for item in stages['COMPOSE'].get('data', [])}
    for claim, key in claims.items():
        if claim in composed: edge(key, answer, '답변에 반영')
    return nodes, edges


def _judgment_flow(body, progress_events=None):
    """Draw a provenance graph of verified entities, without process boxes."""
    import base64
    import math
    import unicodedata
    from html import escape
    started = time.perf_counter()
    view = _judgment_view(body)
    if not view: return None
    records, basis = _flow_nodes(view, progress_events)
    raw_nodes, raw_edges = _flow_graph(body, view, progress_events)
    nodes = [item for item in raw_nodes if item['kind'] in {'law', 'source', 'claim'}]
    if not nodes: return None
    ids = {item['id'] for item in nodes}
    edges = [edge for edge in raw_edges if edge['from'] in ids and edge['to'] in ids]
    lookup = {item['id']: item for item in nodes}
    adjacent = {item['id']: [] for item in nodes}
    for edge in edges:
        adjacent[edge['from']].append(edge['to']); adjacent[edge['to']].append(edge['from'])
    def clean(value):
        return ''.join(char for char in str(value) if ord(char) >= 32 and char not in '\ufffe\uffff')
    def units(value):
        return sum(2 if unicodedata.east_asian_width(char) in ('W','F') else 1 for char in value)
    def wrap(value, width=36):
        lines, remaining = [], clean(value).strip()
        while remaining:
            size, end = 0, 0
            for char in remaining:
                if size+units(char)>width: break
                size+=units(char); end+=1
            if end==len(remaining): lines.append(remaining); break
            # Prefer word boundaries so a Korean sentence ending is not left
            # alone on the next line. Long unspaced names still wrap losslessly.
            space=remaining.rfind(' ',0,end+1)
            split=space if space>=end//2 else max(1,end)
            lines.append(remaining[:split].rstrip()); remaining=remaining[split:].lstrip()
        return lines
    styles = {'law': ('법령', '#69e2cd', '#133c3f'),
              'source': ('원문', '#97baff', '#202f53'),
              'claim': ('판단', '#f2c38c', '#493326')}
    layout = {}
    for item in nodes:
        size = 14 if item['kind']=='claim' else 15
        lines = wrap(_flow_text(item['title']), 42 if item['kind']=='claim' else 30)
        width = max([units(line)*size/2 for line in lines]+[34])+12
        layout[item['id']] = {'x':0.0,'y':0.0,'radius':13,'lines':lines,'font':size,
                              'label_width':width,'label_height':20*len(lines)+14,'above':False}
    def bounds(card):
        half = max(card['radius']+4,card['label_width']/2)
        if card['above']:
            return (card['x']-half-8,card['y']-card['radius']-16-card['label_height'],
                    card['x']+half+8,card['y']+card['radius']+12)
        return (card['x']-half-8,card['y']-card['radius']-12,
                card['x']+half+8,card['y']+card['radius']+18+card['label_height'])
    components, seen = [], set()
    for item in nodes:
        if item['id'] in seen: continue
        queue, component = [item['id']], []
        seen.add(item['id'])
        for key in queue:
            component.append(key)
            for other in adjacent[key]:
                if other not in seen: seen.add(other); queue.append(other)
        components.append(component)
    # Keep each law's evidence together. The old depth rings reused the same
    # angle for a source and its claim, producing a straight diagonal chain.
    # Small components now open into a triangle or a pair of evidence branches;
    # larger components fan out by parent, rather than by execution stage.
    shelf_x, shelf_y, shelf_height, rightmost = 32, 28, 0, 0
    for component in components:
        roots=[key for key in component if lookup[key]['kind']=='law']
        hub=max(roots or component,key=lambda key:len(adjacent[key]))
        layout[hub].update(radius=20 if len(component)>1 else 15,above=True,y=-48)
        depth, parent, queue = {hub:0}, {}, [hub]
        for key in queue:
            for other in adjacent[key]:
                if other not in depth:
                    depth[other]=depth[key]+1; parent[other]=key; queue.append(other)
        branches=[key for key in component if parent.get(key)==hub]
        angles={hub:0.0}
        for index,key in enumerate(branches):
            if len(branches)==1:
                layout[key].update(x=-145,y=58); angles[key]=2.51
            elif len(branches)==2:
                sign=-1 if index==0 else 1
                layout[key].update(x=sign*175,y=8); angles[key]=math.atan2(56,sign*175)
            else:
                angle=-math.pi/2+2*math.pi*index/len(branches)
                radius=max(185,sum(layout[value]['label_width']+35 for value in branches)/(2*math.pi))
                layout[key].update(x=radius*math.cos(angle),y=radius*math.sin(angle)); angles[key]=angle
        for key in queue[1:]:
            children=[other for other in adjacent[key] if parent.get(other)==key]
            for index,child in enumerate(children):
                if key in branches and len(branches)==1 and len(children)==1:
                    layout[child].update(x=145,y=58); angles[child]=0.63
                elif key in branches and len(branches)<=2:
                    sign=-1 if layout[key]['x']<0 else 1
                    layout[child].update(x=layout[key]['x']+sign*15+(index-(len(children)-1)/2)*325,
                                         y=layout[key]['y']+110)
                    angles[child]=angles[key]
                else:
                    angle=angles[key]+0.45+(index-(len(children)-1)/2)*0.75
                    radius=max(140,layout[child]['label_width']/2+55)
                    layout[child].update(x=layout[key]['x']+radius*math.cos(angle),
                                         y=layout[key]['y']+radius*math.sin(angle))
                    angles[child]=angle
        # Separate labels as well as circles. Never omit long names or claims.
        for _ in range(min(32,max(4,1200//len(component)))):
            moved = False
            for index,key in enumerate(component):
                left = layout[key]
                for other in component[index+1:]:
                    right = layout[other]; a,b = bounds(left),bounds(right)
                    dx = min(a[2],b[2])-max(a[0],b[0])+10
                    dy = min(a[3],b[3])-max(a[1],b[1])+10
                    if dx<=0 or dy<=0: continue
                    moved=True
                    if dx<dy:
                        shift=(dx/2+1)*(1 if right['x']>=left['x'] else -1)
                        left['x']-=shift; right['x']+=shift
                    else:
                        shift=(dy/2+1)*(1 if (b[1]+b[3])>=(a[1]+a[3]) else -1)
                        left['y']-=shift; right['y']+=shift
            if not moved: break
        boxes = [bounds(layout[key]) for key in component]
        for key in component:
            layout[key]['side']=-1 if layout[key]['x']<layout[hub]['x'] else 1
            other=parent.get(key)
            if not other or lookup[other]['kind']!='source':continue
            left,right=layout[other],layout[key]
            if abs(right['x']-left['x'])<80 and right['y']>left['y']:
                # Curved links and their captions also need canvas space when
                # the judgment itself is short, such as "승인 필요".
                side=-1 if left['x']<layout[hub]['x'] else 1
                x=min(left['x'],right['x'])-100 if side<0 else max(left['x'],right['x'])+100
                boxes.append((x,left['y'],x,right['y']))
        xmin,ymin = min(box[0] for box in boxes),min(box[1] for box in boxes)
        width = max(box[2] for box in boxes)-xmin
        height = max(box[3] for box in boxes)-ymin
        if shelf_x>32 and shelf_x+width>900:
            shelf_x=32; shelf_y+=shelf_height+40; shelf_height=0
        for key in component:
            layout[key]['x']+=shelf_x-xmin; layout[key]['y']+=shelf_y-ymin
        rightmost=max(rightmost,shelf_x+width); shelf_x+=width+44
        shelf_height=max(shelf_height,height)
    graph_bottom=shelf_y+shelf_height
    width=max(540,math.ceil(rightmost+32))
    annotations=[]
    concept = next((item for item in raw_nodes if item['kind']=='term'),None)
    if concept:
        grouped={}
        for row in concept['rows']: grouped.setdefault(row['usage'],[]).append(row['concept'])
        for usage,values in grouped.items():
            annotations.append({'usage':usage,'lines':wrap(' · '.join(values),int((width-164)/7.5))})
    search=next((item for item in raw_nodes if item['kind']=='search'),None)
    if search and search['details']:
        annotations.append({'usage':'검색 조건','lines':wrap(' · '.join(search['details']),int((width-164)/7.5))})
    annotation_top=graph_bottom+24
    height=math.ceil(annotation_top+sum(max(26,len(row['lines'])*19+7) for row in annotations)+22)
    parts=['<svg xmlns="http://www.w3.org/2000/svg" width="'+str(width)+'" height="'+str(height)+'" viewBox="0 0 '+str(width)+' '+str(height)+'" role="img" aria-labelledby="graph-title graph-desc" font-family="Malgun Gothic,Apple SD Gothic Neo,Noto Sans KR,sans-serif">',
           '<title id="graph-title">법령과 원문 근거의 관계 그래프</title>',
           '<desc id="graph-desc">원형 노드는 법령·원문·판단이며 선은 확인된 포함·근거 관계입니다. 검색 개념은 아래 속성으로 표시합니다.</desc>',
           '<defs>',
           '<linearGradient id="canvas" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#162334"/><stop offset="1" stop-color="#0c1421"/></linearGradient>',
           '<pattern id="grid" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="11" cy="11" r="0.7" fill="#6f8da8" opacity="0.16"/></pattern>']
    for kind, (_, color, deep) in styles.items():
        parts += ['<radialGradient id="halo-'+kind+'"><stop stop-color="'+color+'" stop-opacity="0.15"/><stop offset="1" stop-color="'+color+'" stop-opacity="0"/></radialGradient>',
                  '<linearGradient id="node-'+kind+'" x1="0" y1="0" x2="1" y2="1"><stop stop-color="'+deep+'"/><stop offset="1" stop-color="#142031"/></linearGradient>']
    for index, edge in enumerate(edges):
        left, right = layout[edge['from']], layout[edge['to']]
        start, end = styles[lookup[edge['from']]['kind']][1], styles[lookup[edge['to']]['kind']][1]
        parts.append('<linearGradient id="relation-'+str(index)+'" gradientUnits="userSpaceOnUse" x1="'+str(left['x'])+'" y1="'+str(left['y'])+'" x2="'+str(right['x'])+'" y2="'+str(right['y'])+'"><stop stop-color="'+start+'"/><stop offset="1" stop-color="'+end+'"/></linearGradient>')
    parts += ['</defs>',
              '<rect data-canvas="true" x="0.5" y="0.5" width="'+str(width-1)+'" height="'+str(height-1)+'" rx="18" fill="url(#canvas)" stroke="#2a3b4f"/>',
              '<rect data-canvas="true" x="8" y="8" width="'+str(width-16)+'" height="'+str(height-16)+'" rx="12" fill="url(#grid)"/>']
    # Halos sit behind the relationships. They add depth without hiding text,
    # adding entities, or requiring filters, CSS, scripts or remote assets.
    for item in nodes:
        card = layout[item['id']]
        parts.append('<circle cx="'+str(card['x'])+'" cy="'+str(card['y'])+'" r="'+str(card['radius']+15)+'" fill="url(#halo-'+item['kind']+')"/>')
    relation_labels=set()
    for index, edge in enumerate(edges):
        left,right=layout[edge['from']],layout[edge['to']]
        dx,dy=right['x']-left['x'],right['y']-left['y']
        distance=max(1,math.hypot(dx,dy)); ux,uy=dx/distance,dy/distance
        x1,y1=left['x']+ux*(left['radius']+3),left['y']+uy*(left['radius']+3)
        x2,y2=right['x']-ux*(right['radius']+5),right['y']-uy*(right['radius']+5)
        if lookup[edge['from']]['kind']=='source' and abs(dx)<80 and dy>0:
            # Route beside the source label, then turn into the claim circle.
            sign=left['side']
            x1,y1=left['x']+sign*(left['radius']+4),left['y']
            x2,y2=right['x']+sign*(right['radius']+5),right['y']
            c1x,c1y=x1+sign*52,y1+22
            c2x,c2y=x2+sign*52,y2-22
        else:
            bend=25 if lookup[edge['from']]['kind']=='law' else -38
            sign=-1 if dx<0 else 1
            c1x,c1y=x1+(x2-x1)*0.35-uy*bend*sign,y1+(y2-y1)*0.35+ux*bend*sign
            c2x,c2y=x1+(x2-x1)*0.65-uy*bend*sign,y1+(y2-y1)*0.65+ux*bend*sign
        tx,ty=x2-c2x,y2-c2y; tangent=max(1,math.hypot(tx,ty)); tx,ty=tx/tangent,ty/tangent
        ax,ay=x2-tx*6,y2-ty*6
        arrow='M'+str(ax-ty*2.6)+' '+str(ay+tx*2.6)+' L'+str(x2)+' '+str(y2)+' L'+str(ax+ty*2.6)+' '+str(ay-tx*2.6)
        curve='M'+str(x1)+' '+str(y1)+' C'+str(c1x)+' '+str(c1y)+' '+str(c2x)+' '+str(c2y)+' '+str(x2)+' '+str(y2)
        stroke='url(#relation-'+str(index)+')'
        parts+=['<g data-relation="'+escape(edge['label'])+'" data-from="'+edge['from']+'" data-to="'+edge['to']+'">',
                '<path d="'+curve+'" stroke="'+stroke+'" stroke-width="7" opacity="0.06" fill="none"/>',
                '<path d="'+curve+'" stroke="'+stroke+'" stroke-width="1.5" opacity="0.7" stroke-linecap="round" fill="none"/>',
                '<path d="'+arrow+'" stroke="'+styles[lookup[edge['to']]['kind']][1]+'" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>']
        pair=(lookup[edge['from']]['kind'],lookup[edge['to']]['kind'],edge['label'])
        if pair not in relation_labels:
            relation_labels.add(pair)
            lx,ly=(x1+3*c1x+3*c2x+x2)/8,(y1+3*c1y+3*c2y+y2)/8-7
            label='포함' if edge['label']=='포함하는 원문' else edge['label']
            parts.append('<text x="'+str(lx)+'" y="'+str(ly)+'" text-anchor="middle" font-size="11" fill="#b2c3d5" stroke="#111c2a" stroke-width="5" stroke-linejoin="round" paint-order="stroke">'+escape(label)+'</text>')
        parts.append('</g>')
    for item in nodes:
        card=layout[item['id']]; label,color,_=styles[item['kind']]
        x,y=round(card['x'],3),round(card['y'],3)
        parts+=['<g data-entity="'+item['kind']+'" data-entity-id="'+item['id']+'">',
                '<title>'+escape(clean(item['title']))+'</title>',
                '<circle cx="'+str(x)+'" cy="'+str(y)+'" r="'+str(card['radius'])+'" fill="url(#node-'+item['kind']+')" stroke="'+color+'" stroke-opacity="0.65" stroke-width="1.2"/>']
        ring=card['radius']+6
        parts.append('<path d="M'+str(x-ring)+' '+str(y)+' a'+str(ring)+' '+str(ring)+' 0 1 0 '+str(2*ring)+' 0 a'+str(ring)+' '+str(ring)+' 0 1 0 '+str(-2*ring)+' 0" fill="none" stroke="'+color+'" stroke-opacity="0.16"/>')
        glyph={
            'law':'M-8 -7 Q-4 -9 0 -6 Q4 -9 8 -7 V7 Q4 5 0 8 Q-4 5 -8 7 Z M0 -6 V8',
            'source':'M-5 -7 H2 L6 -3 V7 H-5 Z M2 -7 V-3 H6 M-2 0 H3 M-2 3 H3',
            'claim':'M-5 -5 H-1 V0 H-5 Z M2 -5 H6 V0 H2 Z M-1 0 Q-1 4 -5 5 M6 0 Q6 4 2 5',
        }[item['kind']]
        parts.append('<path transform="translate('+str(x)+' '+str(y)+')" d="'+glyph+'" fill="none" stroke="'+color+'" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>')
        ty=y-card['radius']-12-card['label_height']+card['font'] if card['above'] else y+card['radius']+22
        for line in card['lines']:
            parts.append('<text x="'+str(x)+'" y="'+str(ty)+'" text-anchor="middle" font-size="'+str(card['font'])+'" font-weight="'+('700' if item['kind']=='law' else '600' if item['kind']=='source' else '400')+'" fill="'+('#eff6ff' if item['kind']!='claim' else '#d8e3ef')+'">'+escape(line)+'</text>'); ty+=20
        parts+=['<text x="'+str(x)+'" y="'+str(ty-2)+'" text-anchor="middle" font-size="10" fill="'+color+'" opacity="0.8">'+label+'</text>','</g>']
    if annotations:
        parts.append('<path d="M28 '+str(annotation_top-10)+' H'+str(width-28)+'" stroke="#2b3b4c"/>')
        for row in annotations:
            attribute='data-search-condition' if row['usage']=='검색 조건' else 'data-concept-row'
            parts.append('<g '+attribute+'="true" data-usage="'+escape(row['usage'])+'">')
            parts.append('<text x="28" y="'+str(annotation_top+15)+'" font-size="11" fill="#8fa6bb">'+escape(row['usage'])+'</text>')
            for index,line in enumerate(row['lines']):
                parts.append('<text x="128" y="'+str(annotation_top+15+index*19)+'" font-size="12" fill="#c1d0df">'+escape(line)+'</text>')
            parts.append('</g>'); annotation_top+=max(26,len(row['lines'])*19+7)
    parts.append('</svg>')
    svg='\n'.join(parts); encoded=svg.encode('utf-8')
    image_src='data:image/svg+xml;base64,'+base64.b64encode(encoded).decode('ascii')
    html='<img src="'+image_src+'" alt="법령·원문·판단의 근거 관계 그래프" style="display:block;max-width:100%;height:auto;border-radius:18px;margin-top:12px;"/>'
    return {'svg':svg,'html':html,'metadata':{
        'format':'svg','mime_type':'image/svg+xml','renderer_revision':JUDGMENT_DISPLAY_REVISION,
        'content_sha256':hashlib.sha256(encoded).hexdigest(),'bytes':len(encoded),
        'node_count':len(records),'return_count':sum(node['returned'] for node in records),
        'entity_count':len(nodes),'relation_count':len(edges),'record_entity_count':len(raw_nodes),
        'layout':'law-centered-evidence-clusters','execution_trace_visible':False,'process_nodes_visible':False,
        'theme':'graphite-evidence','external_assets':False,
        'concept_table_grouped_by_usage':True,'answer_body_repeated':False,
        'basis':basis,'judgment_sha256':view['content_sha256'],
        'render_ms':round((time.perf_counter()-started)*1000,3)}}



def _judgment_html(body):
    from html import escape
    view = _judgment_view(body)
    if not view:
        return ''
    def e(value): return escape(str(value), quote=True)
    def reason(value):
        text = str(value or '').strip()
        return '' if text in {'없음','이유 없음','이유가 없음','별도 이유 없음',
                             '모델이 별도 이유를 제공하지 않음','N/A','null','None'} else text
    def paragraphs(title, values):
        if not values: return ''
        if title in {'수행한 행위', '판단 내용'}:
            values = [_flow_text(value) for value in values]
        return '<p><strong>' + title + '</strong></p><ul>' + ''.join(
            '<li>' + e(value) + '</li>' for value in values) + '</ul>'
    border = 'border:1px solid #dbe3ed;border-radius:12px;padding:12px;margin:10px 0;'
    rows = ['<!-- GENOS_JUDGMENT_VIEW_START -->', '<details style="' + border + '">',
            '<summary><strong>AI 판단 과정 보기 · 7단계</strong></summary>', '',
            '<p>현재 질문의 판단 기록입니다. 단계 번호를 지정해 수정 방향을 알려 주세요.</p>']
    for stage in view['stages']:
        rows += ['<details style="' + border + '">',
                 '<summary><strong>' + e(stage['id']) + '. ' + e(stage['label']) + '</strong> · ' + e(stage['status']) + '</summary>', '',
                 paragraphs('수행한 행위', stage.get('actions', [])),
                 paragraphs('판단 내용', stage.get('decisions', [])),
                 paragraphs('검색 개념', stage.get('concepts', [])),
                 paragraphs('검색 대상 문서', stage.get('documents', []))]
        if stage.get('processing'): rows.append('<p>처리 방식: ' + e(stage['processing']) + '</p>')
        facts = stage.get('facts', [])
        if facts:
            rows.append(paragraphs('사용자가 제공한 현재 조건', [
                (str(f.get('name', '')) + ': ' + str(f.get('value', ''))) if isinstance(f, dict) else str(f) for f in facts]))
        if reason(stage.get('reason')):
            rows.append('<p>판단 이유: ' + e(reason(stage['reason'])) + '</p>')
        for law in stage.get('laws', []):
            selection = law.get('selection') or {}
            rows += ['<details style="'+border+'"><summary>'+e(law['name'])+' · 법령별 조사</summary>',
                     '<p>선택 이유: '+e(selection.get('reason') or '미선택')+'</p>',
                     paragraphs('조사한 원문 묶음', [' / '.join(b.get('matched_coordinates', []))+' · '+b['status']+
                        (' · '+b['reason'] if b.get('reason') else '') for b in law.get('branches', [])]), '</details>']
        chain = stage.get('investigation_chain', {})
        judgments = {j['id']: j for j in chain.get('judgments', [])}
        if chain.get('steps'):
            rows.append('<details style="'+border+'"><summary>조사 행동과 선택 이유 · '+str(len(chain['steps']))+'건</summary>')
            for step in chain['steps']:
                rows += ['<details style="'+border+'"><summary>'+e(step['number'])+'. '+e(_flow_text(step['action']))+' · '+e(_flow_text(step['status']))+'</summary>',
                         '<p>'+e(step.get('reason',''))+'</p>',
                         paragraphs('검색 표현',step.get('queries',[]))]
                fields = step.get('structure_filter') or {}
                rows.append(paragraphs('구조 조회 조건', [
                    {'coordinate':'조문 번호','title':'제목','coordinate_scope':'문서 분기'}[key]+': '+str(fields[key])
                    for key in ('coordinate','title','coordinate_scope') if fields.get(key)]))
                lookup = step.get('structure_lookup') or {}
                if lookup:
                    rows.append('<p>구조 조회 결과: '+e(lookup.get('lookup_status',''))+' · 후보 '+e(lookup.get('total',0))+'개</p>')
                    failure = lookup.get('failure') or {}
                    if failure:
                        rows += ['<p>'+e(failure.get('code',''))+' · '+e(failure.get('message',''))+'</p>',
                                 '<p>다음 탐색: '+e(failure.get('suggested_action',''))+'</p>']
                if step.get('structure_path'):
                    rows.append(paragraphs('현재 구조 위치', [
                        ' → '.join(str(n.get('coordinate') or n.get('surface') or n.get('title') or n.get('unit_id',''))
                                   for n in step['structure_path'])]))
                for target in step.get('targets',[]):
                    rows.append('<p>대상: '+e(target.get('label') or target.get('action') or target.get('id',''))+'</p>')
                decisions = [judgments[j]['decision'] for j in step.get('judgment_refs',[]) if j in judgments]
                decisions += step.get('law_decisions',[])+step.get('branch_decisions',[])+step.get('reference_decisions',[])
                for decision in decisions:
                    rows.append('<p>'+e(_flow_text(decision.get('status') or decision.get('action','')))+' · '+e(decision.get('reason',''))+'</p>')
                if step.get('notes'): rows.append('<p>'+e(step['notes'])+'</p>')
                rows.append('</details>')
            rows.append('</details>')
        rows.append(paragraphs('반복 탐색 전환', [
            str(r.get('document_name',''))+' · '+str(r.get('reason',''))+' · '+str(r.get('next_step',''))
            for r in stage.get('structure_recovery',[])]))
        inventory = stage.get('source_inventory',[])
        for item in inventory:
            receipt = item.get('receipt',{})
            rows += ['<details style="'+border+'"><summary>'+e(item.get('path',''))+' · '+e(item.get('status',''))+'</summary>',
                     '<p>확보 완료: '+e(receipt.get('acquired_complete'))+' · 전달 완료: '+e(receipt.get('delivered_complete'))+'</p>',
                     '<p>전달한 페이지: '+e(receipt.get('delivered_pages_count',0))+' / '+e(receipt.get('pages_total',0))+'</p>',
                     '<p>'+e(item.get('reason',''))+'</p>','</details>']
        if stage.get('issue_assessments'):
            rows.append(paragraphs('질문의 요구별 확인 상태',[
                r['issue_id']+' · '+r['status']+' · '+r['reason'] for r in stage['issue_assessments']]))
            rows.append(paragraphs('남은 확인 범위',[g['reason'] for g in stage.get('gaps',[])]))
        data = stage.get('data', [])
        if data:
            rows += ['<details style="' + border + '">',
                     '<summary>사용한 데이터와 행위 · ' + str(len(data)) + '건</summary>', '']
            for item in data:
                rows += ['<details style="' + border + '">',
                         '<summary>' + e(item['document_name']) + ' · ' + e(item['coordinate']) + ' · ' + e(item['action']) + '</summary>', '',
                         '<p>행위: ' + e(item['action']) + '</p>']
                if item.get('judgment'): rows.append('<p>판단: ' + e(item['judgment']) + '</p>')
                if reason(item.get('reason')): rows.append('<p>선택 이유: ' + e(reason(item['reason'])) + '</p>')
                if item.get('quote'): rows.append('<blockquote>' + e(item['quote']) + '</blockquote>')
                rows += ['</details>', '']
            rows += ['</details>', '']
        rows += [paragraphs('추가 확인할 사항', stage.get('limitations', [])),
                 '<p>수정 요청 예: “' + e(stage['id']) + '번 단계에서 이 부분을 다시 확인해 주세요.”</p>', '</details>', '']
    rows += ['</details>', '<!-- GENOS_JUDGMENT_VIEW_END -->']
    return '\n'.join(rows)


def _judgment_graph_html(flow):
    if not flow: return ''
    return '\n'.join(['<!-- GENOS_JUDGMENT_GRAPH_START -->',
                      '<details style="border:1px solid #dbe3ed;border-radius:16px;padding:14px 16px;margin:14px 0;">',
                      '<summary style="cursor:pointer;"><strong>개념·법령 관계 그래프 보기</strong></summary>', '',
                      flow['html'], '', '</details>', '<!-- GENOS_JUDGMENT_GRAPH_END -->'])


def _completion_answer_status(body, answered):
    agent = (body.get('assembly') or {}).get('term_agent') or {}
    if answered:
        return 'partial' if agent.get('completion_contract') and agent.get('answer_coverage') in ('PARTIAL','INSUFFICIENT') else 'answered'
    if body.get('code') == 'SOURCE_INVESTIGATION_INCOMPLETE': return 'incomplete'
    if body.get('code') == 'MODEL_UPSTREAM_UNAVAILABLE': return 'unavailable'
    if isinstance(body.get('_gateway_status'), int) and body['_gateway_status'] >= 400: return 'failed'
    return 'incomplete' if _has_found_source(body) else 'not_found'


def render_error(body, *, question=''):
    """Display the complete received error, including nested causes and traceback."""
    def scrub(value):
        if isinstance(value,dict):
            return {k:('[REDACTED]' if re.search(r'authorization|api[_-]?key|(?:^|_)token$|password|secret|cookie|signature',str(k),re.I)
                       else scrub(v)) for k,v in value.items()}
        if isinstance(value,list):return [scrub(v) for v in value]
        if isinstance(value,str):return _redact_http_error(value,question)
        return value
    safe=scrub(body)
    detail=json.dumps(safe,ensure_ascii=False,indent=2,default=str)
    fence='`'*max(3,1+max((len(m.group()) for m in re.finditer(r'`+',detail)),default=0))
    return '실행 오류 ('+str(safe.get('code') or safe.get('error_type') or 'HTTP '+str(safe.get('_gateway_status')))+') · 전체 오류 로그\n\n'+fence+'json\n'+detail+'\n'+fence


def render(body, *, flow=None):
    if body.get('response_schema')=='ad-mode-v1':return _ad_result(body)['text']
    status = body.get("_gateway_status")
    if isinstance(status, int) and status >= 400:
        return render_error(body)
    answer = _public_answer_text(body)
    source_text = _sources(body)
    if not answer and source_text:
        return "관련 원문은 찾았지만 답변을 완성하지 못했습니다.\n\n"+source_text
    if not answer:
        if _has_found_source(body):
            return "관련 원문은 찾았지만 답변 검토를 완료하지 못했습니다."
        return "관련 근거를 찾지 못해 답변을 만들지 못했습니다. 질문을 조금 더 구체적으로 입력해 주세요."
    text = answer
    graph = _judgment_graph_html(flow or _judgment_flow(body))
    if graph: text += '\n\n'+graph
    if source_text: text += '\n\n'+source_text
    judgments = _judgment_html(body)
    if judgments: text += '\n\n' + judgments
    return text


def _for_markdown(text):
    # Keep code fences and the generated nested HTML intact. In particular,
    # changing the generated image or nested toggle markup breaks rendering.
    pieces = re.split(r'(<!-- GENOS_JUDGMENT_GRAPH_START -->.*?<!-- GENOS_JUDGMENT_GRAPH_END -->|<!-- GENOS_JUDGMENT_VIEW_START -->.*?<!-- GENOS_JUDGMENT_VIEW_END -->|```[^\n]*\n.*?(?:\n```|$))', text, flags=re.S)
    return ''.join(piece if i % 2 else re.sub(r"(?<!\n)\n(?!\n)", "\n\n", re.sub(r"~", r"\\~", piece))
                   for i, piece in enumerate(pieces))


def _workflow_display_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), default=str).encode('utf-8')).hexdigest()


async def workflow_display_result(body, events, *, request_id):
    """Render the current backend response with the shared SVG/progress views."""
    display = _ChatProgress({})
    display.enabled = False
    display.show_progress = os.environ.get('GENOS_RAG_PROGRESS_UI', 'on').lower() != 'off'
    for event in events:
        await display.progress(event)
    flow = _judgment_flow(body, display.flow_events)
    answered = bool(_public_answer_text(body)) and not (
        isinstance(body.get('_gateway_status'), int) and body['_gateway_status'] >= 400)
    result = {
        'schema_version': 'genos-workflow-display-v1', 'producer': 'main_workflow',
        'request_id': request_id,
        'response_sha256': _workflow_display_digest({k: v for k, v in body.items() if k != 'workflow_display'}),
        'text': _for_markdown(render(body, flow=flow)),
        'answer_status': _completion_answer_status(body, answered),
        'judgment_display_revision': JUDGMENT_DISPLAY_REVISION,
        'progress_display_revision': PROGRESS_DISPLAY_REVISION,
    }
    if flow:
        result['judgment_flow'] = flow['metadata']
    if display.blocks:
        result['agentFlowExecutedData'] = display.blocks
    result['content_sha256'] = _workflow_display_digest(result)
    return result


def _bound_workflow_display(body, request_id):
    """Reuse only this request's complete display from a matching backend."""
    value = body.get('workflow_display')
    if not isinstance(value, dict):
        return None
    if (value.get('schema_version') != 'genos-workflow-display-v1'
            or value.get('producer') != 'main_workflow'
            or value.get('request_id') != request_id
            or value.get('judgment_display_revision') != JUDGMENT_DISPLAY_REVISION
            or value.get('progress_display_revision') != PROGRESS_DISPLAY_REVISION
            or not isinstance(value.get('text'), str)):
        return None
    if value.get('response_sha256') != _workflow_display_digest({k: v for k, v in body.items() if k != 'workflow_display'}):
        return None
    if value.get('content_sha256') != _workflow_display_digest({k: v for k, v in value.items() if k != 'content_sha256'}):
        return None
    return value


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
            if probe.get('response_schema')=='ad-mode-v1':return {**_ad_result(probe),'request_id':request_id}
        except Exception as exc:
            # Cannot establish the mode: do not risk sending an admin turn to RAG.
            if _SYSTEM_LOGS is not None:
                if isinstance(exc, urllib.error.HTTPError):
                    _raw_http_error(exc, request_id)
                else:
                    _SYSTEM_LOGS.write("workflow.errors.raw.log", (
                        "request_id=" + request_id + " AD_PROBE\n" + traceback.format_exc()).encode("utf-8"))
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
    display.show_progress = os.environ.get('GENOS_RAG_PROGRESS_UI', 'on').lower() != 'off'
    try:
        body = await _stream_code_serving(question, data, display)
        call_seconds = time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        raw_error = _raw_http_error(exc, request_id)
        detail = raw_error.decode("utf-8", "replace")
        error_diagnostics = _http_error_diagnostics(exc, raw_error, question)
        try:
            failure = unwrap(json.loads(detail))
        except ValueError:
            failure = {'error_type':type(exc).__name__,'detail':detail}
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
            "text": render_error({**failure,'_gateway_status':exc.code,'request_id':request_id},question=question),
            "answer_status": "incomplete" if failure.get("code")=="SOURCE_INVESTIGATION_INCOMPLETE" else "unavailable" if failure.get("code")=="MODEL_UPSTREAM_UNAVAILABLE" else "failed",
            "failure_kind": "http_error",
            "http_status": exc.code,
            "http_error_diagnostics": error_diagnostics,
            "code_serving_transport": dict(display.transport),
            "workflow_revision": WORKFLOW_REVISION,
            "tm_total": round(time.perf_counter() - started, 3),
            "session_id": session_id,
            "request_id": request_id,
        }
        # The complete received HTTP error has already been rendered above.
        await display.finish(failed["text"])
        if display.blocks:
            failed["agentFlowExecutedData"] = display.blocks
        return failed
    except Exception as exc:  # 채팅 단계 밖으로 예외를 내보내지 않는다.
        if _SYSTEM_LOGS is not None:
            _SYSTEM_LOGS.write("workflow.errors.raw.log", (
                "request_id=" + request_id + "\n" + traceback.format_exc()).encode("utf-8"))
        _log_event(
            "workflow.request.crashed",
            level="ERROR",
            request_id=request_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
            traceback=traceback.format_exc(),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        failed = {
            "text": render_error({'request_id':request_id,'error_type':type(exc).__name__,
                'detail':str(exc),'traceback':traceback.format_exc()},question=question),
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

    server_display = _bound_workflow_display(body, request_id)
    flow = None if server_display else _judgment_flow(body, display.flow_events)
    text = (server_display['text'] if server_display else
            render(body) if body.get('response_schema')=='ad-mode-v1' else _for_markdown(render(body, flow=flow)))
    answered = bool(_public_answer_text(body)) and not (
        isinstance(body.get("_gateway_status"), int) and body["_gateway_status"] >= 400
    )
    result = {
        "text": text,
        "answer_status": _completion_answer_status(body, answered),
        "run_id": body.get("run_id"),
        "session_id": session_id,
        "request_id": request_id,
        "history": "not_persisted",
        "workflow_revision": WORKFLOW_REVISION,
        "answer_display_revision": ANSWER_DISPLAY_REVISION,
        "judgment_display_revision": JUDGMENT_DISPLAY_REVISION,
        "progress_display_revision": PROGRESS_DISPLAY_REVISION,
        "code_serving_transport": dict(display.transport),
        "tm_code_serving": round(call_seconds, 3),
        "tm_total": round(time.perf_counter() - started, 3),
    }
    if flow:
        result['judgment_flow'] = flow['metadata']
    if server_display:
        if 'judgment_flow' in server_display:
            result['judgment_flow'] = server_display['judgment_flow']
        result['workflow_display_binding'] = {k: server_display[k] for k in (
            'schema_version', 'producer', 'response_sha256', 'content_sha256')}
    await display.finish(text)
    if display.blocks:
        result["agentFlowExecutedData"] = display.blocks
    if server_display and display.show_progress and server_display.get('agentFlowExecutedData'):
        result['agentFlowExecutedData'] = server_display['agentFlowExecutedData']
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
