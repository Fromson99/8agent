"""CAS integration and promotion preparation from a completed exact candidate."""
from pathlib import Path
import hashlib,json,re,subprocess,sys,tarfile
R=Path(__file__).resolve().parents[2];A=R/sys.argv[1];mode=sys.argv[2];D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
def sha(p):
 with Path(p).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def put(p,v):
 assert not p.exists(),p
 p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def bound(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
f=read(D/'freeze.json');C=R/f['code_root'];cm=read(R/f['candidate']['manifest_path']);baseline=read(D/'baseline.json')
m=read(A/'실험/manifest.json');result=read(A/'artifacts/run-001/result.json')
assert m['reservation']['status']=='completed' and m['decision_eligible'] and not m['in_sample']
assert result['strict_success'] and not result['failed']
assert (A/'artifacts/final-validation.txt').read_text().startswith('OK:')
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer_sha256']
if mode=='integrate':
 before=read(D/'working-before.json');expected={x['path']:x for x in read(D/'integration.json')['changes']};changes=[]
 for row in cm['files']:
  n=row['target_path'];after=sha(C/n);current=sha(R/n) if (R/n).exists() else None
  if current==after:continue
  assert current==before.get(n),('concurrent change',n)
  if n in expected:
   assert expected[n]['after']==after,('unreviewed serving delta',n)
  else:
   assert n.startswith('02_BACKEND/ENGINES/semantic_runtime/1.0.0/') and n.endswith('.json'),n
   old,new=read(R/n),read(C/n);assert {k:v for k,v in old.items() if k!='files'}=={k:v for k,v in new.items() if k!='files'}
   assert set(old['files'])==set(new['files'])
   changed=[k for k in old['files'] if old['files'][k]!=new['files'][k]]
   assert changed==['02_BACKEND/semantic_runtime/legal_agent/minimal_output.py'],changed
   assert new['files'][changed[0]]==sha(C/changed[0])
  changes.append({'path':n,'before':current,'after':after})
 assert len(changes)==40, len(changes)
 backup=A/'artifacts/working-before.tar.gz';assert not backup.exists()
 with tarfile.open(backup,'w:gz') as z:
  for row in changes:
   if row['before'] is not None:z.add(R/row['path'],arcname=row['path'],recursive=False)
 put(A/'artifacts/working-integration-plan.json',{'changes':changes,'backup':bound(backup)})
 for row in changes:
  p=R/row['path'];assert (sha(p) if p.exists() else None)==row['before']
  p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((C/row['path']).read_bytes())
 assert all(sha(R/x['target_path'])==sha(C/x['target_path']) for x in cm['files'])
 put(A/'artifacts/working-integration.json',{'status':'PASS','changes':changes,'candidate_files_match':len(cm['files']),'candidate':f['candidate'],'active_pointer_changed':False,'genos_deployed':False,'backup':bound(backup)})
 print('Integrated40 reviewed files (34 serving plus6 non-serving engine pins);711 candidate files match; MAIN pointer unchanged')
elif mode=='prepare':
 log=(A/'artifacts/working-api.log').read_text();assert re.search(r'\b\d+ passed',log) and not re.search(r'\b\d+ failed',log)
 w=read(A/'artifacts/working-consumer.json');assert w['status']=='PASS' and len(w['checks'])==10 and all(w['checks'].values())
 assert all(sha(R/x['target_path'])==sha(C/x['target_path']) for x in cm['files'])
 live=R/'04_EXPERIMENTS/ADR/ADR-0871-host-owned-fulltext-live';lv=read(live/'artifacts/summary.json')
 assert lv['answer_count']>=1 and lv['schema_error_count']==0 and all(x['fulltext_discovery_events'] and x['navigation_calls'] and not x['generation_rejections'] for x in lv['cases'])
 # Compare the actual model experiment code bytes with this qualified candidate.
 lf=read(live/'artifacts/design/frozen.json');LC=R/lf['release']['code_root']
 assert all(sha(LC/n)==sha(C/n) for n in read(D/'verification-binding.json')['serving_files'])
 auth={'authorized_by':'user','authorization_text':'그럼 시스템이 채울 값은 직접 조립하게 전체 스키마와 복원 계약 맞추고, fulltext 전체 흐름 다시 검증해줘. 최근 MAIN 변경은 유지하면서 수정 반영하고. GENOS ZIP과 실행 TXT도 요청됨.','quality_gate_override':False,'qualification':{'source':bound(A/'실험/manifest.json'),'readme':bound(A/'README.md'),'arm':'qualified','result':bound(A/'artifacts/run-001/result.json'),'rebase':bound(D/'release-rebase.json')}}
 validation={'structural_checks_passed':True,'integration':read(D/'integration.json'),'source_final_validation':bound(A/'artifacts/final-validation.txt'),'working_api':bound(A/'artifacts/working-api.log'),'working_consumer':bound(A/'artifacts/working-consumer.json'),'candidate_files_match':len(cm['files']),'real_fulltext':bound(live/'artifacts/summary.json'),'limitations':result['notes']['limitations']}
 put(A/'artifacts/main-authorization.json',auth);put(A/'artifacts/main-validation.json',validation)
 cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','rag_main_promotion.py','prepare','--code-root',str(C),'--generation',str(R/read(D/'data-binding.json')['path']),'--release-id','host-assembled-output-20261018-r1','--authorization',str(A/'artifacts/main-authorization.json'),'--validation',str(A/'artifacts/main-validation.json')]
 with (A/'artifacts/main-prepare.log').open('x') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
 print('Prepared host-assembled-output-20261018-r1')
else:raise ValueError(mode)
