"""Post-product source ledger, physical usage and contract reconstruction."""
from pathlib import Path
import collections,gzip,hashlib,importlib.util,json,sqlite3,statistics,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0558-model-presentation-repair';ARMS=['baseline','presentation','selected-only']
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'))
from adr_structure import ADR_HEADINGS,QUESTION_HEADINGS_V4,_canonical_value_sha256
spec=importlib.util.spec_from_file_location('ledger',R/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 f=read(A/'artifacts/frozen-design.json');m=read(A/'실험/manifest.json');prod=read(A/'product-cases.json');index=read(A/'artifacts/run-001/results.json')
 for p,expected in {**f['file_hashes'],**f['grader_only_hashes']}.items():assert sha(R/p)==expected,p
 assert read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['release_binding']
 gold={c['case_id']:c for c in read(A/'gold-cases.json')['cases']}
 nav=sqlite3.connect('file:'+str(R/f['generation']/'navigation/navigation.sqlite')+'?mode=ro',uri=True)
 coords={sid:{'doc_id':did,'node':int(uid)} for sid,did,uid in nav.execute("select id,document_id,json_extract(json,'$.unit_id') from source") if str(uid).isdigit()};nav.close()
 corpus=sum(x['doc_id'] in prod['public_scope_document_ids'] for x in coords.values())
 judge_path=A/'artifacts/judge-001/results.json';judges=read(judge_path) if judge_path.exists() else {'rows':[],'usage':[],'physical_calls':0}
 verdicts={(x['case_id'],x['arm']):x['verdict'] for x in judges['rows']}
 allrows=[];ledgerarms=[];totals={};accounting=[]
 for arm in ARMS:
  records=[];rows=[];usage=[]
  for case in prod['cases']:
   cid=case['case_id'];path=R/index['cases'][cid][arm]['path'];row=read(path);out=path.parent
   with gzip.open(out/'trace.json.gz','rt') as z:trace=json.load(z)
   stages=deepcopy_stages={k:list(v) for k,v in row.get('stages',{}).items()}
   required=set(gold.get(cid,{}).get('decisive_source_ids',[]));assert required<=coords.keys()
   g=h.ordered(coords[s] for s in required);outputs={};ledgerstages=[]
   for plan in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
    before=h.ordered(x for parent in plan['parent_stage_ids'] for x in outputs[parent]);after=h.ordered(coords[s] for s in stages.get(plan['stage_id'],[]) if s in coords)
    bkeys={h.key(x) for x in before};akeys={h.key(x) for x in after};discard=[x for x in before if h.key(x) not in akeys]
    reason={'read':'not_read','selected':'not_selected','presented':'no_successful_exact_presentation_receipt'}.get(plan['stage_id'],'not_observed')
    st=h.stage(plan['stage_id'],plan['kind'],plan['parent_stage_ids'],before,[x for x in after if h.key(x) not in bkeys],discard,{h.key(x):reason for x in discard},g)
    ledgerstages.append(st);outputs[plan['stage_id']]=st['after']
   records.append({'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':arm,'case_id':cid,'gold_total':len(g),'gold_identities':g,'stages':ledgerstages})
   checks=[];attempts=[];j=sqlite3.connect('file:'+str(R/row['journal_path'])+'?mode=ro',uri=True)
   vmap={vid:json.loads(raw) for vid,raw in j.execute('select view_id,body_json from model_view')}
   for vid,status,request in j.execute('select view_id,status,request_json from model_attempt'):
    req=json.loads(request);wire=json.loads(req['messages'][1]['content'])['view'];raw=vmap[vid];phase=wire.get('source_stage',wire['phase'])
    attempts.append({'phase':phase,'status':status,'message_chars':sum(len(x['content']) for x in req['messages']),'wire_chars':len(json.dumps(wire,ensure_ascii=False,separators=(',',':')))})
    if phase!='compose':continue
    exact=raw.get('exact_evidence',[]);selected=set(raw.get('evidence_roles',{}).get('support',[]));exceptions=set((raw.get('compose_delivery') or {}).get('required_connections',{}))
    extras=[e['evidence'] for e in exact if e['evidence'] not in selected|exceptions]
    reconstruct=all(wire['bodies'][w['body_refs'][0]]['text']==e['text'] for e,w in zip(exact,wire['exact_evidence'])) and len(exact)==len(wire['exact_evidence']) if arm!='baseline' else True
    checks.append({'status':status,'original_reconstructed':reconstruct,'evidence_choices':len(exact),'selected':len(selected),'required_context':len(exceptions),'unselected_extra':len(extras),'unselected_text_chars':sum(len(e['text']) for e in exact if e['evidence'] in extras),'source_labels':all(bool(e.get('coordinate_label')) for e in wire.get('exact_evidence',[])) if arm!='baseline' else None,'span_objects_sent':sum(len(e.get('spans',[])) for e in wire.get('exact_evidence',[]))})
   j.close();answer=row.get('result',{}).get('answer',{});verdict=verdicts.get((cid,arm),{})
   faults=[json.loads(e['payload_json']) for e in trace['events'] if e['kind']=='BOUNDED_SOURCE_FAILURE']
   measured={'case_id':cid,'arm':arm,'kind':case['kind'],'error':row.get('error'),'stage_counts':{k:len(set(v)) for k,v in stages.items()},'seconds':row.get('seconds'),'physical_calls':row['physical_calls'],'publication_status':row.get('publication_status'),'substantive_answer':bool(answer.get('claims')) if case['kind']=='legal' else bool(answer.get('text','').strip()) and (row.get('request_route') or {}).get('mode')==case['expected_route'],'route':row.get('request_route'),'answer':answer.get('text',''),'claims':answer.get('claims',[]),'limitations':row.get('limitations',[]),'source_failure_events':faults,'session_errors':trace.get('errors',[]),'compose_checks':checks,'physical_attempts':attempts,'judge':verdict,'gold_total':len(g),'gold_presented':ledgerstages[-1]['gold_after'],'result_path':str(path.relative_to(R)),'result_sha256':sha(path),'journal_path':row['journal_path']}
   rows.append(measured);usage+=row['usage'];accounting.append({'case_id':cid,'arm':arm,'checks':checks,'attempts':attempts})
  counts=sorted(r['stages'][-1]['after_count'] for r in records);got=sum(r['stages'][-1]['gold_after'] for r in records);n=sum(r['gold_total'] for r in records)
  t={'cases':len(rows),'published':sum(r['publication_status']=='PUBLISHED' for r in rows),'legal_substantive':sum(r['substantive_answer'] for r in rows if r['kind']=='legal'),'utility_completed':sum(r['substantive_answer'] for r in rows if r['kind']=='utility'),'requirement_pass':sum(r['judge'].get('requirement_pass') is True for r in rows),'critical_errors':sum(r['judge'].get('critical_error') is True for r in rows),'judge_errors':sum('judge_error' in r['judge'] for r in rows),'physical_calls':sum(r['physical_calls'] for r in rows),'input_tokens':sum(u.get('input_tokens') or 0 for u in usage),'output_tokens':sum(u.get('output_tokens') or 0 for u in usage),'cost_usd':sum(u.get('cost_usd') or 0 for u in usage),'usage_missing_calls':sum(r['physical_calls'] for r in rows)-len(usage),'mean_seconds':statistics.mean(r['seconds'] for r in rows),'before_filter':sum(r['stages'][0]['after_count'] for r in records),'after_filter':sum(r['stages'][1]['after_count'] for r in records),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':counts[round((len(counts)-1)*.95)],'golden_recall':got/n if n else None,'selectivity':statistics.mean(counts)/corpus,'gold_obtained':got,'gold_total':n}
  totals[arm]=t;allrows+=rows
  ledgerarms.append({'arm_id':arm,'declared_stage_ids':[s['stage_id'] for s in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]],'cases':records,'aggregate':{'presented_total':sum(counts),'gold_after':got,'gold_total':n}})
 ledger={'schema_version':h.SCHEMA,'adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':ledgerarms}],'audit':{'presentation':'Successful physical attempt exact presentation; article recall is not paragraph completeness','gold_join':'Offline after product processes ended'}}
 ledger['artifact_sha256']=_canonical_value_sha256(ledger);write(A/'artifacts/retrieval-stage-ledger.json',ledger)
 comparisons=[]
 for arm in ARMS[1:]:
  regress=[c['case_id'] for c in prod['cases'] if next(r for r in allrows if r['arm']=='baseline' and r['case_id']==c['case_id'])['substantive_answer'] and not next(r for r in allrows if r['arm']==arm and r['case_id']==c['case_id'])['substantive_answer']]
  comparisons.append({'candidate':arm,'new_completion_regressions':regress,'input_token_ratio':totals[arm]['input_tokens']/totals['baseline']['input_tokens'],'mean_latency_ratio':totals[arm]['mean_seconds']/totals['baseline']['mean_seconds'],'both_complete_legal_cases':[c['case_id'] for c in prod['cases'] if c['kind']=='legal' and all(next(r for r in allrows if r['arm']==a and r['case_id']==c['case_id'])['substantive_answer'] for a in ('baseline',arm))],'interpretation':'Failed/unequal completion must not be described as efficiency improvement; archival paired wire reduction measured separately'})
 violation=sum(not c['original_reconstructed'] or r['arm']=='selected-only' and c['unselected_extra']>0 for r in allrows for c in r['compose_checks'])
 summary={'totals':totals,'rows':allrows,'comparisons':comparisons,'contract_violations':violation,'judge_usage':judges['usage'],'judge_calls':judges['physical_calls'],'model':'google/gemma-4-31b-it','release':f['release_binding'],'in_sample':True,'decision_eligible':False,'main_changed':False,'quality_certified':False,'limitations':['Four legal and two utility cases, one replicate, known audit cases','External Gemma/Parasail FP8, no GENOS internal model measurement','Two WSL workers; end-to-end wall includes cold resource loading','Same-model offline evaluator; actual public originals and rubric provided separately','Article-level delivery recall does not prove exact exception completeness','P0-P2 implemented; P3-P5 remain separate follow-up scope']}
 write(A/'artifacts/summary.json',summary);write(A/'artifacts/physical-request-accounting.json',accounting)
 m['design']['code_isolation']['reason']=None
 m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/results.json'))
 m['results'].update(status='complete',by_arm=totals,comparisons=comparisons,judge_disagreements='Same model independent answer grading; raw verdicts preserved; no holdout certification',usage={a:{k:totals[a][k] for k in ('physical_calls','input_tokens','output_tokens','cost_usd','usage_missing_calls')} for a in ARMS},latency={'mean_seconds':{a:totals[a]['mean_seconds'] for a in ARMS}},error_taxonomy=sorted({x['message'] for r in allrows for x in r['source_failure_events']}|{x['type'] for r in allrows for x in r['session_errors'] if 'type' in x}))
 m['retrieval_accounting']={'changed':True,'corpus_total':corpus,'not_applicable_reason':None,'stage_ledger':{'mode':'measured','schema_version':h.SCHEMA,'accounting_unit':h.UNIT,'summary_run_id':'run-001','artifact_path':str((A/'artifacts/retrieval-stage-ledger.json').relative_to(R)),'sha256':sha(A/'artifacts/retrieval-stage-ledger.json'),'not_applicable_reason':None},**{k:{a:totals[a][k] for a in ARMS} for k in ('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity')}}
 m['actual_model_binding']={'model':'google/gemma-4-31b-it','provider':'Parasail FP8','thinking':'off','physical_calls':sum(t['physical_calls'] for t in totals.values())+judges['physical_calls']}
 m['questions']=[]
 for number,case in enumerate(prod['cases'],1):
  cid=case['case_id'];filename=f'질문-{number:03d}-{cid}.md';qp=A/'실험'/filename
  raw=[]
  for arm in ARMS:
   out=A/'artifacts/run-001'/cid/arm
   raw.extend(f'- [{arm}/{p.parent.name}/{p.name}](../{p.relative_to(A)}) SHA256 `{sha(p)}`' for p in sorted((out/'calls').rglob('*.json')))
  measured=[r for r in allrows if r['case_id']==cid]
  blocks=[f'ADR0558/run-001/{cid}; source question exact; frozen generation31.',case['question'],'```json\n'+json.dumps(gold.get(cid,{'expected_route':case['expected_route']}),ensure_ascii=False,indent=2)+'\n```','Same frozen Pipeline/public145 PeCab data, Gemma policy, controller/call budgets. Product processes cannot read gold.','Full source/read/selected/presented ledger; known-case probe and one repeat.','\n'.join(raw) or 'No physical model send.','Every request, response, usage, repair, output-limit and publication outcome retained.','Offline blinded Gemma evaluation with frozen rubric and public originals; no feedback into product.','```json\n'+json.dumps(measured,ensure_ascii=False,indent=2)+'\n```']
  qp.write_text('# '+cid+'\n\n'+'\n\n'.join(k+'\n\n'+v for k,v in zip(QUESTION_HEADINGS_V4,blocks))+'\n');m['questions'].append({'number':number,'case_id':cid,'file':filename,'sha256':sha(qp)})
 write(A/'실험/manifest.json',m)
 (A/'실험/README.md').write_text('# Gemma presentation probe\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
 front=(A/'README.md').read_text().split('---',2)[1]
 blocks=['Deferred: candidate implementation and experiment completed; MAIN unchanged. No promotion eligibility.','Duplicate relation rows, compose coordinate objects and unselected source filler observed in audit.',m['design']['hypothesis']+'\n\n```json\n'+json.dumps(m['design']['success_criteria'],ensure_ascii=False,indent=2)+'\n```',(A/'PLAN.md').read_text(),'frozen-design.json pins release, candidate revisions, product fixture and grader-only gold separately.','```json\n'+json.dumps(totals,ensure_ascii=False,indent=2)+'\n```','Exact physical sends and evidence reconstruction in question reports, summary and journal.','```json\n'+json.dumps(m['results']['usage'],indent=2)+'\n```','39 archival payload reconstruction is byte/character diagnostic, independent of live E2E quality.','\n'.join('- '+x for x in summary['limitations']),'No production registry edit, no MAIN activation, no GENOS deployment.','```bash\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0558/run_probe.py --execute\n```\nCompleted outputs are immutable; changed candidate or reexecution requires new ADR.']
 (A/'README.md').write_text('---'+front+'---\n\n# ADR0558 Model presentation repair\n\n'+'\n\n'.join(k+'\n\n'+v for k,v in zip(ADR_HEADINGS,blocks))+'\n')
 print(json.dumps({'totals':totals,'comparisons':comparisons,'contract_violations':violation},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
