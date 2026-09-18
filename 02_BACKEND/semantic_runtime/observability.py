"""Credential-safe, one-line JSON events for GENOS container logs."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import os
import sys
import time
from typing import Any, Iterator
import uuid


ROOT = "genos"
_CONTEXT: ContextVar[dict[str, Any]] = ContextVar("genos_log_context", default={})
_FORBIDDEN_PARTS = ("TOKEN", "KEY", "PASSWORD", "SECRET", "AUTHORIZATION")
_CONTENT_KEYS = frozenset(
    {"question", "answer", "content", "text", "prompt", "context", "quote", "chunks", "raw"}
)
_CONFIGURED = False


def _redact_secrets(value: str) -> str:
    result = value
    secrets = [
        item
        for name, item in os.environ.items()
        if item and name.upper() != 'STRUCTURE_RECIPE_MAX_TOKENS'
        and any(part in name.upper() for part in _FORBIDDEN_PARTS)
    ]
    for secret in sorted(secrets, key=len, reverse=True):
        result = result.replace(secret, "[REDACTED]")
    return result


def _safe_fields(fields: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in fields.items():
        upper = key.upper()
        if key.lower() in _CONTENT_KEYS or any(part in upper for part in _FORBIDDEN_PARTS):
            continue
        if isinstance(value, str):
            safe[key] = _redact_secrets(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, (list, tuple)):
            safe[key] = [
                _redact_secrets(item) if isinstance(item, str) else item
                for item in value
            ]
        elif isinstance(value, dict):
            safe[key] = _safe_fields(value)
        else:
            safe[key] = str(value)
    return safe


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        payload.update(_safe_fields(getattr(record, "fields", {}) or {}))
        if record.exc_info and record.exc_info[0]:
            payload["exc_type"] = record.exc_info[0].__name__
            payload["traceback"] = _redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure() -> None:
    """Install one stderr handler; GENOS collects stdout/stderr as container logs."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    root = logging.getLogger(ROOT)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    level = os.environ.get("GENOS_LOG_LEVEL", "INFO").strip().upper()
    root.setLevel(getattr(logging, level, logging.INFO))
    root.propagate = False
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure()
    return logging.getLogger(f"{ROOT}.{name}")


def event(
    logger: logging.Logger,
    name: str,
    *,
    level: int = logging.INFO,
    exc_info: bool = False,
    **fields: Any,
) -> None:
    merged = {**_CONTEXT.get(), **fields}
    logger.log(level, name, extra={"fields": merged}, exc_info=exc_info)


def new_request_id(candidate: Any = None) -> str:
    value = str(candidate or "").strip()
    if value and len(value) <= 64 and all(ch.isalnum() or ch in "_.:-" for ch in value):
        return value
    return uuid.uuid4().hex


@contextmanager
def context(**fields: Any) -> Iterator[None]:
    current = _CONTEXT.get()
    token = _CONTEXT.set({**current, **{k: v for k, v in fields.items() if v is not None}})
    try:
        yield
    finally:
        _CONTEXT.reset(token)


@contextmanager
def step(logger: logging.Logger, name: str, **fields: Any) -> Iterator[None]:
    started = time.perf_counter()
    event(logger, "step.started", step=name, **fields)
    try:
        yield
    except Exception:
        event(
            logger,
            "step.failed",
            level=logging.ERROR,
            exc_info=True,
            step=name,
            duration_ms=int((time.perf_counter() - started) * 1000),
            **fields,
        )
        raise
    else:
        event(
            logger,
            "step.finished",
            step=name,
            duration_ms=int((time.perf_counter() - started) * 1000),
            **fields,
        )


def safe_error(exc: BaseException) -> str:
    return _redact_secrets(f"{type(exc).__name__}: {exc}")[:1000]
