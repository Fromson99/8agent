"""Freeze MAIN87 exactly; retain sealed non-serving dependencies, without live drift."""
import ast, hashlib, io, json, zipfile
from pathlib import Path

H=Path(__file__).resolve().parent
R=H.parents[3]
NAME='GENOS_MAIN87_PATCH_20261019_R1'
CONFIG='00_SYSTEM/GENOS_SERVING_PATHS.json'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def enc(value):return (json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode()
def pack(files):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for n,raw in sorted(files.items()):
            info=zipfile.ZipInfo(n,(2026,10,19,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16;z.writestr(info,raw)
    return buf.getvalue()

def main():
    if (H/'SEALED.json').exists():raise RuntimeError('Preserve sealed delivery; use a new revision')
    pointer_path=H/'SOURCE_POINTER.json'
    if not pointer_path.exists():pointer_path.write_bytes((R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_bytes())
    pointer=json.loads(pointer_path.read_bytes())
    assert pointer['generation']==87 and pointer['release_id']=='cm-read-continuity-20261019-r1'
    release_raw=(R/pointer['manifest_path']).read_bytes()
    assert sha(release_raw)==pointer['release_manifest_sha256']
    release=json.loads(release_raw);code=R/release['code_root']
    prior=H.parent/'main_full_20261016_r2'
    baseline_raw=(prior/'code.zip').read_bytes()
    baseline_sha='49ffde3c33d413d2875a4d7fde39abc281cd135ba8e1d63d863e548bd9a6f903'
    assert sha(baseline_raw)==baseline_sha
    with zipfile.ZipFile(io.BytesIO(baseline_raw)) as z:
        baseline=json.loads(z.read('CODE_MANIFEST.json'));payload={};sources={}
        for row in baseline['files']:
            n=row['path'];raw=z.read(n);assert sha(raw)==row['sha256']
            if n==CONFIG:continue
            payload[n]=raw;sources[n]='sealed:GENOS_MAIN_FULL_20261016_R2'
    dp=H.parent/'oracle_dp_20261016_r1';dp_spec=json.loads((dp/'PATCH_SPEC.json').read_bytes())
    # The serving Oracle modules are selected MAIN. Retain the two previously
    # delivered publishing helpers as well, without enabling DP or moving data.
    for n in ('02_BACKEND/lawrag/pipeline/oracle_migration.py','02_BACKEND/lawrag/pipeline/oracle_publish.py'):
        raw=(dp/'payload'/n).read_bytes();assert sha(raw)==dp_spec['after'][n]
        payload[n]=raw;sources[n]='sealed:GENOS_ORACLE_DP_20261016_R1'
    # MAIN87's qualified snapshot also freezes ingestion/migration helpers that
    # are deliberately outside the narrower service-release manifest. Include
    # those exact versions so basis updates and Oracle publishing stay connected.
    freeze_path=R/'04_EXPERIMENTS/ADR/ADR-0895-committed-answer-consistency/artifacts/design/freeze.json'
    frozen=json.loads(freeze_path.read_bytes());prefix=frozen['code_root']+'/'
    dependency_changes={}
    for path,pin in frozen['files'].items():
        if not path.startswith(prefix):continue
        n=path[len(prefix):];raw=(R/path).read_bytes();assert sha(raw)==pin,path
        if n not in release['files'] and payload.get(n)!=raw:
            dependency_changes[n]={'before_sha256':sha(payload[n]) if n in payload else None,'after_sha256':pin}
        payload[n]=raw;sources[n]='qualified:ADR-0895/consistent/rev-001'
    for n,pin in release['files'].items():
        raw=(code/n).read_bytes();assert sha(raw)==pin,n
        payload[n]=raw;sources[n]='selected:'+release['release_id']
    assert CONFIG not in payload
    assert all(sha(payload[n])==pin for n,pin in release['files'].items())
    for n,raw in payload.items():
        assert not n.startswith(('01_DATA/','90_RUNTIME/','.git/','.venv/'))
        assert Path(n).suffix.lower() not in {'.js','.jsx','.mjs','.cjs','.db','.sqlite','.key','.pem'}
        if n.endswith('.py'):ast.parse(raw,filename=n,feature_version=(3,11))
    pipeline=json.loads(payload['00_SYSTEM/PIPELINE.json'])
    for row in pipeline['engines'].values():
        assert sha(payload[row['manifest']])==row['sha256']
        for n,pin in json.loads(payload[row['manifest']])['files'].items():assert sha(payload[n])==pin,n
    workflows={}
    for row in pipeline['workflows']['registered']:
        assert sha(payload[row['manifest']])==row['sha256']
        manifest=json.loads(payload[row['manifest']]);workflows[row['id']]=manifest['version']
        for n,pin in manifest['files'].items():assert sha(payload['02_BACKEND/workflow/'+n])==pin,n
    assert workflows=={'risk_team_compare_workflow':'1.10.0','internal_basis_discovery_workflow':'1.0.0'}
    basis={'release_id':release['release_id'],'pointer_generation':pointer['generation'],
           'release_manifest_sha256':sha(release_raw),'pointer_sha256':sha(pointer_path.read_bytes()),
           'serving_files':release['files'],'deployment_serving_files':{n:sha(payload[n]) for n in release['files']},
           'genos_overlays':[],'repinned_files':[], 'workflow_versions':workflows,
           'qualification':pointer['qualification'],
           'qualified_dependencies':{'freeze_path':str(freeze_path.relative_to(R)),
               'freeze_sha256':sha(freeze_path.read_bytes()),'changes':dependency_changes},
           'genos_models':'existing internal GENOS settings',
           'data_policy':'preserve field generation, Oracle DP settings and existing selection; code-only install'}
    rows=[{'path':n,'sha256':sha(b),'bytes':len(b)} for n,b in sorted(payload.items())]
    required=[{'path':x['path'],'sha256':sha(payload[x['path']])} for x in baseline['required_files'] if x['path']!=CONFIG]
    manifest={'format':'8agent-code/1','id':NAME,'files':rows,'main_basis':basis,'required_files':required,
              'source_git_commit':None,'dependency_source_git_commit':baseline['source_git_commit'],'dependency_code_zip_sha256':baseline_sha,
              'field_deployment_status':'NOT_VERIFIED'}
    raw=pack({**payload,'CODE_MANIFEST.json':enc(manifest)})
    (H/'code.zip').write_bytes(raw);(H/'CODE_MANIFEST.json').write_bytes(enc(manifest))
    binding={'main_basis':basis,'sources':sources,'code_zip_sha256':sha(raw),'payload_files':len(rows),
             'selected_main_files_unchanged':len(release['files']),
             'working_differences_excluded':[n for n in release['files'] if (R/n).is_file() and sha((R/n).read_bytes())!=release['files'][n]]}
    (H/'SOURCE_BINDING.json').write_bytes(enc(binding))
    (H/'FILENAME_EXCEPTIONS.json').write_bytes(payload['00_SYSTEM/FILENAME_EXCEPTIONS.json'])
    (H/'replace.py').write_bytes(payload['06_TOOLS/OFFLINE/genos_code_replace.py'])
    (H/'GENOS_OVERLAYS.diff').write_text('# All 370 selected MAIN87 serving files are byte-identical. No GENOS overlay or repin.\n')
    print(json.dumps({'main':87,'files':len(rows),'selected_files_unchanged':len(release['files']),'bytes':len(raw),'sha256':sha(raw)}))

if __name__=='__main__':main()
