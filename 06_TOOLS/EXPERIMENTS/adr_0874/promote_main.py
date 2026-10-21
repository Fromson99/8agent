from pathlib import Path
import hashlib,json,sys,subprocess,tarfile
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0874-bounded-followup-continuation';L=R/'04_EXPERIMENTS/ADR/ADR-0875-bounded-followup-live';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
def put(p,v):
 assert not p.exists(),p
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');C=R/f['code_root'];cm=read(R/f['candidate']['manifest_path']);base=read(D/'baseline.json');mode=sys.argv[1]
assert read(A/'실험/manifest.json')['reservation']['status']=='completed'
assert read(L/'실험/manifest.json')['reservation']['status']=='completed'
live=read(L/'artifacts/run-001/result.json');audit=read(L/'artifacts/run-001/committee-comparison/audit.json');checks=read(L/'artifacts/live-contract-checks.json')
assert live['status']=='complete' and audit['rows']>=1 and all(checks['checks'].values())
assert not any(not x['exact_original_match'] for x in audit['evidence_span_checks'])
assert read(L/'artifacts/design/freeze.json')['code_root']==f['code_root']
if mode=='integrate':
 assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
 before=read(D/'working-before.json');delta=read(A/'artifacts/run-001/result.json')['changes'];expected={row['path']:row for row in read(D/'integration.json')['changes']}
 changes=[]
 for n in before:
  after=sha(C/n);current=sha(R/n);assert current==before[n],('concurrent working change',n)
  if current==after:continue
  assert n in delta,n
  if n in expected:assert expected[n]['after']==after
  else:assert n.startswith('02_BACKEND/ENGINES/semantic_runtime/1.0.0/') and n.endswith('.json'),n
  changes.append({'path':n,'before':current,'after':after})
 assert len(changes)==42
 test=R/'05_TESTS/CONTRACTS/test_public_failure_guidance.py';updated=A.parent.parent.parent/'unused'
 test_bytes=(R/'06_TOOLS/EXPERIMENTS/adr_0874/test_public_failure.py').read_bytes()
 test_change={'path':str(test.relative_to(R)),'before':sha(test),'after':hashlib.sha256(test_bytes).hexdigest()}
 backup=A/'artifacts/working-before.tar.gz';assert not backup.exists()
 with tarfile.open(backup,'w:gz') as out:
  for row in [*changes,test_change]:out.add(R/row['path'],arcname=row['path'],recursive=False)
 put(A/'artifacts/working-integration-plan.json',{'changes':changes,'current_test_update':test_change,'backup':bound(backup)})
 for row in changes:
  p=R/row['path'];assert sha(p)==row['before'];p.write_bytes((C/row['path']).read_bytes())
 assert sha(test)==test_change['before'];test.write_bytes(test_bytes)
 assert all(sha(R/x['target_path'])==sha(C/x['target_path']) for x in cm['files'])
 put(A/'artifacts/working-integration.json',{'status':'PASS','candidate_files_match':711,'changes':changes,'current_test_update':test_change,'backup':bound(backup),'pointer_changed':False})
 print('Integrated42 reviewed code/pin files and current failure-guidance test;711candidate files exact;pointer unchanged')
elif mode=='prepare':
 assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
 assert all(sha(R/x['target_path'])==sha(C/x['target_path']) for x in cm['files'])
 working=read(A/'artifacts/working-consumer.json');assert working['status']=='PASS' and all(working['checks'].values())
 authorization={'authorized_by':'user','authorization_text':'MAIN83으로 실제 모델 써서 대사 워크플로우 처음부터 끝까지 검증. 미완료 질의 원인 확인, 문제 있으면 최근 변경 유지하면서 고쳐 MAIN반영. RAM/용량절약 순차실행.','quality_gate_override':False,
  'qualification':{'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'qualified','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}}
 validation={'structural_checks_passed':True,'integration':read(D/'integration.json'),'candidate_tests':bound(A/'artifacts/candidate-api.log'),'candidate_consumer':bound(A/'artifacts/candidate-consumer.json'),'working_consumer':bound(A/'artifacts/working-consumer.json'),'live_workflow':bound(L/'artifacts/run-001/result.json'),'live_contracts':bound(L/'artifacts/live-contract-checks.json'),'limitations':['No legal-quality certification or GENOS deployment claim; exact original data and model policy retained.']}
 put(A/'artifacts/main-authorization.json',authorization);put(A/'artifacts/main-validation.json',validation)
 with (A/'artifacts/main-prepare.log').open('x') as out:
  subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',str(R/base['release']['data_path']),'--release-id','bounded-followup-20261018-r1','--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')],check=True,stdout=out,stderr=subprocess.STDOUT)
 print('Prepared bounded-followup-20261018-r1')
