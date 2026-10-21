"""Overlay exact selected MAIN95 onto the sealed cumulative MAIN94 handoff."""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import zipfile

H=Path(__file__).resolve().parent
R=H.parents[3]
B=H.with_name("main94_investigation_dedup_20261020_r1")
N="GENOS_MAIN95_COMPARISON_SCOPE_20261020_R1"
OLD="GENOS_MAIN94_INVESTIGATION_DEDUP_20261020_R1"
sha=lambda b:hashlib.sha256(b).hexdigest()
enc=lambda v:(json.dumps(v,ensure_ascii=False,indent=2)+"\n").encode()
assert not (H/"SEALED.json").exists()
p=json.loads((R/"01_DATA/ACTIVE/local/ACTIVE_RELEASE.json").read_bytes())
assert p["generation"]==95 and p["release_id"]=="comparison-display-scope-20261020-r1"
m=json.loads((R/p["manifest_path"]).read_bytes())
assert sha((R/p["manifest_path"]).read_bytes())==p["release_manifest_sha256"]
with zipfile.ZipFile(B/"code.zip") as z:
    old=json.loads(z.read("CODE_MANIFEST.json"))
    files={r["path"]:z.read(r["path"]) for r in old["files"]}
    assert all(sha(files[r["path"]])==r["sha256"] for r in old["files"])
before=dict(files)
for n,h in m["files"].items():
    raw=(R/m["code_root"]/n).read_bytes()
    assert sha(raw)==h
    files[n]=raw
config=json.loads(files["00_SYSTEM/PIPELINE.json"])
for entry in config["engines"].values():
    assert sha(files[entry["manifest"]])==entry["sha256"]
    assert all(sha(files[n])==h for n,h in json.loads(files[entry["manifest"]])["files"].items())
for entry in config["workflows"]["registered"]:
    assert sha(files[entry["manifest"]])==entry["sha256"]
    assert all(sha(files["02_BACKEND/workflow/"+n])==h
               for n,h in json.loads(files[entry["manifest"]])["files"].items())
for n,raw in files.items():
    assert Path(n).suffix.lower() not in {".js",".jsx",".mjs",".cjs",".db",".sqlite",".key",".pem"}
    if n.endswith(".py"):ast.parse(raw,filename=n,feature_version=(3,11))
changes={n:{"before":sha(before[n]) if n in before else None,"after":sha(raw)}
         for n,raw in files.items() if before.get(n)!=raw}
manifest={k:v for k,v in old.items() if not k.endswith("_overlay")}
manifest.update(id=N,files=[{"path":n,"sha256":sha(b),"bytes":len(b)} for n,b in sorted(files.items())],
    required_files=[{"path":r["path"],"sha256":sha(files[r["path"]])} for r in old["required_files"]],
    main95_overlay={"base_package":OLD,"source_pointer":p,"changes":changes,
                    "exact_main_files":sorted(m["files"]),"quality_certified":False,"field_status":"NOT_VERIFIED"})
with zipfile.ZipFile(H/"code.zip","w",zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for n,raw in sorted({**files,"CODE_MANIFEST.json":enc(manifest)}.items()):
        info=zipfile.ZipInfo(n,(2026,10,20,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        z.writestr(info,raw)
(H/"CODE_MANIFEST.json").write_bytes(enc(manifest))
(H/"SOURCE_POINTER.json").write_bytes(enc(p))
(H/"SOURCE_BINDING.json").write_bytes(enc({
    "source_pointer":p,"exact_main_files":len(m["files"]),"main_differences":[],
    "base_code_zip_sha256":sha((B/"code.zip").read_bytes()),"changes":changes,
    "field_checkout":"~/DEV, resolve physical existing Git checkout",
    "field_commit":None,"field_generation":None,"field_generation_manifest_sha256":None,
    "field_codeserving_revision":None,"field_verified":False}))
spec=json.loads((B/"PACKAGE_SPEC.json").read_bytes())
spec.update(version=N,main_release=p["release_id"],main_generation=95,
            code_zip_sha256=sha((H/"code.zip").read_bytes()))
(H/"PACKAGE_SPEC.json").write_bytes(enc(spec))
for n in ("replace.py","run.py","code_smoke.py","installed_contract_runner.py",
          "test_delivery.py","final_verify.py","prepare_package.py","compile_311.py","checks.py","display_fixture.py"):
    s=(B/n).read_text().replace(OLD,N).replace("MAIN94_INVESTIGATION_DEDUP","MAIN95_COMPARISON_SCOPE")
    s=s.replace("main94-investigation-dedup-r1-logs","main95-comparison-scope-r1-logs")
    if n=="code_smoke.py":s=s.replace("'1.20.1'","'1.20.2'")
    if n=="test_delivery.py":
        s=s.replace("H.parent/'main93_internal_anchor_20261020_r1/code.zip'",
                    "H.parent/'main94_investigation_dedup_20261020_r1/code.zip'")
    if n=="prepare_package.py":
        s=s.replace("'GUIDE_UTF8.txt']", "'GUIDE_UTF8.txt','EXPERIMENT_RESULT.txt']")
    (H/n).write_text(s)
s=(B/(OLD+"_RUN.txt")).read_text().replace(OLD,N).replace("MAIN94_INVESTIGATION_DEDUP","MAIN95_COMPARISON_SCOPE")
s=s.replace("main94-investigation-dedup-r1-logs","main95-comparison-scope-r1-logs")
(H/(N+"_RUN.txt")).write_text(s)
for n in ("ORACLE_QUERY_DDL.sql","ORACLE_QUERY_IMPLEMENTATION_UTF8.txt"):
    shutil.copyfile(B/n,H/n)
shutil.copytree(B/"wheels",H/"wheels",dirs_exist_ok=True)
root=H/"test-code"
assert not root.exists()
for n,raw in {**files,"CODE_MANIFEST.json":enc(manifest)}.items():
    dest=root/n;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
for row in json.loads(files["00_SYSTEM/WORKSPACE.json"])["roots"]:
    (root/row["canonical_path"]).mkdir(parents=True,exist_ok=True)
(H/"BUILD.json").write_bytes(enc({"code_files":len(files),"changed_files":len(changes),
    "exact_main_files":len(m["files"]),"code_zip_bytes":(H/"code.zip").stat().st_size}))
print((H/"BUILD.json").read_text())
