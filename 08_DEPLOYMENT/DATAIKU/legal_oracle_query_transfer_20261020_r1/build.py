from pathlib import Path
import ast
import hashlib
import json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = "LEGAL_ORACLE_QUERY_TRANSFER_20261020_R1"
PIN_PATHS = [
    "02_BACKEND/lawrag/pipeline/oracle_query_publish.py",
    "02_BACKEND/lawrag/pipeline/oracle_query_navigation_publish.py",
    "02_BACKEND/lawrag/pipeline/oracle_migration.py",
    "02_BACKEND/semantic_runtime/oracle_dp_io.py",
    "02_BACKEND/semantic_runtime/oracle_dp_assets.py",
    "02_BACKEND/semantic_runtime/oracle_query_catalog.py",
    "02_BACKEND/semantic_runtime/navigation_match.py",
    "02_BACKEND/semantic_runtime/structure_navigation.py",
    "02_BACKEND/semantic_runtime/inherited_navigation.py",
    "02_BACKEND/semantic_runtime/multi_entry_navigation.py",
    "02_BACKEND/semantic_runtime/folder_navigation.py",
    "02_BACKEND/semantic_runtime/term_index.py",
    "02_BACKEND/semantic_runtime/search_selection.py",
]


def build():
    previous = ROOT / "08_DEPLOYMENT/GENOS/handoffs/workflow_progress_20261019_r1/CODE_MANIFEST.json"
    records = {r["path"]: r["sha256"] for r in json.loads(previous.read_text())["files"]}
    pins = {}
    for name in PIN_PATHS:
        pins[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        if pins[name] != records[name]:
            raise RuntimeError("Previously sent publisher binding changed: " + name)
    source = (HERE / "handoff_template.py").read_text()
    assert source.count("CODE_PINS = {}") == 1
    source = source.replace("CODE_PINS = {}", "CODE_PINS = " + json.dumps(pins, indent=4))
    ast.parse(source, feature_version=(3, 11))
    package = HERE / "package"
    package.mkdir(exist_ok=True)
    for suffix in (".py", ".txt"):
        (package / (NAME + suffix)).write_text(source, encoding="utf-8")
    (package / "CODE_PINS.json").write_text(json.dumps({
        "source_handoff": "GENOS_WORKFLOW_PROGRESS_20261019_R1",
        "publisher_files": pins,
        "note": "Installed existing checkout is required. No checkout/code/data replacement is performed."
    }, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "BUILT", "files": 2, "publisher_pins": len(pins)}))


if __name__ == "__main__":
    build()
