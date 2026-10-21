"""Freeze the selected MAIN plus sealed pipeline dependencies, never working drift."""
import ast, hashlib, importlib.util, io, json, subprocess, zipfile
from pathlib import Path

H = Path(__file__).resolve().parent
R = H.parents[3]
NAME = 'GENOS_MAIN_FULL_20261016_R1'
CONFIG = '00_SYSTEM/GENOS_SERVING_PATHS.json'

def sha(raw): return hashlib.sha256(raw).hexdigest()
def enc(value): return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode()
def pack(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for n, raw in sorted(files.items()):
            info = zipfile.ZipInfo(n, (2026,10,16,0,0,0)); info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, raw)
    return buf.getvalue()

def main():
    pointer_path = H/'SOURCE_POINTER.json'
    if not pointer_path.exists(): pointer_path.write_bytes((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())
    pointer = json.loads(pointer_path.read_bytes())
    release_raw = (R/pointer['manifest_path']).read_bytes()
    assert sha(release_raw)==pointer['release_manifest_sha256']
    release = json.loads(release_raw); code = R/release['code_root']
    spec=importlib.util.spec_from_file_location('ship',R/'06_TOOLS/COMMANDS/code_ship.py')
    ship=importlib.util.module_from_spec(spec);spec.loader.exec_module(ship)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=R,text=True).strip()
    names=subprocess.check_output(['git','ls-tree','-r','--name-only',commit],cwd=R,text=True).splitlines()
    payload={};sources={}
    for n in names:
        if not ship._allowed(n) or ship._blocked(n) or n==CONFIG: continue
        raw=subprocess.check_output(['git','show',commit+':'+n],cwd=R)
        payload[n]=raw;sources[n]='git:'+commit
    # The prior sealed latest-selection delivery already validated the complete
    # native collector/structure/index dependencies. Serving MAIN takes priority.
    prior=H.parent/'latest_selection_20261015_r1'
    m=json.loads((prior/'PAYLOAD_MANIFEST.json').read_bytes())
    assert sha((prior/'PAYLOAD.zip').read_bytes())==m['payload_sha256']
    with zipfile.ZipFile(prior/'PAYLOAD.zip') as z:
        for n,row in m['files'].items():
            raw=z.read(n);assert sha(raw)==row['sha256']
            payload[n]=raw;sources[n]='sealed:GENOS_LATEST_SELECTION_20261015_R1'
    for n,pin in release['files'].items():
        raw=(code/n).read_bytes();assert sha(raw)==pin,n
        payload[n]=raw;sources[n]='selected:'+release['release_id']
    assert CONFIG not in payload
    for n,raw in payload.items():
        assert not n.startswith(('01_DATA/','90_RUNTIME/','.git/','.venv/'))
        assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs','.db','.sqlite','.key','.pem'}
        if n.endswith('.py'): ast.parse(raw,filename=n,feature_version=(3,11))
    pipeline=json.loads(payload['00_SYSTEM/PIPELINE.json'])
    for row in pipeline['engines'].values():
        assert sha(payload[row['manifest']])==row['sha256'],row['manifest']
        for n,pin in json.loads(payload[row['manifest']])['files'].items():assert sha(payload[n])==pin,n
    rows=[{'path':n,'sha256':sha(b),'bytes':len(b)} for n,b in sorted(payload.items())]
    basis={'release_id':release['release_id'],'pointer_generation':pointer['generation'],
           'release_manifest_sha256':sha(release_raw),'pointer_sha256':sha(pointer_path.read_bytes()),
           'serving_files':release['files'],'genos_models':'existing internal GENOS settings',
           'data_policy':'preserve field generation; apply filename-search-selection-v2 separately'}
    manifest={'format':'8agent-code/1','id':NAME,'files':rows,'main_basis':basis,
              'required_files':[{'path':n,'sha256':sha(payload[n])} for n in ship.REQUIRED_FILES],
              'source_git_commit':commit,'field_deployment_status':'NOT_VERIFIED'}
    raw=pack({**payload,'CODE_MANIFEST.json':enc(manifest)})
    (H/'code.zip').write_bytes(raw);(H/'CODE_MANIFEST.json').write_bytes(enc(manifest))
    (H/'SOURCE_BINDING.json').write_bytes(enc({'main_basis':basis,'sources':sources,'code_zip_sha256':sha(raw),
        'payload_files':len(rows),'selected_main_files_unchanged':len(release['files']),
        'working_differences_excluded':[n for n in release['files'] if (R/n).is_file() and sha((R/n).read_bytes())!=release['files'][n]]}))
    (H/'FILENAME_EXCEPTIONS.json').write_bytes(payload['00_SYSTEM/FILENAME_EXCEPTIONS.json'])
    (H/'replace.py').write_bytes(payload['06_TOOLS/OFFLINE/genos_code_replace.py'])
    (H/'comparison.py').write_bytes((prior/'comparison.py').read_bytes())
    (H/'search_smoke.py').write_bytes((prior/'search_smoke.py').read_bytes())
    # The editor consumer must follow the selected MAIN along with the backend.
    workflow=payload['08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
    (H/(NAME+'_WORKFLOW_PASTE_ALL.txt')).write_bytes(workflow)
    print(json.dumps({'main':pointer['generation'],'files':len(rows),'bytes':len(raw),'sha256':sha(raw)}))

if __name__=='__main__':main()
