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


WORKFLOW_REVISION = "rag-applied-mode-20261027-r1"
LIVE_PROGRESS_REVISION = "workflow-parent-progress-20261019-r1"
PROGRESS_DISPLAY_REVISION = "rag-live-judgment-cards-20261105-r1"
ANSWER_DISPLAY_REVISION = "workflow-guided-unread-20261106-r1"
JUDGMENT_DISPLAY_REVISION = "judgment-evidence-svg-20261008-r10"
HTTP_ERROR_DIAGNOSTICS_REVISION = "http-error-origin-20260928-r1"
QUESTION_KEYS = ("question", "query", "chatInput", "input", "message", "prompt", "text")
META_KEYS = frozenset(
    {
        "team_id",
        "TEAM_ID",
        "scope",
        "document_ids",
        "use_llm",
        "API_TYPE", "workflow_id", "input", "basis_review", "view_id", "rows",
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
        "overrideConfig", "applied_fields",
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
    value=data.get("chatId") or data.get("chat_id") or data.get("sessionId") or data.get("session_id")
    if value is None:return 'sess-anonymous'
    if (not isinstance(value,str) or not value.strip() or len(value)>256
            or value in ('anonymous','sess-anonymous') or any(ord(c)<32 for c in value)):
        raise ValueError('안정적인 대화 세션 식별자가 필요합니다.')
    # Preserve exact IDs: sanitizing/truncating merges distinct chat sessions.
    return value


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


def _progress_mode():
    mode = os.getenv('GENOS_RAG_PROGRESS_UI', 'socketio').strip().lower()
    # Existing editor settings keep live cards; status prose stays in the panel.
    return 'socketio' if mode in {'on', 'socketio-inline'} else mode


def _workflow_settings(data):
    """Inspect the deployed workflow without HTTP, model calls, or secret output."""
    _, _, timeout = _settings()
    mode = _progress_mode()
    settings = {
        "workflow_revision": WORKFLOW_REVISION,
        "progress_display_revision": PROGRESS_DISPLAY_REVISION,
        "judgment_display_revision": JUDGMENT_DISPLAY_REVISION,
        "http_error_diagnostics_revision": HTTP_ERROR_DIAGNOSTICS_REVISION,
        "json_socket_timeout_seconds": timeout,
        "stream_socket_timeout_seconds": timeout,
        "progress_mode": mode,
        "socketio_enabled": mode in {'socketio', 'socketio-inline', 'socketio-final'},
        "socket_client_id_present": bool(data.get('socketIOClientId')),
        "live_progress_channel": 'workflow-main_socketio',
        "live_progress_revision": LIVE_PROGRESS_REVISION,
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
            return public_failure(status=502)
    if not isinstance(payload, dict):
        return public_failure(status=502)

    # service.py의 정상 응답은 {status, body}, 다른 GENOS 리비전은 {code, data}다.
    for key in ("body", "data", "result"):
        if key in payload and not isinstance(payload[key], (dict, str)):
            return public_failure(payload.get("request_id"), status=502)
        if key in payload and isinstance(payload[key], (dict, str)):
            inner = unwrap(payload[key])
            if inner:
                if "_gateway_status" not in inner and isinstance(payload.get("status"), int):
                    inner["_gateway_status"] = payload["status"]
                return inner
    result = dict(payload)
    if type(payload.get("status")) is int and payload["status"] >= 400:
        result["_gateway_status"] = payload["status"]
    return result


class QueryModeError(ValueError):
    """A visible form error; the caller can correct it without a model retry."""


_MODE_LABELS = {
    "전체 법령": "전체 법령", "전체": "전체 법령", "all": "전체 법령",
    "내규": "내규", "internal": "내규",
    "외규": "외규", "external": "외규",
    "대사": "대사", "compare": "대사",
    "문서 대사": "문서 대사", "document_compare": "문서 대사",
}
_MODE_PREFIX = re.compile(r"^\s*(전체 법령|전체|내규|외규|문서 대사|대사)\s*[:,：，]\s*")


def _selected_question(question, data):
    """Translate a form choice to the existing explicit source/workflow contract.

    No legal interpretation or new scope grant: team and document authorization
    remain with the RAG/workflow consumer. The caller's payload is never edited.
    """
    fields = data.get("applied_fields")
    if fields is None:
        return question
    if not isinstance(fields, dict):
        raise QueryModeError("조회 방식 입력 형식이 잘못되었습니다. 선택 항목을 다시 확인해 주세요.")
    value = fields.get("mode")
    if value is None or isinstance(value, str) and not value.strip():
        return question
    if not isinstance(value, str) or value.strip() not in _MODE_LABELS:
        raise QueryModeError("조회 방식은 전체 법령, 내규, 외규, 대사, 문서 대사 중에서 선택해 주세요.")
    label = _MODE_LABELS[value.strip()]
    match = _MODE_PREFIX.match(question)
    if match:
        if _MODE_LABELS[match.group(1)] != label:
            raise QueryModeError("선택한 조회 방식과 질문 앞의 조회 구분이 다릅니다. 둘을 맞춰 주세요.")
        question = question[match.end():].strip()
    if not question.strip():
        raise QueryModeError("조회 방식과 함께 질문을 입력해 주세요.")
    if label in ("대사", "문서 대사"):
        if _session_id(data) == "sess-anonymous":
            raise QueryModeError(label+"는 대화창에서 질문과 함께 실행해 주세요. 대화 식별자가 필요합니다.")
        if not (os.environ.get("TEAM_ID") or data.get("team_id")):
            raise QueryModeError(label+"에 사용할 팀이 연결되지 않았습니다. 앱의 팀 설정을 확인해 주세요.")
    return label + ": " + question


def _request_body(question, data):
    question = _selected_question(question, data)
    request_id = str(data.get("request_id") or uuid.uuid4().hex)
    request_body = {
        "API_TYPE": "LEGAL_AGENT",
        "question": question,
        "channel": "genos-chat",
        "session_id": _session_id(data),
        "request_id": request_id,
        "ad_session_id": str(data.get('chatId') or data.get('chat_id') or data.get('sessionId') or data.get('session_id') or ''),
        "ad_channel": _ad_channel(data),
    }
    for key in ("team_id", "scope", "document_ids", "use_llm", "review_action"):
        if key in data:
            request_body[key] = data[key]
    # A workflow revision can bind a team independently of chat payloads.
    # Read on each request; an explicitly invalid setting must not widen scope.
    if "TEAM_ID" in os.environ:
        team_id = os.environ["TEAM_ID"].strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+_team", team_id):
            raise ValueError("TEAM_ID에 risk_team 같은 실제 팀 폴더명을 설정해 주세요.")
        request_body["team_id"] = team_id
    if 'review_action' in request_body and (request_body['session_id']=='sess-anonymous' or not request_body.get('team_id')):
        raise ValueError('검토 행동에는 기존 대화 세션과 팀이 필요합니다.')
    if data.get('memory') is True or os.environ.get("GENOS_MEMORY_ENABLED", "0").strip().lower() in {"1", "true", "on"}:
        import hashlib
        if not re.fullmatch(r"[A-Za-z0-9_-]+_team", str(request_body.get('team_id', ''))):
            raise ValueError("멀티턴에는 TEAM_ID 또는 입력 team_id가 필요합니다.")
        if request_body["session_id"] == "sess-anonymous":
            raise ValueError("멀티턴에는 대화 세션 식별자가 필요합니다.")
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
    if request_body.get('API_TYPE') in {'WARMUP', 'WARMUP_STATUS'}:
        # Controls do not run a model or wait for cache completion. No retry.
        timeout = min(timeout, 30.0) if timeout > 0 else 30.0
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
        progress = body.get('progress') or {}
        if progress:
            text += '\n준비 단계: ' + str(progress.get('phase', '미확인'))
            text += '\n경과: ' + str(progress.get('elapsed_seconds', 0)) + '초'
            text += '\n마지막 진행 이후: ' + str(progress.get('last_progress_age_seconds', 0)) + '초'
            if 'rows_done' in progress:
                text += '\n원문 행: ' + str(progress['rows_done']) + '/' + str(progress.get('rows_total', '?'))
            if 'parts_done' in progress:
                text += '\n자산 분할: ' + str(progress['parts_done']) + '/' + str(progress.get('parts_total', '?'))
            if progress.get('sql_in_flight'):
                text += '\nOracle 응답 대기: ' + str(progress.get('sql_elapsed_seconds', 0)) + '초'
        if body.get('data_provider'):
            text += '\ndata_provider: ' + str(body['data_provider'])
        if body.get('dp_release_id'):
            text += '\ndp_release_id: ' + str(body['dp_release_id'])
        if 'nfs_source_used' in body:
            text += '\nnfs_source_used: ' + str(body['nfs_source_used'])
        recovery = body.get('ad_worker_recovery') or {}
        if recovery.get('state') in {'RUNNING', 'FAILED'}:
            text += '\n예약 작업 복구: ' + str(recovery['state'])
        _log_event('workflow.warmup.finished', request_id=request_id,
                   operation=operation, state=state, worker_id=body.get('worker_id'))
        return {'text': text, 'answer_status': 'warmup', 'request_id': request_id,
                'warmup': body}
    except Exception as exc:
        _log_event('workflow.warmup.failed', level='ERROR', request_id=request_id,
                   operation=operation, error_type=type(exc).__name__, error_message=str(exc),traceback=traceback.format_exc())
        if isinstance(exc, TimeoutError) or (isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError)):
            return {'text': '준비 상태 조회가 제한 시간(최대 30초) 안에 응답하지 않았습니다. '
                    '워크플로우의 code_serving.request.started와 코드서빙의 http.request.started를 대조해 주세요. '
                    '백그라운드 준비 작업의 종료 여부는 확인되지 않았습니다.\nrequest_id: ' + request_id,
                    'answer_status': 'failed', 'request_id': request_id,
                    'failure_kind': 'warmup_status_transport_timeout'}
        return {'text': render_error({'request_id':request_id,'error_type':type(exc).__name__,
                   'detail':str(exc),'traceback':traceback.format_exc()}, exc=exc),
                'answer_status': 'failed', 'request_id': request_id}


class _ChatProgress:
    """Forward backend SSE actions to the workflow's foldable chat cards."""

    def __init__(self, data):
        self.sid = str(data.get('socketIOClientId') or '')
        self.blocks = []
        self.source_candidate_rows = []
        self.source_candidate_context = None
        self.source_candidate_label = ""
        self.source_read_rows = []
        self.source_read_context = None
        self.source_card_number = 0
        self.summary_stages = set()
        self.flow_events = []
        self.emit = None
        self.mode = _progress_mode()
        self.enabled = self.mode in {'socketio', 'socketio-inline', 'socketio-final'} and bool(self.sid)
        self.show_progress = self.mode in {'socketio', 'socketio-inline', 'final-cards'}
        self.show_inline_progress = self.mode == 'socketio-inline'
        self.emitted_card_events = 0
        self.socket_error_type = None
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
        if not self.enabled:
            return
        try:
            if self.emit is None:
                # This is the GENOS Python workflow's existing chat emitter.
                # The separate SSE backend does not need its own socket server.
                from main_socketio import sio_server
                self.emit = sio_server.emit
            sent = self.emit(event, value, room=self.sid)
            if inspect.isawaitable(sent):
                await sent
            if event == 'agentFlowExecutedData':
                self.emitted_card_events += 1
        except Exception as exc:
            self.enabled = False
            self.socket_error_type = type(exc).__name__
            _log_event("workflow.progress.socket_failed", level="WARNING", error_type=type(exc).__name__)

    async def progress(self, event):
        detail = public_event(event)
        if detail is not None and not self.answer_seq:
            self.flow_events.append(detail)
        if not self.show_progress or self.answer_seq:
            return
        if detail is not None and _decision_card(detail):
            await self._flush_source_reads()
            await self._append_source_card(detail['label'], detail.get('details') or [])
            return
        if detail is not None and detail['basis'].get('kind') in {'WORKFLOW_CHECKPOINT', 'WORKFLOW_SOURCE_READ'} and detail['basis'].get('detail_mode') == 'activity':
            await self._flush_source_reads()
            await self._append_source_card(detail['label'], detail.get('details') or [])
            return
        if await self._source_progress(detail):
            return
        event = compact_event(event)
        if event is None or not self.show_progress or self.answer_seq:
            return
        stage = event['basis']['stage']
        if stage in self.summary_stages:
            return
        # A delayed lower-level event cannot make a finished phase look like a
        # new investigation. Detailed activity remains in the backend journal.
        if self.summary_stages and _SUMMARY_ORDER.index(stage) < max(_SUMMARY_ORDER.index(s) for s in self.summary_stages):
            return
        self.summary_stages.add(stage)
        self.last_status = event['label']
        visible = self._card_rationale(event['label'], event['details'])
        self.blocks.append({'nodeId': 'rag-summary-'+stage, 'nodeLabel': 'Visible Reasoner',
            'status': 'FINISHED', 'data': {'output': {'content': json.dumps(
                {'visible_rationale': visible}, ensure_ascii=False)}}})
        await self._send('agentFlowExecutedData', list(self.blocks))

    @staticmethod
    def _source_label(row):
        # Korean headwords verified in the selected glossary. Provenance is
        # frozen in ADR-0772/provider-label-evidence.json, not inferred by LLM.
        providers = {'krx': '한국거래소', 'kofia': '한국금융투자협회',
                     'law': '법제처', 'moleg': '법제처', 'fsc': '금융위원회',
                     'expc': '법제처 (법령해석례)', 'prec': '판례'}
        prefix = re.match(r"^(external|internal)\s*([>/])", row, re.I)
        if not prefix:
            return None, row
        parts = [p.strip() for p in row.split(prefix.group(2))]
        if len(parts) < 2 or parts[0].lower() not in {'external', 'internal'}:
            return None, row
        if parts[0].lower() == 'internal':
            return '내부 규정', ' / '.join(parts[3:] if len(parts) >= 4 and parts[2].lower() in {'forms', 'rules', 'regulations'} else parts[2:] if len(parts) >= 3 else parts[1:]) or '문서명 미확인'
        # external / provider / title, or external / team / provider / title.
        offset = 2 if len(parts) >= 4 and parts[1].lower() not in providers else 1
        provider = parts[offset].lower() if len(parts) > offset + 1 else ''
        title = ' / '.join(parts[offset+1:]) if provider else parts[-1]
        return '외부법률 / ' + providers.get(provider, '기타 출처'), title or '문서명 미확인'

    def _card_rationale(self, label, details):
        # Markdown list items create real line breaks in Visible Reasoner.
        groups = {}
        plain = []
        for row in details:
            heading, title = self._source_label(row)
            if heading:
                groups.setdefault(heading, []).append(title)
            else:
                plain.append(row)
        blocks = [self._plain(label)]
        if plain:
            blocks.append('\n\n'.join('- ' + self._plain(row) for row in plain))
        for heading, titles in groups.items():
            blocks.append(self._plain(heading) + '\n\n' + '\n'.join(
                str(i) + '. ' + self._plain(title) for i, title in enumerate(titles, 1)))
        return '\n\n'.join(blocks)

    async def _flush_source_candidates(self):
        if not self.source_candidate_rows:
            return
        rows, label = self.source_candidate_rows, self.source_candidate_label
        self.source_candidate_rows = []
        self.source_candidate_context = None
        self.source_candidate_label = ''
        await self._append_source_card(label, rows)

    async def _append_source_card(self, label, details):
        self.source_card_number += 1
        self.blocks.append({'nodeId': 'rag-source-' + str(self.source_card_number),
            'nodeLabel': 'Visible Reasoner', 'status': 'FINISHED',
            'data': {'output': {'content': json.dumps(
                {'visible_rationale': self._card_rationale(label, details)}, ensure_ascii=False)}}})
        await self._send('agentFlowExecutedData', list(self.blocks))

    async def _flush_source_reads(self):
        await self._flush_source_candidates()
        if not self.source_read_rows:
            return
        rows = self.source_read_rows
        self.source_read_rows = []
        self.source_read_context = None
        await self._append_source_card('원문 확인 · 확인 대상 ' + str(len(rows)) + '곳', rows)

    async def _source_progress(self, event):
        """One card per contiguous result/read group, never an LLM-call claim."""
        if not isinstance(event, dict) or event.get('schema_version') != 'rag-progress-v1':
            return False
        if event.get('kind') == 'heartbeat':
            return True
        basis = event.get('basis') or {}
        rows = event.get('details')
        rows = [" ".join(row.split()) for row in rows
                if isinstance(row, str) and row.strip() and len(row) <= 300] if isinstance(rows, list) else []
        if (event.get('kind') == 'reading' and basis.get('kind') == 'UNIT_READ_STARTED'
                and basis.get('detail_mode') == 'activity' and rows):
            await self._flush_source_candidates()
            context = (event.get('request_id'), event.get('run_id'))
            if self.source_read_rows and context != self.source_read_context:
                await self._flush_source_reads()
            self.source_read_context = context
            for row in rows:
                if row not in self.source_read_rows:
                    self.source_read_rows.append(row)
            return True
        if event.get('kind') == 'candidate' and basis.get('kind') in {
                'LAW_FULLTEXT_DIRECTORY', 'SOURCE_FULLTEXT_RESULTS'}:
            label = event.get('label')
            if isinstance(label, str) and 0 < len(label) <= 140:
                if self.source_read_rows:
                    await self._flush_source_reads()
                context = (event.get('request_id'), event.get('run_id'), basis.get('kind'),
                           basis.get('journal_seq'), label)
                if context != self.source_candidate_context:
                    await self._flush_source_candidates()
                if not rows:
                    await self._flush_source_candidates()
                    await self._append_source_card(label, [])
                    return True
                self.source_candidate_context, self.source_candidate_label = context, label
                for row in rows:
                    if row not in self.source_candidate_rows:
                        self.source_candidate_rows.append(row)
                return True
        await self._flush_source_reads()
        return False

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
        await self._flush_source_reads()
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

    async def finish(self, text, *, failed=False):
        # Keep the final card list even with no socket, offloaded rendering, or
        # an emitter failure. Pending reads also survive a failed request.
        await self._flush_source_reads()
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
            elif failed:
                text = '\n\n**답변 전달 미완료**\n\n앞서 표시된 답변은 완성된 답변으로 확정되지 않았습니다.\n\n' + text
            else:
                # A different final rendering must not append a second report.
                # The caller records the mismatch and publishes a failure notice.
                raise ValueError('final answer differs from the delivered prefix')
        elif self.primed:
            text = "---\n\n**최종 답변**\n\n" + text
        for start in range(0, len(text), 160):
            await self._send("token", text[start:start+160])
        await self._send("end", "end")


async def _stream_code_serving(question, data, display, *, probe=False, payload=None):
    endpoint, token, configured_timeout = _settings()
    stream_endpoint = endpoint[:-5] + "/stream"
    body = ({"API_TYPE": "SSE_CHECK", "request_id": data["request_id"]}
            if probe else payload if payload is not None else _request_body(question, data))
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue(maxsize=128)
    reader_closed = threading.Event()

    def enqueue(kind, value):
        async def deliver():
            if (kind == 'progress' and queue.full()
                    and (value.get('basis') or {}).get('detail_mode') not in {'judgment', 'full_error'}):
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
                if payload is not None:
                    return unwrap(await asyncio.to_thread(_post_code_serving, payload))
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
                   "execution_mode": body.get("execution_mode"),
                   "entrypoint": body.get("entrypoint"),
                   "judgment_log_revision": body.get("judgment_log_revision"),
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
    comparison = _comparison_answer_text(body)
    if comparison is not None:
        return comparison
    if _guided_reply_text(body) is not None:
        return _guided_reply_text(body)
    if _source_reply_has_originals(body):
        return _source_reply_conversation(body)
    text = _without_review_diagnostics(body, _answer_text(body))
    if body.get("basis_review_text") and not body.get("workflow_id"):text += "\n"+str(body["basis_review_text"])
    answer = body.get('answer')
    if isinstance(answer, dict) and (answer.get('provider_receipt') or {}).get('final_review_policy') == 'advisory':
        return _without_inline_reference_numbers(text).strip()
    text = re.split(r"(?:^|\n)\s*확인 한계\s*:", text, maxsplit=1)[0]
    return _without_inline_reference_numbers(text).strip()


def _guided_reply_text(body):
    agent=(body.get('assembly') or {}).get('term_agent') or {}
    reply=agent.get('guided_reply') or {}
    text=_answer_text(body)
    if (agent.get('text_integrity')=='GUIDED_SOURCE_EXPLANATION'
            and reply.get('schema_version')=='guided-conversation-v1'
            and reply.get('text_hash')==_workflow_display_digest(text)):
        return text
    return None


def _source_reply_has_originals(body):
    """Project only typed no-claim replies whose full originals remain in cards.

    Keep legacy/missing-body replies intact; never infer failure from wording.
    The stored response and legal assessment are not rewritten by this view.
    """
    assembly = body.get('assembly') or {}
    agent = assembly.get('term_agent') or {}
    answer = body.get('answer')
    originals = assembly.get('context')
    return (isinstance(answer, dict) and answer.get('claims') == []
            and agent.get('source_reply_contract') == 'verified-source-excerpt-reply-v1'
            and agent.get('text_integrity') == 'VERIFIED_SOURCE_EXCERPTS'
            and not agent.get('source_bundle')
            and isinstance(originals, list) and bool(originals)
            and all(isinstance(row, dict) and isinstance(row.get('text'), str)
                    and row['text'].strip() and row.get('content_read') is not False for row in originals))


def _source_reply_conversation(body):
    """Present an unresolved answer as a conversation, without new judgments.

    Only sealed user-fact requests become specific questions. Failed proposals
    and historical investigation notes cannot become a current legal answer.
    Original bodies and document titles stay in the separate source cards.
    """
    agent = body['assembly']['term_agent']
    view = agent.get('review_explanation')
    if (not isinstance(view, dict) or view.get('schema_version') != 'review-explanation-v1'
            or _workflow_display_digest({k:v for k,v in view.items() if k != 'content_sha256'})
            != view.get('content_sha256')):
        view = {}
    actions = view.get('actions', [])
    facts = list(dict.fromkeys(action['fact_name'].strip() for action in actions
        if isinstance(action, dict) and action.get('kind') == 'REQUEST_FACT'
        and action.get('actor') == 'USER' and action.get('enabled')
        and isinstance(action.get('fact_name'), str) and action['fact_name'].strip()))
    plain = _ChatProgress._plain
    paragraphs = []
    if facts:
        paragraphs.append('질문하신 상황에 어떤 조건을 적용해야 할지는 아직 애매합니다. '
                          '구체적으로 설명하려면 다음 내용을 더 알려주시겠어요? '
                          + ' / '.join(plain(fact) for fact in facts[:3]))
    else:
        paragraphs.append('질문하신 상황의 적용 여부는 아직 확인이 필요합니다. '
                          '이 자료와 관련해 어떤 대상이나 상황을 염두에 두셨는지 조금 더 설명해 주시겠어요?')
    return '\n\n'.join(paragraphs)


def _visible_review_limitations(stage):
    hidden, visible = set(), set()
    for row in stage.get('limitation_items', []):
        internal = (row.get('issue_id') is None and
                    row.get('id') in {'L-requirement-review', 'L-review-incomplete'} and
                    row.get('kind') in {'EXECUTION_LIMIT', 'REVIEW_INCOMPLETE'})
        (hidden if internal else visible).add(row['text'])
    return [text for text in stage.get('limitations', []) if text not in hidden - visible]


def _without_review_diagnostics(body, text):
    """Project old saved answers without rewriting their publication or claims."""
    view = _judgment_view(body)
    if not view:
        return text
    stage = next(row for row in view['stages'] if row['stage'] == 'COMPOSE')
    hidden = set(stage.get('limitations', [])) - set(_visible_review_limitations(stage))
    head, marker, tail = text.rpartition('\n\n확인 범위\n\n')
    if not marker or not hidden:
        return text
    lines = [line for line in tail.split('\n') if line not in {'- '+value for value in hidden}]
    return head + (marker + '\n'.join(lines) if any(line.strip() for line in lines) else '')


def _report_document_name(value):
    """Remove known storage prefixes, retaining document and appendix titles."""
    text = str(value or '').strip()
    prefix = re.match(r'^(internal|external)\s*([>/])\s*', text, re.I)
    if not prefix:
        return text or '문서명 미확인'
    parts = [p.strip() for p in text.split(prefix.group(2)) if p.strip()]
    # Appendix names need their parent document to remain distinguishable.
    for index, part in enumerate(parts):
        if index >= 2 and part in {'별표서식', '별표·서식', '별표', '별지', '서식'}:
            return ' · '.join(parts[index-1:])
    return parts[-1] if len(parts) > 1 else '문서명 미확인'


def _report_sources(body):
    bundle = ((body.get('assembly') or {}).get('term_agent') or {}).get('source_bundle') or {}
    counters = {}; records = {}; ordered = []
    for source in bundle.get('sources', []):
        if not isinstance(source, dict) or source.get('content_read') is not True:
            continue
        ident = source.get('selection_id')
        if not isinstance(ident, str) or not ident or ident in records:
            continue
        side = source.get('side')
        category = {'internal':'내규', 'external':'외규'}.get(side, '출처')
        counters[category] = counters.get(category, 0) + 1
        record = {'source':source, 'category':category,
                  'label':category+' '+str(counters[category]),
                  'name':_report_document_name(source.get('document_name'))}
        records[ident] = record; ordered.append(record)
    return records, ordered


def _comparison_answer_text(body):
    """One report from accepted observations, without regenerating judgments."""
    if body.get('workflow_id') == 'risk_team_document_compare_workflow':
        # Server-assembled whole-document report with exact quotations.
        return _answer_text(body)
    if body.get('workflow_id') != 'risk_team_compare_workflow':
        return None
    table=body.get('comparison_table') or {}
    if table.get('schema_version')=='internal-concept-table-v1':
        # The server assembled source names, coordinates and exact quotations.
        # Preserve the same text across live delivery, saved status and JSON.
        return _answer_text(body)
    report = body.get('report') or {}
    issues = (report.get('scope') or {}).get('issues')
    if not isinstance(issues, list):
        return None
    items = (body.get('comparison_items') or {}).get('items') or []
    fields = {'subject':'대상','obligation':'의무','procedure':'절차·담당','authority':'전결·권한',
        'condition':'조건','exceptions':'예외','date':'기준일','definition':'정의','numerator':'분자',
        'denominator':'분모','unit':'단위','period':'산정 기간','direction':'기준 방향','value':'기준 수치',
        'overview':'확인 범위'}
    verdicts = {'CONFORMS':'부합','ADDITIONAL_INTERNAL':'내부 추가기준','CONFLICT':'상충',
                'POSSIBLE_GAP':'미비 후보','DEFERRED':'판정 보류'}
    sources, _ = _report_sources(body)
    issue_names = {i['id']:i['label'] for i in issues}
    pairs = {p['pair_id']:p for p in (report.get('basis') or {}).get('pairs', [])}
    relations = {'DIRECT':'직접 명시','INDIRECT':'상위 내규·위임 경유','CONTENT_ONLY':'내용 대응',
                 'UNKNOWN':'미확인','UNRELATED':'무관'}

    def plain(value):
        text = str(value or '')
        for ident, source in sources.items():
            text = text.replace('['+ident+']', '〔'+source['label']+'〕')
            original = source['source'].get('document_name')
            if original:
                text = text.replace(original, source['name'])
        for ident, label in issue_names.items():
            text = re.sub(r'(?<![A-Za-z0-9_-])'+re.escape(ident)+r'(?![A-Za-z0-9_-])', lambda _:label, text)
        return _ChatProgress._plain(text).replace('|', '\\|')

    def paragraphs(value):
        # Retain every sentence, quotation and number; only split whitespace.
        return '<br><br>'.join(plain(p) for p in re.split(
            r'\n+|(?<=[.!?。])\s+', str(value or '').replace('\r\n', '\n')) if p.strip())

    def references(citations):
        labels = list(dict.fromkeys(sources[c['evidence']]['label']
            for c in citations if c.get('evidence') in sources))
        return ' · '.join('〔'+label+'〕' for label in labels)

    def side_text(value):
        blocks = [paragraphs(value.get('text') or '미확보')]
        refs = references(value.get('citations', []))
        if refs:blocks.append('**근거**<br>'+refs)
        elif value.get('text'):blocks.append('근거 미선택')
        for alternative in value.get('alternatives', []):
            previous = '**이전 확인**<br>'+paragraphs(alternative.get('text'))
            refs = references(alternative.get('citations', []))
            if refs:previous += '<br>'+refs
            blocks.append(previous)
        if value.get('missing'):
            blocks.append('**남은 확인**<br>'+paragraphs(value['missing']))
        if value.get('status') in {'PARTIAL', 'MISSING', 'CONFLICT'}:
            blocks.append('확인 상태: '+{'PARTIAL':'일부 확인','MISSING':'미확보','CONFLICT':'상충'}[value['status']])
        return '<br><br>'.join(blocks)

    lines = ['## 내규·외규 대사 보고서', '', '### 1. 검토 개요', '',
        '내규와 외규를 비교한 결과입니다.' if body.get('status') == 'completed' else
        '확인된 원문 범위의 비교 결과입니다. 미확인 사항이 남아 있습니다.', '',
        '해석은 원문에 대한 LLM의 검토 의견이며, 근거와 함께 검토할 수 있습니다.', '']
    day = next((line for line in _answer_text(body).splitlines() if line.startswith('기준일: ')), None)
    if day:lines.extend([plain(day), ''])
    lines.extend(['### 2. 대사표', '', '| 확인 내용 | 내규 | 외규 | 해석 |', '|---|---|---|---|'])
    unresolved = list(body.get('unresolved') or [])
    for issue in issues:
        related = [i for i in items if i['issue_id'] == issue['id']]
        judgments = [r for r in report.get('rows', [])
                     if pairs.get(r['pair_id'], {}).get('issue_id') == issue['id']]
        if not related:
            # Older/partial results have no field observations. Show only their
            # cited exact excerpts, never invent side summaries from a verdict.
            sides = {}
            for side in ('internal', 'external'):
                citations = [c for row in judgments for c in row.get('citations', [])
                    if c.get('evidence') in sources and sources[c['evidence']]['source'].get('side') == side]
                excerpts = list(dict.fromkeys(sources[c['evidence']]['source'].get('excerpt', '') for c in citations))
                sides[side] = {'text':'\n\n'.join(e for e in excerpts if e), 'citations':citations,
                               'missing':'항목별 요약 미확보 — 확인한 인용 원문만 표시합니다.'}
            related = [{'field':'overview', 'difference':'항목별 비교 검토 미완료', **sides}]
        for index, item in enumerate(related):
            interpretation = [paragraphs(item.get('difference') or '항목별 해석 미확인')]
            if index == 0:
                # The whole-issue opinion is explicitly scoped, once per issue.
                for row in judgments:
                    pair = pairs.get(row['pair_id'], {})
                    interpretation.extend(['**쟁점 전체 의견: '+plain(verdicts.get(row['verdict'], row['verdict']))+'**',
                        paragraphs(row.get('difference')), paragraphs(row.get('reason')),
                        '근거 관계: '+relations.get(pair.get('basis_relation'), '미확인')])
                    refs = references(row.get('citations', []))
                    if refs:interpretation.append('의견 근거: '+refs)
                    for dimension in row.get('dimensions', []):
                        state = {'MATCH':'일치','DIFFERENT':'차이 있음','UNKNOWN':'미확인',
                                 'NOT_APPLICABLE':'해당 없음'}.get(dimension['status'], '미확인')
                        interpretation.append('**산정 검토 · '+plain(fields.get(dimension['name'], '범위'))+
                            ': '+state+'**<br>'+paragraphs(dimension.get('reason'))+
                            ('<br>'+references(dimension.get('citations', [])) if dimension.get('citations') else ''))
                    unresolved.extend(row.get('unresolved') or [])
            cells = ['**'+plain(issue['label'])+'**<br><br>'+plain(fields.get(item['field'], '확인 항목')),
                     side_text(item['internal']), side_text(item['external']),
                     '<br><br>'.join(dict.fromkeys(p for p in interpretation if p))]
            lines.append('| '+' | '.join(cells)+' |')
    if not issues:lines.append('| 확인 범위 미확정 | 미확보 | 미확보 | 비교 검토 미완료 |')
    lines.extend(['', '### 3. 추가 확인 사항', ''])
    remaining = list(dict.fromkeys(plain(value) for value in unresolved if str(value).strip()))
    lines.extend('- '+value+'\n' for value in remaining)
    if not remaining:lines.append('별도로 기록된 추가 확인 사항은 없습니다.')
    return '\n'.join(lines).strip()


_ANSWER_NUMERIC_REFERENCE = re.compile(r"\[[ \t]*[1-9][0-9]*(?:[ \t]*[,，;、\-–][ \t]*[1-9][0-9]*)*[ \t]*\]")
_ANSWER_REFERENCE_PREFIX = re.compile(r"\[[0-9,，;、\-– \t]*")
_ANSWER_QUOTES = {'"': '"', '“': '”', '‘': '’', '「': '」', '『': '』'}


def _without_inline_reference_numbers(text, *, final=True):
    """Hide postfix numeric footnotes in prose, including split SSE fragments.

    Quotes, code, named brackets, line-leading list numbers and Markdown links
    remain literal. Pending brackets wait for their content and link suffix;
    emitted text therefore stays a prefix of the final rendering.
    """
    # The server has already escaped and numbered this source-bound report.
    # Numeric brackets inside its literal quotations are original source text.
    if text.startswith('<!-- GENOS_COMPARISON_START -->'):
        return text
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


def _source_location(item):
    if item.get('coordinate_label'):
        return str(item['coordinate_label'])
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
    return location


def _source_cards(records):
    """Fold already authorized response originals; never fetch or infer content."""
    from html import escape
    def e(value):
        # Entities also keep source Markdown literal in mixed Markdown/HTML chat.
        return (escape(str(value), quote=True).replace('[', '&#91;').replace(']', '&#93;')
                .replace('`', '&#96;').replace('\r', '&#13;').replace('\n', '&#10;'))

    cards = []; seen = set()
    for source, label, note in records:
        if source.get('content_read') is False:
            continue
        # A title/coordinate alone cannot identify a version or a read range.
        key = json.dumps({k:v for k,v in source.items()
                          if k not in {'tier', 'relevance_reason', 'interpretation_status'}},
                         sort_keys=True, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        name = _report_document_name(source.get('document_name') or '문서명 미확인')
        location = _source_location(source)
        title = (label + ' · ' if label else '') + name + (' · ' + location if location else '')
        if 'spans' in source:
            texts = [span['text'] for span in (source.get('spans') or [])
                     if isinstance(span, dict) and isinstance(span.get('text'), str) and span['text'].strip()]
        else:
            original = source.get('text') or source.get('excerpt')
            texts = [original] if isinstance(original, str) and original.strip() else []
        rows = [
            '<details data-genos-source="true" style="border:1px solid #dbe3ed;border-radius:10px;margin:10px 0;background:#fff;color:#172b4d;overflow-wrap:anywhere;">',
            '<summary style="cursor:pointer;padding:14px 16px;font-weight:600;line-height:1.6;">' + e(title) + '</summary>',
            '<div style="border-top:1px solid #e5eaf1;padding:16px;">',
            '<p style="margin:0 0 12px;color:#526174;font-size:13px;">위치: ' + e(location or '상세 위치 미기록') + '</p>',
        ]
        if source.get('version'):
            rows.append('<p>판본: ' + e(source['version']) + '</p>')
        if note:
            rows.append('<p>' + e(note) + '</p>')
        if texts:
            rows.append('<p style="margin:0 0 12px;font-size:13px;color:#526174;">답변에 연결된 원문</p>')
            for original in texts:
                rows.append('<div data-source-text="true" style="white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.85;margin:12px 0;">' + e(original) + '</div>')
        else:
            rows.append('<p>이 답변에 원문 내용이 저장되지 않았습니다.</p>')
        rows.extend(['</div>', '</details>'])
        cards.append('\n'.join(rows))
    if not cards:
        return ''
    return '\n'.join([
        '<!-- GENOS_SOURCES_START -->',
        '<details data-genos-sources="true" style="margin:16px 0;">',
        '<summary style="cursor:pointer;width:fit-content;max-width:100%;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:8px;padding:9px 14px;background:#f5f8fc;color:#172b4d;font-weight:600;">출처 · ' + str(len(cards)) + '건</summary>',
        '<div style="margin-top:12px;">',
        '<p style="font-size:13px;color:#526174;">각 출처를 누르면 해당 원문이 펼쳐집니다.</p>',
        *cards, '</div>', '</details>', '<!-- GENOS_SOURCES_END -->',
    ])


def _unread_cards(body):
    """Fold connected articles the agent saw but did not read; never evidence."""
    from html import escape
    def e(value):
        return (escape(str(value), quote=True).replace('[', '&#91;').replace(']', '&#93;')
                .replace('`', '&#96;').replace('\r', '&#13;').replace('\n', '&#10;'))
    agent = (body.get('assembly') or {}).get('term_agent') or {}
    reply = agent.get('guided_reply') or {}
    if _guided_reply_text(body) is None:
        return ''
    rows = [r for r in reply.get('unread_connections') or []
            if isinstance(r, dict) and r.get('used_as_evidence') is False and isinstance(r.get('target_label'), str)]
    if not rows:
        return ''
    cards = []
    for r in rows:
        same = r.get('relation') == 'SAME_SECTION'
        title = ((r.get('from_label') or '') + ' → ' if r.get('from_label') else '') + r['target_label'] + ' · ' + str(r.get('relation_text') or '연결 조문')
        head = (('같은 절' + ('(' + r['section'] + ')' if r.get('section') else '') + '에 있는 ' + r['target_label']) if same
                else ((r['from_label'] + '에 연결된 ' if r.get('from_label') else '') + r['target_label']))
        verb = '읽을 필요가 없다고 판단했습니다' if r.get('judged_unneeded') else '아직 읽지 않았습니다'
        parts = [
            '<details data-genos-unread="true" style="border:1px solid #e6dcc8;border-radius:10px;margin:10px 0;background:#fffdf8;color:#172b4d;overflow-wrap:anywhere;">',
            '<summary style="cursor:pointer;padding:14px 16px;font-weight:600;line-height:1.6;">' + e(title) + '</summary>',
            '<div style="border-top:1px solid #efe6d6;padding:16px;">',
            '<p style="margin:0 0 12px;">' + e(head + ': 지금은 ' + str(r.get('reason') or '').rstrip('. ') + ' ' + verb + '. 필요하면 말씀해 주세요.') + '</p>',
        ]
        text = r.get('text')
        if isinstance(text, str) and text.strip():
            parts.append('<p style="margin:0 0 12px;font-size:13px;color:#7a5b1e;">답변 근거로 쓰지 않은 원문' + (' (앞부분)' if r.get('text_clipped') else '') + '</p>')
            parts.append('<div data-unread-text="true" style="white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.85;margin:12px 0;">' + e(text) + '</div>')
        else:
            parts.append('<p>이 응답에 원문 내용이 저장되지 않았습니다.</p>')
        parts.extend(['</div>', '</details>'])
        cards.append('\n'.join(parts))
    total = reply.get('unread_connection_total')
    more = total - len(cards) if isinstance(total, int) and total > len(cards) else 0
    return '\n'.join([
        '<!-- GENOS_UNREAD_START -->',
        '<details data-genos-unread-group="true" style="margin:16px 0;">',
        '<summary style="cursor:pointer;width:fit-content;max-width:100%;box-sizing:border-box;border:1px solid #e0cfa8;border-radius:8px;padding:9px 14px;background:#fdf7ea;color:#172b4d;font-weight:600;">미확인 조문 · ' + str(len(cards)) + '건</summary>',
        '<div style="margin-top:12px;">',
        '<p style="font-size:13px;color:#7a5b1e;">연결은 확인했지만 이번 답변에서 읽지 않은 조문입니다. 누르면 어떤 조문에서 연결됐는지와 원문이 펼쳐집니다. 답변 근거가 아니며, 읽지 않았다고 내용이 없다는 뜻은 아닙니다.</p>',
        *cards,
        *(['<p style="font-size:13px;color:#7a5b1e;">그 밖에 ' + str(more) + '건은 목록에서 생략했습니다.</p>'] if more else []),
        '</div>', '</details>', '<!-- GENOS_UNREAD_END -->',
    ])


def _tier_sources(bundle):
    records=[]
    for c in sorted(bundle.get("sources",[]),
                    key=lambda item: isinstance(item,dict) and item.get("tier")!="CORE"):
        if not isinstance(c,dict) or c.get("tier") not in {"CORE","SUPPLEMENTAL"}:
            continue
        tier="핵심" if c["tier"]=="CORE" else "보완"
        records.append((c, tier, ''))
    return _source_cards(records)


def _sources(body):
    if (body.get('comparison_table') or {}).get('display_version') == 'comparison-readable-v1':
        return ''  # Exact sources are already grouped and folded in the report.
    bundle=(body.get("assembly",{}).get("term_agent") or {}).get("source_bundle")
    if isinstance(bundle,dict) and bundle.get('schema_version')=='workflow-source-v1':
        _, records = _report_sources(body)
        if not records:return ''
        cards = []
        for category in ('내규', '외규', '출처'):
            group = [row for row in records if row['category'] == category]
            if not group:continue
            for row in group:
                source = row['source']
                note = ''
                if any(item.get('evidence_id') == source['selection_id'] for item in body.get('unreviewed_sources', [])):
                    note = '확보한 원문이며 항목별 해석은 아직 완료되지 않았습니다.'
                cards.append((source, '〔'+row['label']+'〕', note))
        return _source_cards(cards)
    if isinstance(bundle,dict) and bundle.get("schema_version")=="source-tiers-v4":
        return _tier_sources(bundle)
    assembly = body.get("assembly")
    contexts = assembly.get("context") if isinstance(assembly, dict) else []
    if not isinstance(contexts, list):
        contexts = []
    used = _used_source_ids(body)
    records = []
    for item in contexts:
        if not isinstance(item, dict):
            continue
        # claims가 출처를 특정했다면 실제 사용된 근거만 표시한다.
        if used and str(item.get("id") or "") not in used:
            continue
        records.append((item, '', ''))
    return _source_cards(records)


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
    if body.get('answer_status') in {'failed','error'}:
        safe = public_failure(body.get('request_id'), body=body)
        return {'response_schema':'ad-mode-v1', 'ad_mode':body.get('ad_mode'),
                'answer_status':'failed', 'request_id':safe['request_id'], 'text':render_error(safe)}
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
    search = node('search', '관련 문서·근거 탐색', search_details)
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
    # SELECT may acquire additional original scopes while investigating a law.
    # Its current verified source rows belong in the same evidence graph.
    original_rows = [*stages['READ'].get('data', []), *stages['SELECT'].get('data', [])]
    originals = {item['source_id']: item for item in original_rows
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
    # Search hits have no verified evidence edge. Keep their complete inventory
    # in a separate collapsed list so it cannot bury the current judgment.
    connected = {key for edge in raw_edges if edge['label'] in {'포함하는 원문', '판단 근거'}
                 for key in (edge['from'], edge['to'])}
    candidates = [item for item in raw_nodes if item['kind']=='law' and item['id'] not in connected]
    nodes = [item for item in raw_nodes if item['kind'] in {'law', 'source', 'claim'}
             and (item['kind'] != 'law' or item['id'] in connected)]
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
        title = item['title']
        if item['kind']=='law':
            # Paths are provenance, not the law's display name. The full path
            # remains in the SVG title and the verified judgment detail.
            title = re.split(r'\s+>\s+', title)[-1]
        lines = wrap(_flow_text(title), 42 if item['kind']=='claim' else 30)
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
    for component in sorted(components, key=lambda group: -sum(lookup[key]['kind']=='claim' for key in group)):
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
    if candidates:
        html += '<details data-search-candidates="true"><summary>검색 후보 '+str(len(candidates))+'개 보기</summary><ul>'
        html += ''.join('<li>'+escape(clean(item['title']))+'</li>' for item in candidates)
        html += '</ul></details>'
    return {'svg':svg,'html':html,'metadata':{
        'format':'svg','mime_type':'image/svg+xml','renderer_revision':JUDGMENT_DISPLAY_REVISION,
        'content_sha256':hashlib.sha256(encoded).hexdigest(),'bytes':len(encoded),
        'node_count':len(records),'return_count':sum(node['returned'] for node in records),
        'entity_count':len(nodes),'relation_count':len(edges),'record_entity_count':len(raw_nodes),
        'search_candidate_count':len(candidates),'unconnected_candidates_in_graph':False,
        'layout':'law-centered-evidence-clusters','execution_trace_visible':False,'process_nodes_visible':False,
        'theme':'graphite-evidence','external_assets':False,
        'concept_table_grouped_by_usage':True,'answer_body_repeated':False,
        'basis':basis,'judgment_sha256':view['content_sha256'],
        'render_ms':round((time.perf_counter()-started)*1000,3)}}



def _judgment_html(body):
    from html import escape
    view = _judgment_view(body)
    if not view:
        metrics = _execution_html(body)
        return ('<!-- GENOS_JUDGMENT_VIEW_START -->\n'+metrics+'\n<!-- GENOS_JUDGMENT_VIEW_END -->') if metrics else ''
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
            '<summary><strong>처리 상세 · 판단 근거와 LLM 호출</strong></summary>', '',
            '<p>현재 질문의 판단 기록입니다. 아래 단계는 처리 구분이며 LLM 호출 횟수와 다릅니다.</p>', _execution_html(body)]
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
        rows += [paragraphs('추가 확인할 사항', _visible_review_limitations(stage)),
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
    if body.get('response_schema') == 'workflow-result-v1':
        if body.get('status') in {'failed', 'partial'}:
            return body['status']
    if body.get('response_schema')=='workflow-result-v1':
        return {'completed':'answered','partial':'partial','blocked':'unavailable','failed':'failed'}.get(body.get('status'),'incomplete')
    if body.get("answer_status") in {"failed", "error"}:return "failed"
    agent = (body.get('assembly') or {}).get('term_agent') or {}
    if answered:
        return 'partial' if agent.get('completion_contract') and agent.get('answer_coverage') in ('PARTIAL','INSUFFICIENT') else 'answered'
    if body.get('code') == 'SOURCE_INVESTIGATION_INCOMPLETE': return 'incomplete'
    if body.get('code') == 'MODEL_UPSTREAM_UNAVAILABLE': return 'unavailable'
    if isinstance(body.get('_gateway_status'), int) and body['_gateway_status'] >= 400: return 'failed'
    return 'incomplete' if _has_found_source(body) else 'not_found'


DISPLAY_POLICY_REVISION = 'public-display-v6-workflow'
REVIEW_INCOMPLETE_MESSAGE = (
    '현재 충분한 법률 검토를 하지 못했습니다. '
    '답변에 필요한 원문 조사·검토가 완료되지 않았습니다. '
    '질문이 잘못되었다는 뜻은 아닙니다. 추가로 알려줄 사건 사실이나 확인할 쟁점이 있다면 '
    '같은 대화에서 이어서 적어 주세요. 같은 요청의 반복 전송으로는 해결되지 않습니다.'
)
_TIMEOUT_TYPES = frozenset({'TimeoutError', 'TimeoutException', 'ReadTimeout',
    'ConnectTimeout', 'WriteTimeout', 'PoolTimeout', 'ServerTimeoutError'})


def _failure_hint(body, status=None, exc=None):
    """Project only known metadata; never publish exception text or model output."""
    body = body if isinstance(body, dict) else {}
    codes = [body.get('code'), body.get('error_code')]
    types = [body.get('error_type')]
    statuses = [status, body.get('_gateway_status'), body.get('http_status')]
    nested = body.get('error')
    if isinstance(nested, dict):
        types.extend([nested.get('type'), nested.get('error_type')])
        codes.append(nested.get('code'))
    # TransportError wraps socket/httpx timeouts and carries the upstream status.
    # URLError uses reason instead of __cause__. Keep traversal bounded/cycle-safe.
    seen = set()
    while isinstance(exc, BaseException) and id(exc) not in seen and len(seen) < 8:
        seen.add(id(exc))
        codes.append(getattr(exc, 'code', None))
        types.append(type(exc).__name__)
        statuses.extend([getattr(exc, 'http_status', None), getattr(exc, 'status_code', None),
                         getattr(exc, 'code', None)])
        response = getattr(exc, 'response', None)
        if isinstance(response, dict):
            statuses.insert(0, response.get('status_code'))
        reason = getattr(exc, 'reason', None)
        exc = exc.__cause__ or (reason if isinstance(reason, BaseException) else None) or (None if exc.__suppress_context__ else exc.__context__)
    # These two fields are the closed, idempotent projection used across hops.
    reason = body.get('failure_reason')
    marker = body.get('error_code')
    if (reason == 'timeout' or any(c == 'DEADLINE_EXCEEDED' for c in codes)
            or any(isinstance(t, str) and t.rsplit('.', 1)[-1] in _TIMEOUT_TYPES for t in types)):
        return 'timeout', 'timeout'
    if reason == 'review_incomplete' or 'SOURCE_INVESTIGATION_INCOMPLETE' in codes:
        return 'review_incomplete', None
    if reason == 'budget' or 'BUDGET_EXHAUSTED' in codes:
        return 'budget', 'limit'
    if reason == 'technical' and isinstance(marker, str) and re.fullmatch(r'[45][0-9]{2}|connection|internal', marker):
        return reason, marker
    for value in statuses:
        if type(value) is int and 400 <= value <= 599:
            return 'technical', str(value)
    if any(isinstance(t, str) and t.rsplit('.', 1)[-1] in {
            'ConnectionError', 'ConnectionRefusedError', 'ConnectionResetError',
            'ConnectError', 'NetworkError', 'URLError'} for t in types):
        return 'technical', 'connection'
    return 'technical', 'internal'


def public_failure(request_id=None, *, body=None, status=None, exc=None):
    ident = str(request_id or '')
    if not re.fullmatch(r'[A-Za-z0-9_:.\-]{1,128}', ident):
        ident = uuid.uuid4().hex
    reason, marker = _failure_hint(body, status, exc)
    guidance = {
        '401': '로그인 상태와 접근 권한을 확인해 주세요.',
        '403': '이 자료와 기능에 대한 접근 권한을 확인해 주세요.',
        '409': '요청 상태가 변경되었거나 처리 중입니다. 최신 대화 상태를 확인해 주세요.',
        '413': '질문이나 첨부 자료의 분량을 줄여 다시 요청해 주세요.',
        'limit': '검토 가능한 처리 한도에 도달했습니다. 법률 쟁점을 나누어 질문해 주세요.',
    }.get(marker, '잠시 후 다시 요청해 주세요.')
    message = REVIEW_INCOMPLETE_MESSAGE if reason == 'review_incomplete' else (
        '모델 응답을 확인하지 못해 처리를 중단했습니다. 이미 받은 기록은 보존하며, '
        '같은 요청을 자동으로 재전송하지 않습니다. 시간이 지난 뒤 새 검토를 요청할 수 있습니다. (' + str(marker) + ')'
        if reason == 'timeout' or marker == '504' else
        '현재 충분한 법률 검토를 하지 못했습니다. ' + guidance + ' ('
        + ('처리 오류' if marker == 'internal' else marker) + ')')
    result = {'request_id': ident, 'answer_status': 'failed', 'message': message,
              'failure_reason': reason, 'display_policy_revision': DISPLAY_POLICY_REVISION}
    if marker is not None:
        result['error_code'] = marker
    stage = getattr(exc, 'stage', None) or (body or {}).get('failure_stage')
    stage = stage if stage in ('INTENT','PLAN','RECALL','READ','SELECT','ASSESS','COMPOSE') else 'NOT_RECORDED'
    result['failure_stage'] = stage
    if reason in ('timeout','review_incomplete','budget') or marker == '504':
        notice = {'schema_version':'review-explanation-v1',
            'outcome':'EXECUTION_UNKNOWN' if reason == 'timeout' or marker == '504' else 'REVIEW_INCOMPLETE',
            'stage':stage, 'completed':[], 'acquisition':'NOT_RECORDED',
            'reason':'저장된 자료 확보 상태는 이 오류 응답만으로 확정하지 않습니다.',
            'impact':'최종 검토 결과를 확정하지 못했습니다.',
            'next_action':'CHECK_SAVED_REQUEST', 'actor':'SYSTEM', 'automatic_retry':False,
            'semantic_quality_certified':False}
        notice['content_sha256']=_workflow_display_digest(notice)
        result['review_explanation']=notice
    return result


def public_event(event):
    """Only activity and committed judgment are public; diagnostics stay in logs."""
    if not isinstance(event, dict) or event.get('schema_version') != 'rag-progress-v1':
        return None
    basis = event.get('basis') or {}
    if not isinstance(basis, dict):
        return None
    if basis.get('detail_mode') in {'full_error', 'error', 'diagnostic'}:
        return None
    if basis.get('kind') in {'ATTEMPT_FINISHED', 'COMPLETION_ASSESSMENT_REJECTED',
            'MODEL_OUTPUT_INVALID', 'LAW_DECISION_REJECTED', 'SOURCE_INVESTIGATION_INCOMPLETE',
            'REFERENCE_NAVIGATION_STATUS', 'LAW_STRUCTURE_RECOVERY', 'UNIT_CANDIDATE_ACQUISITION_STOPPED'}:
        return None
    if basis.get('kind') == 'OBS_EVENT' and basis.get('name') not in {
            'request.started', 'request.finished'}:
        return None
    if basis.get('detail_mode') == 'judgment' and (
            basis.get('kind') != 'CASE_JUDGMENT_ACCEPTED' or basis.get('state') not in {'COMPLETED', 'REBOUND'}):
        return None
    if event.get('kind') not in {'phase','candidate','reading','read_complete','selected',
            'revised','review','decision','model_wait','heartbeat','overflow'}:
        return None
    # Do not forward caller-added debug fields, model payloads or exception objects.
    out = {k:event[k] for k in ('schema_version','request_id','run_id','seq','kind','label','elapsed_ms','count','details') if k in event}
    out['basis'] = {k:basis[k] for k in ('kind','name','journal_seq','stage','state','detail_mode','judgment_revision','payload_hash') if k in basis}
    out['display_policy_revision'] = DISPLAY_POLICY_REVISION
    return out


def _decision_card(event):
    basis = event.get('basis') or {}
    return (basis.get('detail_mode') == 'judgment'
            or (event.get('kind') == 'decision' and basis.get('detail_mode') == 'activity'
                and basis.get('kind') in {'LAW_SELECTION_DECISION', 'REFERENCE_GROUP_DECISION'}))


_SUMMARY_ORDER = ('request', 'search', 'sources', 'answer', 'complete')
_SUMMARIES = {
    'request': ('요청 확인', '질문과 확인할 사항을 정리합니다.'),
    'search': ('관련 문서 찾기', '문서명·목차·조문 구조에서 관련 범위를 찾습니다.'),
    'sources': ('선택한 원문 확인', '선택한 문서의 필요한 범위와 근거를 확인합니다.'),
    'answer': ('근거 검토·답변 작성', '확인한 근거와 조건·예외를 검토해 답변을 정리합니다.'),
    'complete': ('답변 준비 완료', '확인한 답변과 근거를 정리했습니다.'),
}

def compact_event(event):
    event = public_event(event)
    if event is None or event.get('kind') in {'heartbeat','model_wait','overflow'}: return None
    b = event['basis']; kind = event.get('kind'); raw = str(b.get('stage','')).upper()
    if b.get('kind') == 'PROGRESS_SUMMARY':
        stage = b.get('stage')
        if stage not in _SUMMARIES: return None
    elif b.get('name') == 'request.finished': stage = 'complete'
    elif raw in {'ASSESS','COMPOSE'} or b.get('kind') == 'CASE_JUDGMENT_ACCEPTED': stage = 'answer'
    elif raw in {'READ','SELECT'} or kind in {'reading','read_complete','selected','revised','review','decision'}: stage = 'sources'
    elif raw == 'RECALL' or kind == 'candidate': stage = 'search'
    else: stage = 'request'
    label, detail = _SUMMARIES[stage]
    return {**{k:event[k] for k in ('schema_version','request_id','run_id','seq','elapsed_ms') if k in event},
            'kind':'phase', 'label':label, 'details':[detail],
            'basis':{'kind':'PROGRESS_SUMMARY','stage':stage,'detail_mode':'summary'},
            'display_policy_revision':DISPLAY_POLICY_REVISION}


def _execution_html(body):
    value = body.get('execution_stats')
    if (not isinstance(value,dict) or value.get('schema_version') != 'rag-execution-stats-v1'
            or value.get('count_basis') != 'transport-attempts'): return ''
    calls = value.get('calls')
    valid_ms = lambda n: type(n) is int and 0 <= n <= 86400000
    if (not isinstance(calls,list) or len(calls)>1024 or type(value.get('llm_calls')) is not int
            or value['llm_calls'] != len(calls) or not valid_ms(value.get('request_duration_ms'))): return ''
    labels = {'request':'요청 확인','sources':'원문·근거 확인','assessment':'조건·예외 판단','answer':'답변 작성','model':'모델 처리'}
    for i,row in enumerate(calls,1):
        if (not isinstance(row,dict) or type(row.get('number')) is not int or row['number']!=i
                or row.get('purpose') not in labels or row.get('duration_ms') is not None and not valid_ms(row['duration_ms'])): return ''
    sec = lambda n: f'{n/1000:.2f}초'
    known = sum(r['duration_ms'] for r in calls if r['duration_ms'] is not None)
    complete = all(r['duration_ms'] is not None for r in calls)
    rows = ['<details><summary><strong>LLM 호출·처리 시간 · '+str(len(calls))+'회</strong></summary>',
            '<p>서버 요청 처리: '+sec(value['request_duration_ms'])+' · 모델 호출 시간 '+('합계' if complete else '확인된 합계')+': '+sec(known)+'</p>',
            '<p>전송 시도 기준이며 재시도도 각각 셉니다. 문서 열람·내부 처리 횟수와 다릅니다. 호출 시간 합계와 서버 요청 처리 시간은 별도입니다.</p>']
    if calls:
        rows += ['<table><thead><tr><th>호출</th><th>작업</th><th>소요 시간</th></tr></thead><tbody>']
        rows += ['<tr><td>'+str(r['number'])+'</td><td>'+labels[r['purpose']]+'</td><td>'+(sec(r['duration_ms']) if r['duration_ms'] is not None else '미확인')+'</td></tr>' for r in calls]
        rows += ['</tbody></table>']
    else: rows += ['<p>이번 요청에서는 모델을 호출하지 않았습니다.</p>']
    return '\n'.join([*rows,'</details>'])


def public_response(body, *, status=200, request_id=None):
    if not isinstance(body, dict):
        return public_failure(request_id, status=status)
    if body.get('answer_status') in {'failed', 'error'} or status >= 400 or (isinstance(body.get('_gateway_status'), int) and body['_gateway_status'] >= 400):
        safe=public_failure(request_id or body.get('request_id'), body=body, status=status)
        if status >= 400 or isinstance(body.get('_gateway_status'), int):
            safe['_gateway_status']=status if status >= 400 else body['_gateway_status']
        if _bound_workflow_display(body,safe['request_id']) and {k:v for k,v in body.items() if k!='workflow_display'}==safe:
            safe['workflow_display']=body['workflow_display']
        return safe
    # Legacy raw diagnostics may be present in successful, recovered responses.
    # Domain reason/limitations are produced separately from these journal records.
    private = {'diagnostics','failure_diagnostics','error_diagnostics','traceback','error',
               'error_type','error_message','rejected_decisions','rejected_assessment',
               'repair_feedback','normalization','retry_history','http_error_diagnostics',
               'failure','blockers','observations','structure_recovery'}
    def project(value):
        if isinstance(value, dict):
            return {k:project(v) for k,v in value.items() if k not in private}
        if isinstance(value, list): return [project(v) for v in value]
        return value
    return project(body)


def render_error(body, *, question='', exc=None):
    """A terminal failure is visible without exposing diagnostic content."""
    safe = public_failure(body.get('request_id') if isinstance(body, dict) else None,
                          body=body, exc=exc)
    stage = safe.get('failure_stage','NOT_RECORDED')
    detail = '\n\n중단 단계: '+stage+' · 해당 단계의 최종 결과는 확정되지 않았습니다.' if stage != 'NOT_RECORDED' else ''
    return safe['message'] + detail + '\n\n조회 번호: ' + safe['request_id']


def render(body, *, flow=None):
    if body.get('response_schema')=='ad-mode-v1':return _ad_result(body)['text']
    status = body.get("_gateway_status")
    if (body.get('answer_status') in {'failed', 'error'} or isinstance(status, int) and status >= 400
            or body.get('response_schema') == 'workflow-result-v1' and body.get('status') == 'failed'):
        return render_error(body)
    answer = _public_answer_text(body)
    source_text = _sources(body)
    if not answer and source_text:
        return REVIEW_INCOMPLETE_MESSAGE + '\n\n' + source_text
    if not answer:
        return REVIEW_INCOMPLETE_MESSAGE
    text = answer
    if (body.get('assembly',{}).get('term_agent') or {}).get('scenario_context'):
        text = '**가정 분기의 검토 결과입니다. 실제 사건과 승인 규칙은 변경하지 않았습니다.**\n\n' + text
    review = _review_explanation_text(body)
    if review: text += '\n\n' + review
    graph = _judgment_graph_html(flow or _judgment_flow(body))
    if graph: text += '\n\n'+graph
    if source_text: text += '\n\n'+source_text
    unread = _unread_cards(body)
    if unread: text += '\n\n' + unread
    judgments = _judgment_html(body)
    if judgments: text += '\n\n' + judgments
    return text


def _for_markdown(text):
    # Keep code fences and the generated nested HTML intact. In particular,
    # changing the generated image or nested toggle markup breaks rendering.
    pieces = re.split(r'(<!-- GENOS_COMPARISON_START -->.*?(?:<!-- GENOS_COMPARISON_END -->|$)|<!-- GENOS_SOURCES_START -->.*?<!-- GENOS_SOURCES_END -->|<!-- GENOS_UNREAD_START -->.*?<!-- GENOS_UNREAD_END -->|<!-- GENOS_JUDGMENT_GRAPH_START -->.*?<!-- GENOS_JUDGMENT_GRAPH_END -->|<!-- GENOS_JUDGMENT_VIEW_START -->.*?<!-- GENOS_JUDGMENT_VIEW_END -->|```[^\n]*\n.*?(?:\n```|$)|(?:^|(?<=\n))\|[^\n]*\|(?:\n\|[^\n]*\|)*)', text, flags=re.S)
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
    await display._flush_source_reads()
    flow = _judgment_flow(body, display.flow_events)
    answered = bool(_public_answer_text(body)) and not (
        isinstance(body.get('_gateway_status'), int) and body['_gateway_status'] >= 400)
    result = {
        'schema_version': 'genos-workflow-display-v1', 'producer': 'main_workflow',
        'request_id': request_id,
        'display_policy_revision': DISPLAY_POLICY_REVISION,
        'response_sha256': _workflow_display_digest({k: v for k, v in body.items() if k != 'workflow_display'}),
        'text': _for_markdown(render(body, flow=flow)),
        'answer_status': _completion_answer_status(body, answered),
        'judgment_display_revision': JUDGMENT_DISPLAY_REVISION,
        'progress_display_revision': PROGRESS_DISPLAY_REVISION,
        'answer_display_revision': ANSWER_DISPLAY_REVISION,
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
    if (value.get('display_policy_revision') != DISPLAY_POLICY_REVISION
            or value.get('schema_version') != 'genos-workflow-display-v1'
            or value.get('producer') != 'main_workflow'
            or value.get('request_id') != request_id
            or value.get('judgment_display_revision') != JUDGMENT_DISPLAY_REVISION
            or value.get('progress_display_revision') != PROGRESS_DISPLAY_REVISION
            or value.get('answer_display_revision') != ANSWER_DISPLAY_REVISION
            or not isinstance(value.get('text'), str)):
        return None
    if value.get('response_sha256') != _workflow_display_digest({k: v for k, v in body.items() if k != 'workflow_display'}):
        return None
    if value.get('content_sha256') != _workflow_display_digest({k: v for k, v in value.items() if k != 'content_sha256'}):
        return None
    return value


async def _run_workflow_stream(data, payload):
    """Explicit workflow execution uses the same SSE and cards as chat questions."""
    display = _ChatProgress(data)
    ident = data['request_id']
    await display.progress({'schema_version': 'rag-progress-v1', 'request_id': ident,
        'kind': 'phase', 'label': '요청 확인',
        'basis': {'kind': 'WORKFLOW', 'name': 'workflow.prepare.started'}})
    try:
        body = await _stream_code_serving('', data, display, payload=payload)
        rendered = await workflow_display_result(body, display.flow_events, request_id=ident)
        result = {k: rendered[k] for k in ('text', 'answer_status')}
        result.update(request_id=ident, run_id=body.get('run_id'), basis_result=body)
        await display.finish(result['text'], failed=result['answer_status'] in {'failed', 'error'})
    except Exception as exc:
        _log_event('workflow.request.crashed', level='ERROR', request_id=ident,
                   error_type=type(exc).__name__, traceback=traceback.format_exc())
        result = {'request_id': ident, 'answer_status': 'failed',
                  'text': render_error({'request_id': ident}, exc=exc)}
        await display.finish(result['text'], failed=True)
    if display.blocks:
        result['agentFlowExecutedData'] = list(display.blocks)
    result['code_serving_transport'] = dict(display.transport)
    return result


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
    if operation in {'BASIS_LINKS_LIST','BASIS_LINKS_PROPOSE','BASIS_LINKS_REVIEW','BASIS_LINKS_HISTORY','BASIS_MIGRATION_STATUS','WORKFLOW_RUN','WORKFLOW_STATUS','WORKFLOW_RESUME'} or data.get('workflow_id')=='internal_basis_discovery_workflow':
        selected=operation or 'WORKFLOW_RUN'
        payload={k:v for k,v in data.items() if k in ('request_id','session_id','team_id','question','workflow_id','input','use_llm','document_ids','as_of','run_id','expected_revision','link_id','migration_id','internal_document_id','json')}
        payload['API_TYPE']=selected
        if selected.startswith('WORKFLOW_'):
            payload.setdefault('session_id',_session_id(data))
            if 'TEAM_ID' in os.environ:payload['team_id']=os.environ['TEAM_ID']
            if isinstance(payload.get('json'),dict):
                payload['json']={**payload['json']}
                for key in ('session_id','team_id','request_id'):
                    if key in payload:
                        if key=='team_id' and 'TEAM_ID' in os.environ and payload['json'].get(key,payload[key])!=payload[key]:
                            raise ValueError('워크플로우 팀과 요청의 team_id가 다릅니다.')
                        payload['json'].setdefault(key,payload[key])
            if selected == 'WORKFLOW_RESUME':
                # The transport request ID belongs to the new delivery, while
                # the saved workflow request/budget must remain immutable.
                payload['json'] = {k:v for k,v in payload.get('json', payload).items()
                                   if k not in {'API_TYPE', 'request_id'}}
        if selected in {'WORKFLOW_RUN', 'WORKFLOW_RESUME'}:
            return await _run_workflow_stream(data, payload)
        response=await asyncio.to_thread(_post_code_serving,payload)
        value=response.get('body',response) if isinstance(response,dict) else {}
        text=(_for_markdown(render(value)) if value.get('response_schema') == 'workflow-result-v1'
              else (value.get('answer') or {}).get('text'))
        if not text:
            if selected=='BASIS_LINKS_REVIEW':text='근거 관계 처리: '+str(value.get('status','미확인'))+'\n'+json.dumps(value.get('items',[]),ensure_ascii=False)
            else:text=json.dumps(value,ensure_ascii=False,indent=2)
        return {'text':text,'answer_status':value.get('status','completed'),'request_id':request_id,'basis_result':value}
    question = _extract_question(data)
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
    # Show preparation before the AD preflight can import/warm the backend.
    # It is a workflow status, not a completed agent judgment.
    await display.progress({'schema_version': 'rag-progress-v1',
        'request_id': request_id, 'kind': 'phase',
        'label': '준비 중 · 자료와 요청 설정을 확인하고 있습니다',
        'basis': {'kind': 'WORKFLOW', 'name': 'workflow.prepare.started'},
        'elapsed_ms': int((time.perf_counter() - started) * 1000)})
    if question:
        try:
            probe=unwrap(await asyncio.to_thread(_post_code_serving, {
                'API_TYPE':'AD_PROBE','question':question,'request_id':request_id,
                'ad_session_id':str(data.get('chatId') or data.get('chat_id') or data.get('sessionId') or data.get('session_id') or ''),
                'ad_channel':_ad_channel(data)}))
            if (probe.get('answer_status') in {'failed','error'}
                    or isinstance(probe.get('_gateway_status'),int) and probe['_gateway_status'] >= 400):
                result = {'text':render_error({**probe,'request_id':request_id}),
                          'answer_status':'failed','request_id':request_id}
                await display.finish(result['text'], failed=True)
                return result
            if probe.get('response_schema')=='ad-mode-v1':
                result = {**_ad_result(probe),'request_id':request_id}
                await display.finish(result.get('text', ''))
                return result
        except Exception as exc:
            # Cannot establish the mode: do not risk sending an admin turn to RAG.
            if _SYSTEM_LOGS is not None:
                if isinstance(exc, urllib.error.HTTPError):
                    _raw_http_error(exc, request_id)
                else:
                    _SYSTEM_LOGS.write("workflow.errors.raw.log", (
                        "request_id=" + request_id + " AD_PROBE\n" + traceback.format_exc()).encode("utf-8"))
            failure = {'text':render_error({'request_id':request_id},exc=exc),'answer_status':'failed','request_id':request_id}
            await display.finish(failure['text'], failed=True)
            if display.blocks:
                failure['agentFlowExecutedData'] = list(display.blocks)
            return failure
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
            "text": render_error({**failure,'_gateway_status':exc.code,'request_id':request_id},question=question,exc=exc),
            "answer_status": "failed",
            "failure_kind": "http_error",
            "http_status": exc.code,
            "code_serving_transport": dict(display.transport),
            "workflow_revision": WORKFLOW_REVISION,
            "tm_total": round(time.perf_counter() - started, 3),
            "session_id": session_id,
            "request_id": request_id,
        }
        # Full diagnostics remain in logs; the chat gets the short public notice.
        await display.finish(failed["text"], failed=True)
        if display.blocks:
            failed["agentFlowExecutedData"] = display.blocks
        return failed
    except QueryModeError as exc:
        await display.finish(str(exc), failed=True)
        return {"text": str(exc), "answer_status": "invalid_input", "request_id": request_id}
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
                'detail':str(exc),'traceback':traceback.format_exc()},question=question,exc=exc),
            "answer_status": "failed",
            "failure_kind": "client_exception",
            "workflow_revision": WORKFLOW_REVISION,
            "code_serving_transport": dict(display.transport),
            "tm_total": round(time.perf_counter() - started, 3),
            "session_id": session_id,
            "request_id": request_id,
        }
        await display.finish(failed["text"], failed=True)
        if display.blocks:
            failed["agentFlowExecutedData"] = display.blocks
        return failed

    try:
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
                'schema_version', 'producer', 'response_sha256', 'content_sha256', 'display_policy_revision')}
        await display.finish(text, failed=result['answer_status'] in {'failed', 'error'})
        result['workflow_progress_delivery'] = {
            'revision': LIVE_PROGRESS_REVISION, 'mode': display.mode,
            'channel': 'workflow-main_socketio', 'socket_client_id_present': bool(display.sid),
            'emitted_card_events': display.emitted_card_events,
            'socket_error_type': display.socket_error_type,
        }
        if display.blocks:
            result["agentFlowExecutedData"] = display.blocks
        if (server_display and display.show_progress and not display.emitted_card_events
                and server_display.get('agentFlowExecutedData')):
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
    except Exception as exc:
        _log_event('workflow.display.failed', level='ERROR', request_id=request_id,
                   error_type=type(exc).__name__, traceback=traceback.format_exc())
        result = {'text':render_error({'request_id':request_id},exc=exc),
                  'answer_status':'failed','request_id':request_id}
        await display.finish(result['text'], failed=True)
        return result



