"""Bind package bytes, installed-code checks and actual ZIP/TXT installation evidence."""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile

H = Path(__file__).resolve().parent
R = H.parents[3]
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
read = lambda p: json.loads(p.read_text())
passes = [read(H / ("PASS_" + m + ".json")) for m in
          ("preserved-config-interruption", "no-config-standalone")]
assert all(p["status"] == "PASS" for p in passes)
suite = ET.parse(H / "CONTRACT_TESTS_01.xml").getroot().find("testsuite")
assert suite is not None
assert int(suite.get("failures")) == int(suite.get("errors")) == 0
assert int(suite.get("tests")) == 204
assert "INSTALLED_CONTRACT_IMPORTS PASS; modules=257" in (H / "CONTRACT_TESTS_01.txt").read_text()
assert "2 passed" in (H / "DELIVERY_TESTS_01.txt").read_text()
for n in ("CONTRACT_RESOURCES_01.json", "DELIVERY_RESOURCES_01.json"):
    value = read(H / n)
    assert value["returncode"] == 0 and value["stop_reason"] is None
python = read(H / "PYTHON311.json")
assert python["status"] == "PASS" and python["python"].startswith("3.11.")
assert python["code_zip_sha256"] == sha(H / "code.zip")
pointer = read(H / "SOURCE_POINTER.json")
assert read(R / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json") == pointer
release = read(R / pointer["manifest_path"])
assert sha(R / pointer["manifest_path"]) == pointer["release_manifest_sha256"]
with zipfile.ZipFile(H / "code.zip") as z:
    exact = []
    for n, pin in release["files"].items():
        assert sha(R / release["code_root"] / n) == pin, n
        raw = z.read(n)
        if hashlib.sha256(raw).hexdigest() == pin:
            exact.append(n)
        else:
            assert n == "00_SYSTEM/PIPELINE.json"
            packaged = json.loads(raw)
            selected = read(R / release["code_root"] / n)
            packaged["authorities"]["oracle_query_serving"] = selected["authorities"]["oracle_query_serving"]
            assert packaged == selected
    for n in ("02_BACKEND/semantic_runtime/legal_agent/model_contract.py",
              "02_BACKEND/semantic_runtime/legal_agent/transport.py",
              "08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py"):
        assert z.read(n) == (R / release["code_root"] / n).read_bytes()
binding = read(H / "SOURCE_BINDING.json")
value = {
    "status": "LOCAL_DELIVERY_VERIFIED_FIELD_PENDING",
    "version": "GENOS_MAIN92_CUMULATIVE_20261020_R1",
    "base": binding["base_package"], "code_zip_sha256": sha(H / "code.zip"),
    "local_main_release_manifest_sha256": pointer["release_manifest_sha256"],
    "main_generation": 92, "workflow_version": "1.19.4",
    "changes": {"with_manifests_and_pins": len(binding["changes"]),
                "unchanged": binding["unchanged_files"], "exact_main_files": len(exact),
                "pipeline_exception": "Only Oracle guide reference points to the included field guide"},
    "contract_tests": {"passed": 204, "product_imports_from_packaged_code": 257,
                       "log": "CONTRACT_TESTS_01.txt", "xml": "CONTRACT_TESTS_01.xml",
                       "coverage": "GENOS model metadata, bounded output recovery, stream completion/failure, AD, workflow resume/hash/deadline/idempotence, current MAIN research state, API and display consumers",
                       "fixture": "synthetic documents and scripted models"},
    "delivery_tests": {"passed": 2, "scenarios": passes,
                       "commands": sum(v["commands"] for v in passes),
                       "coverage": "actual TRANSFER ZIP/TXT, existing Git checkout, preserved config/data, interrupted install, reapply, committed checkout gate, tamper refusal, exact rollback"},
    "python311": python, "workflow_editor": read(H / "WORKFLOW_DIFF.json"),
    "main_source_verification": {"checks": 204, "actual_local_service_verified": True,
                                 "source": "09_ARTIFACTS/AUDITS/20261020-genos-model-metadata-main/final-check.json"},
    "source_pointer_sha256": sha(H / "SOURCE_POINTER.json"),
    "selected_local_main_changed_by_packaging": False,
    "working_source_changed_by_packaging": False,
    "separate_working_changes": read(H / "WORKING_DRIFT_OBSERVATION.json"),
    "model_calls": 0, "quality_certified": False, "cutover": "USER_DIRECTED_CUTOVER",
    "known_limitations": "Prior legal evidence sufficiency/current citation weaknesses, quality/cost validation and existing unrelated regressions remain; no prior ADR verdict changed.",
    "field": {"checkout": "existing DEV Git checkout", "commit": None, "generation_path": None,
              "generation_manifest_sha256": None, "oracle_query_release": None,
              "codeserving_revision": None, "workflow_editor_saved": False, "verified": False},
    "remaining": ["GENOS install/commit/gate/push/new revision",
                  "Replace and save workflow editor with this package's full TXT",
                  "Verify same failed question in workflow test UI with internal model and actual Oracle/NFS"],
    "file_sha256": {n: sha(H / n) for n in (
        "CODE_MANIFEST.json", "SOURCE_BINDING.json", "PACKAGE_SPEC.json", "run.py", "replace.py",
        "code_smoke.py", "CONTRACT_TESTS_01.txt", "DELIVERY_TESTS_01.txt", "WORKFLOW_DIFF.json")},
}
(H / "VALIDATION.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": value["status"], "contract_tests": 204,
                  "installation_commands": value["delivery_tests"]["commands"]}))
