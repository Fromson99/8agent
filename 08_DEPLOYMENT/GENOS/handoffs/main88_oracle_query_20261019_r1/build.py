"""Compose selected MAIN88 and verified Oracle changes over sealed full dependencies."""
from pathlib import Path
import ast,hashlib,io,json,zipfile,difflib
H=Path(__file__).resolve().parent;R=H.parents[3]
NAME='GENOS_MAIN88_ORACLE_QUERY_20261019_R1'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def enc(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode()
def pack(files):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,b in sorted(files.items()):
            info=zipfile.ZipInfo(n,(2026,10,19,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,b)
    return buf.getvalue()
def main():
    assert not (H/'SEALED.json').exists()
    pointer_raw=(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes();pointer=json.loads(pointer_raw)
    assert pointer['generation']==88
    raw=(R/pointer['manifest_path']).read_bytes();assert sha(raw)==pointer['release_manifest_sha256']
    main=json.loads(raw);selected=R/main['code_root']
    prior=H.parent/'session_identity_20261019_r1';base=(prior/'code.zip').read_bytes()
    assert sha(base)==json.loads((prior/'PACKAGE_SPEC.json').read_bytes())['code_zip_sha256']
    with zipfile.ZipFile(io.BytesIO(base)) as z:
        old=json.loads(z.read('CODE_MANIFEST.json'));files={row['path']:z.read(row['path']) for row in old['files']}
        assert all(sha(files[row['path']])==row['sha256'] for row in old['files'])
    sources={n:'sealed-session-identity-full-dependency' for n in files}
    for n,pin in main['files'].items():
        raw=(selected/n).read_bytes();assert sha(raw)==pin,n
        files[n]=raw;sources[n]='selected-MAIN88'
    baseline=dict(files)
    audited=json.loads((R/'09_ARTIFACTS/AUDITS/20261019-oracle-query/CODE_MANIFEST.json').read_bytes())['files']
    for n,pin in audited.items():
        review=json.loads((H/'INTEGRATION_OVERRIDES.json').read_bytes())['files']
        assert sha((R/n).read_bytes())==review.get(n,pin),('Working drift after validation',n)
        if n.startswith(('02_BACKEND/','00_SYSTEM/','06_TOOLS/')) or n in ('service.py','main_router.py','requirements.txt','.env.genos.example'):
            files[n]=(R/n).read_bytes();sources[n]='validated-Oracle-working'
    extras=['genos_diagnostics.py',*map(lambda p:str(p.relative_to(R)),(R/'02_BACKEND/semantic_runtime').glob('oracle_dp*.py'))]
    for n in extras:files[n]=(R/n).read_bytes();sources[n]='Oracle-service-import-dependency'
    files.pop('00_SYSTEM/GENOS_SERVING_PATHS.json',None)
    pipeline=json.loads(files['00_SYSTEM/PIPELINE.json'])
    pipeline['authorities']['oracle_query_serving']='08_DEPLOYMENT/GENOS/ORACLE_QUERY_GUIDE.txt'
    files['08_DEPLOYMENT/GENOS/ORACLE_QUERY_GUIDE.txt']=(R/'09_ARTIFACTS/AUDITS/20261019-oracle-query/IMPLEMENTATION_UTF8.txt').read_bytes()
    sources['08_DEPLOYMENT/GENOS/ORACLE_QUERY_GUIDE.txt']='Oracle-implementation-guide'
    for entry in pipeline['workflows']['registered']:
        n=entry['manifest'];v=json.loads(files[n])
        for rel in v['files']:v['files'][rel]=sha(files['02_BACKEND/workflow/'+rel])
        files[n]=enc(v);entry['sha256']=sha(files[n])
    for entry in pipeline['engines'].values():
        n=entry['manifest'];v=json.loads(files[n])
        for rel in v['files']:v['files'][rel]=sha(files[rel])
        files[n]=enc(v);entry['sha256']=sha(files[n])
    files['00_SYSTEM/PIPELINE.json']=enc(pipeline)
    changes={n:{'before':sha(baseline[n]) if n in baseline else None,'after':sha(b),'source':sources.get(n,'repinned')}
             for n,b in files.items() if baseline.get(n)!=b}
    code_diffs=[]
    for n in changes:
        if n.endswith('.py') and n in baseline:
            code_diffs.extend(difflib.unified_diff(baseline[n].decode().splitlines(True),files[n].decode().splitlines(True),fromfile='MAIN88/'+n,tofile='merged/'+n))
    (H/'MERGED_CODE.diff').write_text(''.join(code_diffs))
    main87=json.loads((R/'08_DEPLOYMENT/RELEASES/cm-read-continuity-20261019-r1/release.json').read_bytes())
    delta={n:h for n,h in main['files'].items() if main87['files'].get(n)!=h}
    overlap={n:changes[n] for n in delta if n in changes and not n.startswith('02_BACKEND/ENGINES/') and n!='00_SYSTEM/PIPELINE.json'}
    assert set(overlap)<= {'service.py','02_BACKEND/semantic_runtime/app.py','02_BACKEND/semantic_runtime/legal_agent/law_candidates.py','02_BACKEND/semantic_runtime/oracle_dp.py'},overlap
    for n,h in delta.items():
        if n not in changes:assert sha(files[n])==h
    for n,b in files.items():
        assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs','.db','.sqlite','.key','.pem'}
        assert not (Path(n).name.startswith('.env') and not n.endswith('.example'))
        if n.endswith('.py'):ast.parse(b,filename=n,feature_version=(3,11))
    basis={'release_id':main['release_id'],'pointer_generation':pointer['generation'],'pointer_sha256':sha(pointer_raw),
           'release_manifest_sha256':pointer['release_manifest_sha256'],'serving_files':main['files'],
           'deployment_serving_files':{n:sha(files[n]) for n in main['files']},'genos_overlays':changes,
           'main88_new_behavior_overlap':overlap,'latest_main_delta_files':len(delta),
           'genos_models':'existing internal GENOS model settings','data_policy':'Oracle selective reads; existing SQLite mode and external NFS state retained'}
    manifest={'format':'8agent-code/1','id':NAME,'main_basis':basis,
       'files':[{'path':n,'sha256':sha(b),'bytes':len(b)} for n,b in sorted(files.items())],
       'required_files':[{'path':v['path'],'sha256':sha(files[v['path']])} for v in old['required_files'] if v['path'] in files],
       'source_git_commit':None,'dependency_code_zip_sha256':sha(base),'field_deployment_status':'NOT_VERIFIED'}
    raw=pack({**files,'CODE_MANIFEST.json':enc(manifest)})
    (H/'code.zip').write_bytes(raw);(H/'CODE_MANIFEST.json').write_bytes(enc(manifest))
    (H/'SOURCE_POINTER.json').write_bytes(pointer_raw)
    (H/'SOURCE_BINDING.json').write_bytes(enc({'main_basis':basis,'sources':sources,'payload_files':len(files),
        'code_zip_sha256':sha(raw),'local_main_pointer_changed':False,'field_checkout':'existing checkout; confirmed physical path required','field_commit':None,'field_codeserving_revision':None}))
    wheels={p.name:sha(p.read_bytes()) for p in (H/'wheels').glob('*.whl')}
    (H/'PACKAGE_SPEC.json').write_bytes(enc({'version':NAME,'code_zip_sha256':sha(raw),'main_release':main['release_id'],
        'main_generation':pointer['generation'],'wheels':wheels}))
    (H/'replace.py').write_bytes(files['06_TOOLS/OFFLINE/genos_code_replace.py'])
    root=H/'test-code';root.mkdir(exist_ok=True)
    for n,b in {**files,'CODE_MANIFEST.json':enc(manifest)}.items():
        p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    print(json.dumps({'files':len(files),'overlays':len(changes),'main88_behavior_overlap':list(overlap),'zip_bytes':len(raw)}))
if __name__=='__main__':main()
