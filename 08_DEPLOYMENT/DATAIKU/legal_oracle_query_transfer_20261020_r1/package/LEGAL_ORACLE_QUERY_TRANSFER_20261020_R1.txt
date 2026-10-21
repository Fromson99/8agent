# 기존 LEGAL_ORACLE_FULL_TRANSFER_20261019_R1 노트북의 새 Python 셀에 전체를 붙입니다.
# 1) ACTION="check" → 2) ACTION="publish" → 3) ACTION="status" 순서로 변경·실행합니다.
# 기존 노트북의 desk, SOURCE_SQLITE, LOG_DIR와 인증/완료 기록을 그대로 사용합니다.
# 새 커널이면 기존 노트북의 00~03 연결까지만 실행한 뒤 이 셀을 사용합니다.
# CODE_ROOT는 앞서 현장 사진에서 확인한 기존 checkout입니다. 실제 위치가 다르면 수정합니다.
ACTION = "check"
CODE_ROOT = "/workspace"
PUBLISH_SECONDS = 3600

import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback

# 빌드 시 기존 발송 누적본과 일치하는 게시/검증 모듈의 SHA-256을 삽입합니다.
CODE_PINS = {
    "02_BACKEND/lawrag/pipeline/oracle_query_publish.py": "550a0d51134a7f61a0a8d467d01cd36ee7657ab6ef251205da36285672aa2629",
    "02_BACKEND/lawrag/pipeline/oracle_query_navigation_publish.py": "57835cd6aabf5738182254a9f78f684e551a4296a094f78f388e349fe1877b40",
    "02_BACKEND/lawrag/pipeline/oracle_migration.py": "eb40d1cad19b7aefeca18b7bb36c7444a140f7beae239984215a2faed76476bd",
    "02_BACKEND/semantic_runtime/oracle_dp_io.py": "fbbbcc79f47ea1f8cb01a48c74e29568a4fc5bd30146803368760af6b03f7eaf",
    "02_BACKEND/semantic_runtime/oracle_dp_assets.py": "0bcf4747da8ba613f08ae8d0c79b8a1450a292ef5210420180e211169eea0528",
    "02_BACKEND/semantic_runtime/oracle_query_catalog.py": "bd0cdcd295a209694c2692602b1310f1050b817ebe39ed8bddf1fe87759b400c",
    "02_BACKEND/semantic_runtime/navigation_match.py": "f7064aa3808ba404304b5e57745c51e68a584c79db4a748a7e63d45720b290a5",
    "02_BACKEND/semantic_runtime/structure_navigation.py": "8bc8acd92913bacb58f2c79c5af9c1bd934bee7d14858f3608b1432ee2637587",
    "02_BACKEND/semantic_runtime/inherited_navigation.py": "d8dc9f442e52d2135457b6addf0e553b3b1165ae06dc9d80674b70ea6c092d9c",
    "02_BACKEND/semantic_runtime/multi_entry_navigation.py": "8cb9dd1a649392679e40b19b12d8be47dea9d6f157ab4197abf605566f1862f2",
    "02_BACKEND/semantic_runtime/folder_navigation.py": "8a0a1797a8af5f2b28b6b7dc503a83ba802d36c478af489f5f3fe8edc69a1b0a",
    "02_BACKEND/semantic_runtime/term_index.py": "bd036e61b401671ef14ce886ae431255cac47411957968c4d001cda9aab823b0",
    "02_BACKEND/semantic_runtime/search_selection.py": "3d6febfedf60384d87142a480e31809c1a6b233cc2fd95b454e559bb3709c013"
}


def _query_load(code_root):
    root = Path(code_root).resolve(strict=True)
    backend = root / "02_BACKEND"
    if not CODE_PINS:
        raise RuntimeError("CODE_PINS: 빌드 전 템플릿 대신 전달된 실행 TXT를 사용하세요.")
    for relative, expected in CODE_PINS.items():
        path = root / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError("CODE_PIN: 기존 Oracle 직접 조회 누적본의 코드 확인 필요: " + relative)
    for name, module in list(sys.modules.items()):
        if name == "lawrag" or name.startswith("lawrag.") or name == "semantic_runtime" or name.startswith("semantic_runtime."):
            filename = getattr(module, "__file__", None)
            if filename and not Path(filename).resolve().is_relative_to(backend):
                raise RuntimeError("CODE_IMPORT: 다른 checkout이 커널에 있습니다. 커널 재시작 후 기존 노트북 00~03부터 연결하세요.")
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    publisher = importlib.import_module("lawrag.pipeline.oracle_query_publish")
    io = importlib.import_module("semantic_runtime.oracle_dp_io")
    catalogue = importlib.import_module("semantic_runtime.oracle_query_catalog")
    return publisher, io, catalogue


