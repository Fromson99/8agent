from common import *
from datetime import datetime,timezone
import ast,gzip
assert not (DES/'freeze.json').exists()
for p in Path(__file__).parent.glob('*.py'):compile(p.read_text(),str(p),'exec')
f=read(SOURCE/'design/freeze.json');code=ROOT/f['code_root'];binding=read(SOURCE/'run-002/binding.json');result=read(CASE/'result.json')
assert result['model_calls']==9 and result['http_status']==200
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==106 and all(sha(code/n)==h for n,h in release['files'].items())
calls=[]
for i in range(1,10):
 paths=list((CASE/'raw').glob(f'call-{i:03d}-*/response.json'));assert len(paths)==1
 with gzip.open(CASE/'wire'/f'{i:03d}.json.gz','rt') as stream:wire=json.load(stream)
 response=read(paths[0]);assert response['choices'][0]['finish_reason']=='stop'
 calls.append({'number':i,'wire':bound(CASE/'wire'/f'{i:03d}.json.gz'),'response':bound(paths[0])})
criteria={'frozen_at':datetime.now(timezone.utc).isoformat(),'purpose':'Diagnose known22.930s residual and original prompt/repair usability; no product or semantic behavior change',
 'runs':1,'recorded_responses':9,'expected_views':4,'new_model_calls':0,'network_allowed':False,
 'measurement':'perf_counter named nested spans plus10ms thread-stack samples and SQL trace counts; inclusive times not added; original historical22.930s remains distinct from replay measured totals',
 'success':['All9protected transmitted requests equal original, except generated V32view_id in comparison copies only','Return literal recorded responses without output rewriting; same final answer contents apart from verified native run/query IDs','All four view calls and retained source/permission/state validators execute; categorize the residual without treating sampling estimates as exact SQL latency','MAIN106/code/data/prompt/schema unchanged; retain failure if replay diverges; no adaptive model response'],
 'failure':'Stop on protected input mismatch, extra model call, integrity or resource failure; do not rewrite recorded choices to force completion',
 'limits':{'rss_gib':4,'available_gib':3,'disk_gib':20,'swap_gib':0.5,'address_space_gib':6,'heavy_workers':1},
 'one_second_target':'Entire request non-model overhead excluding glossary initialization; also report broader all-resource-init exclusion. Target, not achieved or certified.',
 'prompt_analysis':'Read-only actual call2-5 user/system/schema/response and repair; distinguish demonstrated field defects from causal model-performance hypotheses.'}
put(DES/'criteria.json',criteria)
put(DES/'freeze.json',{'code_root':f['code_root'],'code_files':f['files'],'source_binding':bound(SOURCE/'run-002/binding.json'),'source_result':bound(CASE/'result.json'),'request':bound(CASE/'request.json'),'response':bound(CASE/'response.json'),'source_journal':bound(ROOT/result['journal_paths'][0]),'calls':calls,'active_pointer':bound(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'active_release':bound(ROOT/active['manifest_path']),'scripts':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')}})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['purpose'];m['design'].update(hypothesis=criteria['purpose'],primary_metric='Protected replay equivalence and named/sampled nonmodel attribution',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='not_applicable',reason='Read-only measurement of unchanged immutable1086revision, now same429serving bytes as MAIN106; no new product candidate. Profiling/recorded transport only lives in research runner.')
for arm in m['design']['arms']:arm.update(changes='Historical1086recorded outputs and log intervals' if arm['id']=='baseline' else 'Same product bytes and literal9responses; add measurement only',controls='No product/data/profile/prompt/schema/model decision modifications; no new LLM call or MAIN activation')
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['observed'],'selection_rule':'One full known9response native request, no new model, stop at first divergence','status':'planned','artifact_path':str((ART/'run-001/result.json').relative_to(ROOT)),'sha256':'PENDING'}]
m['dataset'].update(name='Known1086fsc-hard-005 recorded trace',version='exact9-v1',frozen_source=str((DES/'freeze.json').relative_to(ROOT)),sha256=sha(DES/'freeze.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[]
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1086-compact-wire-binding/실험/manifest.json')
m['retrieval_accounting']=parent['retrieval_accounting'];m['retrieval_accounting']['changed']=False;m['retrieval_accounting']['stage_ledger']['mode']='inherited'
put(ADR/'실험/manifest.json',m)
print('Frozen9literalresponses; single sequential profile; MAIN106 preserved')
