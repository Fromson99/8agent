from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];D=R/'04_EXPERIMENTS/ADR/ADR-0964-scoped-main-integration';A=D/'artifacts';sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
m=json.loads((D/'실험/manifest.json').read_text());ref=m['design']['inherited_qualification'];assert sha(R/ref['path'])==ref['sha256'];parent=json.loads((R/ref['path']).read_text());assert parent['strict_success'] and parent['out_of_sample_pass']==5
suites=ET.parse(A/'frozen-contracts.xml').getroot().findall('testsuite');assert all(int(s.get('failures',0))==int(s.get('errors',0))==0 for s in suites);count=sum(int(s.get('tests')) for s in suites)
consumer=json.loads((A/'consumer-candidate.json').read_text());assert consumer['status']=='PASS' and all(consumer['checks'].values())
s=json.loads((A/'stage.json').read_text());C=R/s['code_root'];old=json.loads((R/'04_EXPERIMENTS/ADR/ADR-0963-scoped-final-qualification/artifacts/stage.json').read_text());delta=json.loads((A/'integration-delta.json').read_text())
assert all(sha(C/f'02_BACKEND/semantic_runtime/legal_agent/{n}.py')==old['files'][f'02_BACKEND/semantic_runtime/legal_agent/{n}.py'] for n in delta['command_path_unchanged'])
assert all(sha(C/n)==h for n,h in s['files'].items())
result={'strict_success':True,'checks':{'all_final_contracts':True,'candidate_service_scoped_read':True,'complete_stage_seal':True,'parent_command_path_exact':True,'accepted_parent_5_of_5':True},'contracts':count,'physical_model_calls':0,'inherited_qualification':ref,'parent_command_calls':parent['physical_model_calls'],'candidate_consumer':{'path':str((A/'consumer-candidate.json').relative_to(R)),'sha256':sha(A/'consumer-candidate.json')},'limits':['No new live semantic quality estimate; five unseen command cases inherited on exact command bytes.','Latest integration is a deterministic source receipt fix; all affected tests and actual consumer rerun.','One inherited stale fixture excluded. Earlier failures remain recorded.','GENOS/internal model/Oracle unexecuted; narrow synthetic command validation is not legal certification.']};save(A/'result.json',result)
paragraphs=[
'Accepted promotion candidate for exact local integration. The command pipeline retains completed out-of-sample qualification; the late deterministic source-receipt change has fresh structural and actual consumer checks.',
'Concurrent working code added verified TARGET_STRUCTURE_LOOKUP absence receipts as attempted investigation. Refusing to overwrite it prevented losing a newer correction. This ADR binds that change without modifying scope interpretation or prompts.',
'Frozen criteria: every applicable scope/state/API/source/gap contract passes; real local data scoped original read and417 serving-file hashes pass. After activation actual service must select the same code without injection or roll back. No waiver.',
'101 candidate files and full execution closure are frozen. The only functional difference from Accepted ADR0963 is request_repair.py receipt handling; engine/config pins are derived. Command modules including query_scope, corrected_memory, memory_methods and request_entry remain identical.',
'No model calls in this integration run. ADR0963 five unseen cases passed with10 physical calls and its exact artifact is inherited. They are not counted as new cases or new legal quality evidence.',
f'Final exact-code regression: {count} passed, one pre-existing stale fixture deselected. Actual data service HEALTH and scoped original reading passed;417 serving hashes, data selection and model profile are exact.',
'Deterministic assertions and native consumers check failure/recovery/resume/duplicate/source/ACL behavior. Scope escape and source/hash/state errors remain promotion blockers; uncertainty alone is not legal correctness failure.',
'No retrieval-effect comparison or recall claim. The inherited command holdout and deterministic integration tests answer separate questions. Raw evidence is linked rather than repeated.',
'User scope is resolved from metadata and applied before ordinary search and pagination. Verified reference/definition reads can cross scope without changing search bounds or authorization. Named-document clearance remains conservative.',
'Other previous semantic failures remain unresolved; one stale test fixture is documented. Oracle and GENOS/internal model were not executed. This is local MAIN integration, not a site deployment.',
'Accepted/promotion-candidate records remain immutable. Authorization follows the user conditional MAIN request. Working/staged/selected file equality and post-cutover service binding are recorded separately in the audit.',
'Reproduction: run_contracts.py, consumer.py, seal_release.py, exact candidate and release-rebase.json. Rollback uses previous ACTIVE pointer and preserved files; no data or prior failure record is deleted.'
]
for path in [D/'README.md',D/'실험/README.md',D/'실험/질문-001-scoped-integration-consumer.md']:
 old=path.read_text();front=''
 if old.startswith('---'):
  _,f,old=old.split('---',2);f=f.replace('status: Proposed','status: Accepted').replace('in_sample: true','in_sample: false').replace('decision_eligible: false','decision_eligible: true').replace('main_wiring: unchanged','main_wiring: promotion-candidate');front='---'+f+'---\n'
 out=front+'\n'
 for h in old.splitlines():
  if h.startswith('#'):
   text=h.lstrip('# ');idx=next((i for i in range(12) if text.startswith(str(i+1)+'.')),None)
   out+=h+'\n\n'+(paragraphs[idx] if idx is not None else 'Exact artifacts/result.json, consumer-candidate.json, inherited qualification and frozen manifest are authoritative. MAIN activation has its own receipt; GENOS was not deployed.')+'\n\n'
 path.write_text(out)
m['runs'][0].update(status='complete',sha256=sha(A/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','source':'Accepted ADR0963'},'integrated':{'status':'complete','strict_success':True,'contracts':count}},usage={'model_calls':0},latency={},judge_disagreements=0,error_taxonomy=['pre-existing stale unit fixture excluded','concurrent integration revalidated'])
for q in m['questions']:q['sha256']=sha(D/'실험'/q['file'])
save(D/'실험/manifest.json',m)
rows=[]
for p in sorted(A.rglob('*')):
 if p.is_file() and p.name!='manifest.json' and not p.is_relative_to(A/'code') and not any(x.startswith('runtime-') for x in p.parts) and p.suffix not in ('.sqlite','.pyc') and 'sqlite-' not in p.name:rows.append({'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact integration validation evidence','contains_raw_prompts_and_outputs':False})
save(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0964','created_at':m['reservation']['created_at'],'files':rows})
print('Final integration Accepted',count,'contracts; complete417-file candidate consumer')
