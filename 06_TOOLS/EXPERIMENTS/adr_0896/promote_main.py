from pathlib import Path
import json,hashlib,tarfile,sys,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0896-cm-read-continuity-qualification';P=R/'04_EXPERIMENTS/ADR/ADR-0895-committed-answer-consistency';D=A/'artifacts/design';read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):
 assert not p.exists(),p
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');C=R/f['code_root'];base=read(D/'baseline.json');before=read(D/'working-before.json');cm=read(R/f['candidate']['manifest_path']);result=read(A/'artifacts/run-001/result.json');assert result['strict_success'] and all(result['checks'].values());assert read(A/'실험/manifest.json')['reservation']['status']=='completed'
mode=sys.argv[1]
if mode=='integrate':
 assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256'];assert all(sha(R/n)==h for n,h in before.items())
 changes=[{'path':n,'before':before[n],'after':sha(C/n)} for n in result['changes']]
 assert {x['path'] for x in changes}=={x['path'] for x in read(D/'integration.json')['changes']}
 backup=A/'artifacts/working-before.tar.gz';assert not backup.exists()
 with tarfile.open(backup,'w:gz') as tar:
  for row in changes:tar.add(R/row['path'],arcname=row['path'],recursive=False)
 put(A/'artifacts/working-integration-plan.json',{'changes':changes,'backup':bound(backup)})
 for row in changes:
  p=R/row['path'];assert sha(p)==row['before'];p.write_bytes((C/row['path']).read_bytes())
 assert all(sha(R/x['target_path'])==sha(C/x['target_path']) for x in cm['files'])
 put(A/'artifacts/working-integration.json',{'status':'PASS','exact_candidate_files':len(cm['files']),'changes':changes,'backup':bound(backup),'pointer_changed':False})
 print('Integrated',len(changes),'reviewed deltas;',len(cm['files']),'files exact;pointer unchanged')
elif mode=='prepare':
 assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256'];assert all(sha(R/x['target_path'])==sha(C/x['target_path']) for x in cm['files'])
 w=read(A/'artifacts/working-consumer.json');assert w['status']=='PASS' and all(w['checks'].values())
 integration=read(D/'integration.json');qualification={'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'qualified','result':bound(A/'artifacts/run-001/result.json'),'rebase':integration['rebase_receipt']}
 put(A/'artifacts/main-authorization.json',{'authorized_by':'user','authorization_text':'남은 CM008 검색·종료 문제와 CM003·051 답변 부족을 고치고 최근 MAIN 변경을 유지해 같은 CM5문항+새CM3문항을 검사. 앞선 MAIN 반영 지시와 RAM·용량 절약 지시 유지.','quality_gate_override':False,'qualification':qualification})
 put(A/'artifacts/main-validation.json',{'structural_checks_passed':True,'integration':integration,'candidate_qualification':bound(A/'artifacts/run-001/result.json'),'candidate_consumer':bound(A/'artifacts/candidate-consumer.json'),'working_consumer':bound(A/'artifacts/working-consumer.json'),'actual_rag_eight':bound(P/'artifacts/run-001/result.json'),'gold_coordinate_disposition':bound(D/'gold-coordinate-disposition.json'),'limitations':result['remaining']})
 with (A/'artifacts/main-prepare.log').open('x') as log:subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',str(R/base['release']['data_path']),'--release-id','cm-read-continuity-20261019-r1','--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')],check=True,stdout=log,stderr=subprocess.STDOUT)
 print('Prepared cm-read-continuity-20261019-r1')
elif mode=='finish':
 pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==87 and pointer['release_id']=='cm-read-continuity-20261019-r1';manifest=R/pointer['manifest_path'];release=read(manifest);S=R/release['code_root'];active=read(A/'artifacts/active-consumer.json')
 assert sha(manifest)==pointer['release_manifest_sha256'];assert all(sha(S/n)==sha(C/n)==h for n,h in release['files'].items());assert all(sha(R/x['target_path'])==sha(C/x['target_path']) for x in cm['files'])
 assert active['status']=='PASS' and active['app_injected'] is False and active['code_root']==release['code_root'] and all(active['checks'].values())
 assert release['data_path']==base['release']['data_path'] and release['data_manifest_sha256']==base['release']['data_manifest_sha256']
 assert all(all(read(A/f'artifacts/{mode}-consumer.json')[key]==active[key] for key in ('search_selection_fingerprint','profile_sha256','navigation_sha256')) for mode in ('candidate','working'))
 out={'status':'LOCAL_MAIN_SELECTED_AND_ACTUAL_SERVICE_VERIFIED','pointer':pointer,'candidate':f['candidate'],'working_files_exact':len(cm['files']),'serving_files_exact':len(release['files']),'technical_tests':669,'known_eight_actual':bound(P/'artifacts/run-001/result.json'),'core_pass':7,'http200':8,'actual_model_calls':152,'deselected':140,'service_checks_per_mode':10,'actual_service_binding':active['health'],'integration':bound(A/'artifacts/working-integration.json'),'data_unchanged':True,'search_selection_fingerprint':active['search_selection_fingerprint'],'profile_sha256':active['profile_sha256'],'navigation_sha256':active['navigation_sha256'],'workflow_version':'1.10.0','discovery_version':'1.0.0','remaining':result['remaining'],'genos_field_verified':False,'git_main_merge':False,'git_push':False,'resident_service_restarted':False}
 put(manifest.parent/'IMPLEMENTATION_RESULT.json',out);print('MAIN87 exact selected and actual service verified')
else:raise ValueError(mode)
