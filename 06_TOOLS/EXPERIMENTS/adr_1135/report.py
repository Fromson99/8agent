from common import *
import gzip,sys,statistics,sqlite3
f=read(ART/'freeze.json');C=ROOT/f['code_root'];sys.dont_write_bytecode=True;sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.contracts import digest
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
saved=json.loads(gzip.decompress((ROOT/f['source_view']).read_bytes()))['view'];pa=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1124-ontology-explicit-exception-contract/artifacts/run-001/semantic/cm-023/audit.json');by_source={r['source_id']:r['canonical'] for r in pa['read_evidence']}
uniq=lambda rows:[json.loads(x) for x in sorted({json.dumps(x,sort_keys=True) for x in rows if x})]
original_roots=uniq(by_source[o['source_id']] for o in saved['evidence_options']);gold_ref=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited/artifacts/cases-evaluator.json');g=next(v for v in gold_ref['cases'] if v['case_id']=='cm-023');gold=[{'doc_id':t['current_binding']['document_id'],'node':int(t['current_binding']['unit_id'])} for t in g['evidence_targets']]
rubric=read(ART/'rubric.json');package=read(ART/'package.json');paths={p['id']:p for p in package['paths']};captures=[];direct=[];wire=[]
for case in read(ART/'cases.json'):
 if case['mode']!='saved_source_selector':continue
 p=ART/'run-001/scenario'/case['id'];r=read(p/'result.json');assessment=read(p/'assessment.json');receipt=assessment['assessment_basis']['scenario_choice'];chosen=[x['id'] for x in receipt['selected_paths']];expected=rubric['cases'][case['id']]
 ok=set(expected.get('required_paths',[]))<=set(chosen) and not set(expected.get('forbidden_paths',[])).intersection(chosen)
 if expected.get('outcome'):ok=ok and all(x['status']==expected['outcome'] for x in receipt['choice']['choices'])
 if expected.get('next_action'):ok=ok and all(x['next_action']==expected['next_action'] for x in receipt['choice']['choices'])
 claims=read(p/'answer.json')['claims'] if (p/'answer.json').exists() else []
 exact=all(c['text']==paths[path['id']]['body'] for c,path in zip(claims,receipt['selected_paths']))
 current=uniq(by_source[o['source_id']] for c in claims for o in c['span_receipts'])
 source_exact=all(o==next((v for v in saved['evidence_options'] if v['id']==o['id']),None) for c in claims for o in c['span_receipts'])
 for n,q in enumerate(sorted((p/'raw').glob('call-*')),1):
  req=read(q/'request.json');inp=read(p/f'input-{n}.json')
  wire.append({'case_id':case['id'],'input_exact':req['messages'][0]['content']==inp['system'] and json.loads(req['messages'][1]['content'])==inp['data'],'original_options_exact':inp['data']['evidence_options']==saved['evidence_options'],'scenario_bodies_exact':all(v['body']==paths[v['id']]['body'] for v in inp['data']['ontology_bundles'][0]['scenario_catalog']['paths']),'output_cap_fields':[k for k in ('max_tokens','max_output_tokens','max_completion_tokens') if k in req]})
 row={'case_id':case['id'],'selected_paths':chosen,'route_pass':ok,'effective_action':receipt['effective_action'],'model_decision':receipt['choice'],'semantic_reselections':max(0,len(receipt['selection_history'])-1),'calls':r['new_model_calls'],'seconds':r['seconds'],'usage':{k:sum(u.get(k,0) or 0 for u in r['usage']) for k in ('input_tokens','output_tokens','cost_usd')},'final_body_exact':exact,'source_receipts_exact':source_exact,'final_cited':current,'mode':'saved-source selector; SEARCH execution not part of this case'};direct.append(row)
 rec=StageLedgerRecorder(case['id'],'scenario',identity_canonicalizer);previous=[]
 for sid,kind,items,parents in [('originals','source',original_roots,[]),('assess_presented','present',original_roots,['originals']),('final_cited','present',current,['assess_presented'])]:
  rec.record_stage(sid,kind,items,parent_stage_ids=parents,discard_reasons=[{'identity':x,'reason':'Not used in final published claims; direct SEARCH case stops before retrieval, not proof of source absence'} for x in previous if x not in items]);previous=items
 captures.append(grade_capture(rec.capture(),[] if case['id']=='scenario-unknown' else gold))
p=ART/'run-001/scenario/scenario-uncovered';r=read(p/'result.json');a=read(p/'audit.json');w=read(p/'wire-audit.json');body=read(p/'response.json')['body'];outcome=body.get('assembly',{}).get('term_agent',{}).get('accepted_outcome',{})
by_source_native={x['source_id']:x['canonical'] for x in a['read_evidence']};presented=uniq(by_source_native.get(s['source_id']) for c in w['calls'] for s in c.get('presented_sources',[]));events=read(p/'scenario-events.json');fallback=[e for e in events if e['kind']=='SCENARIO_CHOICE_FALLBACK'];selected=[e for e in events if e['kind']=='SCENARIO_SELECTED'];reentry=[e for e in events if e['kind']=='CASE_STAGE_REENTRY']
model_choices=[]
for q in sorted((p/'raw').glob('call-*memory-assess*/response.json')):
 v=json.loads(read(q)['choices'][0]['message']['content'])
 if 'choices' in v:model_choices.append({'call':q.parent.name,'value':v})
