"""Offline article-coordinate accounting. Never imported by product worker."""
from pathlib import Path
import json,hashlib,sqlite3,statistics,math,gzip,sys,importlib.util,collections
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0524-gemma-fp8-scoped-retrieval'
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'))
from adr_structure import _canonical_value_sha256,ADR_HEADINGS,QUESTION_HEADINGS_V4
spec=importlib.util.spec_from_file_location('ledger',R/'06_TOOLS/EXPERIMENTS/adr_0473/build_ledger.py');h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)
def read(p):return json.loads(p.read_text())
def sha(p):
 d=hashlib.sha256()
 with p.open('rb') as f:
  while c:=f.read(8388608):d.update(c)
 return d.hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 index=read(A/'artifacts/run-001/results.json');f=read(A/'artifacts/frozen-design.json');m=read(A/'실험/manifest.json');prod=read(A/'product-cases.json')
 for p,v in f['file_hashes'].items():assert sha(R/p)==v,p
 for p,v in f['grader_only_hashes'].items():assert sha(R/p)==v,p
 gold={x['case_id']:x for x in read(A/'gold-cases.json')['cases']}
 db=sqlite3.connect('file:'+str(R/f['generations']['guarded']/'navigation/navigation.sqlite')+'?mode=ro',uri=True)
 coords={sid:{'doc_id':did,'node':int(uid)} for sid,did,uid in db.execute("SELECT id,document_id,json_extract(json,'$.unit_id') FROM source") if str(uid).isdigit()};db.close()
 corpus=sum(c['doc_id'] in prod['public_scope_document_ids'] for c in coords.values())
 rows=[];arms=[];totals={};traces={};all_usage=[]
 for arm in ('baseline','guarded'):
  records=[];arows=[]
  for c in prod['cases']:
   cid=c['case_id'];path=R/index['cases'][cid][arm]['path'];row=read(path);out=path.parent
   stages=row.get('stages',{})
   if not stages and (out/'journal.sqlite').exists():
    j=sqlite3.connect('file:'+str(out/'journal.sqlite')+'?mode=ro',uri=True)
    ev={eid:sid for eid,sid in j.execute('SELECT evidence_id,source_id FROM evidence_unit')};read_ids=set(ev.values());discovered={json.loads(raw).get('source_id') for (raw,) in j.execute('SELECT identity_json FROM navigation_handle')}-{None};discovered|=read_ids
    delivered={ev[eid] for (eid,) in j.execute("SELECT DISTINCT p.evidence_id FROM presentation p JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'") if eid in ev}
    selected=[]
    for (raw,) in j.execute("SELECT v.payload_json FROM entity_head h JOIN entity_version v USING(kind,entity_id,version) WHERE h.kind='source_selection' AND h.validity='CURRENT'"):
     v=json.loads(raw)
     if v.get('status')=='SELECTED' and v.get('evidence_id') in ev:selected.append(ev[v['evidence_id']])
    stages={'discovered':sorted(discovered),'read':sorted(read_ids),'presented':sorted(delivered),'selected':sorted(set(selected))};j.close()
   trace={}
   if (out/'trace.json.gz').exists():
    with gzip.open(out/'trace.json.gz','rt') as z:trace=json.load(z)
   origins=collections.Counter();verbs=collections.Counter()
   for act in trace.get('actions',[]):
    result=json.loads(act['result_json']) if act.get('result_json') else {};origins[result.get('exploration_origin',{}).get('route_class','unspecified')]+=1
    for k in ('action_json','args_json'):
     if act.get(k):
      val=json.loads(act[k]);verbs[val.get('tool',val.get('verb','unknown'))]+=1
   required=set(gold[cid]['decisive_source_ids']);assert required<=set(coords)
   got={k:len(required&set(ids)) for k,ids in stages.items()}
   g=h.ordered(coords[s] for s in required);prev=[];ledger_stages=[]
   for plan in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
    after=h.ordered(coords[s] for s in stages.get(plan['stage_id'],[]) if s in coords);ak={h.key(x) for x in after};pk={h.key(x) for x in prev};drop=[x for x in prev if h.key(x) not in ak]
    st=h.stage(plan['stage_id'],plan['kind'],plan['parent_stage_ids'],prev,[x for x in after if h.key(x) not in pk],drop,{h.key(x):'not_read' if plan['stage_id']=='read' else 'not_presented_to_successful_model_call' for x in drop},g);ledger_stages.append(st);prev=st['after']
   records.append({'schema_version':h.SCHEMA,'computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':h.UNIT,'arm_id':arm,'case_id':cid,'gold_total':len(g),'gold_identities':g,'stages':ledger_stages})
   provider_errors=collections.Counter()
   for rp in (out/'calls').glob('call-*/response.json'):
    response=read(rp);err=response.get('error')
    if isinstance(err,dict):provider_errors[str(err.get('code','unknown'))]+=1
   usage=row.get('usage',[]);all_usage+=usage
   rr={'case_id':cid,'arm':arm,'error':row.get('error'),'provider_errors':dict(provider_errors),'gold_total':len(required),'gold_by_stage':got,'counts':{k:len(set(v)) for k,v in stages.items()},'missing_presented':sorted(required-set(stages.get('presented',[]))),'physical_calls':row['physical_calls'],'seconds':row['seconds'],'controller_seconds':row.get('controller_seconds'),'graph':row.get('graph_summary'),'cost_usd':sum(u.get('cost_usd') or 0 for u in usage),'unknown_usage':row.get('in_flight_usage_unknown',False),'limitations':row.get('limitations',[]),'gate':row.get('control'),'action_origins':dict(origins),'session_errors':trace.get('errors',[]),'artifacts':{'result':str(path.relative_to(R)),'result_sha256':sha(path),'trace':str((out/'trace.json.gz').relative_to(R)) if trace else None}}
   rows.append(rr);arows.append(rr);traces[cid,arm]=trace
  counts=sorted(r['stages'][-1]['after_count'] for r in records);n=sum(r['gold_total'] for r in records);got=sum(r['stages'][-1]['gold_after'] for r in records)
  arms.append({'arm_id':arm,'declared_stage_ids':[p['stage_id'] for p in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]],'cases':records,'aggregate':{'presented_total':sum(counts),'gold_after':got,'gold_total':n}})
  totals[arm]={'cases':len(records),'error_cases':sum(bool(x['error']) for x in arows),'bounded_cases':sum((x.get('gate') or {}).get('gate')=='BOUNDED' for x in arows),'no_read_cases':sum(not x['counts'].get('read') for x in arows),'provider_429_responses':sum(x['provider_errors'].get('429',0) for x in arows),'proposal_errors':sum(len(x['session_errors']) for x in arows),'gold_obtained':got,'gold_total':n,'golden_recall':got/n,'before_filter':sum(r['stages'][0]['after_count'] for r in records),'after_filter':sum(counts),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':counts[math.ceil(.95*len(counts))-1],'selectivity':statistics.mean(counts)/corpus,'physical_calls':sum(x['physical_calls'] for x in arows),'mean_seconds':statistics.mean(x['seconds'] for x in arows if x['seconds'] is not None),'cost_usd':sum(x['cost_usd'] for x in arows),'partial_graphs':sum((x['graph'] or {}).get('status')=='PARTIAL' for x in arows),'unknown_graph_cases':sum(arm=='guarded' and not x['graph'] and (x.get('error') or {}).get('type')=='HardDeadlineExceeded' for x in arows),'gold_by_stage':{k:sum(x['gold_by_stage'].get(k,0) for x in arows) for k in ['discovered','read','presented','selected','answer','protected_originals']},'mean_counts':{k:statistics.mean(x['counts'].get(k,0) for x in arows) for k in ['discovered','read','presented','selected','answer','protected_originals']}}
 ledger={'schema_version':h.SCHEMA,'adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':h.UNIT,'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':arms}],'audit':{'presentation':'Evidence spans linked to model attempts with successful responses; article identity recall does not certify complete decisive provision delivery','protected_originals':'Local graph preservation is a separate count, never equated with delivered evidence','gold_join':'Only in this offline script after all product workers completed'}};ledger['artifact_sha256']=_canonical_value_sha256(ledger);write(A/'artifacts/retrieval-stage-ledger.json',ledger)
 summary={'totals':totals,'rows':rows,'active_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['file_hashes']['01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'],'quality_certified':False,'main_changed':False,'model':'google/gemma-4-31b-it','provider':'OpenRouter / Parasail FP8','thinking':False,'usage':{'physical_calls':sum(t['physical_calls'] for t in totals.values()),'input_tokens':sum(u.get('input_tokens') or 0 for u in all_usage),'output_tokens':sum(u.get('output_tokens') or 0 for u in all_usage),'cost_usd':sum(u.get('cost_usd') or 0 for u in all_usage)},'limitations':['Six previously observed public questions, one run per arm; not out-of-sample or statistical certification','Article-level gold recall does not certify exact paragraph/item coverage or answer correctness','No independent model/human semantic grading','Hard-killed case graph counts are unknown when no checkpoint artifact survived; mean preserved counts include only observable outputs and are not a complete corpus count','External Gemma proxy; no GENOS measurement','The two provider probes overlapped in time on one WSL host; setup and latency are descriptive, not isolated provider performance comparisons','Legacy90/90 retrieval union used a different acquisition workflow; not a comparable end-to-end baseline','Baseline retains its automatic reads and source cap; candidate changes these as designed; this is a system comparison, not isolated graph ablation']}
 write(A/'artifacts/summary.json',summary)
 decision='Deferred: provider-overload-contaminated paired probe; quality comparison is inconclusive and zero delivered recall must not be read as a causal code-regression score.' if any(t['provider_429_responses'] for t in totals.values()) else 'Deferred: six-case paired probe completed; no MAIN promotion. See errors, missed originals and partial-frontier results.'
 m['results'].update(status='complete',by_arm=totals,comparisons=[{'baseline':'baseline','candidate':'guarded','interpretation':decision}],judge_disagreements=None,usage=summary['usage'],latency={'mean_seconds':{k:t['mean_seconds'] for k,t in totals.items()}},error_taxonomy=sorted({x['error']['type'] for x in rows if x['error']}))
 m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/results.json'))
 m['gemma_binding']['live_calls']=summary['usage']['physical_calls']
 m['retrieval_accounting']={'changed':True,'corpus_total':corpus,'not_applicable_reason':None,'stage_ledger':{'mode':'measured','schema_version':h.SCHEMA,'accounting_unit':h.UNIT,'summary_run_id':'run-001','artifact_path':str((A/'artifacts/retrieval-stage-ledger.json').relative_to(R)),'sha256':sha(A/'artifacts/retrieval-stage-ledger.json'),'not_applicable_reason':None},**{key:{arm:t[key] for arm,t in totals.items()} for key in ('before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity')}}
 m['questions']=[]
 for number,c in enumerate(prod['cases'],1):
  cid=c['case_id'];filename=f'질문-{number:03d}-{cid}.md';qp=A/'실험'/filename;goldrow=gold[cid];crows=[x for x in rows if x['case_id']==cid];raw=[]
  for arm in ('baseline','guarded'):
   for p in sorted((A/'artifacts/run-001'/cid/arm/'calls').rglob('*.json')):
    raw.append(f'- {arm}: [{p.name}](../{p.relative_to(A)}) SHA256 `{sha(p)}`')
  blocks=[f'ADR0524 / run-001 / {cid}. Fresh paired Gemma execution. 원본 상태: exact.',c['question'],'```json\n'+json.dumps(goldrow,ensure_ascii=False,indent=2)+'\n```','Frozen product-cases.json, frozen-design.json and public export-rebinding.json. No gold read by product workers.','artifacts/retrieval-stage-ledger.json; article identity counts, gold joined after completion.','\n'.join(raw) or 'No physical model sends.','Planning/tool exploration/selection/compose/review and repairs are included in the raw call sequence above; no separate hidden model calls.','No evaluator model calls; deterministic source-coordinate matching only.','```json\n'+json.dumps(crows,ensure_ascii=False,indent=2)+'\n```']
  qp.write_text('# '+cid+'\n\n'+'\n\n'.join(k+'\n\n'+v for k,v in zip(QUESTION_HEADINGS_V4,blocks))+'\n');m['questions'].append({'number':number,'case_id':cid,'file':filename,'sha256':sha(qp)})
 write(A/'실험/manifest.json',m)
 (A/'실험/README.md').write_text('# Six paired Gemma cases\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in m['questions'])+'\n')
 original=(A/'README.md').read_text();front=original.split('---',2)[1]
 blocks=[decision,'The frozen ADR0522 graph candidate and corrected DB are compared with selected r3 serving code. Preflight discovered a stale fulltext binding; identical33443 indexed inputs were verified before isolated metadata rebinding. No model calls preceded that correction.',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria'],(A/'PLAN.md').read_text(),'Exact Gemma model/provider and all input/code/data/prompt/schema hashes in artifacts/frozen-design.json; public originals only.','```json\n'+json.dumps(totals,ensure_ascii=False,indent=2)+'\n```','Each question file links exact request, response, validation schema, binding, usage and SQLite journal; summary.json contains per-case errors.','```json\n'+json.dumps(summary['usage'],indent=2)+'\n```','Model-delivered originals and locally preserved originals are different measurements; no inference of performance from preservation alone.','\n'.join('- '+x for x in summary['limitations']),'MAIN unchanged. Both candidate and new data generation remain experimental. No promotion or deployment.','```bash\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0524/run_probe.py --execute\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0524/summarize.py\n```\nCompleted run directories are immutable; any repeated model execution must reserve a new ADR.']
 (A/'README.md').write_text('---'+front+'---\n\n# ADR0524 Gemma paired experiment\n\n'+'\n\n'.join(k+'\n\n'+v for k,v in zip(ADR_HEADINGS,blocks))+'\n')
 print(json.dumps(summary['totals'],ensure_ascii=False,indent=2))
if __name__=='__main__':main()