async def run(data):
    """GENOS 워크플로우 규약: 완성된 답변을 ``text`` dict로 한 번 반환한다.

    현장 GENOS 테스트 런타임은 async generator의 token/end 문자열을
    최종 워크플로우 결과로 해석하지 않는다. 기준 브랜치처럼 단일
    dictionary를 반환해 코드 서빙이 준 검증된 답변을 그대로 전달한다.
    """
    data = dict(data) if isinstance(data, dict) else {}
    data['request_id'] = str(data.get('request_id') or data.get('messageId') or uuid.uuid4().hex)
    _log_event('workflow.entry.received', request_id=data['request_id'],
               input_keys=sorted(str(key) for key in data))
    try:
        return await _run_once(data)
    except Exception as exc:
        ident = data.get('request_id') if isinstance(data,dict) else None
        safe = public_failure(ident,exc=exc)
        _log_event('workflow.entry.failed', level='ERROR', request_id=safe['request_id'],
                   error_type=type(exc).__name__, traceback=traceback.format_exc())
        return {'text':render_error(safe),'answer_status':'failed','request_id':safe['request_id']}


def _review_explanation_text(body, *, diagnostics=False):
    """Show failed checks and follow-up instructions without private diagnostics."""
    if not diagnostics and (_source_reply_has_originals(body) or _guided_reply_text(body) is not None):
        # The conversational answer already contains the questions and action.
        # Keep the complete diagnostic projection available on explicit request.
        return ''
    agent = (body.get('assembly') or {}).get('term_agent') or {}
    view = agent.get('review_explanation')
    if not isinstance(view, dict) or view.get('schema_version') != 'review-explanation-v1':
        return ''
    if _workflow_display_digest({k:v for k,v in view.items() if k != 'content_sha256'}) != view.get('content_sha256'):
        return ''
    from html import escape
    def safe(value):
        text=escape(str(value)).replace('|', '&#124;').replace('\n', ' ')
        return re.sub(r'([\\`*_\[\]()#!~])', r'\\\1', text)
    if not diagnostics:
        facts = [action for action in view.get('actions', [])
                 if action.get('kind') == 'REQUEST_FACT' and action.get('actor') == 'USER'
                 and action.get('enabled') and action.get('fact_name')]
        checks = list(dict.fromkeys(check['reason'] for check in view.get('failed_checks', [])
                      if isinstance(check, dict) and isinstance(check.get('reason'), str) and check['reason'].strip()))
        pending = [item for item in view.get('items', []) if item.get('kind') == 'REVIEW'
                   and item.get('next_action') == 'REVIEW_AGAIN' and item.get('reason')]
        if not checks and pending:
            checks = list(dict.fromkeys(item['reason'] for item in pending))
        lines = ['**답변 검토에서 실패한 부분**', '', *('- '+safe(reason) for reason in checks)] if checks else []
        if checks:
            lines += ['', '이 실패만으로 원문이 없거나 질문이 잘못됐다는 뜻은 아닙니다.']
        if any(action.get('kind') == 'REVIEW_AGAIN' and action.get('item_id') == 'final-review'
               and action.get('enabled') for action in view.get('actions', [])):
            lines += ['', '**같은 대화에서 이어서 요청하기**', '',
                      '이 대화에 `검토 다시 하기`를 보내면 이미 확보한 원문을 재사용해 직전 답변을 다시 검토합니다.']
        if facts:
            lines += ['', '**추가로 필요한 정보**', '', *('- '+safe(action['fact_name']) for action in facts)]
        return '\n'.join(lines + _scenario_comparison_lines(agent, safe)).strip()
    lines = ['**검토 상태: '+safe(view['outcome'])+'**', '', '| 대상 | 자료 확보 | 최종 검토 | 이유·영향 |', '|---|---|---|---|']
    for item in view['items']:
        target = ' / '.join(t.get('coordinate') or t['id'] for t in item.get('targets', [])) or item['id']
        lines.append('| '+ ' | '.join(safe(x) for x in (target,item['acquisition'],item['review'],item['reason']+' '+item['impact']))+' |')
    history = [item for item in view['items'] if item.get('historical_declaration')]
    if history:
        lines += ['', '**기준 사건의 조사 이력 (현재 가정의 요구사항 아님)**']
        for item in history:
            lines.append('- '+safe(item['historical_declaration']))
    if view.get('historical_issues'):
        lines += ['', '**기준 사건의 질문 이력 (현재 가정값은 계산표 참조)**']
        lines.extend('- '+safe(text) for text in view['historical_issues'])
    for check in view.get('failed_checks', []):
        lines.append('- 검토 실패: '+safe(check['reason'])+' '+safe(check['impact']))
    lines += ['', '다음 행동:']
    for number, action in enumerate(view['actions'], 1):
        lines.append(str(number)+'. '+safe(action['label'])+' — '+safe(action.get('actor','USER'))+
            (' · '+safe(action['fact_name']) if action['enabled'] and action.get('fact_name') else '' if action['enabled'] else ' · '+safe(action['unavailable_reason'])))
    ontology = view['ontology']
    lines += ['', '온톨로지: '+safe(ontology['status'])+' · 채택 연결: '+safe(ontology['adoption'])]
    for bundle in ontology.get('bundles', []):
        adoption={'ADOPTED':'최종 주장에 채택 연결 확인','NOT_USED':'최종 주장에 미사용','NOT_RECORDED':'최종 주장 채택 미확인'}.get(bundle.get('adoption'),'채택 미확인')
        lines.append('- '+safe(bundle.get('bundle_id') or '지식 묶음')+': '+adoption)
        for use in bundle.get('claim_uses', []):
            lines.append('  - 주장 '+safe(use['claim_id'])+' ← 경로 '+safe(use['path_id'])+' · 요소 '+safe(', '.join(use['node_ids'])))
        catalog = bundle.get('assembly') or {}
        for source in catalog.get('source_bindings', []):
            anchor=source['anchor']
            lines.append('- 원문: '+safe(anchor.get('label') or anchor['document_id'])+' · 판본 '+safe(anchor['version']))
        for path in catalog.get('paths', []):
            lines.append('- '+safe(path['title'])+' · 목적 '+safe(path['purpose'])+' · 판본 '+safe(catalog['revision'])+' · '+safe(path['status']))
            for node in path['nodes']:
                lines.append('  - '+safe(node['kind'])+': '+safe(node['text']))
            for edge in path['edges']:
                lines.append('  - 관계: '+safe(edge['from'])+' → '+safe(edge['to'])+' · '+safe(edge['type']))
    return '\n'.join(lines + _scenario_comparison_lines(agent, safe))


def _scenario_comparison_lines(agent, safe):
    lines = []
    scenario = agent.get('scenario_comparison')
    if scenario:
        lines += ['', '**가정 비교 — 실제 사건·승인 규칙 유지 / 최종 결론 미확정**', '', '| 항목 | 기준 | 가정 |', '|---|---|---|']
        for key,value in scenario['changes'].items():
            lines.append('| '+safe(key)+' 입력 변경 | 기준 입력 유지 | '+safe(value.get('value'))+' '+safe(value.get('unit',''))+' |')
        for row in scenario['comparisons']:
            lines.append('| '+safe(row['node_id'])+' | '+safe(row['before']['status'])+' | '+safe(row['after']['status'])+' |')
        lines.extend('- '+safe(row.get('reason') or row.get('state')) for row in scenario['unresolved'])
    return lines
