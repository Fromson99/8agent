"""Build a small additive DP patch from the sealed mailed MAIN81 R2, never live service.py."""
import ast,base64,difflib,hashlib,io,json,subprocess,zipfile,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4];H=Path(__file__).resolve().parent
DATA=ROOT/'08_DEPLOYMENT/DATAIKU/legal_oracle_dp_20261016_r1'
NAME='GENOS_ORACLE_DP_20261016_R1'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def enc(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
def pack(files):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,raw in sorted(files.items()):
            assert Path(n).suffix.lower() not in ('.js','.jsx','.mjs','.cjs')
            info=zipfile.ZipInfo(n,(2026,10,16,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,raw)
    return buf.getvalue()
def replace(s,before,after,count=1):
    assert s.count(before)==count,(before,s.count(before))
    return s.replace(before,after)
def main():
    if (H/'SEALED.json').exists():raise RuntimeError('sealed delivery; use a new revision')
    base=H.parent/'main_full_20261016_r2/code.zip'
    assert sha(base.read_bytes())=='49ffde3c33d413d2875a4d7fde39abc281cd135ba8e1d63d863e548bd9a6f903'
    with zipfile.ZipFile(base) as z:
        baseline=json.loads(z.read('CODE_MANIFEST.json'));old=z.read('service.py').decode()
    (H/'BASE_MANIFEST.json').write_bytes(enc(baseline))
    s=replace(old,'def _resolve_binding() -> tuple[Path, Path, dict[str, Any]]:\n',
        'def _resolve_binding() -> tuple[Path, Path, dict[str, Any]]:\n    from semantic_runtime.oracle_dp import enabled as dp_enabled, resolve as dp_resolve\n    if dp_enabled():\n        return dp_resolve(_ROOT)\n')
    s=replace(s,'    if _APP is not None:\n        obs.event(log, "runtime.cache.hit", binding=_BINDING)',
        '''    if _APP is not None:
        from semantic_runtime.oracle_dp import enabled as dp_enabled, environment_binding as dp_environment_binding
        if dp_enabled() != ((_BINDING or {}).get('mode') == 'oracle-dp'):
            raise RuntimeError('data provider changed; restart this process before reusing the application')
        if dp_enabled() and dp_environment_binding() != _BINDING.get('dp_environment_binding'):
            raise RuntimeError('Oracle DP release/connection/cache settings changed; restart this process')
        obs.event(log, "runtime.cache.hit", binding=_BINDING)''')
    s=replace(s,"('genos-generation', 'genos-data-current')","('genos-generation', 'genos-data-current', 'oracle-dp')",3)
    s=replace(s,'("genos-generation", "genos-data-current")','("genos-generation", "genos-data-current", "oracle-dp")')
    s=replace(s,'if not (os.environ.get("GENOS_GENERATION", "").strip() or\n            os.environ.get("GENOS_DATA_ROOT", "").strip()):',
        'from semantic_runtime.oracle_dp import enabled as dp_enabled\n    if not (dp_enabled() or os.environ.get("GENOS_GENERATION", "").strip() or\n            os.environ.get("GENOS_DATA_ROOT", "").strip()):')
    s=replace(s,'if (os.environ.get("GENOS_GENERATION", "").strip() or os.environ.get("GENOS_DATA_ROOT", "").strip()) and os.environ.get("GENOS_AUTO_WARMUP", "1")',
        'if (os.environ.get("DP", "").strip().lower() in {"1", "true", "oracle"} or os.environ.get("GENOS_GENERATION", "").strip() or os.environ.get("GENOS_DATA_ROOT", "").strip()) and os.environ.get("GENOS_AUTO_WARMUP", "1")')
    s=replace(s,'return {"generation_path": str(store.path), "document_count": len(scope)}',
        '''return {"generation_path": str(store.path), "document_count": len(scope),
                    "data_provider": (_BINDING or {}).get("data_provider", "generation"),
                    "dp_release_id": (_BINDING or {}).get("release_id") if (_BINDING or {}).get("mode")=="oracle-dp" else None,
                    "nfs_source_used": (_BINDING or {}).get("nfs_source_used"),
                    "cache_hit": (_BINDING or {}).get("cache_hit")}''')
    files={'service.py':s.encode()}
    for module in ('semantic_runtime/oracle_dp_io.py','semantic_runtime/oracle_dp_assets.py','semantic_runtime/oracle_dp.py',
                   'lawrag/pipeline/oracle_migration.py','lawrag/pipeline/oracle_publish.py'):
        files['02_BACKEND/'+module]=(ROOT/'02_BACKEND'/module).read_bytes()
    for n,raw in files.items():
        ast.parse(raw,filename=n,feature_version=(3,11));path=H/'payload'/n;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    (H/'SERVICE_DP.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='MAIN81_R2/service.py',tofile='ORACLE_DP/service.py')))
    after={n:sha(raw) for n,raw in files.items()}
    spec={'id':NAME,'base_code_zip_sha256':sha(base.read_bytes()),'main_basis':baseline['main_basis'],
        'before':{r['path']:r['sha256'] for r in baseline['files']},'after':after,'payload_sha256':sha(enc(after))}
    (H/'PATCH_SPEC.json').write_bytes(enc(spec))
    (H/'code_smoke.py').write_bytes((H.parent/'main_full_20261016_r2/code_smoke.py').read_bytes()+b'\nimport semantic_runtime.oracle_dp, lawrag.pipeline.oracle_publish\nprint("ORACLE_DP_IMPORT_PASS")\n')
    # Complete standalone notebook cell; uniquely named modules, no edit to DEV/import path.
    mods=[('oracle_dp_io','02_BACKEND/semantic_runtime/oracle_dp_io.py'),('oracle_dp_assets','02_BACKEND/semantic_runtime/oracle_dp_assets.py'),
          ('oracle_migration','02_BACKEND/lawrag/pipeline/oracle_migration.py'),('oracle_publish','02_BACKEND/lawrag/pipeline/oracle_publish.py')]
    cell='''# 원문 전체 이관 + ACTION="verify" 성공 후 같은 R6 커널의 새 Code 셀에서 실행
# 위 이관 셀의 LEGAL_FULL_TRANSFER_RESULT를 사용합니다. 커널을 다시 시작했다면 아래 경로를 직접 지정하세요.
TRANSFER_RECEIPT = globals().get("LEGAL_FULL_TRANSFER_RESULT", {}).get("receipt", "")
RUN_SECONDS = 3600
import base64 as _b, zlib as _z, types as _t, sys as _s, hashlib as _h
'''
    aliases={name:'_dp_publish_r1_'+name for name,_ in mods}
    for name,path in mods:
        code=(ROOT/path).read_text()
        for module,alias in aliases.items():
            code=code.replace('from semantic_runtime.'+module+' import','from '+alias+' import').replace('from .'+module+' import','from '+alias+' import')
        blob=code.encode();encoded=base64.b64encode(zlib.compress(blob,9)).decode()
        cell+=f'_raw=_z.decompress(_b.b64decode({encoded!r}))\nassert _h.sha256(_raw).hexdigest()=={sha(blob)!r}\n_m=_t.ModuleType({aliases[name]!r});_s.modules[_m.__name__]=_m\nexec(compile(_raw,{(name+".py")!r},"exec"),_m.__dict__)\n'
    cell+='''if "desk" not in globals() or not TRANSFER_RECEIPT:
    raise RuntimeError("R6 연결 desk와 VERIFIED 원문 전체 이관 receipt 경로가 필요합니다.")
LEGAL_DP_PUBLISH_RESULT = _m.from_notebook(desk, TRANSFER_RECEIPT, seconds=RUN_SECONDS)
print(LEGAL_DP_PUBLISH_RESULT)
'''
    (H/(NAME+'_PUBLISH_CELL.txt')).write_text(cell)
    (H/(NAME+'_CREATE_TABLES.txt')).write_bytes((DATA/'DP_EXTRA_TABLES.sql').read_bytes())
    runtime={str(p.relative_to(H)):p.read_bytes() for p in (H/'payload').rglob('*') if p.is_file()}
    runtime.update({n:(H/n).read_bytes() for n in ('PATCH_SPEC.json','BASE_MANIFEST.json','install.py','code_smoke.py')})
    raw=pack(runtime)
    shell='''#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
task_logs="./oracle-dp-r1-logs"
mkdir -p -- "$task_logs"
task_log="$task_logs/$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
exec > >(tee -a "$task_log") 2>&1
trap 'task_exit=$?; printf "DP_PATCH_EXIT=%s LOG=%s\\n" "$task_exit" "$task_log"; printf "%s\\n" "$task_exit" > "$task_log.exit"' EXIT
printf 'TRANSFER=%s\\n' "$PWD"
if [[ -n "${GENOS_PYTHON_DIR:-}" ]]; then export PATH="$GENOS_PYTHON_DIR:$PATH"; elif [[ -x /venv/bin/python3 ]]; then export PATH="/venv/bin:$PATH"; fi
python3 - "$@" <<'DP_PATCH_PY'
import base64,hashlib,io,os,pathlib,subprocess,sys,zipfile
raw=base64.b64decode('EMBEDDED')
if hashlib.sha256(raw).hexdigest()!='SHA':raise ValueError('embedded patch changed')
root=pathlib.Path.cwd()/'oracle-dp-r1-state'
if any(p.is_symlink() for p in (root,*root.parents)):raise ValueError('state symlink')
root.mkdir(exist_ok=True)
with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for name in z.namelist():
        p=pathlib.PurePosixPath(name)
        if p.is_absolute() or '..' in p.parts or '\\\\' in name:raise ValueError('unsafe package')
        target=root/name;value=z.read(name)
        if any(p.is_symlink() for p in (target,*target.parents)):raise ValueError('state symlink')
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if target.read_bytes()!=value:raise ValueError('state bytes differ: '+name)
        else:target.write_bytes(value)
raise SystemExit(subprocess.run([sys.executable,str(root/'install.py'),*sys.argv[1:]],env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}).returncode)
DP_PATCH_PY
'''.replace('EMBEDDED',base64.b64encode(raw).decode()).replace("'SHA'",repr(sha(raw)))
    (H/(NAME+'_RUN.txt')).write_text(shell);subprocess.run(['bash','-n',H/(NAME+'_RUN.txt')],check=True)
    outer={**runtime,NAME+'_RUN.txt':shell.encode()}
    for name in (NAME+'_PUBLISH_CELL.txt',NAME+'_CREATE_TABLES.txt','GUIDE_UTF8.txt','SERVICE_DP.diff','VALIDATION.json'):
        if (H/name).exists():outer[name]=(H/name).read_bytes()
    (H/(NAME+'.zip')).write_bytes(pack(outer))
    records={n:{'sha256':sha((H/n).read_bytes()),'bytes':(H/n).stat().st_size} for n in (NAME+'.zip',NAME+'_RUN.txt',NAME+'_PUBLISH_CELL.txt',NAME+'_CREATE_TABLES.txt')}
    (H/'PACKAGE_BINDING.json').write_bytes(enc({'files':records,'payload_sha256':spec['payload_sha256'],'base':spec['main_basis']}))
    print(json.dumps(records))
if __name__=='__main__':main()
