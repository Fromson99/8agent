"""Derive R2 service and R3 entry from sealed R1/R2 bytes, without rebuilding MAIN."""
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
R1 = HERE.parent / "pipeline_service_20261022_r1"
SERVICE = "GENOS_PIPELINE_SERVICE_20261022_R2"
RUNNER = "DATAIKU_PIPELINE_RUN_20261022_R3"
BASE_SERVICE_SHA = "9c0366d77d190b4ff3aba8ea3f7caf89085bdecf52432015c0173c934912a66b"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build():
    source = (R1 / "GENOS_PIPELINE_SERVICE_20261022_R1.zip").read_bytes()
    assert digest(source) == BASE_SERVICE_SHA
    with zipfile.ZipFile(R1 / "GENOS_PIPELINE_SERVICE_20261022_R1.zip") as z:
        files = {n.split("/", 1)[1]: z.read(n) for n in z.namelist()}
    old_pins = json.loads(files.pop("CODE_PINS.json"))
    assert set(old_pins["files"]) == set(files)
    assert all(digest(files[n]) == sha for n, sha in old_pins["files"].items())
    transport = (HERE / "src/transport.py").read_bytes()
    files["transport.py"] = transport
    rawstore = "02_BACKEND/lawrag/core/rawstore.py"
    files[rawstore] = (HERE.parents[2] / rawstore).read_bytes()
    guide = files["GUIDE.txt"].decode().replace("GENOS_PIPELINE_SERVICE_20261022_R1", SERVICE)
    guide += "\nR2: 긴 원문 이름을 유지하며 임시 파일명만 짧게 생성합니다. Dataiku 실행 R3와 함께 사용합니다.\nNFS 설정·generation은 변경하지 않습니다. 현장 배포·Git commit/push는 별도입니다.\n"
    files["GUIDE.txt"] = guide.encode()
    for name in ["VERIFY_PIPELINE_RELEASE.py", "GENOS_PIPELINE_CHECK.txt"]:
        files[name] = (HERE / name).read_bytes()
    pins = {"format": "pipeline-code-pins-v1", "files": {n: digest(b) for n, b in files.items()}}
    files["CODE_PINS.json"] = json.dumps(pins, ensure_ascii=False, sort_keys=True, indent=2).encode()
    service_sha = digest(files["CODE_PINS.json"])
    with zipfile.ZipFile(HERE / (SERVICE + ".zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in sorted(files.items()):
            item = zipfile.ZipInfo(SERVICE + "/" + n, date_time=(2026, 10, 22, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(item, data)
    helpers = (HERE / "client_helpers.py").read_text().replace("__TRANSPORT_SOURCE__", repr(transport.decode()))
    helpers = helpers.replace("__TRANSPORT_SHA256__", repr(digest(transport)))
    helpers = helpers.replace("__SERVICE_SHA256__", repr(service_sha))
    runner = (HERE / "runner_template.py").read_text().replace("__CLIENT_R3_HELPERS__", helpers)
    compile(runner, RUNNER + ".txt", "exec")
    (HERE / (RUNNER + ".txt")).write_text(runner)
    (HERE / "DATAIKU_PIPELINE_RUN.py").write_text(runner)
    manifest = {"base_service_zip_sha256": BASE_SERVICE_SHA, "service_code_sha256": service_sha,
                "service_zip_sha256": digest((HERE / (SERVICE + ".zip")).read_bytes()),
                "service_zip": SERVICE + ".zip", "transport_sha256": digest(transport),
                "runner_sha256": digest(runner.encode()),
                "changed_service_runtime_files": ["transport.py", rawstore],
                "rawstore_sha256": digest(files[rawstore]),
                "new_service_tools": ["VERIFY_PIPELINE_RELEASE.py", "GENOS_PIPELINE_CHECK.txt"],
                "service_file_count": len(pins["files"]), "git_checkout": "FIELD_VALUE_REQUIRED",
                "git_commit": "NOT_PERFORMED", "genos_revision": "NOT_DEPLOYED",
                "generation": "per-job temporary input; no NFS generation changes",
                "data_archives_changed": False, "main_changed": False}
    (HERE / "CODE_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    package_names = [RUNNER + ".txt", "DATAIKU_PIPELINE_RUN.py", "GUIDE.txt", "WORK_CONTRACT.txt", "CODE_MANIFEST.json"]
    if (HERE / "VALIDATION.json").exists():
        package_names.append("VALIDATION.json")
    code_pins = {n: digest((HERE / n).read_bytes()) for n in package_names}
    (HERE / "SHA256.json").write_text(json.dumps(code_pins, indent=2) + "\n")
    with zipfile.ZipFile(HERE / (RUNNER + ".zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for n in [*package_names, "SHA256.json"]:
            z.write(HERE / n, RUNNER + "/" + n)
    print(json.dumps(manifest))


if __name__ == "__main__":
    build()
