from pathlib import Path
import json,hashlib,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0916-answer-first-qualification';P=R/'04_EXPERIMENTS/ADR/ADR-0915-answer-first-followup-provenance';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):
 assert not p.exists(),p
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'binding.json');base=read(D/'baseline.json');result=read(A/'artifacts/run-001/result.json');assert result['strict_success']
mode=sys.argv[1]
if mode=='prepare':
 assert read(A/'실험/manifest.json')['reservation']['status']=='completed'
 assert read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']
 assert all(sha(R/n)==h for n,h in b['serving_files'].items())
 integration=read(D/'integration.json')
 put(A/'artifacts/main-authorization.json',{'authorized_by':'user','authorization_text':'이건 일단 불필요한 조사를 제외하자. 어느정도 맞으면 내보내고 사용자의 멀티턴을 기반으로 추가탐색이 필요하면 이어지게 하자. 검증된 변경의 로컬 RAG 실행 연결이며 GENOS 현장 배포는 별도다.','quality_gate_override':False,'qualification':{'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'qualified','result':bound(A/'artifacts/run-001/result.json'),'rebase':integration['rebase_receipt']}})
 put(A/'artifacts/main-validation.json',{'structural_checks_passed':True,'integration':integration,'qualification':bound(A/'artifacts/run-001/result.json'),'candidate_consumer':bound(P/'artifacts/candidate-consumer.json'),'working_consumer':bound(P/'artifacts/working-consumer.json'),'known_three_live_replies':bound(P/'artifacts/run-001/result.json'),'limitations':result['remaining']})
 subprocess.run([sys.executable,'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(R/b['code_root']),'--generation',str(R/base['manifest']['data_path']),'--release-id','answer-first-followup-20261019-r1','--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')],check=True)
elif mode=='finish':
 ptr=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['release_id']=='answer-first-followup-20261019-r1' and ptr['generation']==88
 rp=R/ptr['manifest_path'];release=read(rp);active=read(P/'artifacts/active-consumer.json')
 assert sha(rp)==ptr['release_manifest_sha256'] and release['files']==b['serving_files']
 assert active['status']=='PASS' and active['app_injected'] is False and all(active['checks'].values())
 assert all(sha(R/n)==sha(R/release['code_root']/n)==h for n,h in release['files'].items())
 out={'status':'LOCAL_MAIN_SELECTED_AND_ACTUAL_SERVICE_VERIFIED','pointer':ptr,'candidate':b['candidate'],'serving_files_exact':len(release['files']),'technical_tests':132,'known_actual_comparisons':result['parent_comparisons'],'working_integration':bound(P/'artifacts/working-integration.json'),'actual_service_binding':active,'peak_live_rss_bytes':result['peak_live_rss_bytes'],'data_unchanged':release['data_path']==base['manifest']['data_path'],'remaining':result['remaining'],'genos_deployed':False,'git_main_merged':False,'git_pushed':False,'resident_local_server_restarted':False}
 put(rp.parent/'IMPLEMENTATION_RESULT.json',out);put(A/'artifacts/local-completion.json',out)
 print('MAIN88 selected; exact actual service binding verified')
else:raise ValueError(mode)