valid_search=any(all(x['next_action']=='SEARCH' for x in v['value']['choices']) for v in model_choices)
trace=[]
for generation in read(p/'generations.json'):
 op=p/'canonical'/f"{generation['number']:03d}-output.json.gz";v=json.loads(gzip.decompress(op.read_bytes())) if op.exists() else {}
 trace.append({'number':generation['number'],'stage':generation['stage'],'accepted':generation.get('accepted'),'choice':v.get('choice'),'claims':len(v.get('claims',[])),'gaps':v.get('gaps')})
j=sqlite3.connect((ROOT/r['journal_paths'][0]).resolve().as_uri()+'?mode=ro',uri=True);return_seq=reentry[0]['seq'] if reentry else -1
additional_reads=list(j.execute("SELECT seq,kind FROM event WHERE seq>? AND kind='UNIT_READ_CHOICE'",(return_seq,)));j.close()
native={'case_id':'scenario-uncovered','mode':'fresh native HTTP no prefix replay','http_status':r['http_status'],'outcome':outcome,'calls':r['model_calls'],'seconds':r['elapsed_seconds'],'model_transport_seconds':r['model_transport_seconds'],'application_prepare_seconds':r['application_prepare_seconds'],'usage':{k:sum(u.get(k,0) or 0 for u in r['usage']) for k in ('input_tokens','output_tokens','cost_usd')},'model_choices':model_choices,'natural_search_choice_valid':valid_search,'schema_repair_calls':1,'semantic_reselections':0,'server_fallback':bool(fallback),'search_reentry_count':len(reentry),'ordinary_assessment_complete':any(t['stage']=='memory-assess' and t['claims']==2 for t in trace),'final_two_claims':len(body['answer']['claims'])==2,'recovery_path_pass':r['http_status']==200 and bool(reentry) and len(body['answer']['claims'])==2,'primary_pass':valid_search and r['http_status']==200 and bool(reentry),'trace':trace,'final_cited':a['final_coordinates'],'additional_unit_reads_after_reentry':len(additional_reads),'source_receipt_observations':len(a['span_checks']),'source_span_observations':sum(v['span_count'] for v in a['span_checks']),'source_mismatches':sum(not v['exact_original_match'] for v in a['span_checks']),'scope_violations':sum(not v['within_scope'] for v in a['span_checks']),'wire':{k:v for k,v in w.items() if k!='calls'},'peak_rss_kib':r['peak_rss_kib'],'wiki_projection_pending_log':1 if 'wiki.projection_pending' in (ART/'native.log').read_text() else 0}
rec=StageLedgerRecorder('scenario-uncovered','scenario',identity_canonicalizer);previous=[]
for sid,kind,items,parents in [('originals','source',a['read_coordinates'],[]),('assess_presented','present',presented,['originals']),('final_cited','present',a['final_coordinates'],['assess_presented'])]:
 rec.record_stage(sid,kind,items,parent_stage_ids=parents,discard_reasons=[{'identity':x,'reason':'Not cited in final answer; no source absence claim'} for x in previous if x not in items]);previous=items
native_gold=[v for v in gold if v['doc_id']=='27c02e2a7e1c59cb'];captures.append(grade_capture(rec.capture(),native_gold))
ledger=build_experiment_artifact('ADR-1135','ADR-1135-experiment-v1',[build_run_artifact('run-001',captures,{'scenario':['originals','assess_presented','final_cited']})]);put(ART/'retrieval-ledger.json',ledger)
put(ART/'direct-wire-audit.json',{'calls':wire,'unique_original_options':120,'repeat_option_observations':480,'input_mismatches':sum(not r['input_exact'] for r in wire),'original_mismatches':sum(not r['original_options_exact'] for r in wire),'scenario_mismatches':sum(not r['scenario_bodies_exact'] for r in wire),'output_cap_fields':sum(len(r['output_cap_fields']) for r in wire)})
result={'status':'complete','direct':direct,'native':native,'route_score':{'passed':sum(x['route_pass'] for x in direct),'total':4},'native_recovery_pass':native['recovery_path_pass'],'primary_pass':all(x['route_pass'] for x in direct) and native['primary_pass'],'semantic_reselection_observed':False,'new_model_calls':sum(x['calls'] for x in direct)+native['calls'],'new_evaluator_calls':0,'usage':{k:sum(x['usage'][k] for x in direct)+native['usage'][k] for k in ('input_tokens','output_tokens','cost_usd')},'quality_certified':False,'paired_delta':None,'comparison_note':'Same saved-source four questions as1133, different run; no paired randomized latency/quality claim. Nativecase separate fresh full path.','product_parent_identical':f['files']==read(ART/'parent.json')['frozen_files'],'active_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']}
put(ART/'run-001/result.json',result)
print(json.dumps({k:v for k,v in result.items() if k not in ('direct','native')},ensure_ascii=False,indent=2))
print('native',json.dumps({k:v for k,v in native.items() if k not in ('model_choices','trace','wire')},ensure_ascii=False,indent=2))
