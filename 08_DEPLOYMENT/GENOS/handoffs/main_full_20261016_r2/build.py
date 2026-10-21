"""Freeze the selected MAIN plus sealed pipeline dependencies, never working drift."""
import ast, difflib, hashlib, importlib.util, io, json, subprocess, zipfile
from pathlib import Path

H = Path(__file__).resolve().parent
R = H.parents[3]
NAME = 'GENOS_MAIN_FULL_20261016_R2'
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
    if (H/'SEALED.json').exists():raise RuntimeError('Preserve the sealed delivery; use a new revision')
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
    # Preserve previously shipped GENOS-only behavior which the selected local
    # MAIN does not yet include. Apply only sealed, exact-context edits onto MAIN;
    # never replace entire evolving modules with an older field snapshot.
    transform_spec=importlib.util.spec_from_file_location('field_transform',H.parent/'ad_request_logs_20261013_r1/build_delivery.py')
    transform=importlib.util.module_from_spec(transform_spec);transform_spec.loader.exec_module(transform)
    original=dict(payload);overlays=[];changes={}
    for folder,n in [('output_unlimited_20261015_r1','service.py'),
                     ('output_unlimited_20261015_r1','02_BACKEND/semantic_runtime/ad_model.py'),
                     ('fact_reason_20261015_r1','02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py')]:
        origin=H.parent/folder;before=(origin/'preimage'/n).read_bytes();after=(origin/'payload'/n).read_bytes()
        if folder.startswith('output_'):
            source=json.loads((origin/'SOURCE_BINDING.json').read_bytes())
            assert sha(before)==source['preimage_files'][n] and sha(after)==source['source_files'][n]
        else:
            assert sha(before)=='b3fbe5f16b6322654b363e1487a38a0026bd6762aa70ca4bb89cb62d4cb2db08'
            assert sha(after)=='df86acfa871bbadc3d2fabdab6f8d1f9874a8e18a2b1cc6a84909914ca2e3fa9'
        changes[n]=transform.transform(payload[n],before,after,n)
        overlays.append({'path':n,'sealed_source':folder,'main_sha256':sha(payload[n]),'deployment_sha256':sha(changes[n]),
                         'sealed_preimage_sha256':sha(before),'sealed_result_sha256':sha(after)})
    payload=transform.repin(payload,changes,{})
    changed={n for n in payload if payload[n]!=original[n]}
    for n in changed:sources[n]='selected MAIN + sealed GENOS overlay/pin'
    (H/'GENOS_OVERLAYS.diff').write_text(''.join(''.join(difflib.unified_diff(original[n].decode().splitlines(keepends=True),payload[n].decode().splitlines(keepends=True),fromfile='MAIN/'+n,tofile='GENOS/'+n)) for n in sorted(changes)))
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
           'serving_files':release['files'],'deployment_serving_files':{n:sha(payload[n]) for n in release['files']},
           'genos_overlays':overlays,'repinned_files':sorted(changed-set(changes)),
           'genos_models':'existing internal GENOS settings',
           'data_policy':'preserve field generation and existing search selection; code-only install'}
    manifest={'format':'8agent-code/1','id':NAME,'files':rows,'main_basis':basis,
              'required_files':[{'path':n,'sha256':sha(payload[n])} for n in ship.REQUIRED_FILES],
              'source_git_commit':commit,'field_deployment_status':'NOT_VERIFIED'}
    raw=pack({**payload,'CODE_MANIFEST.json':enc(manifest)})
    (H/'code.zip').write_bytes(raw);(H/'CODE_MANIFEST.json').write_bytes(enc(manifest))
    (H/'SOURCE_BINDING.json').write_bytes(enc({'main_basis':basis,'sources':sources,'code_zip_sha256':sha(raw),
        'payload_files':len(rows),'selected_main_files_unchanged':sum(sha(payload[n])==pin for n,pin in release['files'].items()),
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
