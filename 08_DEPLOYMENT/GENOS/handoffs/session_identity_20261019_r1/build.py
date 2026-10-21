"""Overlay the reviewed session fix on the sealed cumulative MAIN87 package."""
import ast
import hashlib
import io
import json
import zipfile
from pathlib import Path

H=Path(__file__).resolve().parent
R=H.parents[3]
NAME='GENOS_SESSION_IDENTITY_20261019_R1'
CHANGED=['02_BACKEND/workflow/api.py','02_BACKEND/semantic_runtime/app.py',
         '02_BACKEND/semantic_runtime/legal_agent/memory_identity.py',
         '02_BACKEND/semantic_runtime/legal_agent/corrected_memory.py',
         '02_BACKEND/semantic_runtime/chat_adapter.py',
         '08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py','service.py',
         '02_BACKEND/semantic_runtime/session_identity.py']
NEW='02_BACKEND/semantic_runtime/session_identity.py'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def pack(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in sorted(files.items()):
            info=zipfile.ZipInfo(n,(2026,10,19,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
            z.writestr(info,b)
    return out.getvalue()

def main():
    assert not (H/'SEALED.json').exists(),'Do not overwrite a sealed delivery'
    prior=H.parent/'main87_patch_20261019_r1'
    base=(prior/'code.zip').read_bytes()
    assert sha(base)==json.loads((prior/'PACKAGE_SPEC.json').read_bytes())['code_zip_sha256']
    with zipfile.ZipFile(io.BytesIO(base)) as z:
        manifest=json.loads(z.read('CODE_MANIFEST.json'))
        files={row['path']:z.read(row['path']) for row in manifest['files']}
        assert all(sha(files[row['path']])==row['sha256'] for row in manifest['files'])
    before=dict(files)
    for n in CHANGED:
        if n!=NEW:assert (H/'before'/n).read_bytes()==before[n],n
        files[n]=(R/n).read_bytes()
    pipeline=json.loads(files['00_SYSTEM/PIPELINE.json'])
    for row in pipeline['workflows']['registered']:
        n=row['manifest'];v=json.loads(files[n])
        for rel in v['files']:
            v['files'][rel]=sha(files['02_BACKEND/workflow/'+rel])
        files[n]=enc(v);row['sha256']=sha(files[n])
    for row in pipeline['engines'].values():
        n=row['manifest'];v=json.loads(files[n]);pins=v['files']
        for rel in list(pins):pins[rel]=sha(files[rel])
        if '02_BACKEND/semantic_runtime/app.py' in pins:pins[NEW]=sha(files[NEW])
        v['files']=dict(sorted(pins.items()));files[n]=enc(v);row['sha256']=sha(files[n])
    files['00_SYSTEM/PIPELINE.json']=enc(pipeline)
    changes={n:{'before':sha(before[n]) if n in before else None,'after':sha(b)}
             for n,b in files.items() if before.get(n)!=b}
    # Integrate exact changed pins without replacing other working-tree content.
    for n in changes:
        if n in CHANGED:continue
        current=(R/n).read_bytes()
        if current!=files[n]:
            assert current==before[n] or ((H/'before'/n).exists() and current==(H/'last-built'/n).read_bytes()),n
            old=H/'before'/n;old.parent.mkdir(parents=True,exist_ok=True)
            if not old.exists():old.write_bytes(current)
            (R/n).write_bytes(files[n])
        last=H/'last-built'/n;last.parent.mkdir(parents=True,exist_ok=True);last.write_bytes(files[n])
    for n,b in files.items():
        assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs'}
        if n.endswith('.py'):ast.parse(b,filename=n,feature_version=(3,11))
    basis=manifest['main_basis'];basis['genos_overlays']=changes
    basis['deployment_serving_files']={n:sha(files[n]) for n in basis['serving_files']}
    basis['repinned_files']=[n for n in changes if n not in CHANGED]
    basis['identity_policy']='team-session-v1'
    manifest.update(id=NAME,files=[{'path':n,'sha256':sha(b),'bytes':len(b)} for n,b in sorted(files.items())])
    for row in manifest['required_files']:row['sha256']=sha(files[row['path']])
    raw=pack({**files,'CODE_MANIFEST.json':enc(manifest)})
    (H/'code.zip').write_bytes(raw);(H/'CODE_MANIFEST.json').write_bytes(enc(manifest))
    source={'main_basis':basis,'code_zip_sha256':sha(raw),'payload_files':len(files),
            'baseline_code_zip_sha256':sha(base),'changes':changes,
            'selected_main_files_unchanged':sum(before[n]==files[n] for n in basis['serving_files']),
            'local_main_pointer_changed':False,'genos_field_status':'NOT_VERIFIED'}
    (H/'SOURCE_BINDING.json').write_bytes(enc(source))
    (H/'FILENAME_EXCEPTIONS.json').write_bytes(files['00_SYSTEM/FILENAME_EXCEPTIONS.json'])
    (H/'GENOS_OVERLAYS.diff').write_text('\n'.join(n+' '+v['after'] for n,v in changes.items())+'\n')
    # One small code fixture, shared by sequential tests. No original data copied.
    root=H/'test-code'
    for n,b in {**files,'CODE_MANIFEST.json':enc(manifest)}.items():
        p=root/n;p.parent.mkdir(parents=True,exist_ok=True)
        if not p.exists() or p.read_bytes()!=b:p.write_bytes(b)
    print(json.dumps({'files':len(files),'changes':len(changes),'code_zip_sha256':sha(raw)}))

if __name__=='__main__':main()
