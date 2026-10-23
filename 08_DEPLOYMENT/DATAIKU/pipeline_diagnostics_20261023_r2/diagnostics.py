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