def _query_event(path, record):
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"at": time.time(), **record}, ensure_ascii=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _query_resources(folder):
    ram = None
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            ram = int(line.split()[1]) * 1024
    free = shutil.disk_usage(folder).free
    if ram is None or ram < 1024**3:
        raise RuntimeError("RESOURCE_RAM: 가용 RAM 1GiB 이상을 확보한 뒤 같은 셀을 실행하세요.")
    if free < 512 * 1024**2:
        raise RuntimeError("RESOURCE_DISK: 로그 디스크 여유 512MiB 이상이 필요합니다. 기존 기록은 보존하세요.")
    return {"available_ram_mib": ram // 1024**2, "free_disk_mib": free // 1024**2}


def run_query_step(namespace, action, code_root, seconds=3600):
    if action not in {"check", "publish", "status"}:
        raise RuntimeError("ACTION은 check / publish / status 중 하나여야 합니다.")
    if type(seconds) is not int or not 1 <= seconds <= 21600:
        raise RuntimeError("PUBLISH_SECONDS는 1~21600초 범위여야 합니다. 최초 7일 기한은 별도로 유지됩니다.")
    desk = namespace.get("desk")
    flow = namespace.get("_legal19_flow")
    source = namespace.get("SOURCE_SQLITE")
    if desk is None or flow is None or not source:
        raise RuntimeError("PREREQUISITE: 기존 전체 이관 노트북과 같은 커널에서 실행하세요. 새 커널은 기존 00~03을 먼저 실행합니다.")
    log_root = Path(desk.settings.get("log_dir") or "./ords_notebook_logs").resolve()
    log_root.mkdir(parents=True, exist_ok=True)
    event_path = log_root / "legal_query_handoff_events.jsonl"
    _query_event(event_path, {"action": action, "status": "STARTED"})
    io = None
    try:
        resources = _query_resources(log_root)
        publisher, io, catalogue = _query_load(code_root)
        check = desk.require_connection()
        if desk.recovery_required or getattr(check.client, "deadline", None) is not None:
            raise io.DPError("R6_STATE: 기존 쓰기 보류 또는 실행 중인 셀을 먼저 확인하세요.")
        # 기존 08 결과를 Oracle/로컬 receipt에서 다시 확인합니다. 원문 이관은 호출하지 않습니다.
        original = flow.summary(desk, source)
        if original.get("status") != "TRANSFER_AND_ASSETS_COMPLETE":
            raise io.DPError("SOURCE_NOT_COMPLETE: 기존 원문 대조·자산 게시 완료가 필요합니다.")
        source_release = catalogue.pin(original["DP_RELEASE_ID"])
        generation = Path(source).resolve(strict=True).parent
        if generation.joinpath("store.sqlite") != Path(source).resolve():
            raise io.DPError("SOURCE_PATH: 기존 generation/store.sqlite를 사용하세요.")
        if io.file_sha(generation / "manifest.json") != original["dataset_version"]:
            raise io.DPError("SOURCE_VERSION: 기존 이관 버전과 원본 manifest가 다릅니다.")
        folder = log_root / "legal_query_publish" / source_release
        receipt = folder / "state.json"
        identity = {"source_release_id": source_release, "target_binding": desk.binding(),
                    "generation": str(generation)}
        previous = None
        if receipt.exists():
            if receipt.stat().st_size > 8 * 1024**2:
                raise io.DPError("STATE_SIZE: 이관 상태 파일 크기를 확인하세요.")
            previous = json.loads(receipt.read_text())
            if previous.get("identity") != identity:
                raise io.DPError("QUERY_RESUME_BINDING: 이전 게시의 원본/접속 정보가 다릅니다. 로그 폴더를 바꾸어 우회하지 마세요.")
        schema = publisher.schema_from_notebook(desk, create=False)
        if schema["status"] != "READY":
            raise io.DPError("QUERY_SCHEMA_MISSING: 생성 또는 조회 권한 확인 필요: " + ", ".join(schema["missing"]))
        base = {"source_release_id": source_release, "generation": str(generation),
                "receipt": str(receipt), "active_changed": False,
                "state_table_migrated": False, "resources": resources}
        if action == "check":
            result = {**base, "status": "READY_TO_PUBLISH", "schema": "READY",
                      "previous_status": previous.get("status") if previous else "NOT_STARTED"}
        elif action == "publish":
            print("조회 행 적재 시작. 장시간 수행될 수 있습니다. 같은 커널에서 다른 이관을 실행하지 마세요.", flush=True)
            print("진행/실패 기록:", str(folder / "calls.jsonl"), flush=True)
            result = {**base, **publisher.from_notebook(
                desk, generation=generation, source_release_id=source_release, seconds=seconds)}
            if result.get("status") != "COMPLETE" or result.get("active_changed") is not False:
                raise io.DPError("QUERY_PUBLICATION: 예상한 비활성 COMPLETE 결과가 아닙니다.")
        else:
            if previous is None or previous.get("status") != "COMPLETE":
                raise io.DPError("QUERY_NOT_COMPLETE: publish 완료가 필요합니다. 현재 상태=" +
                                 (previous.get("status", "UNKNOWN") if previous else "NOT_STARTED"))
            sql = io.SQL(check.client, journal=folder / "notebook_status_calls.jsonl",
                         binding=io.digest(identity), seconds=300)
            release_id = catalogue.pin(previous["release_id"])
            manifest = catalogue.read_release(sql, release_id)
            if (manifest["source_release_id"] != source_release or
                    manifest["dataset_version"] != original["dataset_version"]):
                raise io.DPError("QUERY_RELEASE_BINDING: 조회 릴리스의 원문 버전이 다릅니다.")
            total = 0
            for kind, table in manifest["tables"].items():
                rows = sql.query(f"SELECT COUNT(*) AS N FROM {catalogue.ROW} WHERE RELEASE_ID=:release AND KIND=:kind",
                                 [("release", release_id, "VARCHAR2"), ("kind", kind, "VARCHAR2")], limit=1)
                if rows != [{"N": table["rows"]}]:
                    raise io.DPError("QUERY_ROW_COUNT: 원격 조회 행 수 불일치: " + kind)
                total += table["rows"]
            result = {**base, "status": "QUERY_PUBLICATION_VERIFIED", "release_id": release_id,
                      "kinds": len(manifest["tables"]), "rows": total,
                      "main_pointer": catalogue.active(sql, "main")}
        _query_event(event_path, {"action": action, "status": result["status"],
                                 "source_release_id": source_release,
                                 "release_id": result.get("release_id"), "receipt": str(receipt)})
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print("채널 활성화/GENOS 배포는 별도입니다. 이번 셀은 QUERY_ACTIVE와 QUERY_STATE를 변경하지 않습니다.")
        return result
    except Exception as exc:
        known = isinstance(exc, RuntimeError) or (io is not None and isinstance(exc, io.DPError))
        message = str(exc) if known else type(exc).__name__
        detail = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        for secret in getattr(desk, "_auth", ()):
            if isinstance(secret, str) and secret:
                message = message.replace(secret, "[MASKED]")
                detail = detail.replace(secret, "[MASKED]")
        paused = io is not None and isinstance(exc, io.BudgetPause)
        _query_event(event_path, {"action": action, "status": "PAUSED" if paused else "FAILED",
                                 "error_type": type(exc).__name__, "error": message, "traceback": detail})
        raise RuntimeError(("PAUSED: " if paused else "FAILED: ") + message +
                           "; 기록=" + str(event_path)) from None


if __name__ == "__main__":
    QUERY_TRANSFER_RESULT = None
    QUERY_TRANSFER_RESULT = run_query_step(globals(), ACTION, CODE_ROOT, PUBLISH_SECONDS)
