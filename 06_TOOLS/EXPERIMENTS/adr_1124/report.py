"""Post-selection evidence and input accounting; no product mutation or LLM."""
from common import *
import gzip,sys,statistics
f=read(ART/'freeze.json');C=ROOT/f['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
from semantic_runtime.contracts import digest
ref=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1066-ontology-input-unlimited/artifacts/cases-evaluator.json');g=next(x for x in ref['cases'] if x['case_id']=='cm-023');gold=[{'doc_id':t['current_binding']['document_id'],'node':int(t['current_binding']['unit_id'])} for t in g['evidence_targets']]
def uniq(items):return [json.loads(v) for v in sorted({json.dumps(x,sort_keys=True) for x in items if x})]
def gz(p):return json.loads(gzip.decompress(p.read_bytes()))
results={};captures=[]
for arm in ('baseline','semantic'):
 P=ART/'run-001'/arm/'cm-023'
 if not (P/'result.json').exists():continue
 r=read(P/'result.json');a=read(P/'audit.json');w=read(P/'wire-audit.json');body=read(P/'response.json')['body'];outcome=body.get('assembly',{}).get('term_agent',{}).get('accepted_outcome',{})
 by_source={x['source_id']:x['canonical'] for x in a['read_evidence']};presented=uniq(by_source.get(s['source_id']) for c in w['calls'] for s in c.get('presented_sources',[]))
 stages=[('original_read','source',a['read_coordinates'],[]),('assess_presented','present',presented,['original_read']),('final_cited','present',a['final_coordinates'],['assess_presented'])]
 rec=StageLedgerRecorder('cm-023',arm,identity_canonicalizer);prev=[]
 for name,kind,items,parents in stages:
  rec.record_stage(name,kind,items,parent_stage_ids=parents,discard_reasons=[{'identity':x,'reason':'Not delivered/cited in this later stage; no irrelevance/absence conclusion'} for x in prev if x not in items]);prev=items
 captures.append(grade_capture(rec.capture(),gold))
 trace=[]
 for generation in read(P/'generations.json'):
  op=P/'canonical'/f"{generation['number']:03d}-output.json.gz";v=gz(op) if op.exists() else {}
  trace.append({'number':generation['number'],'stage':generation['stage'],'accepted':generation.get('accepted'),'choice':v.get('choice'),'claims':len(v.get('claims',[])),'gaps':v.get('gaps'),'issue_assessments':v.get('issue_assessments')})
 results[arm]={'http_status':r.get('http_status'),'outcome':outcome,'new_model_calls':r['model_calls'],'replayed_prefix_calls':sum(c.get('status')=='replayed' for c in read(P/'calls.json')),'seconds':r['elapsed_seconds'],'model_seconds':r['model_transport_seconds'],'outside_model_seconds':r['elapsed_seconds']-r['model_transport_seconds'],'usage':{k:sum(u.get(k,0) or 0 for u in r['usage']) for k in ('input_tokens','output_tokens','cost_usd')},'trace':trace,'read_article_roots':len(a['read_coordinates']),'assess_article_roots':len(presented),'final_article_roots':len(a['final_coordinates']),'reference_coverage':{n:{'matched':sum(x in items for x in gold),'total':len(gold)} for n,_,items,_ in stages},'source_checks':len(a['span_checks']),'source_mismatches':sum(not x['exact_original_match'] for x in a['span_checks']),'acl_violations':sum(not x['within_scope'] for x in a['span_checks']),'wire_mismatches':w['request_copy_mismatches']+w['assess_original_mismatches'],'unknown_ontology_refs':w['unknown_ontology_refs'],'semantic_unknown_refs':w['semantic_unknown_refs'],'semantic_quote_failures':w['semantic_quote_failures'],'output_cap_fields':w['output_cap_fields'],'peak_rss_kib':r['peak_rss_kib']}
 stages_by_arm={x:[n for n,_,_,_ in stages] for x in results}
ledger=build_experiment_artifact('ADR-1124','ADR-1124-experiment-v1',[build_run_artifact('run-001',captures,stages_by_arm)])
put(ART/'retrieval-ledger.json',ledger)
comparison={'same_first_assess_originals':read(ART/'run-001/baseline/cm-023/first-assess-originals.json')==read(ART/'run-001/semantic/cm-023/first-assess-originals.json') if len(results)==2 else None,'changed_selected_release':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')!=f['pointer_sha256'],'quality_certified':False,'in_sample':True,'partial_replay':True,'new_evaluator_calls':0,'semantic_evaluation':'See source-based review.json; no automatic legal correctness score'}
build=read(ART/'build/result.json');put(ART/'run-001/result.json',{'status':'complete','arms':results,'build':build,'comparison':comparison,'new_model_calls':build['calls']+sum(r['new_model_calls'] for r in results.values()),'contract_checks':read(ART/'check-001.json')['passed']})
print(json.dumps({'arms':results,'build':{k:v for k,v in build.items() if k!='usage'},'comparison':comparison},ensure_ascii=False,indent=2))
