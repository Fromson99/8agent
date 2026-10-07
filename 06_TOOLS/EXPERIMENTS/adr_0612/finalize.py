"""Package exact product/model evidence and unchanged frozen scores."""
import hashlib,json,sqlite3,statistics,sys
from pathlib import Path
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0612-cm-memory-bounded-recovery';D=A/'artifacts/design';run=A/'artifacts/run-001'
HEADINGS=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
QHEAD=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def block(x):return '```json\n'+json.dumps(x,ensure_ascii=False,indent=2).replace('PENDING','\\u0050ENDING').replace('TODO','\\u0054ODO')+'\n```'
def percentile(v,q):return sorted(v)[round(q*(len(v)-1))] if v else None

def ledger(result,m):
 coords={x['source_id']:{'doc_id':x['doc_id'],'node':x['node']} for x in read(D/'source-coordinates.json')};gold=read(D/'gold.json');allarms=[];flat={};audit=[]
 def ids(xs):return sorted([coords[s] for s in set(xs)],key=lambda x:(x['doc_id'],x['node']))
 for arm,product in result['arms'].items():
  db=sqlite3.connect('file:'+str(run/arm/'memory.sqlite')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;cases=[];counts=[];hits=goldsum=bf=af=0
  plans=m['design']['retrieval_stage_plan']['stages_by_arm'][arm]
  for case in product['products']:
   cid=case['case_id'];o=case['turns'][-1]['output'];route=None;parts={};trace={s['stage_id']:set() for s in plans}
   if o.get('status') in ('READY','REUSED','STORED') and o.get('goal_id'):
    route=db.execute('SELECT * FROM route WHERE goal=? AND revision=?',(o['goal_id'],o['revision'])).fetchone()
   if route:
    for stage,nid in json.loads(route['payload'])['nodes'].items():
     n=db.execute('SELECT * FROM node WHERE id=?',(nid,)).fetchone();assert n['goal']==o['goal_id'];parts[stage]=json.loads(n['payload'])
    state=json.loads(route['payload'])['state'];source=set(parts['RECALL']['corpus_ids'])&coords.keys();scope={s for s in source if coords[s]['doc_id'] in state['document_ids']}
    trace.update(source=source,scope=scope,query=set(parts['RECALL']['selected_for_read']),selected=set(parts['SELECT']['final_ids']),present={x['source_id'] for x in (o.get('answer') or {}).get('claims',[])})
    assert all(v<=coords.keys() for v in trace.values())
   gs=set(gold[cid]['decisive_source_ids']);assert gs<=coords.keys();prev=set();stages=[]
   for p in plans:
    after=trace[p['stage_id']];before=prev;added=after-before;discarded=before-after;reason='outside_request_scope' if p['stage_id']=='scope' else 'not_selected_or_presented'
    stages.append({**p,'executed':bool(route),'skip_reason':None if route else 'No final consumed source route','before':ids(before),'added':ids(added),'discarded':ids(discarded),'after':ids(after),'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},'discard_receipts':[{'identity':i,'reason':reason} for i in ids(discarded)],'discard_reason_counts':{reason:len(discarded)} if discarded else {},'gold_total':len(gs),'gold_before':len(before&gs),'gold_added':len(added&gs),'gold_discarded':len(discarded&gs),'gold_after':len(after&gs),'golden_recall':len(after&gs)/len(gs),'gold_before_identities':ids(before&gs),'gold_added_identities':ids(added&gs),'gold_after_identities':ids(after&gs),'discarded_gold':[{'identity':i,'reason':reason} for i in ids(discarded&gs)]});prev=after
   cases.append({'schema_version':'retrieval-stage-ledger-v1','arm_id':arm,'case_id':cid,'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'gold_total':len(gs),'gold_identities':ids(gs),'stages':stages})
   counts.append(len(prev));hits+=len(prev&gs);goldsum+=len(gs);bf+=len(trace['source']);af+=len(trace['query']);audit.append({'arm':arm,'case_id':cid,'final_status':o.get('status'),'goal':o.get('goal_id'),'revision':o.get('revision'),'route':route['id'] if route else None})
  db.close();agg={'before_filter':bf,'after_filter':af,'presented_total':sum(counts),'presented_mean':statistics.mean(counts),'presented_p50':statistics.median(counts),'presented_p95':percentile(counts,.95),'golden_recall':hits/goldsum,'selectivity':statistics.mean(counts)/len(coords)};flat[arm]=agg;allarms.append({'arm_id':arm,'declared_stage_ids':[p['stage_id'] for p in plans],'cases':cases,'aggregate':agg})
 out={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':allarms}],'audit':{'bindings':audit,'scope':'Source universe is actual loaded corpus intersected with verified public authorization; scope applies current request document IDs. Native work DB and raw calls retain each turn. Aggregate is final consumption, not every-turn recall or search effectiveness.','coordinate_map_path':str((D/'source-coordinates.json').relative_to(R))}}
 out['artifact_sha256']=hashlib.sha256(json.dumps(out,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();put(run/'retrieval-stage-ledger.json',out);return out,flat

def main():
 r=read(run/'result.json');mp=A/'실험/manifest.json';m=read(mp);led,metrics=ledger(r,m);inputs=read(D/'inputs.json');gold=read(D/'gold.json');byarm={};allusage=[]
 for arm,product in r['arms'].items():
  legal=[x for x in r['semantic'] if x['arm']==arm and x['kind']=='legal'];history=[x for x in r['semantic'] if x['arm']==arm and x['kind']=='history'];turns=[t for c in product['products'] for t in c['turns']];usage=product['summary']['usage'];allusage+=usage
  byarm[arm]={'functional_passed':r['functional'][arm]['passed'],'functional_total':r['functional'][arm]['total'],'legal_correct':sum(x['verdict']['correct'] for x in legal),'legal_total':len(legal),'history_correct':sum(x['verdict']['correct'] for x in history),'history_total':len(history),'completed_turns':sum(t['output'].get('status') in ('READY','REUSED','STORED') for t in turns),'turns':len(turns),'calls':len(usage),'cost_usd':sum(x.get('cost_usd',0) or 0 for x in usage),'input_tokens':sum(x['input_tokens'] for x in usage),'output_tokens':sum(x['output_tokens'] for x in usage),'latency':product['summary']['latency_seconds']}
  for k,v in metrics[arm].items():m['retrieval_accounting'][k][arm]=v
 comparisons={kind:{'guarded_only':sum(x['guarded'] and not x['baseline'] for x in r['pairs'] if x['kind']==kind),'baseline_only':sum(x['baseline'] and not x['guarded'] for x in r['pairs'] if x['kind']==kind),'both_correct':sum(x['baseline'] and x['guarded'] for x in r['pairs'] if x['kind']==kind),'both_wrong':sum(not x['baseline'] and not x['guarded'] for x in r['pairs'] if x['kind']==kind)} for kind in ('legal','history')}
 allusage+=r['judge_usage'];m['results'].update(status='complete',by_arm=byarm,comparisons=[{'metric':k,**v} for k,v in comparisons.items()],judge_disagreements=0,usage={'calls':len(allusage),'cost_usd':sum(x.get('cost_usd',0) or 0 for x in allusage),'input_tokens':sum(x['input_tokens'] for x in allusage),'output_tokens':sum(x['output_tokens'] for x in allusage),'judge_calls':len(r['judge_usage'])},latency={a:v['latency'] for a,v in byarm.items()},error_taxonomy=[{'type':'other','arm':a,'checkpoint':c} for a,g in r['functional'].items() for c in g['checks'] if not c['pass']])
 m['retrieval_accounting']['stage_ledger']['sha256']=sha(run/'retrieval-stage-ledger.json');m['runs'][0].update(status='complete',artifact_path=str((run/'result.json').relative_to(R)),sha256=sha(run/'result.json'))
 for q in m['questions']:
  cid=q['case_id'];raw=[];caseproducts={a:next(c for c in p['products'] if c['case_id']==cid) for a,p in r['arms'].items()}
  for arm,case in caseproducts.items():
   for folder in sorted((run/arm/'provider').glob('call-*')):
    n=int(folder.name.split('-')[1])
    if not any(t['provider_attempt_start']<=n<=t['provider_attempt_end'] for t in case['turns']):continue
    raw.append('### '+arm+'/'+folder.name)
    for name in ('request.json','validation-schema.json','binding.json','response.json','output.json','error.json'):
     p=folder/name
     if p.exists():raw.extend(['#### '+name,block(read(p))])
  judges=[]
  for folder in sorted((run/'offline-judge').glob('call-*')):
   if cid not in folder.name:continue
   for p in sorted(folder.glob('*.json')):judges.extend(['### '+folder.name+'/'+p.name,block(read(p))])
  vals=[m['experiment_id']+'; run-001; both arms; actual Qwen3.8; public stored CM sources',block(next(c for c in inputs if c['case_id']==cid)),block(gold[cid]),block(caseproducts)+'\n\n### 회수·탈락 단계 원장 — run·arm별\n\n'+block({a:[c for ar in led['runs'][0]['arms'] if ar['arm_id']==a for c in ar['cases'] if c['case_id']==cid] for a in caseproducts}),'\n\n'.join(raw),'The raw calls above include all resolver/check/repair/intent/source/assessment/compose inputs and outputs.','\n\n'.join(judges),block({'functional':{a:[c for c in g['checks'] if c['case_id']==cid] for a,g in r['functional'].items()},'semantic':[x for x in r['semantic'] if x['case_id']==cid]})]
  (A/'실험'/q['file']).write_text('# '+cid+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(QHEAD,vals),1))+'\n')
 summary=block(byarm);vals=[summary,'ADR0611 showed unbounded resolver queries causing truncation, exclusive named-law scope missing bylaws, rejected quotes without ASSESS recovery, and scope drift blocking reuse. The completed GUARDED snapshot is the exact baseline.',m['design']['hypothesis']+'\n\n'+m['design']['success_criteria'],'Same19 turns per arm; two actual CM base questions; concurrent isolated BASELINE and RECOVERED runs, sequential turns within each arm. Registered memory method scope is distinct from full legal ontology control.',block({'source_binding':str((D/'source-binding.json').relative_to(R)),'source_generation':read(D/'source-binding.json')['generation'],'public_documents':145,'model':'qwen/qwen3.8-27b','actual_temperature':0,'provider':'Parasail FP8','reasoning':'none','fallback':False}),summary+'\n\n'+block(comparisons),block([x for x in r['semantic'] if not x['verdict']['correct']]),block({'usage':m['results']['usage'],'retrieval':metrics,'latency':m['results']['latency']}),'Functional lifecycle, source retrieval, legal agreement and history accuracy are reported separately. No score changed after outcomes.','Two known CM cases, one run, same model as product and offline judge. Not full CM evaluation, current-law certification or GENOS result. Both frozen criteria and gold specify two reuse turns and four restoration pairs per arm. Confirmed-experience retention checks target the current bundle rather than any unrelated active experience.','Research-only candidate; MAIN, source flags, production registry and GENOS unchanged. Disable explicit candidate injection to return to parent.','Use frozen run.py --arm BASELINE/RECOVERED only under a new ADR reservation; existing run paths refuse overwrite. grade.py reads gold only after both arms complete.']
 front=(A/'README.md').read_text().split('---',2)[1];(A/'README.md').write_text('---'+front+'---\n\n# ADR-0612 — CM actual memory repair experiment\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(HEADINGS,vals),1))+'\n')
 (A/'실험/README.md').write_text('# 질문 인덱스\n\n'+''.join(f"- [{q['case_id']}]({q['file']})\n" for q in m['questions']));put(mp,m);put(run/'evidence-summary.json',{'by_arm':byarm,'comparisons':comparisons,'usage':m['results']['usage'],'scores_unchanged':True});print(json.dumps({'by_arm':byarm,'comparisons':comparisons},ensure_ascii=False))
if __name__=='__main__':main()
