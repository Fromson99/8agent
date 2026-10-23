"""Paste this whole file into a Dataiku Python notebook in LEGAL_RAG."""
# First prepare the files. Then set ACTION = "run" after configuring the
# project variables described in GUIDE.txt. Reuse WORK_DIR and JOB_NAME to resume.
_previous_settings = getattr(globals().get("run"), "__defaults__", None)
ACTION = "prepare"                    # prepare / check / run
FOLDER_NAME = "LEGAL_PIPELINE_WORKSPACE"
WORK_DIR = "./legal_pipeline_work"     # writable local scratch; durable state in managed folder
JOB_NAME = "run_20261023_01"
# Keep the actual current work/job names when replacing a cell in this notebook.
# After a kernel restart, set FOLDER_NAME / WORK_DIR / JOB_NAME above to the same
# values shown in the previous notebook output. Never invent a new name for BUSY.
if isinstance(_previous_settings, tuple) and len(_previous_settings) == 4:
    FOLDER_NAME, WORK_DIR, JOB_NAME = _previous_settings[1:]


import fcntl
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import time
import zipfile

PROJECT_KEY = "LEGAL_RAG"
CLIENT_NAME = "DATAIKU_PIPELINE_CLIENT_20261023_R1"
CLIENT_SHA256 = "9d553a32d460b6ddfe4b73a4186dea5501a0b878512ccd622fa7cbae631b9bb3"
CLIENT_BYTES = 224607
ARCHIVES = ("RAW_INPUT.zip", "PIPELINE_SUPPORT.zip")
CHUNK = 1024 * 1024
RESERVE = 512 * CHUNK


