"""Post-selection flow/source audit; no model or product calls."""
from common import *
import sys,sqlite3,gzip
f=read(ART/'freeze.json');C=ROOT/f['arms']['ontology']['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
evaluator=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited/artifacts/cases-evaluator.json')
goldcase=next(c for c in evaluator['cases'] if c['case_id']=='cm-023')
gold=[{'doc_id':t['current_binding']['document_id'],'node':int(t['current_binding']['unit_id'])} for t in goldcase['evidence_targets']]
def uniq(items):return [json.loads(v) for v in sorted({json.dumps(x,sort_keys=True) for x in items if x})]
def gz(p):return json.loads(gzip.decompress(p.read_bytes()))
results={};captures=[];inputs=[];metrics=[]
for arm in ('baseline','ontology'):
 P=ART/'run-001'/arm/'cm-023';r=read(P/'result.json');a=read(P/'audit.json');w=read(P/'wire-audit.json');body=read(P/'response.json')['body'];outcome=body['assembly']['term_agent']['accepted_outcome']
 by_source={x['source_id']:x['canonical'] for x in a['read_evidence']}
 presented=uniq(by_source.get(s['source_id']) for c in w['calls'] for s in c.get('presented_sources',[]))
 stages=[('original_read','source',a['read_coordinates'],[]),('assess_presented','present',presented,['original_read']),('final_cited','present',a['final_coordinates'],['assess_presented'])]
 rec=StageLedgerRecorder('cm-023',arm,identity_canonicalizer);prev=[]
 for ident,kind,items,parents in stages:
  rec.record_stage(ident,kind,items,parent_stage_ids=parents,discard_reasons=[{'identity':x,'reason':'Not included in this later ASSESS/claim-citation stage; no absence or irrelevance conclusion'} for x in prev if x not in items]);prev=items
 captures.append(grade_capture(rec.capture(),gold))
 trace=[]
 for c in read(P/'calls.json'):
  raw=read(next((P/'raw').glob(f"call-{c['call']:03d}-*/response.json")))
  try:value=json.loads(raw['choices'][0]['message']['content'])
  except (KeyError,ValueError,TypeError):value={}
  trace.append({'call':c['call'],'phase':c['phase'],'seconds':c['seconds'],'choice':value.get('choice'),
    'queries':value.get('command',{}).get('queries'),'selections':value.get('selections'),
    'gaps':value.get('gaps'),'issue_assessments':value.get('issue_assessments')})
 input1=read(next((P/'raw').glob('call-001-*/request.json')));inputs.append(input1)
 summary={'arm':arm,'http_status':r['http_status'],'outcome':outcome,'model_calls':r['model_calls'],'seconds':r['elapsed_seconds'],
  'model_transport_seconds':r['model_transport_seconds'],'outside_model_seconds':r['elapsed_seconds']-r['model_transport_seconds'],
  'application_prepare_seconds':r['application_prepare_seconds'],'peak_rss_kib':r['peak_rss_kib'],
  'usage':{k:sum(u.get(k,0) or 0 for u in r['usage']) for k in ('input_tokens','output_tokens','cost_usd')},
  'original_evidence_units':len(a['span_checks']),'source_mismatches':sum(not x['exact_original_match'] for x in a['span_checks']),
  'permission_violations':sum(not x['within_scope'] for x in a['span_checks']),
  'wire_mismatches':w['request_copy_mismatches']+w['assess_original_mismatches'],'unknown_ontology_refs':w['unknown_ontology_refs'],'output_cap_fields':w['output_cap_fields'],
  'read_article_roots':len(a['read_coordinates']),'assess_article_roots':len(presented),'claim_cited_article_roots':len(a['final_coordinates']),
  'reference_root_coverage':{ident:{'matched':len([g for g in gold if g in items]),'total':len(gold)} for ident,kind,items,parents in stages},
  'ontology_cards':sum(c['ontology_cards'] for c in w['calls']),'ontology_provisions':sum(o['provisions'] for c in w['calls'] for o in c.get('ontology',[])),
  'trace':trace,'active_pointer_unchanged':r['active_pointer_unchanged'],'quality_certified':False}
 results[arm]=summary
 p=read(P/'binding.json') if (P/'binding.json').exists() else read(P.parent/'binding.json')
 metrics.append(p)
ledger=build_experiment_artifact('ADR-1105','ADR-1105-experiment-v1',[build_run_artifact('run-001',captures,{a:['original_read','assess_presented','final_cited'] for a in results})])
put(ART/'retrieval-ledger.json',ledger)
v=[json.loads(x['messages'][1]['content']) for x in inputs]
ids=[x['view'].pop('view_id') for x in v]
comparison={'initial_system_prompt_equal':inputs[0]['messages'][0]==inputs[1]['messages'][0],
 'initial_user_input_equal_except_view_id':v[0]==v[1],'initial_view_ids':ids,
 'initial_model_queries_differ':results['baseline']['trace'][0]['queries']!=results['ontology']['trace'][0]['queries'],
 'same_question_data_model_budgets':True,'causal_speed_or_retrieval_gain_claim_allowed':False,
 'reason':'Single known question per arm; initial fresh model outputs differed before ontology activation. Different retrieval/decisions confound timing and first-selection quality.',
 'direct_handoff_verified':'A1 call2 READ -> ontology acquisition -> call3 ASSESS with one complete bundle/28 provisions -> call4 narrative COMPOSE; no intervening navigation or ASSESS repair',
 'assessment_and_output_issues':[
 {'stage':'ASSESS','finding':'issue status PARTIAL while its reason says no concrete unknown remains and gaps=[]; host preserves model status as LIMITED_ANSWER', 'kind':'SEMANTIC_STATUS_INCONSISTENCY'},
 {'stage':'COMPOSE','finding':'Final paragraph merges exemption below the threshold and the separate refund condition. ASSESS C1 stores these as separate exception entries; source law article41-3(1) excludes low gain, (4) gives refund only under the specified decrease condition.', 'source_coordinates':[{'document_id':'27c02e2a7e1c59cb','block_id':'346'},{'document_id':'27c02e2a7e1c59cb','block_id':'353'}], 'kind':'NARRATIVE_MEANING_DRIFT'},
 {'stage':'ASSESS','finding':'C3 combines the source distinction 추정한다 / 본다 into 추정한다; transferred to prose. This is a local source comparison, not certified legal scoring.', 'source_coordinates':[{'document_id':'27c02e2a7e1c59cb','block_id':'355'}], 'kind':'SEMANTIC_DISTINCTION_LOSS'}],
 'model_evaluator_calls':0,'reference_answer_status':goldcase['source_provenance']['reference_status']}
put(ART/'comparison.json',comparison);put(ART/'run-001/result.json',{'status':'complete','arms':results,'comparison':comparison,'contract_checks':read(ART/'check-001.json')['passed'],'new_model_calls':sum(x['model_calls'] for x in results.values())})
put(ART/'verification.json',{'same_main_429_baseline_files':all(f['arms']['baseline']['files'][n]==h for n,h in read(ART/'baseline.json')['release']['files'].items()),
 'candidate_files_unchanged':all(sha(ROOT/arm['code_root']/n)==h for arm in f['arms'].values() for n,h in arm['files'].items()),
 'active_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256'],
 'data_selection_equal':metrics[0]['search_selection_fingerprint']==metrics[1]['search_selection_fingerprint'],
 'public_scope_equal':metrics[0]['public_scope']==metrics[1]['public_scope'],
 'response_schema_changed':False,'product_modules_changed':read(ART/'composition.json')['changed_product'],
 'new_model_calls':12,'new_evaluator_calls':0,'quality_certified':False})
for arm,x in results.items():print(arm,x['model_calls'],round(x['seconds'],3),x['outcome'],x['reference_root_coverage'])
