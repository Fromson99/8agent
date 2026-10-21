from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];D=R/'04_EXPERIMENTS/ADR/ADR-0963-scoped-final-qualification';A=D/'artifacts';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
m=json.loads((D/'실험/manifest.json').read_text());live=json.loads((A/'command-results.json').read_text());assert len(live['results'])==5 and all(x['pass'] for x in live['results']);consumer=json.loads((A/'consumer-candidate.json').read_text());assert consumer['status']=='PASS' and all(consumer['checks'].values())
ref=m['design']['inherited_contract_result'];assert sha(R/ref['path'])==ref['sha256'];prior=json.loads((R/ref['path']).read_text());assert prior['strict_success'] and prior['contracts']==120
seal=json.loads((A/'stage.json').read_text());stage=R/seal['code_root'];assert all(sha(stage/n)==h for n,h in seal['files'].items())
result={'strict_success':True,'checks':{'five_withheld_commands':True,'inherited_120_contracts_exact':True,'real_data_service_scoped_read':True,'all_staged_files_exact':True,'document_inventory_not_in_command':True},'out_of_sample_cases':5,'out_of_sample_pass':5,'physical_model_calls':live['model_calls'],'contracts':120,'contract_evidence':ref,'candidate_consumer':{'path':str((A/'consumer-candidate.json').relative_to(R)),'sha256':sha(A/'consumer-candidate.json')},'limits':['Five synthetic command cases are narrow, not legal quality certification.','Exact known regression and tests inherited from completed probe, not counted as unseen cases.','One pre-existing stale fixture excluded; earlier provider and harness failures preserved.','GENOS/internal model and Oracle not executed.','Mixed named document/global-clear language is conservatively clarified.']};save(A/'result.json',result)
paragraphs=[
'Accepted for conditional local MAIN promotion: five withheld command cases all passed on unchanged candidate bytes;120 frozen contracts and repeated actual local data/service consumer passed.',
'User wants corrections to remain in the same question and explicit law/chapter/article scope to persist. The original AUTHORIZED command expanded161 document IDs into a maxItems160 schema and failed before retrieval.',
'Criteria were fixed before live calls:5/5 unseen synthetic commands, exact inherited contracts, scoped original read and complete release binding. Any critical source/ACL/state/scope escape rejects promotion. No quality waiver.',
'Candidate rev-001 has101 files, identical to the completed guarded probe. Evaluated release has417 serving files. Only derived upstream engine hashes were refreshed; concurrent runtime edits were already merged and tested in the parent.',
'Five cases were explicitly withheld before parent model calls and never executed until this qualification. Qwen3.8 Parasail FP8 reasoning none, no fallback. This is a narrow command interpretation holdout, not legal reasoning accuracy.',
f'5/5 passed with{live["model_calls"]} physical calls. Repeated real-data service HEALTH, exact file hashes and unique stored coordinate scoped original read passed with0 consumer model calls. Inherited120 contracts include API correction/duplicate, resume, witnessed links, source and permission checks.',
'Judging uses deterministic command fields and actual source/state consumers; no evaluator model or majority vote. Known failed q3 is separate parent regression and excluded from the five unseen cases.',
'No retrieval effectiveness score or golden recall estimate. Pre-pagination search bounds are structural contracts; actual data read verifies service connection. Data/model/profile/search-selection generation remains unchanged.',
'Implementation permits only verified acquired-original reference/definition endpoints to be read outside direct scope. Those grants never change direct search scope or ACL. State hashes and metadata version are checked again on resume.',
'Prior failed qualifications and harness fixes are preserved. Mixed named-document/global-clear requests ask for clarification. Existing semantic failures, Oracle/runtime data compliance and GENOS internal model remain unverified.',
'Accepted promotion-candidate source remains immutable. Release integration receipt binds every changed and preserved serving file. After activation actual service must select the release with no app injection; failure requires rollback.',
'Reproduce using the exact candidate manifest, stage.json, release-rebase.json, inherited contract result, probe.py and consumer.py. Authorization derives from the user instruction to test and reflect to MAIN if good; no separate GENOS deployment is authorized.'
]
for path in [D/'README.md',D/'실험/README.md',D/'실험/질문-001-scoped-final-heldout.md']:
 old=path.read_text();front=''
 if old.startswith('---'):
  _,f,old=old.split('---',2);f=f.replace('status: Proposed','status: Accepted').replace('decision_eligible: false','decision_eligible: true').replace('main_wiring: unchanged','main_wiring: promotion-candidate');front='---'+f+'---\n'
 out=front+'\n'
 for h in old.splitlines():
  if h.startswith('#'):
   s=h.lstrip('# ');idx=next((i for i in range(12) if s.startswith(str(i+1)+'.')),None)
   out+=h+'\n\n'+(paragraphs[idx] if idx is not None else 'Evidence: artifacts/result.json, artifacts/command-results.json, artifacts/consumer-candidate.json and frozen manifest. Local MAIN activation is recorded separately; GENOS is not deployed.')+'\n\n'
 path.write_text(out)
m['runs'][0].update(status='complete',sha256=sha(A/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','source':'ADR0962 exact probe'},'qualified':{'status':'complete','commands_pass':5,'commands_total':5,'contracts':120,'strict_success':True}},usage={'model_calls':live['model_calls']},latency={'seconds':live['elapsed_seconds']},judge_disagreements=0,error_taxonomy=[])
for q in m['questions']:q['sha256']=sha(D/'실험'/q['file'])
save(D/'실험/manifest.json',m)
rows=[]
for p in sorted(A.rglob('*')):
 if p.is_file() and p.name!='manifest.json' and not any(x.startswith('runtime-') for x in p.parts) and p.suffix not in ('.sqlite','.pyc') and 'sqlite-' not in p.name:rows.append({'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen qualification evidence','contains_raw_prompts_and_outputs':p.is_relative_to(A/'model')})
save(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0963','created_at':m['reservation']['created_at'],'files':rows})
print('Accepted unchanged-code qualification:5/5,120 contracts,417 serving files')