class RunError(RuntimeError):
    pass


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def safe_path(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise RunError("SYMLINK_REFUSED: " + str(path))
    return path


def event(work, phase, **fields):
    with safe_path(work / "runner-events.jsonl").open("a", encoding="utf-8") as stream:
        os.chmod(stream.name, 0o600)
        stream.write(json.dumps({"time": time.time(), "phase": phase, **fields}, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def save_json(path, value):
    path = safe_path(path)
    temp = safe_path(path.with_name(path.name + ".tmp"))
    with temp.open("w", encoding="utf-8") as stream:
        os.chmod(temp, 0o600)
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def read_receipt(folder, remote, name):
    chunks, count = [], 0
    with folder.get_download_stream(remote) as stream:
        while True:
            block = stream.read(min(8192, 65537 - count))
            if not block:
                break
            chunks.append(block)
            count += len(block)
            if count > 65536:
                raise RunError("RECEIPT_TOO_LARGE: " + name)
    raw = b"".join(chunks)
    value = json.loads(raw)
    if (not isinstance(value, dict) or value.get("archive") != name
            or type(value.get("bytes")) is not int or not 0 < value["bytes"] <= 100 * 1024**3
            or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("sha256", "")))):
        raise RunError("RECEIPT_INVALID: " + name)
    return value


def download(folder, remote, destination, expected, size, work):
    destination = safe_path(destination)
    if destination.exists():
        if destination.stat().st_size != size or digest(destination) != expected:
            raise RunError("CACHED_FILE_CHANGED: " + destination.name)
        print("VERIFIED", destination.name, flush=True)
        return
    partial = safe_path(destination.with_name(destination.name + ".partial"))
    # Only this runner's regenerable partial is restarted. Originals, completed
    # downloads and failure events remain unchanged; no automatic retry occurs.
    if partial.exists():
        event(work, "RESTART_DOWNLOAD", file=destination.name,
              previous_bytes=partial.stat().st_size, previous_sha256=digest(partial))
    reclaimable = partial.stat().st_size if partial.exists() else 0
    if shutil.disk_usage(work).free + reclaimable < size + RESERVE:
        raise RunError("DOWNLOAD_CAPACITY: " + destination.name)
    print("DOWNLOAD", destination.name, "bytes=", size, flush=True)
    h, count, last = hashlib.sha256(), 0, time.monotonic()
    with folder.get_download_stream(remote) as source, partial.open("wb") as target:
        os.chmod(partial, 0o600)
        for block in iter(lambda: source.read(CHUNK), b""):
            count += len(block)
            if count > size:
                raise RunError("DOWNLOAD_SIZE: " + destination.name)
            if shutil.disk_usage(work).free < RESERVE + len(block):
                raise RunError("DOWNLOAD_CAPACITY: " + destination.name)
            target.write(block)
            h.update(block)
            if time.monotonic() - last >= 15:
                print("DOWNLOAD", destination.name, count, "/", size, flush=True)
                last = time.monotonic()
        target.flush()
        os.fsync(target.fileno())
    if count != size or h.hexdigest() != expected:
        raise RunError("DOWNLOAD_HASH_OR_SIZE: " + destination.name)
    os.replace(partial, destination)
    event(work, "DOWNLOADED", file=destination.name, bytes=count, sha256=expected)


def install_client(archive, work):
    code = safe_path(work / "code")
    code.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        prefix = CLIENT_NAME + "/"
        if len(names) != len(set(names)):
            raise RunError("CODE_DUPLICATE_MEMBER")
        for item in z.infolist():
            name, path = item.filename, PurePosixPath(item.filename)
            if (not name.startswith(prefix) or str(path) != name or ".." in path.parts
                    or "\\" in name or ":" in name or item.is_dir()
                    or stat.S_ISLNK(item.external_attr >> 16) or item.file_size > 8 * CHUNK):
                raise RunError("CODE_UNSAFE_MEMBER")
        # The entire uploaded client ZIP was checked against the delivery SHA.
        # Check every extracted byte again before allowing imports in this kernel.
        for item in z.infolist():
            data = z.read(item)
            target = safe_path(code / item.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if target.read_bytes() != data:
                    raise RunError("INSTALLED_CODE_CHANGED: " + item.filename)
            else:
                temp = safe_path(target.with_name(target.name + ".install-partial"))
                with temp.open("wb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temp, target)
    return code / CLIENT_NAME




def load_client(code):
    # A notebook can keep old modules alive even after sys.path changes.
    # Do not silently mix another loader release with these verified files.
    prefixes = ("transport", "restore_inputs", "dataiku_run", "managed_job", "lawrag", "semantic_runtime")
    for name, module in list(sys.modules.items()):
        if any(name == p or name.startswith(p + ".") for p in prefixes):
            source = getattr(module, "__file__", None)
            if not source or not Path(source).resolve().is_relative_to(code.resolve()):
                raise RunError("KERNEL_RESTART_REQUIRED: 다른 버전이 메모리에 있습니다. 커널 재시작 후 다시 실행하세요.")
    sys.path.insert(0, str(code))
    restore = importlib.import_module("restore_inputs")
    client = importlib.import_module("dataiku_run")
    _observe_client(client)
    return restore, client


"""Embedded into the R2 notebook runner; no imports from an unverified directory."""
import functools
import io
import traceback
import uuid

DIAGNOSTIC_REVISION = "mapped-notebook-diagnostics-20261023-r2"


def _redact(value, secrets=()):
    text = str(value)
    for secret in sorted({s for s in secrets if isinstance(s, str) and s}, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    text = re.sub(r"(?i)(bearer\s+)[^\s,;\"']+", r"\1[REDACTED]", text)
    text = re.sub(r"(?im)(\b(?:set-cookie|cookie)\s*:\s*)[^\r\n]*", r"\1[REDACTED]", text)
    text = re.sub(
        r'''(?ix)(["']?(?:authorization|cookie|set-cookie|job_token|token|password|passwd|secret|api_key)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}]+)''',
        r"\1[REDACTED]", text,
    )
    text = re.sub(r"(https?://)[^/\s@]+@", r"\1[REDACTED]@", text)
    return "".join(c if c in "\n\t" or ord(c) >= 32 else "?" for c in text)


def _exception_chain(exc):
    seen = set()
    for _ in range(12):
        if not isinstance(exc, BaseException) or id(exc) in seen:
            return
        seen.add(id(exc))
        yield exc
        exc = exc.__cause__ or exc.__context__


def _observe_client(module):
    original = module.Client.call
    if getattr(original, "_diagnostic_revision", None) == DIAGNOSTIC_REVISION:
        return

    @functools.wraps(original)
    def observed(self, operation, **fields):
        try:
            return original(self, operation, **fields)
        except Exception as exc:
            # Annotate, never retry or alter the API result/exception.
            exc._pipeline_operation = operation
            exc._pipeline_job_id = fields.get("job_id")
            exc._pipeline_secrets = (self.token, fields.get("job_token"))
            raise

    observed._diagnostic_revision = DIAGNOSTIC_REVISION
    module.Client.call = observed


def _next_step(code):
    if code == "BUSY":
        return ("이전 작업이 RELEASED가 아니어서 새 작업 접수가 거절됐습니다. "
                "pipeline_jobs()로 현재 상태를 확인하세요. 실패 작업의 원문·로그 보존 후 "
                "해제가 필요합니다. 작업 이름 변경이나 run 반복으로 해결되지 않습니다.")
    if code in {"INSTANCE_CHANGED", "JOB_LOST", "CODE_BINDING_CHANGED", "JOB_CODE_CHANGED", "DEPLOYED_CODE_MISMATCH"}:
        return "기존 작업·배포 리비전·코드 결속을 확인하세요. 상태나 해시를 고쳐 우회하지 마세요."
    if code in {"INPUT_BINDING_CHANGED", "JOB_BINDING_CHANGED", "INPUT_CHANGED"}:
        return "기존 작업 기록을 보존하세요. 실제 입력이 바뀐 경우에만 새 WORK_DIR/JOB_NAME으로 시작합니다."
    if code in {"HTTP_ERROR", "TRANSPORT_UNCERTAIN"}:
        return "HTTP 상태와 원래 전송 오류를 확인하세요. 접수 여부를 확인하기 전 새 작업을 만들지 마세요."
    if "BUDGET" in code or "DEADLINE" in code:
        return "기존 작업의 기한·사용 예산을 확인하세요. 재실행이나 새 이름으로 예산을 초기화하지 마세요."
    if code == "RUNNING":
        return "같은 작업 폴더를 사용하는 실행이 끝났는지 확인하세요. 동시에 실행하지 마세요."
    return "아래 상세 오류·호출·단계와 저장된 진단을 확인하세요. 성공 처리하거나 자동 재시도하지 않았습니다."


def _read_small_json(path):
    path = safe_path(path)
    with path.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("DIAGNOSTIC_STATE_TOO_LARGE")
    return json.loads(raw)


def report_failure(exc, *, work, action, job_name, folder=None, phase=None):
    chain = list(_exception_chain(exc))
    secrets = []
    for item in chain:
        secrets.extend(getattr(item, "_pipeline_secrets", ()))
    try:
        import dataiku
        variables = dataiku.get_custom_variables()
        secrets.extend(v for k, v in variables.items()
                       if re.search(r"TOKEN|PASSWORD|PASSWD|SECRET|COOKIE|API_KEY", k, re.I))
    except Exception:
        pass  # The original failure still reports if project settings cannot be read.
    state, state_error = {}, None
    try:
        state_path = safe_path(Path(work) / "jobs" / job_name / "client.json")
        if state_path.is_file():
            state = _read_small_json(state_path)
            secrets.append(state.get("job_token"))
    except Exception as state_exc:
        state_error = type(state_exc).__name__
    clean = lambda value: _redact(value, secrets)
    operation = next((getattr(e, "_pipeline_operation", None) for e in chain
                      if getattr(e, "_pipeline_operation", None)), None)
    code = None
    for item in chain:
        match = re.match(r"PIPELINE_REPLY:\s*([A-Z][A-Z0-9_]{1,79})(?=[:\s]|$)", str(item))
        if match:
            code = match.group(1)
            break
    http = next((getattr(e, "code", None) for e in chain
                 if type(getattr(e, "code", None)) is int and 100 <= e.code <= 599), None)
    if not code:
        match = re.match(r"([A-Z][A-Z0-9_]{1,79})(?=[:\s]|$)", str(exc))
        code = "HTTP_ERROR" if http else (match.group(1) if match else type(exc).__name__)
    entries = []
    for item in chain:
        message = clean(item)
        frames = traceback.extract_tb(item.__traceback__, limit=12)
        entries.append({"type": type(item).__name__, "message": message[:16384],
                        "message_truncated": len(message) > 16384,
                        "frames": [{"file": clean(Path(f.filename).name), "line": f.lineno,
                                    "function": clean(f.name)} for f in frames]})
    remote = state.get("remote") if isinstance(state.get("remote"), dict) else {}
    report = {"revision": DIAGNOSTIC_REVISION, "time": time.time(), "code": code,
              "action": clean(action), "job_name": clean(job_name), "operation": clean(operation or "not reached"),
              "job_id": clean(next((getattr(e, "_pipeline_job_id", None) for e in chain
                                    if getattr(e, "_pipeline_job_id", None)), state.get("job_id", "unknown"))),
              "phase": clean(remote.get("phase") or state.get("phase") or phase or "unknown"),
              "saved_status": clean(state.get("status", "not created")), "state_read_error": state_error,
              "http_status": http, "exceptions": entries, "chain_limit_reached": len(chain) == 12,
              "next_step": _next_step(code), "automatic_retry": False, "success": False}
    print("\nPIPELINE_ERROR", report["code"], flush=True)
    print("ACTION", report["action"], "CALL", report["operation"], "PHASE", report["phase"], flush=True)
    print("JOB_NAME", report["job_name"], "JOB_ID", report["job_id"], "SAVED_STATUS", report["saved_status"], flush=True)
    if http:
        print("HTTP_STATUS", http, flush=True)
    for entry in entries:
        print(entry["type"] + ": " + entry["message"], flush=True)
        if entry["message_truncated"]:
            print("DETAIL_TRUNCATED: 16 KiB per exception", flush=True)
    print("NEXT_STEP", report["next_step"], flush=True)
    name = "error-" + uuid.uuid4().hex + ".json"
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    try:
        target = safe_path(Path(work) / "diagnostics" / name)
        target.parent.mkdir(exist_ok=True, mode=0o700)
        with target.open("xb") as stream:
            os.chmod(target, 0o600)
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        print("DIAGNOSTIC_FILE", str(target), flush=True)
    except Exception as save_exc:
        print("DIAGNOSTIC_LOCAL_SAVE_FAILED", type(save_exc).__name__, flush=True)
    if folder is not None:
        try:
            remote_path = "_pipeline/diagnostics/" + job_name + "/" + name
            folder.upload_stream(remote_path, io.BytesIO(raw))
            with folder.get_download_stream(remote_path) as stream:
                check = bytearray()
                while len(check) <= len(raw):
                    block = stream.read(min(65536, len(raw) + 1 - len(check)))
                    if not block:
                        break
                    check.extend(block)
            if bytes(check) != raw:
                raise ValueError("DIAGNOSTIC_READBACK")
            print("DIAGNOSTIC_MANAGED", remote_path, flush=True)
        except Exception as save_exc:
            print("DIAGNOSTIC_MANAGED_SAVE_FAILED", type(save_exc).__name__, flush=True)
    return report


def pipeline_jobs(folder_name=FOLDER_NAME, limit=20):
    """Inspect latest hash-verified checkpoints and STATUS; never release jobs."""
    import dataiku
    if dataiku.default_project_key() != PROJECT_KEY:
        raise RunError("LEGAL_RAG 프로젝트에서 실행하세요.")
    if type(limit) is not int or not 1 <= limit <= 20:
        raise RunError("JOB_INSPECTION_LIMIT: 1..20")
    folder = dataiku.Folder(folder_name, project_key=PROJECT_KEY)
    latest, counts = {}, {}
    pattern = re.compile(r"_pipeline/jobs/([A-Za-z0-9_-]{1,80})/checkpoint-(\d{10})-([0-9a-f]{64})\.json")
    for index, path in enumerate(folder.list_paths_in_partition()):
        if index >= 100000:
            raise RunError("JOB_INSPECTION_PATH_LIMIT")
        match = pattern.fullmatch(path.lstrip("/"))
        if not match:
            continue
        name, seq, sha = match.group(1), int(match.group(2)), match.group(3)
        if name not in latest or seq > latest[name][0]:
            latest[name] = (seq, sha, path); counts[name] = 1
        elif seq == latest[name][0]:
            counts[name] += 1
    if len(latest) > limit:
        raise RunError("JOB_INSPECTION_LIMIT: 작업 " + str(len(latest)) + "개. 범위를 좁혀 확인해야 합니다.")
    variables = dataiku.get_custom_variables()
    module = sys.modules.get("dataiku_run")
    if module is None:
        raise RunError("CLIENT_NOT_LOADED: 먼저 run(action='prepare')로 검증된 클라이언트를 읽으세요.")
    _observe_client(module)
    client = module.Client(variables.get("LEGAL_PIPELINE_URL", ""), variables.get("LEGAL_PIPELINE_TOKEN", ""))
    expected_url = hashlib.sha256(client.url.encode()).hexdigest()
    rows = []
    for name, (_, sha, path) in sorted(latest.items()):
        if counts[name] != 1:
            raise RunError("CONCURRENT_JOB_CHECKPOINT: " + name)
        with folder.get_download_stream(path) as stream:
            raw = bytearray()
            while len(raw) <= 1024 * 1024:
                block = stream.read(min(65536, 1024 * 1024 + 1 - len(raw)))
                if not block:
                    break
                raw.extend(block)
        if len(raw) > 1024 * 1024 or hashlib.sha256(raw).hexdigest() != sha:
            raise RunError("CHECKPOINT_HASH: " + name)
        checkpoint = json.loads(raw)
        binding = checkpoint.get("binding", {})
        if (binding.get("service_url_sha256") != expected_url
                or binding.get("input", {}).get("folder_id") != folder.get_id()
                or binding.get("input", {}).get("project") != PROJECT_KEY
                or binding.get("input", {}).get("client_sha256") != CLIENT_SHA256):
            print("JOB_SKIP_BINDING", name, flush=True)
            continue
        state = checkpoint.get("client")
        if not state:
            print("JOB_NO_CLIENT_STATE", name, flush=True)
            continue
        if state.get("code_sha256") != binding.get("service_code"):
            raise RunError("JOB_CODE_BINDING: " + name)
        auth = {k: state[k] for k in ("job_id", "job_token", "instance", "code_sha256")}
        try:
            status = client.call("STATUS", **auth)
            row = {"job_name": name, "job_id": state["job_id"], "status": status.get("status"),
                   "phase": status.get("phase"), "error": _redact(status.get("error", ""), (client.token, state["job_token"])),
                   "checkpoint": path}
        except Exception as exc:
            row = {"job_name": name, "job_id": state["job_id"], "status": "STATUS_UNCONFIRMED",
                   "error": _redact(exc, (client.token, state["job_token"]))}
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False, indent=2), flush=True)
    print("JOB_INSPECTION_COMPLETE: ACK·삭제·실행 요청 없음. STATUS는 서버의 유실 작업 상태를 갱신할 수 있습니다.", flush=True)
    return rows


def run(action=ACTION, folder_name=FOLDER_NAME, work_dir=WORK_DIR, job_name=JOB_NAME):
    import dataiku
    if action not in {"prepare", "check", "run"}:
        raise RunError("ACTION은 prepare, check, run입니다.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", job_name):
        raise RunError("JOB_NAME에는 영문, 숫자, 밑줄, 하이픈만 사용하세요.")
    if dataiku.default_project_key() != PROJECT_KEY:
        raise RunError("LEGAL_RAG 프로젝트의 Python 노트북에서 실행하세요.")
    work = safe_path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    os.chmod(work, 0o700)
    print("WORK_DIR", str(work), flush=True)
    with safe_path(work / "runner.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RunError("RUNNING: 같은 WORK_DIR에서 이미 실행 중입니다.") from None
        folder = None
        phase = "MANAGED_INPUTS"
        try:
            event(work, "START", action=action, job=job_name, diagnostic_revision=DIAGNOSTIC_REVISION)
            folder = dataiku.Folder(folder_name, project_key=PROJECT_KEY)
            remote = {}
            required = {CLIENT_NAME + ".zip", *ARCHIVES, *(n + ".receipt.json" for n in ARCHIVES)}
            for path in folder.list_paths_in_partition():
                name = path.lstrip("/")
                if name in required:
                    if name in remote:
                        raise RunError("DUPLICATE_UPLOAD: " + name)
                    remote[name] = path
            missing = sorted(required - remote.keys())
            if missing:
                raise RunError("폴더 최상위에 필요한 파일이 없습니다: " + ", ".join(missing))
            receipts = {name: read_receipt(folder, remote[name + ".receipt.json"], name) for name in ARCHIVES}
            binding = {"project": PROJECT_KEY, "folder_id": folder.get_id(), "client_sha256": CLIENT_SHA256,
                       "archives": {n: {k: r[k] for k in ("sha256", "bytes")} for n, r in receipts.items()}}
            marker = safe_path(work / "input-binding.json")
            if marker.exists() and json.loads(marker.read_text()) != binding:
                raise RunError("INPUT_BINDING_CHANGED: 업로드 원본이 변경됐습니다. 새 WORK_DIR와 JOB_NAME을 사용하세요.")
            if not marker.exists():
                save_json(marker, binding)
            upload = safe_path(work / "download"); upload.mkdir(exist_ok=True)
            download(folder, remote[CLIENT_NAME + ".zip"], upload / (CLIENT_NAME + ".zip"),
                     CLIENT_SHA256, CLIENT_BYTES, work)
            code = install_client(upload / (CLIENT_NAME + ".zip"), work)
            restore, client = load_client(code)
            if action == "run":
                variables = dataiku.get_custom_variables()
                for key in ("LEGAL_PIPELINE_URL", "LEGAL_PIPELINE_TOKEN"):
                    if not isinstance(variables.get(key), str) or not variables[key].strip():
                        raise RunError("프로젝트 변수 설정 필요: " + key)
                if not variables["LEGAL_PIPELINE_URL"].startswith("https://"):
                    raise RunError("LEGAL_PIPELINE_URL은 새 파이프라인 코드서빙 HTTPS 주소여야 합니다.")
            for name, receipt in receipts.items():
                save_json(upload / (name + ".receipt.json"), receipt)
                download(folder, remote[name], upload / name, receipt["sha256"], receipt["bytes"], work)
            inputs = safe_path(work / "inputs")
            print("RESTORE_AND_VERIFY: 원문·용어집 해시 검사와 압축 해제 중", flush=True)
            phase = "RESTORE_AND_VERIFY"
            restore.restore(upload, inputs)
            job = safe_path(work / "jobs" / job_name)
            result = {"status": "READY", "input_dir": str(inputs), "job_dir": str(job), "oracle_written": False}
            if action in {"check", "run"}:
                print("PIPELINE: 스키마 검증 → GENOS 비동기 구조화·색인 → Oracle LGL_* 적재·검증", flush=True)
                phase = "SCHEMA_OR_PIPELINE"
                result = client.run_dataiku(inputs, upload / "PIPELINE_SUPPORT.zip", job,
                                           folder=folder, job_name=job_name, input_binding=binding, action=action)
                result = {k: v for k, v in result.items() if k != "identity"}
            event(work, "RESULT", action=action, status=result.get("status"), job=job_name)
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
            return result
        except BaseException as exc:
            try:
                report = report_failure(exc, work=work, action=action, job_name=job_name,
                                        folder=folder, phase=phase)
            except Exception as diagnostic_exc:
                print("DIAGNOSTIC_FAILED", type(diagnostic_exc).__name__,
                      "ORIGINAL_ERROR_TYPE", type(exc).__name__, flush=True)
                report = {"code": type(exc).__name__, "exceptions": [], "next_step": "원래 예외 연결을 보존했습니다."}
            try:
                event(work, "STOPPED", action=action, job=job_name, error_type=type(exc).__name__,
                      error_code=report["code"], next_step=report["next_step"])
            except Exception as logging_error:
                print("LOG_WRITE_FAILED", type(logging_error).__name__, "ORIGINAL_ERROR", report["code"], flush=True)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            detail = "\n".join(e["type"] + ": " + e["message"] for e in report["exceptions"])
            raise RunError(report["code"] + "\n" + detail + "\n" + report["next_step"]) from None


if __name__ == "__main__":
    print("RUNNER_READY", DIAGNOSTIC_REVISION)
    print("FOLDER_NAME", FOLDER_NAME, "WORK_DIR", WORK_DIR, "JOB_NAME", JOB_NAME)
    print("코드 등록 완료. 배치는 자동 실행하지 않았습니다. BUSY 상태 확인: pipeline_jobs()")
