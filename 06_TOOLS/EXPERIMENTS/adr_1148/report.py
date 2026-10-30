"""Read-only model-output evaluation; expected route IDs are never product input."""
from common import *
import gzip,sys,statistics
f=read(ART/'freeze.json');sys.path.insert(0,str(ROOT/f['arms']['concise']['code_root']/'02_BACKEND'))
from semantic_runtime.contracts import digest
from lawrag.research.experiment_client import _schema_for_api
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
assert read(ART/'run-001/completed.json')['cells']==22
saved=json.loads(gzip.decompress((ROOT/f['source_view']).read_bytes()))['view']
rubric=read(ART/'rubric.json')['cases'];paths={p['id']:p for p in read(ART/'package.json')['paths']}
cases={c['id']:c for c in read(ART/'cases.json')}
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1124-ontology-explicit-exception-contract/artifacts/run-001/semantic/cm-023/audit.json')
by_source={r['source_id']:r['canonical'] for r in parent['read_evidence']}
uniq=lambda rows:[json.loads(x) for x in sorted({json.dumps(x,sort_keys=True) for x in rows})]
roots=uniq(by_source[o['source_id']] for o in saved['evidence_options'])
option_map={o['id']:o for o in saved['evidence_options']}
# Gold coordinates only join this evaluator after all calls finish. These measure
# source-package coverage, not independent legal correctness.
saved_by_label={p['anchor']['label']:p for p in saved['ontology_bundles'][0]['payload']['provisions']}
originals={s['id']:s for s in read(ART/'build-input.json')['originals']}
path_refs={pid:list(dict.fromkeys(r for sid in p['source_ids'] for r in saved_by_label[originals[sid]['anchor']['label']]['source_refs'])) for pid,p in paths.items()}
rows=[];wire=[];captures=[];first_inputs={}
for cell in read(ART/'schedule.json'):
 cid=cell['case_id'];name=cid+'__r'+str(cell['rep']);arm=cell['arm'];p=ART/'run-001'/arm/name
 r=read(p/'result.json');a=read(p/'assessment.json');receipt=a['assessment_basis']['scenario_choice'];choice=receipt['choice']['choices'][0]
 selected=[v['id'] for v in receipt['selected_paths']];expected=rubric[cid]
 exact=all(c['text']==paths[x['id']]['body'] and digest(c['text'])==x['body_sha256'] for c,x in zip(a['claims'],receipt['selected_paths']))
 source_match=all(o==option_map.get(o['id']) for c in a['claims'] for o in c['span_receipts'])
 current=uniq(by_source[o['source_id']] for c in a['claims'] for o in c['span_receipts'])
 gold=uniq(by_source[option_map[ref]['source_id']] for pid in expected['exact_paths'] for ref in path_refs[pid])
 rec=StageLedgerRecorder(name,arm,identity_canonicalizer);previous=[]
 for sid,kind,items,parents in [('saved_originals','source',roots,[]),('selector_presented','present',roots,['saved_originals']),('selected_cited','present',current,['selector_presented'])]:
  rec.record_stage(sid,kind,items,parent_stage_ids=parents,discard_reasons=[{'identity':v,'reason':'Not used in selected scenario; no claim of legal irrelevance or source absence'} for v in previous if v not in items]);previous=items
 captures.append(grade_capture(rec.capture(),gold))
 rawpaths=[]
 for n,q in enumerate(sorted((p/'raw').glob('call-*')),1):
  req=read(q/'request.json');inp=read(p/f'input-{n}.json');resp=read(q/'response.json');out=read(p/f'output-{n}.json');rawpaths.append(out['choices'][0]['path_ids'])
  wire.append({'cell':name,'arm':arm,'call':n,'input_exact':req['messages'][0]['content']==inp['system'] and json.loads(req['messages'][1]['content'])==inp['data'],'schema_exact':read(q/'validation-schema.json')==_schema_for_api(inp['schema']),'output_cap_fields':[k for k in ('max_tokens','max_output_tokens','max_completion_tokens') if k in req],'model':resp.get('model'),'provider':resp.get('provider'),'scenario_bodies_exact':all(v['body']==paths[v['id']]['body'] for v in inp['data']['ontology_bundles'][0]['scenario_catalog']['paths']),'original_options_exact':inp['data']['evidence_options']==saved['evidence_options'],'request_policy':{'provider':req.get('provider'),'reasoning':req.get('reasoning'),'model':req.get('model')}})
  if n==1:first_inputs[(arm,name)]=inp
 pass_=set(selected)==set(expected['exact_paths']) and choice['status']==expected['status'] and receipt['effective_action']==expected['next_action'] and choice['next_action']==expected['next_action'] and receipt.get('failure_code') is None
 rows.append({**cell,'group':cases[cid]['group'],'cell_id':name,'selected_paths':selected,'model_output_path_lists':rawpaths,'expected':expected,'route_pass':pass_,'status':choice['status'],'next_action':choice['next_action'],'effective_action':receipt['effective_action'],'reason':choice['reason'],'failure_code':receipt.get('failure_code'),'semantic_reselections':max(len(receipt['selection_history'])-1,0),'schema_repairs':sum('repair' in q.name for q in (p/'raw').glob('call-*')),'final_body_exact':exact,'source_receipts_exact':source_match,'final_article_roots':len(current),'final_cited':current,'expected_article_roots':gold,'new_model_calls':r['new_model_calls'],'seconds':r['seconds'],'usage':{k:sum(u.get(k,0) or 0 for u in r['usage']) for k in ('input_tokens','output_tokens','cost_usd')},'peak_rss_kib':r['peak_rss_kib'],'path':str(p.relative_to(ROOT))})
