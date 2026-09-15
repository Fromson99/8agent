"""GENOS 채팅 워크플로우 Python 단계.

GENOS 워크플로우 편집기에 이 파일 전체를 붙여 넣고 ``run``을 진입점으로
사용한다. 질문은 코드서빙의 ``ELS_QUERY``로 전달하고, 검증된 RAG 답변은
다시 생성하거나 고쳐 쓰지 않고 화면의 ``text``로 반환한다.
"""

import json
import os
import re
import time
import traceback
import urllib.error
import urllib.request
import uuid


QUESTION_KEYS = ("question", "query", "chatInput", "input", "message", "prompt", "text")
META_KEYS = frozenset(
    {
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
    if isinstance(value, str):
        if value.strip():
            found.append(value)
    elif isinstance(value, dict):
        for key, nested in value.items():
            if key not in META_KEYS:
                _walk(nested, found)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            _walk(nested, found)


def _safe_id(value, fallback):
    cleaned = _UNSAFE_ID.sub("-", str(value or "")).strip("-")[:64]
    return cleaned or fallback


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
        timeout = float(os.getenv("GENOS_CODESERVING_TIMEOUT_SECONDS", "120"))
    except ValueError:
        timeout = 120.0
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


def call_code_serving(question, data):
    endpoint, token, timeout = _settings()
    request_id = str(data.get("request_id") or uuid.uuid4().hex)
    request_body = {
        "API_TYPE": "ELS_QUERY",
        "question": question,
        "channel": "genos-chat",
        "session_id": _session_id(data),
        "user_id": _user_id(data),
        "request_id": request_id,
    }
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


def _answer_text(body):
    answer = body.get("answer")
    if isinstance(answer, dict):
        return str(answer.get("text") or "").strip()
    return str(answer or "").strip()


def _used_source_ids(body):
    answer = body.get("answer")
    if not isinstance(answer, dict):
        return set()
    used = set()
    for claim in answer.get("claims") or []:
        if isinstance(claim, dict):
            used.update(str(item) for item in (claim.get("evidence_ids") or []) if item)
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


def _sources(body):
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


def render(body):
    status = body.get("_gateway_status")
    if isinstance(status, int) and status >= 400:
        return "지금 답변을 만들지 못했습니다. 잠시 후 다시 시도해 주세요."
    answer = _answer_text(body)
    if not answer:
        return "관련 근거를 찾지 못해 답변을 만들지 못했습니다. 질문을 조금 더 구체적으로 입력해 주세요."
    source_text = _sources(body)
    return f"{answer}\n\n{source_text}" if source_text else answer


def _for_markdown(text):
    text = re.sub(r"~", r"\\~", text)
    return re.sub(r"(?<!\n)\n(?!\n)", "\n\n", text)


async def _run_once(data):
    """질문 하나를 처리해 화면에 보낼 텍스트와 관측 필드를 만든다."""
    started = time.perf_counter()
    data = data if isinstance(data, dict) else {}
    request_id = uuid.uuid4().hex
    data = {**data, "request_id": request_id}
    question = _extract_question(data)
    session_id = _session_id(data)
    _log_event(
        "workflow.request.started",
        request_id=request_id,
        session_id=session_id,
        input_keys=sorted(str(key) for key in data),
        question_chars=len(question),
    )
    if not question:
        _log_event("workflow.request.invalid", level="WARNING", request_id=request_id, reason="question_missing")
        return {"text": "질문을 입력해 주세요.", "answer_status": "invalid_input", "request_id": request_id}
    try:
        body = call_code_serving(question, data)
        call_seconds = time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        _log_event(
            "code_serving.request.failed",
            level="ERROR",
            request_id=request_id,
            http_status=exc.code,
            error_type=type(exc).__name__,
            detail=detail,
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        return {
            "text": f"지금 답변을 가져오지 못했습니다. (코드서빙 응답 {exc.code}, 추적 번호: {request_id})",
            "answer_status": "failed",
            "session_id": session_id,
            "request_id": request_id,
        }
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
        return {
            "text": f"지금 답변을 가져오지 못했습니다. (추적 번호: {request_id})",
            "answer_status": "failed",
            "session_id": session_id,
            "request_id": request_id,
        }

    text = _for_markdown(render(body))
    answered = bool(_answer_text(body)) and not (
        isinstance(body.get("_gateway_status"), int) and body["_gateway_status"] >= 400
    )
    result = {
        "text": text,
        "answer_status": "answered" if answered else "not_found",
        "run_id": body.get("run_id"),
        "session_id": session_id,
        "request_id": request_id,
        "history": "not_persisted",
        "tm_code_serving": round(call_seconds, 3),
        "tm_total": round(time.perf_counter() - started, 3),
    }
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
