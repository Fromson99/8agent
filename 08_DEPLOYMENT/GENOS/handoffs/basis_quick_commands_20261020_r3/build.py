"""Package only the command extension; never mutate sealed source deliveries."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
KIT = HERE / "BASIS_QUICK_R3"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build():
    assert not (HERE / "SEALED.json").exists(), "Do not replace a mailed release."
    KIT.mkdir(exist_ok=True)
    shutil.copyfile(ROOT / "06_TOOLS/COMMANDS/basis_quick.py", KIT / "basis_quick.py")
    shutil.copyfile(ROOT / "06_TOOLS/COMMANDS/basis_preflight.py", KIT / "basis_preflight.py")
    specs = []
    for folder, default_job in [
        ("basis_batch_20261020_r4", "pilot-review-skip-20261020-r4"),
        ("basis_entry_fix_20261020_r1", "pilot-review-entryfix-20261020-r1"),
    ]:
        base = HERE.with_name(folder)
        package = json.loads((base / "PACKAGE.json").read_text())
        name = package["version"]
        files = ["PACKAGE.json", "runner.py", name + "_RUN.txt",
                 "tools/CODE_REQUIREMENTS.json", "tools/runner.py", "tools/basis_batch.py",
                 "tools/basis_batch_candidates.py", "tools/basis_batch_artifacts.py", "tools/basis_batch_report.py"]
        specs.append({"folder": name, "shell": name + "_RUN.txt", "default_job": default_job,
                      "pipeline_sha256": package["code"]["00_SYSTEM/PIPELINE.json"],
                      "files": {n: sha(base / n) for n in files}})
    put(KIT / "RUNNERS.json", {"runners": specs})
    put(KIT / "MANIFEST.json", {"schema": "basis-quick-r3-v1",
        "source": "06_TOOLS/COMMANDS/basis_quick.py",
        "files": {name: sha(KIT / name) for name in ("basis_quick.py", "basis_preflight.py", "RUNNERS.json")},
        "checkout_modified": False, "data_generation_changed": False,
        "GENOS_field_verified": False})
    subprocess.run(["bash", "-n", str(HERE / "BASIS_RUN.txt")], check=True)
    archive = HERE / "GENOS_BASIS_QUICK_20261020_R3.zip"
    names = ["BASIS_RUN.txt", "COMMANDS.txt", "BASIS_QUICK_R3/basis_quick.py",
             "BASIS_QUICK_R3/basis_preflight.py", "BASIS_QUICK_R3/RUNNERS.json", "BASIS_QUICK_R3/MANIFEST.json"]
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for name in names:
            assert Path(name).suffix.lower() not in (".js", ".jsx", ".mjs", ".cjs")
            z.write(HERE / name, name)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None and z.read("BASIS_RUN.txt") == (HERE / "BASIS_RUN.txt").read_bytes()
    put(HERE / "BUILD.json", {"zip_sha256": sha(archive), "zip_bytes": archive.stat().st_size,
                            "members": names, "source_equals_delivered":
                            sha(ROOT / "06_TOOLS/COMMANDS/basis_quick.py") == sha(KIT / "basis_quick.py")})
    print((HERE / "BUILD.json").read_text())


if __name__ == "__main__":
    build()
