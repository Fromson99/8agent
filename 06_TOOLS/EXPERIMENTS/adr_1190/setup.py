from common import *
import shutil

active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
base=read(ROOT/active['manifest_path'])
assert active['generation']==114
criteria={
 'scope':'User requested Parasail as primary for local serving and new experiments; no latency or model-quality comparison',
 'success':['Only provider configuration and dependent pins change from MAIN114',
 'Parasail FP8 first; known429 alone switches once to NearAI; each physical request charged',
 'Unknown/non429/schema/model/provider violations never trigger switch or same-provider retry',
 'Same model, source contracts, requirement review, data, budgets, reasoning none and unlimited output',
 'Prospective existing routing contracts pass; exact selected service binding and mocked outbound routing verified',
 'Preserve unrelated working changes and completed releases'],
 'failure':'Any routing, budget, state, inventory or source-code drift blocks activation',
 'external_model_calls':0,'quality_certified':False,
 'resources':{'max_parallel_heavy_processes':1,'min_available_GiB':5,'address_space_GiB':6},
}
put(DES/'criteria.json',criteria)
put(DES/'baseline.json',{'active':active,'manifest':base,
 'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'working_files':{n:sha(ROOT/n) if (ROOT/n).is_file() else None for n in base['files']},
 'research_client':bind(ROOT/'02_BACKEND/lawrag/research/experiment_client.py')})
m=read(ADR/'실험/manifest.json')
h='A primary-provider configuration change reaches actual serving while preserving single known429 failover, budgets and all existing source behavior.'
m['lineage']['hypothesis_delta']=h
m['design'].update(hypothesis=h,primary_metric='Routing and release integrity contract pass rate; no performance claim',
 success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,
 criteria_freeze_evidence=bind(DES/'criteria.json'),execution=criteria,
 arms=[{'id':'switched','role':'candidate','derived_from':['ADR-1188-experiment-v1/reviewed'],
 'changes':'Primary provider Chutes to Parasail; retained NearAI on known429 only',
 'controls':'All MAIN114 application code, data, model and source/response/deadline contracts unchanged'}])
m['dataset'].update(name='Prospective synthetic serving/research provider contract suite',version='v1',
 frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['llm_policy']['llm_calls']=[]
m['runs'][0].update(arm_ids=['switched'],selection_rule='Existing routing fixtures adapted to requested primary; no live model call',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Provider routing contracts only; no real retrieval',stage_ledger={
 'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1',
 'accounting_unit':'case_id + canonical article-root coordinate','artifact_path':None,'sha256':None,
 'not_applicable_reason':'No retrieval or legal answer benchmark'})
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
C=ac.snapshot(ADR,'switched',list(base['files']),experiment_id=m['experiment_id'],arm_id='switched',run_ids=['run-001'])
S=C/'snapshot'
for n,h in base['files'].items():
 assert sha(ROOT/base['code_root']/n)==h,n
 shutil.copyfile(ROOT/base['code_root']/n,S/n)
p=S/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'
cfg=read(p)
cfg['providers'][0]={'tag':'parasail/fp8','name':'Parasail'}
cfg['authorization']={'source':'user_message','text':'parasail로 바꿔봐봐',
 'session_id':'01a18102-29c3-78b3-9b53-cc33aaca63e7','date':'2026-10-29',
 'retained_rule':'Previously authorized known HTTP429 only, one switch to Near AI'}
cfg['reason']='User requested Parasail primary after Chutes noncompletion diagnosis; speed/reliability improvement unverified.'
cfg['previous_policy']={'path':str((ROOT/base['code_root']/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json').relative_to(ROOT)),
 'sha256':base['files']['00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json']}
p.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+'\n')
put(DES/'candidate.json',{'root':str(C.relative_to(ROOT)),'snapshot':str(S.relative_to(ROOT))})
put(DES/'verification-fixtures.json',{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('test_*.py')})
print(S)
