"""Dependency-free GENOS process diagnostics, with durable local spooling.

Each process owns its output files. NFS writes run in a daemon thread; records
are acknowledged only after fsync and byte verification. Failed transfers keep
their original byte offsets, so recovery can safely repeat an interrupted write.
"""
from __future__ import annotations

import atexit
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import fcntl
import json
import logging
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import threading
import time
import traceback
import uuid

DEFAULT_ROOT = "/nfs-root/diamo/8-agent/logs/system"
REVISION = "genos-system-logging-20261007-r1"
_INSTANCE = None
_INSTALL_LOCK = threading.Lock()


def _json(value):
    return (json.dumps(value, ensure_ascii=False, default=str) + "\n").encode("utf-8")


def _sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _name(value):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,160}", value) or value in {".", ".."}:
        raise ValueError("Invalid diagnostic run/component name")
    return value


def enabled():
    if os.getenv("GENOS_SYSTEM_LOG_ENABLED", "1").lower() in {"0", "false", "off"}:
        return False
    return bool(os.getenv("GENOS_SYSTEM_LOG_DIR") or
                os.getenv("SEMANTIC_LLM_BACKEND", "").lower() == "genos" or
                any(os.getenv(key, "").startswith("/nfs-root/") for key in
                    ("GENOS_RUNTIME_DIR", "GENOS_DATA_ROOT", "GENOS_GENERATION")))


def environment():
    # Preserve useful configuration facts without dumping secrets or arbitrary
    # environment values. Raw error/output files remain internal original data.
    keys = ("GENOS_MAIN_MODE", "GENOS_CHAT_TRANSPORT", "SEMANTIC_LLM_BACKEND",
            "GENOS_GENERATION", "GENOS_DATA_ROOT", "GENOS_RUNTIME_DIR", "GENOS_STATE_DIR",
            "GENOS_SYSTEM_LOG_DIR", "GENOS_LOG_LEVEL", "GENOS_SYSTEM_LOG_LEVEL",
            "PORT", "UVICORN_PORT", "SERVER_PORT", "GENOS_PORT")
    root = Path(__file__).resolve().parent
    fingerprints = {}
    for name in ("main.py", "main_router.py", "service.py", "genos_diagnostics.py",
                 "genos_log_runner.py", "00_SYSTEM/PIPELINE.json"):
        path = root / name
        if path.is_file():
            fingerprints[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"revision": REVISION, "python_executable": sys.executable,
            "python_version": sys.version, "cwd": str(Path.cwd()), "code_root": str(root),
            "hostname": socket.gethostname(), "pid": os.getpid(),
            "configured_environment": {key: os.environ[key] for key in keys if key in os.environ},
            "environment_names": sorted(key for key in os.environ if key.startswith(("GENOS_", "SEMANTIC_"))),
            "code_sha256": fingerprints, "serving_revision": os.getenv("GENOS_CODESERVING_REVISION"),
            "configuration_is_actual_runtime_binding": False}


