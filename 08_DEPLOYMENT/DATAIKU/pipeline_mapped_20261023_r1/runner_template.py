"""Paste this whole file into a Dataiku Python notebook in LEGAL_RAG."""
# First prepare the files. Then set ACTION = "run" after configuring the
# project variables described in GUIDE.txt. Reuse WORK_DIR and JOB_NAME to resume.
ACTION = "prepare"                    # prepare / check / run
FOLDER_NAME = "LEGAL_PIPELINE_WORKSPACE"
WORK_DIR = "./legal_pipeline_work"     # writable local scratch; durable state in managed folder
JOB_NAME = "run_20261023_01"

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
CLIENT_SHA256 = "__CLIENT_SHA256__"
CLIENT_BYTES = __CLIENT_BYTES__
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
    return importlib.import_module("restore_inputs"), importlib.import_module("dataiku_run")


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
        try:
            event(work, "START", action=action, job=job_name)
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
            restore.restore(upload, inputs)
            job = safe_path(work / "jobs" / job_name)
            result = {"status": "READY", "input_dir": str(inputs), "job_dir": str(job), "oracle_written": False}
            if action in {"check", "run"}:
                print("PIPELINE: 스키마 검증 → GENOS 비동기 구조화·색인 → Oracle LGL_* 적재·검증", flush=True)
                result = client.run_dataiku(inputs, upload / "PIPELINE_SUPPORT.zip", job,
                                           folder=folder, job_name=job_name, input_binding=binding, action=action)
                result = {k: v for k, v in result.items() if k != "identity"}
            event(work, "RESULT", action=action, status=result.get("status"), job=job_name)
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
            return result
        except BaseException as exc:
            match = re.match(r"[A-Z][A-Z0-9_]{2,60}(?=[: ]|$)", str(exc))
            error_code = match.group(0) if match else type(exc).__name__
            details = {}
            if isinstance(exc, OSError):
                details = {"errno": exc.errno,
                           "os_reason": os.strerror(exc.errno) if exc.errno is not None else "unknown"}
                if exc.filename:
                    failure_path = Path(os.fsdecode(exc.filename)).absolute()
                    try:
                        details["path_in_work"] = str(failure_path.relative_to(work))
                    except ValueError:
                        details["path_in_work"] = "outside WORK_DIR"
                error_code += " errno=" + str(exc.errno) + " " + details["os_reason"]
            try:
                event(work, "STOPPED", action=action, job=job_name, error_type=type(exc).__name__,
                      error_code=error_code, **details,
                      detail=str(exc) if isinstance(exc, RunError) else "Original exception context retained.")
            except OSError as logging_error:
                print("LOG_WRITE_FAILED errno=", logging_error.errno, "ORIGINAL_ERROR", error_code, flush=True)
            if isinstance(exc, (RunError, KeyboardInterrupt, SystemExit)):
                raise
            raise RunError("중단: " + error_code + ". 원문과 작업 상태를 보존했습니다. 원인을 확인한 뒤 같은 경로에서 재실행하세요.") from None



if __name__ == "__main__":
    PIPELINE_RESULT = run()
