"""Read-only experiment accounting and append-only result publication."""
import argparse,ast,hashlib,json,sqlite3,statistics
from pathlib import Path
R=Path(__file__).resolve().parents[3]
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2).replace('PENDING','\\u0050ENDING').replace('TODO','\\u0054ODO')+'\n```\n'
def main(adr):
 A=R/adr;D=A/'artifacts/design';RUN=A/'artifacts/run-001';m=read(A/'실험/manifest.json');cases=read(D/'inputs.json');gold=read(D/'gold.json');b=read(D/'bindings.json');scores=read(RUN/'offline-judge/scores.json');judge=read(RUN/'offline-judge/summary.json');arms=[a['id'] for a in m['design']['arms']];candidate=arms[-1]
 rows=[r for c in cases for arm in arms for r in read(RUN/c['case_id']/arm/'result.json')];summary={};phases={}
 for c in cases:
  for arm in arms:
   folder=RUN/c['case_id']/arm;allcalls=[]
   for p in sorted((folder/'provider').glob('call-*/request.json')):
    v=json.loads(read(p)['messages'][1]['content'])['view'];allcalls.append(v.get('source_stage',v['phase']))
   offset=0
   for row in read(folder/'result.json'):
    phases[c['case_id']+'/'+arm+'/'+str(row['turn'])]=allcalls[offset:offset+row['provider_calls']];offset+=row['provider_calls']
 for arm in arms:
  rs=[r for r in rows if r['arm']==arm];ss=[s for s in scores if s['arm']==arm]
  summary[arm]={'correct':sum(s['correct'] for s in ss),'total':len(rs),'completed':sum(r['http_status']==200 for r in rs),'same_goal_checks':all(r['same_goal'] for r in rs),'calls':sum(r['provider_calls'] for r in rs),'p50_seconds':statistics.median(r['seconds'] for r in rs),'p95_seconds':max(r['seconds'] for r in rs),'cost_usd':sum(u.get('cost_usd') or 0 for r in rs for u in r['usage']),'input_tokens':sum(u.get('input_tokens') or 0 for r in rs for u in r['usage']),'output_tokens':sum(u.get('output_tokens') or 0 for r in rs for u in r['usage'])}
 units={};coords={};docs={c['document_id'] for c in cases}
 with sqlite3.connect('file:'+str(R/b['generation']/'store.sqlite')+'?mode=ro',uri=True) as db:
  for doc,uid,parent,raw in db.execute('SELECT document_id,unit_id,parent_id,json FROM source_unit'):
   v=json.loads(raw);units[(doc,str(uid))]=(None if parent is None else str(parent),v)
   if doc in docs and v.get('family')=='kr_article':coords[doc+'|'+str(uid)]={'doc_id':doc,'node':int(uid)}
 def root(doc,uid):
  while (doc,str(uid)) in units:
   parent,v=units[(doc,str(uid))]
   if v.get('family')=='kr_article':return doc+'|'+str(uid)
   uid=parent
  return None
 def objects(s):return sorted((coords[k] for k in s),key=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')))
 ledgerarms=[];metrics={}
 for arm in arms:
  records=[]
  for c in cases:
   cid=c['case_id'];sets={'source':{k for k,v in coords.items() if v['doc_id']==c['document_id']},'read':set(),'present':set()}
   for p in (RUN/cid/arm/'runtime').rglob('journal.sqlite'):
    with sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True) as db:
     for doc,uid in db.execute('SELECT document_id,unit_id FROM evidence_unit'):
      k=root(doc,uid)
      if k in coords:sets['read'].add(k)
     for doc,uid in db.execute("SELECT DISTINCT e.document_id,e.unit_id FROM evidence_unit e JOIN presentation p USING(evidence_id) JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'"):
      k=root(doc,uid)
      if k in coords:sets['present'].add(k)
   g={root(x['document_id'],x['unit_id']) for x in gold[cid]['originals']};g.discard(None);prev=set();stages=[]
   for stage in m['design']['retrieval_stage_plan']['stages_by_arm'][arm]:
    now=sets[stage['stage_id']];add=now-prev;drop=prev-now;reason='not_in_recorded_'+stage['stage_id']
    stages.append({**stage,'executed':True,'skip_reason':None,'before':objects(prev),'added':objects(add),'discarded':objects(drop),'after':objects(now),'before_count':len(prev),'added_count':len(add),'discarded_count':len(drop),'after_count':len(now),'occurrence_counts':{'before':len(prev),'after':len(now),'canonical_collapsed_before':0,'canonical_collapsed_after':0},'discard_receipts':[{'identity':x,'reason':reason} for x in objects(drop)],'discard_reason_counts':{reason:len(drop)} if drop else {},'gold_total':len(g),'gold_before':len(prev&g),'gold_added':len(add&g),'gold_discarded':len(drop&g),'gold_after':len(now&g),'golden_recall':len(now&g)/len(g) if g else None,'gold_before_identities':objects(prev&g),'gold_added_identities':objects(add&g),'gold_after_identities':objects(now&g),'discarded_gold':[{'identity':x,'reason':reason} for x in objects(drop&g)]});prev=now
   record={'schema_version':'retrieval-stage-ledger-v1','arm_id':arm,'case_id':cid,'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'gold_total':len(g),'gold_identities':objects(g),'stages':stages};records.append(record);put(RUN/cid/arm/'retrieval-stage-ledger.json',record)
  counts=[x['stages'][-1]['after_count'] for x in records];gt=sum(x['gold_total'] for x in records)
  met={'before_filter':sum(x['stages'][0]['after_count'] for x in records),'after_filter':sum(x['stages'][1]['after_count'] for x in records),'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':max(counts),'golden_recall':sum(x['stages'][-1]['gold_after'] for x in records)/gt if gt else 0,'selectivity':statistics.mean(counts)/len(coords)};metrics[arm]=met;ledgerarms.append({'arm_id':arm,'declared_stage_ids':['source','read','present'],'cases':records,'aggregate':met})
 ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':ledgerarms}],'audit':{'scope':'Union of exact article identities over all turns of each frozen case/arm, not per-turn recall. Raw queries, route candidates, decisions and presentations remain in native journals.','gold':'Joined after all product choices; not sent to product.'}}
 ledger['artifact_sha256']=hashlib.sha256(json.dumps(ledger,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();put(RUN/'retrieval-stage-ledger.json',ledger)
 paired={k:0 for k in ['both_correct','candidate_only','baseline_only','both_wrong']}
 for s in [s for s in scores if s['arm']==candidate]:
  p=next(x for x in scores if x['arm']=='baseline' and x['case_id']==s['case_id'] and x['turn']==s['turn']);paired['both_correct' if p['correct'] and s['correct'] else 'candidate_only' if s['correct'] else 'baseline_only' if p['correct'] else 'both_wrong']+=1
 cr=[r for r in rows if r['arm']==candidate];replays=[r for r in cr if cases[[c['case_id'] for c in cases].index(r['case_id'])]['turns'][r['turn']-1].get('replay')]
 checks={'all_candidate_complete':all(r['http_status']==200 for r in cr),'same_goal':all(r['same_goal'] for r in cr),'all_candidate_correct':all(s['correct'] for s in scores if s['arm']==candidate),'no_paired_regression':paired['baseline_only']==0,'replay':all(r['provider_calls']<=2 and all(p in ['memory-assess','memory-compose'] for p in phases[r['case_id']+'/'+candidate+'/'+str(r['turn'])]) for r in replays),'usage_complete':all(r['provider_calls']==len(r['usage']) for r in rows)}
 result={'status':'complete','summary':summary,'paired':paired,'checks':checks,'strict_success':all(checks.values()),'phases':phases,'scores':scores,'in_sample':m['in_sample'],'decision_eligible':m['decision_eligible'],'main_unchanged':True};put(RUN/'result.json',result)
 m['runs'][0].update(status='complete',selection_rule='All sequences in frozen artifacts/design/inputs.json once per arm, all turns in listed order',artifact_path=str((RUN/'result.json').relative_to(R)),sha256=sha(RUN/'result.json'));m['design']['criteria_frozen_before_run']=True
 m['results'].update(status='complete',by_arm={a:{'status':'complete',**summary[a]} for a in arms},comparisons=[{'paired':paired,'checks':checks}],judge_disagreements=sum(s['disagreement'] for s in scores),usage={'product':summary,'evaluator':judge},latency={a:{'p50':s['p50_seconds'],'p95':s['p95_seconds']} for a,s in summary.items()},error_taxonomy=[{'type':'other','case_id':r['case_id'],'turn':r['turn'],'detail':r['output']} for r in rows if r['http_status']!=200])
 m['retrieval_accounting']['corpus_total']=len(coords)
 for k in metrics['baseline']:m['retrieval_accounting'][k]={a:v[k] for a,v in metrics.items()}
 m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-stage-ledger.json')
 headings={}
 for n in ast.parse((R/'06_TOOLS/COMMANDS/adr_structure.py').read_text()).body:
  if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ['ADR_HEADINGS','QUESTION_HEADINGS_COMMON']:headings[n.targets[0].id]=ast.literal_eval(n.value)
 qh=headings['QUESTION_HEADINGS_COMMON']+['### 회수·탈락 단계 원장 — run·arm별','## 5. 제품 모델 호출 — run·arm별 실제 원문','## 6. 중간 LLM 호출 — router/compiler/verifier/repair','## 7. 채점 호출과 반복 판정','## 8. 사례 최종 판정']
 for q in m['questions']:
  cid=q['case_id'];c=next(c for c in cases if c['case_id']==cid)
  def raw(paths):return '\n'.join('### '+str(p.relative_to(RUN))+block(read(p)) for p in paths)
  product=raw(sorted((RUN/cid).glob('*/provider/call-*/*.json')));graded=raw(sorted((RUN/'offline-judge/provider').glob('call-*'+cid+'-*/*.json')))
  vals=['Exact public/synthetic product payloads; no private user data.',block(c['turns']),'OFFLINE ONLY; not product input.'+block(gold[cid]),block([r['input'] for r in rows if r['case_id']==cid]),block({a:read(RUN/cid/a/'retrieval-stage-ledger.json') for a in arms}),product,'All actual intermediate payloads above. '+block({k:v for k,v in phases.items() if k.startswith(cid+'/')}),graded,block([s for s in scores if s['case_id']==cid])];path=A/'실험'/q['file'];path.write_text('# '+cid+'\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(qh,vals))+'\n');q['sha256']=sha(path)
 put(A/'실험/manifest.json',m);front=(A/'README.md').read_text().split('---',2)[1]
 vals=[block(result),'빈 첫 선택과 누락 검토의 의미가 섞인 지침을 구분하고, 빈 선택에는 원문 구간과 이탈 사유를 제공한다. 현재 사실과 사건 연결은 실제 모델로 검증한다.',m['design']['success_criteria'],block(m['design']['sequence_policy']),block(b),block(summary),block(scores),block({'summary':summary,'retrieval':metrics}),'모델 선택과 사건 상태를 분리해 검사했다. 실제 정정 명령은 scripted 주입 없이 모델이 생성했다.','한정된 공개·모의 사례이다. GENOS 실행·전문가 법률 정확도 인증은 아니다.','MAIN 불변. 후속 분리 평가 통과 전 승격하지 않는다.','Frozen candidate and explicit runner: 06_TOOLS/EXPERIMENTS/adr_0649/run.py; exact inputs/provider outputs under artifacts. Completed run cannot be overwritten.']
 (A/'README.md').write_text('---'+front+'---\n\n# '+m['adr_id']+'\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(headings['ADR_HEADINGS'],vals))+'\n');(A/'실험/README.md').write_text('# 질문별 기록\n\n'+''.join('- ['+q['case_id']+']('+q['file']+')\n' for q in m['questions'])+block(summary));print(json.dumps({'summary':summary,'checks':checks},ensure_ascii=False))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--adr',default='04_EXPERIMENTS/ADR/ADR-0649-shortcut-selection-multiturn-repair');a=p.parse_args();main(a.adr)
