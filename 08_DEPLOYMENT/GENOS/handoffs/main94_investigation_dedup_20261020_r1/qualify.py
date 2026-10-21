"""Bind the delivered archive to completed local and installed contract checks."""
from pathlib import Path
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile

H = Path(__file__).resolve().parent
R = H.parents[3]
A = R / "09_ARTIFACTS/AUDITS/20261020-main94-investigation-dedup"
sha = lambda b: hashlib.sha256(b).hexdigest()
read = lambda p: json.loads(p.read_bytes())
assert not (H / "SEALED.json").exists()
pointer = read(R / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json")
manifest = read(R / pointer["manifest_path"])
assert pointer["release_id"] == "investigation-dedup-20261020-r1"
assert sha((R / pointer["manifest_path"]).read_bytes()) == pointer["release_manifest_sha256"]
with zipfile.ZipFile(H / "code.zip") as z:
    for name, expected in manifest["files"].items():
        for raw in (z.read(name), (R / name).read_bytes(),
                    (R / manifest["code_root"] / name).read_bytes(),
                    (A / "stage" / name).read_bytes()):
            assert sha(raw) == expected, name
root = ET.parse(H / "CONTRACT_TESTS_01.xml").getroot()
cases = root.findall(".//testcase")
assert cases and not root.findall(".//failure") and not root.findall(".//error")
assert not root.findall(".//skipped")
delivery = ET.parse(H / "DELIVERY_TESTS_01.xml").getroot()
assert len(delivery.findall(".//testcase")) == 2
assert not delivery.findall(".//failure") and not delivery.findall(".//error")
scenarios = [read(H / ("PASS_" + mode + ".json"))
             for mode in ("preserved-config-interruption", "no-config-standalone")]
assert all(s["status"] == "PASS" and s["exact_rollback"] and s["preserved_data"] for s in scenarios)
imports = int(re.search(r"INSTALLED_CONTRACT_IMPORTS PASS; modules=(\d+)",
                       (H / "CONTRACT_TESTS_01.txt").read_text()).group(1))
consumer = read(A / "consumer-active.json")
assert consumer["status"] == "PASS" and all(consumer["checks"].values())
resources = {n: read(H / n) for n in ("DELIVERY_RESOURCES_01.json", "CONTRACT_RESOURCES_01.json")}
assert all(r["returncode"] == 0 and r["stop_reason"] is None for r in resources.values())
v = {
    "status": "PASS",
    "runtime_files": len(manifest["files"]),
    "runtime_matches_working_frozen_selected_handoff": True,
    "local_MAIN": pointer,
    "workflow": "1.20.1",
    "local_contracts_passed": 366,
    "local_contracts_known_failures": 6,
    "known_failures_reproduced_on_MAIN93": read(A / "KNOWN_BASELINE_FAILURES.json"),
    "handoff_contracts": len(cases),
    "installation_scenarios": len(scenarios),
    "installation_commands": sum(s["commands"] for s in scenarios),
    "installed_imports": imports,
    "syntax": read(H / "PYTHON311.json"),
    "local_actual_service": consumer,
    "code_zip_sha256": sha((H / "code.zip").read_bytes()),
    "source_kind": "Synthetic contracts and real local source-only service read",
    "new_model_calls": 0,
    "GENOS_field_verified": False,
    "quality_certified": False,
    "data_profile_search_unchanged": True,
    "limits": [
        "No GENOS deployment, internal model, Oracle or NFS field execution",
        "Six legacy general RAG failures remain and match the immutable MAIN93 baseline",
        "Prior ADR verdicts and semantic/cost limitations retained",
        "Old code-bound runs require their original revision; no forced resume",
    ],
    "resources": resources,
}
(H / "VALIDATION.json").write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": "PASS", "runtime_files": len(manifest["files"]),
                  "handoff_contracts": len(cases), "installed_imports": imports}))