elif mode=='finish':
 pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==84 and pointer['release_id']=='bounded-followup-20261018-r1'
 manifest=R/pointer['manifest_path'];rel=read(manifest);selected=R/rel['code_root'];active=read(A/'artifacts/active-consumer.json')
 assert sha(manifest)==pointer['release_manifest_sha256'] and all(sha(selected/n)==sha(C/n)==h for n,h in rel['files'].items())
 assert all(sha(R/x['target_path'])==sha(C/x['target_path']) for x in cm['files'])
 assert active['status']=='PASS' and active['app_injected'] is False and active['code_root']==rel['code_root'] and all(active['checks'].values())
 assert all(read(A/f'artifacts/{mode}-consumer.json')['search_selection_fingerprint']==active['search_selection_fingerprint'] for mode in ('candidate','working'))
 assert rel['data_path']==base['release']['data_path'] and rel['data_manifest_sha256']==base['release']['data_manifest_sha256']
 result={'status':'LOCAL_MAIN_SELECTED_AND_ACTUAL_SERVICE_VERIFIED','pointer':pointer,'release':bound(manifest),'candidate':f['candidate'],'working_files_exact':711,'serving_files_exact':len(rel['files']),'contracts_passed':311,'service_consumer_checks_per_mode':10,'actual_service_binding':active['health'],'live_model':bound(L/'artifacts/run-001/result.json'),'live_checks':bound(L/'artifacts/live-contract-checks.json'),'baseline_live':bound(R/'04_EXPERIMENTS/ADR/ADR-0873-main83-workflow-live-diagnosis/artifacts/run-001/result.json'),'integration':bound(A/'artifacts/working-integration.json'),'data_unchanged':True,'search_selection_fingerprint':active['search_selection_fingerprint'],'workflow_version':'1.9.1','discovery_version':'1.0.0','genos_field_verified':False,'git_main_merge':False,'git_push':False,'resident_service_restarted':False}
 put(manifest.parent/'IMPLEMENTATION_RESULT.json',result)
 (manifest.parent/'IMPLEMENTATION.txt').write_text('MAIN84 대사 후속 조사 수정 (2026-10-18)\n\n최근 MAIN83 출력압축·시스템조립·근거원장·Oracle 배선을 유지했다. 데이터/검색/모델/40회1800초 예산 불변.\n첫 과제가 원문을 못 찾았어도 기존2회 한도 안에서 다른 독립 과제를 진행한다. 동일 자료 조사는 항목간 공유한다. 실제 과제의 원문 확보 영수증으로 완료/부분/실패를 구분한다. 재개 시 최초 조사 전 근거 목록과 과제 ID를 보존하여 중복 호출과 새 근거 누락을 방지한다.\n조사 미완료 안내는 근거 없이 질문을 구체화하라고 요구하지 않는다. 실제 사용자 사실 질문/권한·시간초과·오류 표시는 유지한다.\n311계약 검사, 후보·작업·실제 활성 서비스 각10검사, 고정후보의 실제모델 대사 결과는 IMPLEMENTATION_RESULT.json에 연결했다. 원문 부족·판단 불확실성은 부분 결과에 남기며 법률 정답으로 인증하지 않는다.\n로컬 활성화 완료. GENOS 내부 모델·현장 Git push·서빙배포·워크플로우편집기 검증은 별도다. 이전 MAIN83 코드와 실패·부분 결과는 보존했다. 롤백은 현재 generation84/이release인지 확인 후 stable rag_main_promotion.py rollback --confirm-main을 사용한다.\n')
 print('MAIN84 actual service and selected370files verified;711workingcandidate files equal')
else:raise ValueError(mode)
