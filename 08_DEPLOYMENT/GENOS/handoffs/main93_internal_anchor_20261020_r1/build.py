"""Exact MAIN93 runtime over sealed MAIN92, preserving later basis tooling."""
from pathlib import Path
import ast, hashlib, json, shutil, zipfile
H = Path(__file__).resolve().parent
R = H.parents[3]
B = H.with_name("main92_cumulative_20261020_r1")
N = "GENOS_MAIN93_INTERNAL_ANCHOR_20261020_R1"
OLD = "GENOS_MAIN92_CUMULATIVE_20261020_R1"
sha = lambda b: hashlib.sha256(b).hexdigest()
enc = lambda v: (json.dumps(v, ensure_ascii=False, indent=2) + "\n").encode()
assert not (H / "SEALED.json").exists()
p = json.loads((R / "01_DATA/ACTIVE/local/ACTIVE_RELEASE.json").read_bytes())
assert p["generation"] == 93 and p["release_id"] == "internal-anchor-comparison-20261020-r1"
m = json.loads((R / p["manifest_path"]).read_bytes())
assert sha((R / p["manifest_path"]).read_bytes()) == p["release_manifest_sha256"]
with zipfile.ZipFile(B / "code.zip") as z:
    old = json.loads(z.read("CODE_MANIFEST.json"))
    files = {r["path"]: z.read(r["path"]) for r in old["files"]}
    assert all(sha(files[r["path"]]) == r["sha256"] for r in old["files"])
field_guide = json.loads(files["00_SYSTEM/PIPELINE.json"])["authorities"]["oracle_query_serving"]
before = dict(files)
for n, h in m["files"].items():
    raw = (R / m["code_root"] / n).read_bytes()
    assert sha(raw) == h
    files[n] = raw
# The previously corrected inventory excludes legacy build data ignored by Git.
correction = json.loads((H.with_name("ignore_push_next_20261020_r2") /
                         "CORRECTED_CODE_INVENTORY.json").read_bytes())
excluded = {}
for n in list(files):
    if n.startswith("02_BACKEND/lawrag/agents/agent6/corpus/"):
        assert n not in m["files"]
        excluded[n] = sha(files.pop(n))
assert len(excluded) == 6
extra = [R / "06_TOOLS/pipeline.py", R / "02_BACKEND/lawrag/pipeline/oracle_query_publish.py",
         R / "02_BACKEND/lawrag/pipeline/oracle_transfer_progress.py"]
extra += list((R / "02_BACKEND/lawrag/pipeline").glob("basis_*.py"))
extra += list((R / "02_BACKEND/lawrag/pipeline").glob("risk_basis_*.py"))
config = json.loads(files["00_SYSTEM/PIPELINE.json"])
files[field_guide] = (R / config["authorities"]["oracle_query_serving"]).read_bytes()
for source in extra:
    n = str(source.relative_to(R))
    files[n] = source.read_bytes()
assert all(sha(files[n]) == h for n, h in m["files"].items())
for entry in config["engines"].values():
    assert sha(files[entry["manifest"]]) == entry["sha256"]
    for n, h in json.loads(files[entry["manifest"]])["files"].items():
        assert sha(files[n]) == h, n
for entry in config["workflows"]["registered"]:
    assert sha(files[entry["manifest"]]) == entry["sha256"]
    for n, h in json.loads(files[entry["manifest"]])["files"].items():
        assert sha(files["02_BACKEND/workflow/" + n]) == h, n
for n, raw in files.items():
    assert Path(n).suffix.lower() not in {".js", ".jsx", ".mjs", ".cjs", ".db", ".sqlite", ".key", ".pem"}
    assert not (Path(n).name.startswith(".env") and not n.endswith(".example"))
    if n.endswith(".py"):
        ast.parse(raw, filename=n, feature_version=(3, 11))
changes = {n: {"before": sha(before[n]) if n in before else None, "after": sha(raw)}
           for n, raw in files.items() if before.get(n) != raw}
manifest = {k: v for k, v in old.items() if not k.endswith("_overlay")}
manifest.update(id=N,
    files=[{"path": n, "sha256": sha(b), "bytes": len(b)} for n, b in sorted(files.items())],
    required_files=[{"path": r["path"], "sha256": sha(files[r["path"]])}
                    for r in old["required_files"] if r["path"] in files],
    main93_overlay={"base_package": OLD, "source_pointer": p, "changes": changes,
                    "exact_main_files": sorted(m["files"]), "excluded_legacy_data": excluded,
                    "quality_certified": False, "field_status": "NOT_VERIFIED"})
