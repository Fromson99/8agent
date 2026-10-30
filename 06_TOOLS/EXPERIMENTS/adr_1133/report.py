from common import *
import gzip,sys,statistics
f=read(ART/'freeze.json');C=ROOT/f['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import ontology_scenarios as sc
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
raw=read(ART/'run-001/raw-summary.json');rubric=read(ART/'rubric.json');package=read(ART/'package.json');paths={p['id']:p for p in package['paths']}
saved=__import__('json').loads(gzip.decompress((ROOT/f['source_view']).read_bytes()))['view']
parent_audit=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1124-ontology-explicit-exception-contract/artifacts/run-001/semantic/cm-023/audit.json');by_source={r['source_id']:r['canonical'] for r in parent_audit['read_evidence']}
uniq=lambda rows:[__import__('json').loads(x) for x in sorted({__import__('json').dumps(x,sort_keys=True) for x in rows})]
original_roots=uniq(by_source[o['source_id']] for o in saved['evidence_options'])
# Evaluation coordinates joined after all product selection has finished.
ref=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited/artifacts/cases-evaluator.json');g=next(x for x in ref['cases'] if x['case_id']=='cm-023');gold=[{'doc_id':t['current_binding']['document_id'],'node':int(t['current_binding']['unit_id'])} for t in g['evidence_targets']]
rows=[];captures=[];wire=[]
for r in raw['cases']:
 case=r['case_id'];p=ART/'run-001/scenario'/case;answer=read(p/'answer.json');assessment=read(p/'assessment.json');chosen=assessment['assessment_basis']['scenario_choice'];selected=[v['id'] for v in chosen['selected_paths']];expected=rubric['cases'][case]
 route_pass=set(expected.get('required_paths',[]))<=set(selected) and not set(expected.get('forbidden_paths',[])).intersection(selected)
 if 'outcome' in expected:route_pass=route_pass and all(v['status']==expected['outcome'] for v in chosen['choice']['choices'])
 exact=all(c['text']==paths[x['id']]['body'] and digest(c['text'])==x['body_sha256'] for c,x in zip(answer['claims'],chosen['selected_paths']))
 source_match=all(o==next((v for v in saved['evidence_options'] if v['id']==o['id']),None) for c in answer['claims'] for o in c['span_receipts'])
 current=uniq(by_source[o['source_id']] for c in answer['claims'] for o in c['span_receipts'])
 rec=StageLedgerRecorder(case,'scenario',identity_canonicalizer);previous=[]
 for sid,kind,items,parents in [('saved_originals','source',original_roots,[]),('selector_presented','present',original_roots,['saved_originals']),('selected_cited','present',current,['selector_presented'])]:
  rec.record_stage(sid,kind,items,parent_stage_ids=parents,discard_reasons=[{'identity':v,'reason':'Not used by selected scenario; not a claim of source absence or irrelevance for other questions'} for v in previous if v not in items]);previous=items
 captures.append(grade_capture(rec.capture(),[] if case=='scenario-unknown' else gold))
 for n,q in enumerate(sorted((p/'raw').glob('call-*')),1):
  req=read(q/'request.json');inp=read(p/f'input-{n}.json');resp=read(q/'response.json')
  check={'case_id':case,'call':n,'input_exact':req['messages'][0]['content']==inp['system'] and __import__('json').loads(req['messages'][1]['content'])==inp['data'],'output_cap_fields':[k for k in ('max_tokens','max_output_tokens','max_completion_tokens') if k in req],'model':resp.get('model'),'provider':resp.get('provider'),'scenario_bodies_exact':all(v['body']==paths[v['id']]['body'] for v in inp['data']['ontology_bundles'][0]['scenario_catalog']['paths']),'original_options_exact':inp['data']['evidence_options']==saved['evidence_options']}
  wire.append(check)
 rows.append({'case_id':case,'selected_paths':selected,'expected':expected,'route_pass':route_pass,'status':[c['status'] for c in chosen['choice']['choices']],'reason':[c['reason'] for c in chosen['choice']['choices']],'final_body_exact':exact,'selected_source_receipts_exact':source_match,'final_article_roots':len(current),'new_model_calls':r['new_model_calls'],'seconds':r['seconds'],'usage':{k:sum(u.get(k,0) or 0 for u in r['usage']) for k in ('input_tokens','output_tokens','cost_usd')},'peak_rss_kib':r['peak_rss_kib']})
run=build_run_artifact('run-001',captures,{'scenario':['saved_originals','selector_presented','selected_cited']});ledger=build_experiment_artifact('ADR-1133','ADR-1133-experiment-v1',[run]);put(ART/'retrieval-ledger.json',ledger)
put(ART/'wire-audit.json',{'calls':wire,'input_mismatches':sum(not r['input_exact'] for r in wire),'scenario_body_mismatches':sum(not r['scenario_bodies_exact'] for r in wire),'original_option_mismatches':sum(not r['original_options_exact'] for r in wire),'output_cap_fields':sum(len(r['output_cap_fields']) for r in wire),'unique_original_options':len(saved['evidence_options']),'repeated_option_observations':len(saved['evidence_options'])*len(wire),'mode':'saved original input, not new DB/ACL retrieval'})
result={'status':'complete','cases':rows,'route_score':{'passed':sum(r['route_pass'] for r in rows),'total':len(rows)},'quality_certified':False,'paired_delta':None,'paired_reason':'Single-arm path-selection implementation probe; historical1124 is provenance only, no paired baseline.','new_model_calls':sum(r['new_model_calls'] for r in rows),'new_evaluator_calls':0,'compiler_model_calls':0,'compose_model_calls':0,'contract_checks':read(ART/'check-001.json')['passed'],'usage':{k:sum(r['usage'][k] for r in rows) for k in ('input_tokens','output_tokens','cost_usd')},'latency':{'scope':'selector plus saved-source binding/rendering, not complete service','p50_seconds':statistics.median(r['seconds'] for r in rows),'p95_seconds':sorted(r['seconds'] for r in rows)[-1],'p95_method':'nearest-rank,n=4'},'source_options_per_case':len(saved['evidence_options']),'source_roots_per_case':len(original_roots),'source_receipt_mismatches':sum(not r['selected_source_receipts_exact'] for r in rows),'final_body_mismatches':sum(not r['final_body_exact'] for r in rows),'active_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256'],'changed_frozen_files':[n for n,h in f['files'].items() if sha(C/n)!=h]}
put(ART/'run-001/result.json',result)
print(__import__('json').dumps(result,ensure_ascii=False,indent=2))