@contextmanager
def _transfer_lock(spool):
    with (spool / "transfer.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def transfer(spool):
    """Recover one spool, including after a killed container if it was retained."""
    spool = Path(spool)
    with _transfer_lock(spool):
        _transfer(spool)


def _transfer(spool):
    info = json.loads((spool / "spool.json").read_text())
    target = Path(info["target"])
    if not target.is_absolute():
        raise ValueError("Diagnostic target must be absolute")
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    for folder in sorted(spool.glob("*.stream")):
        filename = _name(folder.name.removesuffix(".stream"))
        pending = sorted(folder.glob("*.pending"))[:256]
        if not pending:
            continue
        destination = target / filename
        if destination.is_symlink():
            raise ValueError("Diagnostic output symlink is forbidden")
        batches = [(path, int(path.stem), path.read_bytes()) for path in pending]
        # Repeat writes at the SAME byte offset, never append recovered data
        # blindly. An interrupted NFS write cannot duplicate the traceback.
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        with os.fdopen(os.open(destination, flags, 0o600), "r+b") as output:
            for path, offset, raw in batches:
                output.seek(offset)
                output.write(raw)
            output.flush()
            os.fsync(output.fileno())
            for path, offset, raw in batches:
                output.seek(offset)
                if output.read(len(raw)) != raw:
                    raise OSError("NFS diagnostic byte verification failed: " + filename)
        for path, offset, raw in batches:
            path.unlink()
        _sync_directory(folder)


class Session:
    def __init__(self, component, *, root=None, spool_root=None, run_id=None):
        self.run_id = _name(run_id or os.getenv("GENOS_LOG_RUN_ID") or
                            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12])
        self.prefix = _name(component) + "-" + str(os.getpid()) + "-" + uuid.uuid4().hex[:8]
        self.target = Path(root or os.getenv("GENOS_SYSTEM_LOG_DIR") or DEFAULT_ROOT) / self.run_id
        if not self.target.is_absolute():
            raise ValueError("GENOS_SYSTEM_LOG_DIR must be absolute")
        local = Path(spool_root or os.getenv("GENOS_LOG_SPOOL_DIR") or
                     Path(tempfile.gettempdir()) / ("8-agent-system-logs-" + str(os.getuid())))
        if not local.is_absolute():
            raise ValueError("GENOS_LOG_SPOOL_DIR must be absolute")
        local.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.spool = local / (self.run_id + "-" + self.prefix)
        self.spool.mkdir(mode=0o700)
        with (self.spool / "spool.json").open("wb") as output:
            os.chmod(output.name, 0o600)
            output.write(_json({"revision": REVISION, "target": str(self.target),
                               "prefix": self.prefix, "run_id": self.run_id}))
            output.flush()
            os.fsync(output.fileno())
        _sync_directory(self.spool)
        self.lock = threading.RLock()
        self.offsets = {}
        self.wakeup = threading.Event()
        self.stopping = threading.Event()
        self.last_error = None
        self.local_errors = 0
        self.worker = threading.Thread(target=self._worker, name="genos-nfs-system-log", daemon=True)
        self.write("environment.json", _json(environment()))
        self.event("process.logging.started", component=component, target=str(self.target), spool=str(self.spool))
        self.worker.start()

    def write(self, stream, raw):
        if not raw:
            return
        filename = _name(self.prefix + "-" + stream)
        with self.lock:
            folder = self.spool / (filename + ".stream")
            try:
                folder.mkdir(exist_ok=True, mode=0o700)
                offset = self.offsets.get(filename, 0)
                pending = folder / (f"{offset:020d}.pending")
                temporary = pending.with_suffix(".tmp")
                with temporary.open("wb") as output:
                    os.chmod(temporary, 0o600)
                    output.write(raw)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, pending)
                _sync_directory(folder)
                self.offsets[filename] = offset + len(raw)
                self.wakeup.set()
            except OSError:
                self.local_errors += 1
                self._warn("LOCAL_SPOOL_FAILED", traceback.format_exc())

    @staticmethod
    def _warn(event, detail):
        # Avoid recursion through sys.stderr's tee and logging handlers.
        try:
            os.write(2, ("GENOS_SYSTEM_LOG " + event + "\n" + detail + "\n").encode("utf-8", "backslashreplace"))
        except OSError:
            pass

    def event(self, event, **fields):
        self.write("events.jsonl", _json({"ts": datetime.now(timezone.utc).isoformat(),
                                         "event": event, "pid": os.getpid(), **fields}))

    def _worker(self):
        while True:
            try:
                transfer(self.spool)
                if self.last_error:
                    self.event("nfs.logging.recovered", previous_error=self.last_error)
                self.last_error = None
            except Exception:
                detail = traceback.format_exc()
                if detail != self.last_error:
                    self._warn("NFS_PENDING spool=" + str(self.spool), detail)
                    self.event("nfs.logging.failed", traceback=detail, spool=str(self.spool))
                self.last_error = detail
            if self.stopping.is_set():
                if self.pending() and self.last_error is None:
                    continue
                return
            self.wakeup.wait(1)
            self.wakeup.clear()
            # Batch chatty logs; NFS is never touched by the request thread.
            self.stopping.wait(0.2)

    def pending(self):
        return len(list(self.spool.glob("*.stream/*.pending")))

    def drain(self, timeout=3):
        deadline = time.monotonic() + timeout
        self.wakeup.set()
        while self.pending() and time.monotonic() < deadline:
            time.sleep(0.02)
        return self.pending() == 0 and self.local_errors == 0

    def close(self, timeout=3):
        complete = self.drain(timeout)
        self.stopping.set()
        self.wakeup.set()
        self.worker.join(timeout=0.25)
        return complete


