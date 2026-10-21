from pathlib import Path
import hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0926-connected-source-release-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):
    assert not p.exists(),p
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'binding.json');base=read(D/'baseline.json');result=read(A/'artifacts/run-001/result.json');assert result['strict_success']
mode=sys.argv[1];release_id='connected-source-selection-20261019-r1'
if mode=='prepare':
    assert read(A/'실험/manifest.json')['reservation']['status']=='completed'
    assert read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']
    assert all(sha(R/b['code_root']/n)==h for n,h in b['serving_files'].items())
    assert read(A/'artifacts/graph-disposition.json')['new_errors']==[]
    integration=read(D/'integration.json')
    put(A/'artifacts/main-authorization.json',{'authorized_by':'user','authorization_text':'연결된 원문을 함께 선택하고 추가 용어 탐색을 구현하여 진행하라는 요청 및 제시한 MAIN 연결 설계에 대한 진행 지시. 검증한 동일 코드의 로컬 MAIN 연결이며 GENOS 현장 배포는 별도다.','quality_gate_override':False,'qualification':{'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'qualified','result':bound(A/'artifacts/run-001/result.json'),'rebase':integration['rebase_receipt']}})
    put(A/'artifacts/main-validation.json',{'structural_checks_passed':True,'integration':integration,'qualification':bound(A/'artifacts/run-001/result.json'),'candidate_consumer':bound(A/'artifacts/candidate-consumer.json'),'working_consumer':bound(A/'artifacts/working-consumer.json'),'working_integration':bound(A/'artifacts/working-integration.json'),'known_observation':result['known_live_observation'],'limitations':result['remaining']})
    subprocess.run([sys.executable,'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(R/b['code_root']),'--generation',str(R/base['manifest']['data_path']),'--release-id',release_id,'--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')],check=True)
elif mode=='finish':
    pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['release_id']==release_id and pointer['generation']==base['pointer']['generation']+1
    rp=R/pointer['manifest_path'];release=read(rp);active=read(A/'artifacts/active-consumer.json')
    assert sha(rp)==pointer['release_manifest_sha256'] and release['files']==b['serving_files']
    assert active['status']=='PASS' and active['app_injected'] is False and all(active['checks'].values())
    drift=read(D/'concurrent-working-only.json')['preserved']
    assert all(sha(R/release['code_root']/n)==h and sha(R/n)==(drift[n]['current'] if n in drift else h) for n,h in release['files'].items())
    out={'status':'LOCAL_MAIN_SELECTED_AND_ACTUAL_SERVICE_VERIFIED','pointer':pointer,'candidate':b['candidate'],'serving_files_exact':len(release['files']),'technical_tests':162,'working_integration':bound(A/'artifacts/working-integration.json'),'working_only_concurrent_files':drift,'actual_service_binding':active,'known_observation':result['known_live_observation'],'data_unchanged':release['data_path']==base['manifest']['data_path'],'remaining':result['remaining'],'genos_deployed':False,'git_main_merged':False,'git_pushed':False,'resident_local_server_restarted':False}
    put(rp.parent/'IMPLEMENTATION_RESULT.json',out);put(A/'artifacts/local-completion.json',out)
    print('Local MAIN selected and exact actual service binding verified:',pointer['generation'])
else:raise ValueError(mode)
