"""Freeze all 111 cells, including the mandatory first-nine gate, before calls."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
from common import ROOT,ADR,ART,read,save,sha,exact_write
CAND=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1063/catalogue-projection-r1'
PRIOR=ROOT/'04_EXPERIMENTS/ADR/ADR-1062-ontology-mvp-runner-binding/artifacts/design-freeze.json'
def rel(p):return str(p.relative_to(ROOT))
def main():
 assert not (ART/'design-freeze.json').exists() and not (ART/'matrix').exists()
 old=read(PRIOR);f=deepcopy(old)
 CODE=CAND/'revisions'/read(CAND/'candidate.json')['revisions'][-1]['revision_id']/'snapshot'
 files={str(p.relative_to(CODE)):sha(p) for p in CODE.rglob('*') if p.is_file()}
 for name in ('release-check','frozen-api'):
  t=read(ART/(name+'-summary.json'))
  assert t['validation_status']==0 and not t['new_failures'] and t['files']==files and not t['production_import_leaks'] and not t['candidate_changed_during_tests'],name
 replay_path=ART/'catalogue-preview-frozen.json';replay=read(replay_path)
 assert replay['all_within_24000'] and replay['candidate_files_unchanged_during_replay']
 assert replay['physical_calls']==0 and not replay['original_request_reconstruction_claimed']
 replay_files={p:h for p,h in files.items() if p.startswith(('02_BACKEND/','00_SYSTEM/')) and p.endswith(('.py','.json')) and '__pycache__' not in p}
 assert replay['candidate_files_sha256']==replay_files,'catalogue preview used different code/config bytes'
 assert len(replay['cells'])==9 and all(c['preserved']['exact_restore_verified'] and c['candidate_prepared']['measured_chars']<=24000 for c in replay['cells'])
 expected_replay=[f"{r['ordinal']:03d}-{r['case_id']}-{r['arm']}" for r in old['execution_order'][:9]]
 assert [row['cell'] for row in replay['cells']]==expected_replay,'replay does not cover the exact first nine cells'
 assert set(replay['replay_tool_hashes'])=={rel(Path(__file__).with_name(n)) for n in ('replay_catalogue.py','common.py')}
 assert all(sha(ROOT/p)==h for p,h in replay['replay_tool_hashes'].items()),'replay tools changed since proof'
 prior_matrix=PRIOR.parent/'matrix'
 for row in replay['cells']:
  journal=ROOT/row['source_journal']
  assert journal.is_relative_to(prior_matrix/row['cell']/'runtime')
  assert sha(journal)==row['source_journal_sha256'],'source replay journal changed'
 source=ROOT/old['data_path']/'store.sqlite';before=source.stat();assert sha(source)==old['store_sha256'];after=source.stat()
 fields=lambda s:(s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 assert fields(before)==fields(after)
 receipt=read(ROOT/old['source_integrity_path']);assert (receipt['size'],receipt['mtime_ns'],receipt['ctime_ns'])==fields(after)
 for path,h in read(ART/'preservation.json')['files'].items():assert sha(ROOT/path)==h
 for key in ('product_cases','evaluator_cases','corpus','authorization','evaluation_contract'):
  assert sha(ROOT/old[key+'_path'])==old[key+'_sha256']
 product=read(ROOT/old['product_cases_path'])['cases'];first=['fsc-hard-005','cm-023','fsc-hard-008']
 ids=first+[c['case_id'] for c in product if c['case_id'] not in first]
 assert len(ids)==len(set(ids))==37
 order=[]
 for i,cid in enumerate(ids):
  for arm in [('A0','A1','A2'),('A1','A2','A0'),('A2','A0','A1')][i%3]:order.append({'ordinal':len(order)+1,'case_id':cid,'arm':arm})
 m=read(ADR/'실험/manifest.json')
 for binding in m['design']['code_isolation']['candidates']:
  binding['runner_sha256']=sha(ROOT/binding['runner_path'])
 save(ADR/'실험/manifest.json',m)
 f.update(frozen_at=datetime.now(timezone.utc).isoformat().replace('+00:00','Z'),experiment_id=m['experiment_id'],design=m['design'],manifest_sha256_at_freeze=sha(ADR/'실험/manifest.json'),code_root=rel(CODE),files=files,policy_sha256=sha(CODE/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json'),validation_inheritance=False,validation_note='Execution repair contracts and exact frozen API checked; prior failures retained. 111 frozen cells, first9 mandatory gate, in-sample only.',execution_order=order)
 for key in ('client','judge_client'):
  f[key+'_path']=rel(CODE/'02_BACKEND/lawrag/research/experiment_client.py');f[key+'_sha256']=sha(ROOT/f[key+'_path'])
 for key,name in [('optimization_authorization','implementation-plan.json'),('validation','release-check-summary.json'),('validation_receipt','tested-freeze.json')]:
  f[key+'_path']=rel(ART/name);f[key+'_sha256']=sha(ART/name)
 f['semantic_contract_files']={p:files[p] for p in old['semantic_contract_files']}
 f['provider_failover']=read(CODE/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json')['provider_failover']
 f['input_output_representation'].update(query_language='grouped-fulltext-v1',law_choices='presentation-local-law-number-v1',navigation_values='navigation-values-v1',bound_research_scope='server-retained-exact-ACL-list',large_read_threshold_chars=24000,final_request_limit_chars=100000,execution_review=True,maximum_current_sources=3,pending_global=True,required_output_schema='shared-exact-subtrees; independent valid row commit; one targeted row patch')
 f['equal_operational_overrides'].update(minimum_available_memory_bytes=3*1024**3,memory_limit_bytes=5*1024**3,memory_limit_kind='worker_RSS',address_space_limit_bytes=6*1024**3,minimum_disk_free_bytes=20*1024**3,maximum_swap_increase_bytes=512*1024**2)
 f['mode_limits']=read(ART/'implementation-plan.json')['input_limits']
 f['first_nine_gate']={'implementation':rel(Path(__file__).with_name('gate.py')),'sha256':sha(Path(__file__).with_name('gate.py')),'first9':order[:9],'remaining':102,'failure_stops_new_cells':True,'unknown_is_failure':True,'semantic_wrong_answer_alone_stops':False}
 f['offline_evaluation_scope']='All completed integrity-valid triples from this freeze, including first9 if gate stops. No incomplete triple or provider failure replay. Partial matrix has no full37 effect claim.'
 f['arm_code_bindings']=m['design']['code_isolation']['candidates'];f['shared_execution_code']='All three candidate file maps identical; run_case uses A2 shared code with exact A0/A1/A2 ontology configuration recorded per cell.'
 f['prior_design_freeze_path']=rel(PRIOR);f['prior_design_freeze_sha256']=sha(PRIOR)
 for key in ('saved_input_replay_path','saved_input_replay_sha256'):f.pop(key,None)
 f['saved_input_replay_path']=rel(replay_path);f['saved_input_replay_sha256']=sha(replay_path)
 f['runner_hashes']={rel(p):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))}
 for name in ('known-existing-failures.json','validation-coverage-plan.json','candidate-code-diff.json','implementation-amendment-01.json'):
  f['runner_hashes'][rel(ART/name)]=sha(ART/name)
 f['runner_hashes'][rel(ROOT/'06_TOOLS/EXPERIMENTS/adr_1037/trace.py')]=sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1037/trace.py')
 for key in ('provider_authorization','optimization_authorization'):f['runner_hashes'][f[key+'_path']]=f[key+'_sha256']
 f['evaluation_scripts']={rel(Path(__file__).parent/n):sha(Path(__file__).parent/n) for n in ('collect_metrics.py','common.py','wire_audit.py','gate.py','judge.py','evaluate_matrix.py','report_results.py')}
 p=ROOT/'02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py';f['evaluation_scripts'][rel(p)]=sha(p)
 exact_write(ART/'design-freeze.json',f)
 print('FROZEN37x3=111; first9gate; exact tested code; no live calls yet')
if __name__=='__main__':main()