with zipfile.ZipFile(H / "code.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
    for n, raw in sorted({**files, "CODE_MANIFEST.json": enc(manifest)}.items()):
        info = zipfile.ZipInfo(n, (2026, 10, 20, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        z.writestr(info, raw)
(H / "CODE_MANIFEST.json").write_bytes(enc(manifest))
(H / "SOURCE_POINTER.json").write_bytes(enc(p))
(H / "SOURCE_BINDING.json").write_bytes(enc({
    "source_pointer": p, "exact_main_files": len(m["files"]), "main_differences": [],
    "base_code_zip_sha256": sha((B / "code.zip").read_bytes()), "changes": changes,
    "excluded_legacy_build_data": excluded, "extra_tools": [str(x.relative_to(R)) for x in extra],
    "field_checkout": "~/DEV, resolve physical existing Git checkout",
    "field_commit": None, "field_generation": None, "field_generation_manifest_sha256": None,
    "field_codeserving_revision": None, "field_verified": False,
}))
spec = json.loads((B / "PACKAGE_SPEC.json").read_bytes())
spec.update(version=N, main_release=p["release_id"], main_generation=93,
            code_zip_sha256=sha((H / "code.zip").read_bytes()))
(H / "PACKAGE_SPEC.json").write_bytes(enc(spec))
for n in ("replace.py", "run.py", "code_smoke.py", "installed_contract_runner.py",
          "test_delivery.py", "final_verify.py", "prepare_package.py", "compile_311.py"):
    s = (B / n).read_text().replace(OLD, N).replace("MAIN92_CUMULATIVE", "MAIN93_INTERNAL_ANCHOR")
    s = s.replace("main92-cumulative-r1-logs", "main93-internal-anchor-r1-logs")
    if n == "code_smoke.py":
        s = s.replace("'1.19.4'", "'1.20.0'").replace("'internal_basis_discovery_workflow':'1.0.0'", "'internal_basis_discovery_workflow':'1.2.0'")
    if n == "test_delivery.py":
        s = s.replace("H.parent/'main90_research_20261020_r1/code.zip'", "H.parent/'main92_cumulative_20261020_r1/code.zip'")
        # Exercise ordinary Git add; the previous forced add concealed ignored corpus data.
        s = s.replace("names=[n for n in before if n!='.env']", "names=[n for n in before if n not in ('.env','CODE_MANIFEST.json','01_DATA/source.txt') and '/agent6/corpus/' not in n and not n.startswith('02_BACKEND/GENERATIONS/')]")
        s = s.replace("'add','-f','--'", "'add','--'")
        s = s.replace("*receipt['units']", "*[n for n in receipt['units'] if n!='CODE_MANIFEST.json']")
    (H / n).write_text(s)
s = (B / (OLD + "_RUN.txt")).read_text().replace(OLD, N).replace("MAIN92_CUMULATIVE", "MAIN93_INTERNAL_ANCHOR").replace("main92-cumulative-r1-logs", "main93-internal-anchor-r1-logs")
(H / (N + "_RUN.txt")).write_text(s)
for n in ("ORACLE_QUERY_DDL.sql", "ORACLE_QUERY_IMPLEMENTATION_UTF8.txt"):
    shutil.copyfile(B / n, H / n)
shutil.copytree(B / "wheels", H / "wheels", dirs_exist_ok=True)
root = H / "test-code"
assert not root.exists()
for n, raw in {**files, "CODE_MANIFEST.json": enc(manifest)}.items():
    dest = root / n
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
for row in json.loads(files["00_SYSTEM/WORKSPACE.json"])["roots"]:
    (root / row["canonical_path"]).mkdir(parents=True, exist_ok=True)
(H / "BUILD.json").write_bytes(enc({"code_files": len(files), "changed_files": len(changes),
    "exact_main_files": len(m["files"]), "excluded_legacy_data": len(excluded),
    "code_zip_bytes": (H / "code.zip").stat().st_size}))
print((H / "BUILD.json").read_text())