paired=[]
for name in sorted({r['cell_id'] for r in rows}):
 a=first_inputs['baseline',name];b=first_inputs['concise',name]
 paired.append({'cell_id':name,'data_equal':a['data']==b['data'],'schema_equal':a['schema']==b['schema'],'only_system_prompt_differs':a['system']!=b['system'] and a['data']==b['data'] and a['schema']==b['schema']})
scores={}
for arm in ('baseline','concise'):
 subset=[r for r in rows if r['arm']==arm]
 scores[arm]={g:{'passed':sum(r['route_pass'] for r in subset if g=='all' or r['group']==g),'total':sum(g=='all' or r['group']==g for r in subset)} for g in ('general','control','all')}
wa={'calls':wire,'paired_inputs':paired,'input_mismatches':sum(not r['input_exact'] for r in wire),'schema_mismatches':sum(not r['schema_exact'] for r in wire),'scenario_body_mismatches':sum(not r['scenario_bodies_exact'] for r in wire),'original_option_mismatches':sum(not r['original_options_exact'] for r in wire),'output_cap_fields':sum(len(r['output_cap_fields']) for r in wire),'unique_original_options':len(saved['evidence_options']),'mode':'saved exact original input; no new DB/ACL retrieval'}
put(ART/'wire-audit.json',wa)
ledger=build_experiment_artifact('ADR-1148','ADR-1148-experiment-v1',[build_run_artifact('run-001',captures,{arm:['saved_originals','selector_presented','selected_cited'] for arm in scores})]);put(ART/'retrieval-ledger.json',ledger)
integrity=all(r['final_body_exact'] and r['source_receipts_exact'] for r in rows) and all(p['only_system_prompt_differs'] for p in paired) and all(wa[k]==0 for k in ('input_mismatches','schema_mismatches','scenario_body_mismatches','original_option_mismatches','output_cap_fields'))
result={'status':'complete','cases':rows,'scores':scores,'primary_pass':scores['concise']['general']['passed']==6 and scores['baseline']['general']['passed']<6 and scores['concise']['control']['passed']==5 and integrity and read(ART/'check-001.json')['status']==0,'integrity_pass':integrity,'quality_certified':False,'in_sample':True,'new_model_calls':sum(r['new_model_calls'] for r in rows),'new_evaluator_calls':0,'contract_tests':read(ART/'check-001.json')['passed'],'usage':{k:sum(r['usage'][k] for r in rows) for k in ('input_tokens','output_tokens','cost_usd')},'source_roots_per_cell':len(roots),'latency':{arm:{'p50_seconds':statistics.median(r['seconds'] for r in rows if r['arm']==arm),'max_seconds':max(r['seconds'] for r in rows if r['arm']==arm)} for arm in scores},'latency_scope':'selector and deterministic source-bound rendering only; not whole service; no latency causal claim','source_receipt_mismatches':sum(not r['source_receipts_exact'] for r in rows),'final_body_mismatches':sum(not r['final_body_exact'] for r in rows),'semantic_reselections':sum(r['semantic_reselections'] for r in rows),'schema_repairs':sum(r['schema_repairs'] for r in rows),'active_pointer_at_finish':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'this_task_main_mutations':0}
put(ART/'run-001/result.json',result)
print(json.dumps({k:v for k,v in result.items() if k not in ('cases','active_pointer_at_finish')},ensure_ascii=False,indent=2))
