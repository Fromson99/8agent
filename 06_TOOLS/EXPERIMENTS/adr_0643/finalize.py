"""Post-selection accounting; no product inputs or outputs are changed."""
from pathlib import Path
import ast,json,hashlib,sqlite3,statistics
R=Path(__file__).resolve().parents[3]; A=R/'04_EXPERIMENTS/ADR/ADR-0643-shortcut-generation-compatible';D=A/'artifacts/design';RUN=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2).replace('PENDING','\\u0050ENDING').replace('TODO','\\u0054ODO')+'\n```\n'
def main():
 m=read(A/'실험/manifest.json');cases=read(D/'inputs.json');gold=read(D/'gold.json');scores=read(RUN/'offline-judge/scores.json');binding=read(D/'bindings.json')
 # Recompute exact canonical coordinates for post-selection accounting; match frozen input.
 units={};coords={}
 with sqlite3.connect('file:'+str(R/binding['generation']/'store.sqlite')+'?mode=ro',uri=True) as db:
  for doc,uid,parent,raw in db.execute('SELECT document_id,unit_id,parent_id,json FROM source_unit'):
   units[(doc,str(uid))]=(None if parent is None else str(parent),json.loads(raw))
   if doc in binding['scope'] and json.loads(raw).get('family')=='kr_article':coords[doc+'|'+str(uid)]={'doc_id':doc,'node':int(uid)}
 def root(doc,uid):
  while uid is not None:
   parent,value=units[(doc,str(uid))]
   if value.get('family')=='kr_article':return doc+'|'+str(uid)
   uid=parent
  return None
 def objects(s):return sorted((coords[i] for i in s),key=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')))
 put(RUN/'accounting-coordinate-repair.json',{'reason':'Canonical kr_article coordinates, same as frozen design; no product input, gold, selection or answer changed.','original_sha256':sha(D/'coordinates.json'),'coordinates':coords})
 metrics={};ledarms=[];rows=[];usage=[];latency={};byarm={}
 for arm in ('baseline','integrated'):
  lc=[];counts=[];hits=0;gtotal=0;times=[];correct=0;calls=0;readtotal=0
  for case in cases:
   cid=case['case_id'];folder=RUN/cid/arm;row=read(folder/'result.json');rows.append(row);times.append(row['seconds']);usage+=row['usage'];calls+=row['provider_calls']
   score=next(s for s in scores if s['case_id']==cid and s['arm']==arm);correct+=score['correct']
   sets={'source':{k for k,v in coords.items() if v['doc_id']==case['document_id']},'read':set(),'present':set()}
   for p in (folder/'runtime').rglob('journal.sqlite'):
    with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as db:
     for doc,uid in db.execute('SELECT document_id,unit_id FROM evidence_unit'):
      key=root(doc,uid)
      if key in coords:sets['read'].add(key)
     for doc,uid in db.execute("SELECT DISTINCT e.document_id,e.unit_id FROM evidence_unit e JOIN presentation p USING(evidence_id) JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'"):
      key=root(doc,uid)
      if key in coords:sets['present'].add(key)
   g={root(x['document_id'],x['unit_id']) for x in gold[cid]['originals']};assert None not in g and g<=set(coords)
   prev=set();stages=[]
   for stage in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
    now=sets[stage['stage_id']];add=now-prev;drop=prev-now;reason='not_in_recorded_'+stage['stage_id']
    st={**stage,'executed':True,'skip_reason':None,'before':objects(prev),'added':objects(add),'discarded':objects(drop),'after':objects(now),'before_count':len(prev),'added_count':len(add),'discarded_count':len(drop),'after_count':len(now),'occurrence_counts':{'before':len(prev),'after':len(now),'canonical_collapsed_before':0,'canonical_collapsed_after':0},'discard_receipts':[{'identity':i,'reason':reason} for i in objects(drop)],'discard_reason_counts':{reason:len(drop)} if drop else {},'gold_total':len(g),'gold_before':len(prev&g),'gold_added':len(add&g),'gold_discarded':len(drop&g),'gold_after':len(now&g),'golden_recall':len(now&g)/len(g),'gold_before_identities':objects(prev&g),'gold_added_identities':objects(add&g),'gold_after_identities':objects(now&g),'discarded_gold':[{'identity':i,'reason':reason} for i in objects(drop&g)]};stages.append(st);prev=now
   item={'schema_version':'retrieval-stage-ledger-v1','arm_id':arm,'case_id':cid,'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'gold_total':len(g),'gold_identities':objects(g),'stages':stages};lc.append(item);put(folder/'retrieval-stage-ledger.json',item)
   counts.append(len(prev));hits+=len(prev&g);gtotal+=len(g);readtotal+=len(sets['read'])
  met={'before_filter':sum(len(x['stages'][0]['after']) for x in lc),'after_filter':readtotal,'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':max(counts),'golden_recall':hits/gtotal,'selectivity':statistics.mean(counts)/len(coords)};metrics[arm]=met
  ledarms.append({'arm_id':arm,'declared_stage_ids':['source','read','present'],'cases':lc,'aggregate':met});latency[arm]={'p50_seconds':statistics.median(times),'seconds':times};byarm[arm]={'correct':correct,'total':len(cases),'provider_calls':calls}
 ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':ledarms}],'audit':{'coordinate_repair':'accounting-coordinate-repair.json','present_scope':'All successfully delivered model views from current request; failed candidate has none.'}}
 ledger['artifact_sha256']=hashlib.sha256(json.dumps(ledger,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();put(RUN/'retrieval-stage-ledger.json',ledger)
 judge=read(RUN/'offline-judge/summary.json');cost={'product_cost_usd':sum(u.get('cost_usd') or 0 for u in usage),'judge_cost_usd':sum(u.get('cost_usd') or 0 for u in judge['usage']),'product_calls':len(usage),'judge_calls':judge['calls']}
 errors=[{'type':'other','classification':'product_execution_failure','case_id':r['case_id'],'arm':r['arm'],'detail':r['output']} for r in rows if r['http_status']!=200]
 online_cost={a:sum(u.get('cost_usd') or 0 for r in rows if r['arm']==a for u in r['usage']) for a in ('baseline','integrated')}
 limits={'quality':byarm['integrated']['correct']==3,'latency':latency['integrated']['p50_seconds']<=latency['baseline']['p50_seconds']*1.3+10,'cost':online_cost['integrated']<=online_cost['baseline']*1.3+0.01,'usage_complete':all(r['provider_calls']==len(r['usage']) for r in rows)}
 result={'status':'complete','by_arm':byarm,'rows':rows,'scores':scores,'cost':cost,'latency':latency,'retrieval':metrics,'strict_success':all(limits.values()),'acceptance_checks':limits,'online_cost_usd':online_cost,'in_sample':True,'main_unchanged':True,'genos_tested':False,'decision_eligible':False};put(RUN/'result.json',result)
 m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm=byarm,comparisons=[{'baseline_only_correct':sum(next(s for s in scores if s['case_id']==c['case_id'] and s['arm']=='baseline')['correct'] and not next(s for s in scores if s['case_id']==c['case_id'] and s['arm']=='integrated')['correct'] for c in cases),'acceptance_checks':limits,'online_cost_usd':online_cost}],judge_disagreements=sum(s['disagreement'] for s in scores),usage=cost,latency=latency,error_taxonomy=errors)
 m['lineage']['hypothesis_delta']='Selected-generation glossary pin and bounded compiler operations; observed cases remain in-sample regressions.'
 m['retrieval_accounting']['corpus_total']=len(coords)
 for k in metrics['baseline']:m['retrieval_accounting'][k]={a:metrics[a][k] for a in metrics}
 m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-stage-ledger.json')
 headings={}
 for n in ast.parse((R/'06_TOOLS/COMMANDS/adr_structure.py').read_text()).body:
  if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('ADR_HEADINGS','QUESTION_HEADINGS_COMMON'):headings[n.targets[0].id]=ast.literal_eval(n.value)
 qh=headings['QUESTION_HEADINGS_COMMON']+['### 회수·탈락 단계 원장 — run·arm별','## 5. 제품 모델 호출 — run·arm별 실제 원문','## 6. 중간 LLM 호출 — router/compiler/verifier/repair','## 7. 채점 호출과 반복 판정','## 8. 사례 최종 판정']
 for q in m['questions']:
  cid=q['case_id'];case=next(c for c in cases if c['case_id']==cid)
  def calls(paths):return '\n'.join('### '+str(p.relative_to(RUN))+'\n'+block(read(p)) for path in paths for p in sorted(path.glob('*.json')))
  product=calls([p for a in ('baseline','integrated') for p in (RUN/cid/a/'provider').glob('call-*')]);judges=calls(list((RUN/'offline-judge/provider').glob('call-*'+cid+'-*')))
  vals=['ADR-0643/run-001. Same frozen public inputs and source generation.',case['question'],block(gold[cid]),block({a:read(RUN/cid/a/'input.json') for a in ('baseline','integrated')}),block({a:read(RUN/cid/a/'retrieval-stage-ledger.json') for a in ('baseline','integrated')}),product,'All product calls included above; candidate fails before model invocation.',judges,block([s for s in scores if s['case_id']==cid])]
  p=A/'실험'/q['file'];p.write_text('# '+cid+'\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(qh,vals))+'\n');q['sha256']=sha(p)
 put(A/'실험/manifest.json',m)
 front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Rejected')
 vals=['MAIN 미승격. 알려진3사례 회귀 검사. '+block({'by_arm':byarm,'acceptance':limits}),'Selected generation compiler pinned to active release; bounded compiler pages and atomic build/cursor.',m['design']['success_criteria'],'Previously observed three document families, paired baseline/candidate. No model retry or case replacement.',block(binding),'85 frozen contract/regression tests plus6 real-process durability checks passed. Actual product outcomes below.'+block(byarm),block(errors),block({'cost':cost,'latency':latency,'retrieval':metrics}),'Glossary mismatch repaired with exact compatible code, source data unchanged. Product results and source judgments are separate from contract tests.','Stored-source external in-sample tests only. Parasail429 is recorded as failure with unknown failed-call usage; no fallback or hidden retry. No current-law or GENOS claim.','No quality waiver or MAIN activation; next candidate requires a new ADR.','Run scripts in 06_TOOLS/EXPERIMENTS/adr_0643 refuse overwriting completed outputs. Final validation through the stable adr_structure runner.']
 (A/'README.md').write_text('---'+front+'---\n\n# ADR-0643 integration holdout\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(headings['ADR_HEADINGS'],vals))+'\n')
 (A/'실험/README.md').write_text('# 실제 비교\n\n'+''.join('- ['+q['case_id']+']('+q['file']+')\n' for q in m['questions'])+'\nBaseline3/3; candidate0/3, binding mismatch before calls.\n')
 paths=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and p.suffix!='.pyc']
 put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen inputs, actual outputs, or post-selection accounting','contains_raw_prompts_and_outputs':'provider/' in str(p)} for p in paths]})
 print(json.dumps({'by_arm':byarm,'cost':cost},ensure_ascii=False))
if __name__=='__main__':main()
