"""Small, sequential command coordinator over the sealed GENOS basis runners.

No RAG implementation, model retry, approval, or SQLite publication lives here.
"""
import argparse
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import uuid


TERMINAL = {"completed", "partial"}
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
CHUNK = 20
R2_COORDINATOR = "5d74d281d0d3c283cf161f4e56b935ac8bb210d7ddc5610bd5a4348e4edb6da1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def sha(path):
    with plain(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def plain(path):
    path = Path(os.path.abspath(path))
    require(not any(p.is_symlink() for p in (path, *path.parents)), f"심볼릭 링크 경로 거부: {path}")
    return path


def read(path):
    path = plain(path)
    require(path.stat().st_size <= 32 * 1024**2, f"제어 파일 크기 초과: {path}")
    return json.loads(path.read_text("utf-8"))


def checked(path, key):
    value = read(path)
    require(value.get(key) == digest({k: v for k, v in value.items() if k != key}),
            f"계획/상태 해시 불일치: {path}")
    return value


def atomic(path, value, key=None):
    path = plain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if key:
        value = {k: v for k, v in value.items() if k != key}
        value[key] = digest(value)
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        with directory_fd(path.parent) as fd:
            os.fsync(fd)
    finally:
        if temp.exists():
            temp.unlink()


@contextmanager
def directory_fd(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        yield fd
    finally:
        os.close(fd)


def event(path, kind, **fields):
    value = {"at": datetime.now(timezone.utc).isoformat(), "event": kind, **fields}
    with plain(path).open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(value, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps(value, ensure_ascii=False), flush=True)


@contextmanager
def lock(path):
    path = plain(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("다른 간편 조사 명령이 실행 중입니다. 종료 후 다시 실행하세요.") from exc
        yield stream.fileno()


def resources(path):
    available = next(int(line.split()[1]) * 1024 for line in
                     Path("/proc/meminfo").read_text().splitlines()
                     if line.startswith("MemAvailable:"))
    require(available >= 2 * 1024**3, "가용 RAM 2 GiB 미만: 추가 실행을 중단합니다.")
    require(shutil.disk_usage(path).free >= 1024**3, "가용 디스크 1 GiB 미만: 추가 실행을 중단합니다.")


class Runner:
    def __init__(self, root, transfer, spec):
        self.root, self.transfer, self.spec = root, transfer, spec
        self.package = plain(transfer / spec["folder"])
        self.shell = self.package / spec["shell"]
        for name, expected in spec["files"].items():
            require(sha(self.package / name) == expected, f"기존 실행 패키지 해시 불일치: {name}")
        self.identity = {"package": spec["folder"], "files": spec["files"],
                         "checkout_pipeline_sha256": spec["pipeline_sha256"]}
        self.config_sha256 = sha(root / "00_SYSTEM/GENOS_SERVING_PATHS.json")
        self.lock_fd = None

    def call(self, action, job=None, *, ids=None, count=None, output=None, log=None):
        require(sha(self.root / "00_SYSTEM/GENOS_SERVING_PATHS.json") == self.config_sha256,
                "실행 도중 generation/runtime 설정이 변경되었습니다.")
        command = ["bash", str(self.shell), action, "--root", str(self.root)]
        if job is not None:
            command += ["--job", str(job)]
        if ids:
            command += ["--ids", *ids]
        if count is not None:
            command += ["--count", str(count)]
        if output is not None:
            command += ["--output", str(output)]
        return self.execute(command, log)

    def execute(self, command, log=None):
        # Keep the coordinator's lock alive in the outer shell if its parent dies.
        child = subprocess.Popen(command, cwd=self.transfer, start_new_session=True,
                                 pass_fds=(() if self.lock_fd is None else (self.lock_fd,)),
                                 stdout=log, stderr=subprocess.STDOUT if log else None)
        try:
            return child.wait()
        except BaseException:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGINT)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGTERM)
                    try:
                        child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
            raise

    def preflight(self, folder, ids=None, listing=False):
        require(sha(self.root / "00_SYSTEM/GENOS_SERVING_PATHS.json") == self.config_sha256,
                "실행 도중 generation/runtime 설정이 변경되었습니다.")
        folder = plain(folder)
        folder.mkdir(parents=True, exist_ok=True)
        # Preserve a separate log for each interrupted attempt.
        token = uuid.uuid4().hex
        output = folder / ("PREFLIGHT-" + token + ".json")
        command = [sys.executable, "-u", str(Path(__file__).with_name("basis_preflight.py")),
                   "--root", str(self.root), "--transfer", str(self.transfer),
                   "--package", self.spec["folder"], "--output", str(output)]
        if ids is not None:
            command += ["--ids", *ids]
        if listing:
            command += ["--catalogue", str(folder / "LATEST_INTERNAL.csv")]
        trace = folder / ("PREFLIGHT-" + token + ".log")
        with trace.open("x", encoding="utf-8") as stream:
            code = self.execute(command, stream)
        require(code == 0, f"목록/구조 사전 확인 실패(exit={code}): {trace}")
        result = checked(output, "receipt_sha256")
        require(result["schema"] == "basis-structure-preflight-v1", "구조 확인 결과 버전 불일치")
        return result


def select_runner(root, transfer, specs):
    actual = sha(root / "00_SYSTEM/PIPELINE.json")
    matches = [s for s in specs if s["pipeline_sha256"] == actual]
    require(len(matches) == 1, "현재 checkout은 지원하는 R4/ENTRY_FIX 코드와 다릅니다. 코드 검사를 우회하지 않습니다.")
    runner = Runner(root, transfer, matches[0])
    require(runner.call("gate") == 0, "기존 코드 게이트 실패: 원래 로그를 확인하세요.")
    return runner


def diagnose(root, transfer, specs):
    pipeline_path = root / "00_SYSTEM/PIPELINE.json"
    pipeline = read(pipeline_path)
    manifest_errors, code_errors = [], {}
    for engine, entry in pipeline["engines"].items():
        path = plain(root / entry["manifest"])
        path.relative_to(root)
        actual = sha(path) if path.is_file() else None
        if actual != entry["sha256"]:
            manifest_errors.append({"engine": engine, "path": str(path),
                                    "expected": entry["sha256"], "actual": actual})
            continue
        for name, expected in read(path)["files"].items():
            code = plain(root / name)
            code.relative_to(root)
            actual = sha(code) if code.is_file() else None
            if actual != expected:
                code_errors[name] = {"expected": expected, "actual": actual}
    matches = [s["folder"] for s in specs if s["pipeline_sha256"] == sha(pipeline_path)]
    result = {"root": str(root), "pipeline_sha256": sha(pipeline_path), "matched_packages": matches,
              "manifest_mismatches": manifest_errors, "code_mismatches": code_errors,
              "status": "PASS" if not manifest_errors and not code_errors and len(matches) == 1 else "MISMATCH",
              "model_calls": 0, "files_changed": False,
              "note": "현재 디스크 검사입니다. 이전 프로세스가 메모리에 읽었던 PIPELINE 값은 확인할 수 없습니다."}
    output = transfer / ("BASIS_CODE_CHECK_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") +
                         "-" + str(os.getpid()) + ".json")
    atomic(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    print("DIAGNOSTIC=" + str(output), flush=True)
    return 0 if result["status"] == "PASS" else 1


def catalogue(path):
    rows, seen = [], set()
    require(plain(path).stat().st_size <= 32 * 1024**2, "전체 목록 제어 파일이 32 MiB를 초과했습니다.")
    with plain(path).open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            did = row["document_id"]
            require(did and not did.startswith("-") and did not in seen, "목록의 중복/잘못된 문서 ID")
            require(row["is_latest"] == "True" and int(row["chars"]) > 0, "최신 내규 목록 계약 불일치")
            require(re.fullmatch(r"[0-9a-f]{64}", row["source_artifact_sha256"]), "원문 해시 형식 불일치")
            seen.add(did)
            rows.append({k: row[k] for k in ("document_id", "name", "source_artifact_sha256")})
    require(rows, "조사 가능한 최신 내규가 없습니다.")
    return rows


class Campaign:
    def __init__(self, runner, job, runtime, binding):
        self.runner, self.job, self.runtime, self.binding = runner, plain(job), runtime, binding
        self.plan_path = self.job / "ALL_PLAN.json"
        self.state_path = self.job / "ALL_STATE.json"
        self.events = self.job / "ALL_EVENTS.jsonl"

    def initialize(self):
        self.job.mkdir(parents=True, exist_ok=True)
        require(not (self.job / "PLAN.json").exists(), "같은 이름의 개별 작업이 있습니다. all에 다른 이름을 지정하세요.")
        if self.plan_path.exists():
            return
        require(not self.state_path.exists() and not (self.job / "parts").exists(),
                "전체 계획 없이 하위 기록이 남아 있습니다. 원본을 보존하고 원인을 확인하세요.")
        resources(self.runtime)
        listing = self.job / "catalogue"
        # Catalogue must not run inventory on the first three documents.
        receipt_path = listing / "CATALOGUE_CHECK.json"
        csv_path = listing / "LATEST_INTERNAL.csv"
        if not receipt_path.exists():
            if csv_path.exists():
                csv_path.rename(csv_path.with_name("INTERRUPTED-" + uuid.uuid4().hex + ".csv"))
            result = self.runner.preflight(listing, listing=True)
            result.pop("receipt_sha256")
            result["catalogue_sha256"] = sha(csv_path)
            atomic(receipt_path, result, "receipt_sha256")
        receipt = checked(receipt_path, "receipt_sha256")
        require(receipt["catalogue_sha256"] == sha(csv_path), "목록 생성 확인 해시 불일치")
        rows = catalogue(listing / "LATEST_INTERNAL.csv")
        require(rows == [{k: r[k] for k in ("document_id", "name", "source_artifact_sha256")}
                         for r in receipt["documents"]], "전체 목록이 사전 확인 결과와 다릅니다.")
        parts = [{"name": f"part-{i // CHUNK + 1:05d}", "documents": rows[i:i + CHUNK]}
                 for i in range(0, len(rows), CHUNK)]
        plan = {"schema": "basis-all-v1", "binding": self.binding,
                "documents": len(rows), "parts": parts, "chunk_size": CHUNK,
                "catalogue_sha256": sha(listing / "LATEST_INTERNAL.csv"),
                "scope": "accessible-latest-internal-with-source",
                "publication": "json-candidates-manual-review-only"}
        atomic(self.plan_path, plan, "plan_sha256")
        event(self.events, "all.planned", documents=len(rows), parts=len(parts))

    def load(self, *, read_only=False):
        self.plan = checked(self.plan_path, "plan_sha256")
        require(self.plan["schema"] == "basis-all-v1", "전체 계획 버전 불일치")
        old = self.plan["binding"]
        compatible = (old.get("coordinator_sha256") == R2_COORDINATOR and
                      {k: v for k, v in old.items() if k != "coordinator_sha256"} ==
                      {k: v for k, v in self.binding.items() if k not in ("coordinator_sha256", "preflight_sha256")})
        require(read_only or old == self.binding or compatible, "전체 작업의 코드·설정·runtime 결속이 달라졌습니다.")
        self.upgrade = {"from_binding": old, "to_binding": self.binding,
                        "plan_sha256": self.plan["plan_sha256"]} if old != self.binding else None
        if (self.job / "COORDINATOR_UPGRADE.json").exists():
            receipt = checked(self.job / "COORDINATOR_UPGRADE.json", "receipt_sha256")
            require((read_only and receipt.get("from_binding") == old and
                     receipt.get("plan_sha256") == self.plan["plan_sha256"]) or
                    {k: v for k, v in receipt.items() if k != "receipt_sha256"} == self.upgrade,
                    "이 작업의 명령 버전 전환 기록과 다릅니다.")
        require(self.plan["catalogue_sha256"] == sha(self.job / "catalogue/LATEST_INTERNAL.csv"),
                "확정한 전체 문서 목록이 변경되었습니다.")
        self.state = checked(self.state_path, "state_sha256") if self.state_path.exists() else {
            "schema": "basis-all-state-v1", "plan_sha256": self.plan["plan_sha256"],
            "status": "planned", "parts": {}, "service_binding": None}
        require(self.state["plan_sha256"] == self.plan["plan_sha256"], "다른 전체 계획의 상태입니다.")
        flat = [r["document_id"] for p in self.plan["parts"] for r in p["documents"]]
        require(len(flat) == len(set(flat)) == self.plan["documents"], "전체 문서 목록 누락/중복")
        for i, part in enumerate(self.plan["parts"], 1):
            require(part["name"] == f"part-{i:05d}" and 1 <= len(part["documents"]) <= CHUNK,
                    "하위 계획 순서/크기 불일치")

    def save(self):
        atomic(self.state_path, self.state, "state_sha256")

    def inspection(self, part, create=False):
        folder = plain(self.job / "parts" / part["name"])
        path = folder / "STRUCTURE_CHECK.json"
        saved = self.state["parts"].get(part["name"], {})
        if not path.exists():
            require(not saved.get("structure_sha256"), "저장된 구조 실패 기록이 사라졌습니다.")
            if not create:
                return None
            result = self.runner.preflight(folder, ids=[d["document_id"] for d in part["documents"]])
            result.pop("receipt_sha256")
            result["all_plan_sha256"] = self.plan["plan_sha256"]
            atomic(path, result, "receipt_sha256")
            for failure in result["failures"]:
                event(self.events, "all.document.structure_failed", part=part["name"], **failure)
        result = checked(path, "receipt_sha256")
        require(result["all_plan_sha256"] == self.plan["plan_sha256"], "다른 전체 계획의 구조 확인 기록")
        actual = [{k: d[k] for k in ("document_id", "name", "source_artifact_sha256")}
                  for d in result["documents"]]
        require(actual == part["documents"], "구조 확인의 문서/원문 해시 불일치")
        failures = result["failures"]
        ids = [d["document_id"] for d in failures]
        require(len(ids) == len(set(ids)), "구조 실패 문서 중복")
        require(all({k: d[k] for k in ("document_id", "name", "source_artifact_sha256")} in actual and
                    d["code"] == "BASIS_STRUCTURE" and d["phase"] == "plan" and d["status"] == "failed" and
                    d["research_attempted"] is False for d in failures), "허용하지 않은 구조 오류 건너뛰기")
        require(not saved.get("structure_sha256") or saved["structure_sha256"] == result["receipt_sha256"],
                "구조 실패 기록이 변경되었습니다.")
        if self.state["service_binding"] is not None:
            require(result["binding"] == self.state["service_binding"], "구조 확인의 서비스 결속 불일치")
        return result

    def child(self, part, create=False):
        folder = plain(self.job / "parts" / part["name"])
        path = folder / "PLAN.json"
        saved = self.state["parts"].get(part["name"], {})
        inspection = self.inspection(part, create=create and not path.exists())
        failed = {d["document_id"] for d in inspection["failures"]} if inspection else set()
        expected_docs = [d for d in part["documents"] if d["document_id"] not in failed]
        if not expected_docs:
            require(not path.exists() and not (folder / "STATE.json").exists(),
                    "구조 실패 전체 제외와 기존 실행 기록이 충돌합니다.")
            if create:
                self.state["service_binding"] = inspection["binding"]
                self.state["parts"][part["name"]] = {"status": "partial",
                    "structure_sha256": inspection["receipt_sha256"], "no_research": True}
                self.save()
            return folder, None, None
        if not path.exists():
            require(not saved, "저장된 하위 계획이 사라졌습니다. 새 계획으로 재생성하지 않습니다.")
            if not create:
                return folder, None, None
            resources(self.runtime)
            code = self.runner.call("plan", folder, ids=[d["document_id"] for d in expected_docs])
            require(code == 0, f"하위 계획 실패(exit={code}): {part['name']}")
        plan = checked(path, "plan_sha256")
        actual = [{k: d[k] for k in ("document_id", "name", "source_artifact_sha256")}
                  for d in plan["documents"]]
        require(actual == expected_docs, "하위 계획이 확정 전체 목록과 다릅니다.")
        require(not inspection or plan["binding"] == inspection["binding"], "구조 확인 후 계획 결속이 달라졌습니다.")
        storage = plan.get("candidate_storage", {})
        require(storage.get("kind") == "json-candidates-v1" and
                storage.get("path") == str(folder / "CANDIDATES.json") and
                storage.get("publication") == "manual-review-only", "JSON 후보 저장 계약 불일치")
        require(not saved or saved["plan_sha256"] == plan["plan_sha256"], "하위 계획이 바뀌었습니다.")
        if self.state["service_binding"] is not None:
            require(plan["binding"] == self.state["service_binding"], "하위 계획 간 코드·모델·권한·데이터 결속 불일치")
        if create:
            self.state["service_binding"] = plan["binding"]
            self.state["parts"].setdefault(part["name"], {"plan_sha256": plan["plan_sha256"], "status": "planned"})
            if inspection:
                self.state["parts"][part["name"]]["structure_sha256"] = inspection["receipt_sha256"]
            self.save()
        state = checked(folder / "STATE.json", "state_sha256") if (folder / "STATE.json").exists() else None
        if state:
            require(state["plan_sha256"] == plan["plan_sha256"], "하위 실행 상태가 다른 계획에 속합니다.")
            expected = {d["document_id"] for d in expected_docs}
            require(set(state["documents"]) <= expected, "하위 상태의 문서 범위 불일치")
            if state["status"] in TERMINAL:
                require(set(state["documents"]) == expected and
                        all(d["status"] in {"completed", "partial", "failed"} for d in state["documents"].values()),
                        "종료 상태인데 처리 문서가 누락되었습니다.")
        require(not saved or saved.get("status") not in TERMINAL or
                (state is not None and state["status"] in TERMINAL), "종료된 하위 상태가 사라지거나 되돌아갔습니다.")
        return folder, plan, state

    def run(self):
        self.load()
        if self.upgrade and not (self.job / "COORDINATOR_UPGRADE.json").exists():
            atomic(self.job / "COORDINATOR_UPGRADE.json", self.upgrade, "receipt_sha256")
            event(self.events, "all.coordinator.upgraded", from_sha256=R2_COORDINATOR,
                  to_sha256=self.binding["coordinator_sha256"], original_plan_preserved=True)
        self.state["status"] = "running"
        self.save()
        try:
            # Freeze every explicit-ID plan before the first research/model call.
            for part in self.plan["parts"]:
                self.child(part, create=True)
            for ordinal, part in enumerate(self.plan["parts"], 1):
                folder, plan, state = self.child(part)
                if plan is None:
                    require(self.state["parts"][part["name"]].get("no_research"), "미확정 하위 계획")
                    continue
                inspection = self.inspection(part)
                has_failures = bool(inspection and inspection["failures"])
                if state and state["status"] in TERMINAL:
                    self.state["parts"][part["name"]]["status"] = "partial" if has_failures else state["status"]
                    self.save()
                    continue
                resources(self.runtime)
                action = "resume" if state is not None else "run"
                event(self.events, "all.part.started", part=part["name"], ordinal=ordinal,
                      total=len(self.plan["parts"]), action=action)
                code = self.runner.call(action, folder)
                self.state["parts"][part["name"]]["last_exit"] = code
                self.save()
                require(code in (0, 2), f"하위 조사 중단(exit={code}): {part['name']}. 같은 all 명령으로 재개하세요.")
                _, _, result = self.child(part)
                require(result is not None and result["status"] in TERMINAL, "종료 코드와 하위 상태가 다릅니다.")
                require((code == 0) == (result["status"] == "completed"), "정상/부분 종료 코드가 상태와 다릅니다.")
                self.state["parts"][part["name"]]["status"] = "partial" if has_failures else result["status"]
                self.save()
                event(self.events, "all.part.finished", part=part["name"], status=result["status"], exit=code)
            self.state["status"] = ("completed" if all(p["status"] == "completed" for p in
                                                       self.state["parts"].values()) else "partial")
            self.save()
            event(self.events, "all.finished", status=self.state["status"], documents=self.plan["documents"],
                  candidates="각 parts/part-*/CANDIDATES.json", published_to_sqlite=False)
            self.status()
            return 0 if self.state["status"] == "completed" else 2
        except BaseException as exc:
            self.state["status"] = "interrupted"
            self.state["last_error"] = {"type": type(exc).__name__, "message": str(exc)}
            self.save()
            event(self.events, "all.interrupted", **self.state["last_error"])
            raise

    def status(self):
        self.load(read_only=True)
        counts = {"completed": 0, "partial": 0, "failed": 0, "running": 0, "pending": 0}
        for part in self.plan["parts"]:
            _, _, state = self.child(part)
            docs = state["documents"] if state else {}
            inspection = self.inspection(part)
            failures = {d["document_id"] for d in inspection["failures"]} if inspection else set()
            for doc in part["documents"]:
                status = "failed" if doc["document_id"] in failures else docs.get(doc["document_id"], {}).get("status", "pending")
                counts[status if status in counts else "pending"] += 1
        value = {"job": str(self.job), "status": self.state["status"], "total_documents": self.plan["documents"],
                 "documents": counts, "total_parts": len(self.plan["parts"]),
                 "publication": "검토용 후보 JSON; SQLite 자동 반영 없음"}
        print(json.dumps(value, ensure_ascii=False, indent=2), flush=True)
        return value

    def render(self, destination, export=False):
        self.load(read_only=True)
        destination = plain(destination)
        destination.mkdir(parents=True, exist_ok=True)
        rows = []
        failures = []
        for part in self.plan["parts"]:
            folder, plan, state = self.child(part)
            inspection = self.inspection(part)
            part_failures = inspection["failures"] if inspection else []
            failures.extend(part_failures)
            if plan is None:
                rows.append((part["name"], "구조 오류로 조사 제외" if part_failures else "계획 준비 전", None, None))
                continue
            resources(self.runtime)
            output = destination / (part["name"] + ".html")
            trace = destination / (part["name"] + ".log")
            with trace.open("w", encoding="utf-8") as stream:
                code = self.runner.call("report", folder, output=output, log=stream)
            require(code == 0, f"보고서 생성 실패: {trace}")
            links = None
            for line in trace.open(encoding="utf-8"):
                if line.startswith("{"):
                    value = json.loads(line)
                    if value.get("event") == "basis.artifacts.html":
                        links = value["links"]
            require(links is not None, f"보고서 완료 receipt 누락: {trace}")
            bundle = None
            if export and links:
                # A new snapshot gets a distinct folder; no existing review is overwritten.
                version = sha(folder / "CANDIDATES.json")[:16] if (folder / "CANDIDATES.json").exists() else plan["plan_sha256"][:16]
                bundle = f"{part['name']}-{version}"
                require(self.runner.call("export", folder, output=destination / bundle) == 0,
                        f"검토·이관 묶음 생성 실패: {part['name']}")
            status = state["status"] if state else "아직 조사 전"
            rows.append((part["name"], status + (f" / 구조 실패 {len(part_failures)}개" if part_failures else ""), output.name,
                         bundle + "/LINKS.html" if bundle else None))
        lines = ['<!doctype html><meta charset="utf-8"><title>전체 내규 연결 후보</title>',
                 '<h1>전체 내규 연결 후보</h1><p>검토용 후보입니다. 부분·실패는 외규 부재를 뜻하지 않습니다.</p>',
                 f'<p>대상 내규 {self.plan["documents"]}개 / 상태 {html.escape(self.state["status"])}</p>',
                 "<ul>"]
        for name, status, report, bundle in rows:
            link = f'<a href="{report}">{name}</a>' if report else html.escape(name)
            transfer = f' · <a href="{bundle}">검토·이관 묶음</a>' if bundle else ""
            lines.append(f"<li>{link}: {html.escape(status)}{transfer}</li>")
        lines.append("</ul><p>각 보고서에 내규·외규의 출처, 실제 원문, 연결 이유와 미확인을 표시합니다.</p>")
        lines.append("<h2>구조 오류로 조사하지 못한 문서</h2><ul>")
        for doc in failures:
            lines.append("<li>" + html.escape(f"{doc['name']} ({doc['document_id']}) — {doc['code']}: {doc['message']}") + "</li>")
        lines.append("</ul><p>구조 오류 문서는 연결 여부 미확인입니다. 원문 구조를 수정한 새 세대에서 별도로 재조사해야 합니다.</p>")
        plain(destination / "INDEX.html").write_text("\n".join(lines), encoding="utf-8")
        print("HTML=" + str(destination / "INDEX.html"), flush=True)
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["check", "all", "new", "plan", "run", "resume", "status", "report", "export"])
    parser.add_argument("name", nargs="?")
    parser.add_argument("count", nargs="?", type=int)
    parser.add_argument("--root", type=Path, default=Path.home() / "DEV")
    parser.add_argument("--kit", type=Path, default=Path(__file__).parent)
    a = parser.parse_args(argv)
    require(a.name is None or NAME.fullmatch(a.name), "작업 이름은 영문·숫자·밑줄·하이픈 1~64자입니다.")
    require(a.count is None or (a.action in ("new", "plan") and 1 <= a.count <= 20), "개별 작업 문서 수는 1~20입니다.")
    require(a.action != "check" or a.name is None, "check에는 작업 이름을 붙이지 않습니다.")
    require(a.action not in ("new", "plan") or a.name is not None, "새 작업 이름을 지정하세요.")
    root, transfer = a.root.resolve(strict=True), Path.cwd()
    specs = read(a.kit / "RUNNERS.json")["runners"]
    if a.action == "check":
        return diagnose(root, transfer, specs)
    config_path = root / "00_SYSTEM/GENOS_SERVING_PATHS.json"
    config = read(config_path)
    runtime = plain(config["runtime"])
    require(Path(config["runtime"]).is_absolute() and runtime.is_dir(), "설정의 공유 runtime 경로가 없습니다.")
    runner = select_runner(root, transfer, specs)
    name = a.name or ("all" if a.action == "all" else None)
    job = runtime / "basis-batch" / ("pilot-review-user-" + name if name else runner.spec["default_job"])
    campaign = a.action == "all" or (job / "ALL_PLAN.json").exists()
    require(not campaign or a.action not in ("new", "plan"), "전체 작업을 덮어쓸 수 없습니다. 새 이름으로 all을 실행하세요.")
    binding = {"runner": runner.identity, "root": str(root), "runtime": str(runtime),
               "config_sha256": sha(config_path), "coordinator_sha256": sha(Path(__file__)),
               "preflight_sha256": sha(Path(__file__).with_name("basis_preflight.py"))}
    current = Campaign(runner, job, runtime, binding)
    if campaign and a.action == "status":
        current.status()
        return 0
    with lock(runtime / "basis-batch/basis-quick.lock") as fd:
        runner.lock_fd = fd
        if campaign:
            if a.action == "all":
                current.initialize()
            if a.action in ("all", "run", "resume"):
                return current.run()
            return current.render(transfer / ("basis-" + a.action + "-" + name), export=a.action == "export")
        resources(runtime)
        if a.action in ("new", "plan"):
            require(not (job / "PLAN.json").exists(), "기존 작업입니다. resume을 쓰거나 새 이름을 지정하세요.")
            code = runner.call("plan", job, count=a.count or 3)
            if code or a.action == "plan":
                return code
            return runner.call("run", job)
        return runner.call(a.action, job, output=transfer / ("basis-review-" + (name or "default") + ".html")
                           if a.action == "report" else None)


if __name__ == "__main__":
    os.umask(0o077)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt("SIGTERM")))
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("중단 기록을 보존했습니다. 같은 all 또는 resume 명령으로 이어가세요.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"BASIS_QUICK_FAILED {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