class _Tee:
    def __init__(self, original, session, stream):
        self.original, self.session, self.stream = original, session, stream

    def write(self, value):
        self.session.write(self.stream, value.encode(getattr(self.original, "encoding", None) or "utf-8", "backslashreplace"))
        return self.original.write(value)

    def flush(self):
        self.original.flush()

    def __getattr__(self, name):
        return getattr(self.original, name)


class RawHandler(logging.Handler):
    _genos_system_capture = True

    def __init__(self, session):
        super().__init__()
        self.session = session

    def emit(self, record):
        try:
            line = (datetime.fromtimestamp(record.created, timezone.utc).isoformat() + " " +
                    record.levelname + " " + record.name + " " + record.getMessage() + "\n")
            fields = getattr(record, "fields", None)
            if fields:
                line += json.dumps(fields, ensure_ascii=False, default=str) + "\n"
            if record.exc_info:
                line += "".join(traceback.format_exception(*record.exc_info))
            elif record.exc_text:
                line += record.exc_text + "\n"
            if record.stack_info:
                line += record.stack_info + "\n"
            self.session.write("python.raw.log", line.encode("utf-8", "backslashreplace"))
        except Exception:
            self.session._warn("PYTHON_CAPTURE_FAILED", traceback.format_exc())


def install(component="python"):
    """Call before importing FastAPI/runtime to capture import/environment failures."""
    global _INSTANCE
    if os.environ.get('DP','').strip().lower() in ('oracle','1','true'):
        # Oracle serving has no local data/log spool. Structured stdout and
        # explicitly configured external request journals remain available.
        return None
    if not enabled():
        return None
    with _INSTALL_LOCK:
        if _INSTANCE is not None:
            return _INSTANCE
        try:
            session = Session(component)
        except Exception:
            Session._warn("INITIALIZATION_FAILED", traceback.format_exc())
            return None
        _INSTANCE = session
        if os.getenv("GENOS_LOG_CAPTURED") != "1":
            sys.stdout = _Tee(sys.stdout, session, "stdout.log")
            sys.stderr = _Tee(sys.stderr, session, "stderr.log")
        handler = RawHandler(session)
        level = getattr(logging, os.getenv("GENOS_SYSTEM_LOG_LEVEL", "INFO").upper(), logging.INFO)
        handler.setLevel(level)
        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(min(root.level, level))
        # genos deliberately does not propagate to the Python root logger.
        logging.getLogger("genos").addHandler(handler)
        original = sys.excepthook
        def exception_hook(kind, value, tb):
            session.write("exceptions.raw.log", "".join(traceback.format_exception(kind, value, tb)).encode("utf-8"))
            original(kind, value, tb)
        sys.excepthook = exception_hook
        thread_original = threading.excepthook
        def thread_hook(args):
            session.write("exceptions.raw.log", "".join(traceback.format_exception(
                args.exc_type, args.exc_value, args.exc_traceback)).encode("utf-8"))
            thread_original(args)
        threading.excepthook = thread_hook
        atexit.register(session.close)
        return session
