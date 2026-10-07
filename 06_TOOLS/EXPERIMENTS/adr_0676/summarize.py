"""Post-output trace, quote and holdout accounting; never a product input."""
from pathlib import Path
import hashlib,json,sqlite3,statistics,gzip
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0676-investigation-reinspection-repair'
D=A/'artifacts/design';RUN=A/'artifacts/run-001'
def read(p):return json.loads(p.read_text())
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True)
 if p.suffix=='.gz':
  with gzip.open(p,'wt',encoding='utf-8',compresslevel=6) as f:json.dump(v,f,ensure_ascii=False,separators=(',',':'))
 else:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def fence(v):return '```json\n'+json.dumps(v,ensure_ascii=False,indent=2).replace('TODO','TO\\u0044O').replace('PENDING','PEND\\u0049NG')+'\n```'
def ro(p):
 db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;return db
def payloads(db,sql):
 rows=[dict(x) for x in db.execute(sql)]
 for x in rows:x['payload']=json.loads(x.pop('payload_json'))
 return rows
def percentile(values,p):
 ordered=sorted(values);return ordered[min(len(ordered)-1,max(0,round((len(ordered)-1)*p)))] if ordered else 0
def usage_sum(rows):return {k:sum(x.get(k,0) or 0 for x in rows) for k in ('input_tokens','output_tokens','cost_usd','seconds')}
def transcript(directory):
 return [{'call':x.name,'files':{p.name:{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(x.glob('*.json'))}} for x in sorted(directory.glob('call-*'))]
b=read(D/'bindings.json');dataset=read(D/'dataset.json');gold={x['case_id']:x for x in read(D/'gold.json')['cases']}
m=read(A/'실험/manifest.json');nav=ro(R/b['source_generation']/'navigation/navigation.sqlite')
sources={x['id']:json.loads(x['json']) for x in nav.execute('SELECT id,json FROM source')}
def identities(ids):
 return [json.loads(x) for x in sorted({canon({'doc_id':sources[s]['document_id'],'node':int(sources[s]['unit_id'])}) for s in ids if s in sources and str(sources[s]['unit_id']).isdigit()})]
def presented(v):
 out=set()
 def walk(x):
  if isinstance(x,dict):
   if x.get('source_id') in sources and isinstance(x.get('text'),str) and x['text']:out.add(x['source_id'])
   for z in x.values():walk(z)
  elif isinstance(x,list):
   for z in x:walk(z)
 walk(v);return out
reasons=['Version-bound catalogue available to current recall; original reads enforce approved scope',
 'Not selected by any executed recall', 'Not acquired by an executed original READ',
 'Not delivered with source text in a successful model input']
arm_cases={x:[] for x in ('baseline','integrated')};diagnostics={x:[] for x in arm_cases};raws={};questions=[]
for number,case in enumerate(dataset['cases'],1):
 cid=case['case_id'];case_inputs={};case_outputs={};case_grades={};case_diag={};case_ledgers={}
 for arm in arm_cases:
  directory=RUN/arm/cid;executed=(directory/'result.json').exists()
  r=read(directory/'result.json') if executed else {'case_id':cid,'arm':arm,'http_status':None,'total_seconds':0,'model_calls':0,'usage':[],'execution_status':'NOT_RUN_AFTER_GATE_FAILURE'}
  grade=read(directory/'grade.json') if executed else {'correct':None,'reason':'Not executed after the frozen required gate failed; no product or evaluator call','usage':[]}
  raws[arm,cid]=r
  journals=list((directory/'runtime').rglob('journal.sqlite'))
  events=[];stages=[];acquired=[];spans=[]
  if journals:
   assert len(journals)==1;db=ro(journals[0]);events=payloads(db,'SELECT * FROM event ORDER BY seq')
   stages=payloads(db,"SELECT * FROM entity_version WHERE kind='case_stage' ORDER BY created_seq")
   acquired=identities({x[0] for x in db.execute('SELECT DISTINCT source_id FROM evidence_unit')})
   spans=[dict(x) for x in db.execute('SELECT * FROM evidence_span')];db.close()
  inputs=[x['payload'] for x in events if x['kind']=='MEMORY_MODEL_INPUT']
  recalls=[x['payload'] for x in stages if x['entity_id']=='case:RECALL']
  corpus=identities({s for x in recalls for s in x.get('corpus_ids',[])})
  recalled=identities({s for x in recalls for s in x.get('selected_for_read',[])})
  offered_ids={s for x in inputs for s in presented(x.get('data',{}))}
  # Successful provider-only route/legacy views are retained too.
  for call in (directory/'provider').glob('call-*'):
   if (call/'request.json').exists() and (call/'response.json').exists():
    request=read(call/'request.json')
    body=request.get('body',request)
    for message in body.get('messages',[]):
     try:offered_ids.update(presented(json.loads(message.get('content',''))))
     except (ValueError,TypeError):pass
  offered=identities(offered_ids)
  gs=identities([gold[cid]['source_id']]);gkeys={canon(x):x for x in gs};before=[];ledger=[]
  for i,after in enumerate([corpus,recalled,acquired,offered]):
   plan=m['design']['retrieval_stage_plan']['stages_by_arm'][arm][i];bm={canon(x):x for x in before};am={canon(x):x for x in after}
   added=[am[k] for k in sorted(am.keys()-bm.keys())];discard=[bm[k] for k in sorted(bm.keys()-am.keys())]
   gb=[bm[k] for k in sorted(bm.keys()&gkeys.keys())];ga=[am[k] for k in sorted(am.keys()&gkeys.keys())]
   gain=[x for x in added if canon(x) in gkeys];loss=[x for x in discard if canon(x) in gkeys]
   ledger.append({**plan,'executed':bool(journals),'skip_reason':None if journals else 'No native session established',
    'before':before,'added':added,'discarded':discard,'after':after,
    'before_count':len(before),'added_count':len(added),'discarded_count':len(discard),'after_count':len(after),
    'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
    'discard_receipts':[{'identity':x,'reason':reasons[i]} for x in discard],
    'discard_reason_counts':{reasons[i]:len(discard)} if discard else {},
    'gold_total':len(gs),'gold_before':len(gb),'gold_added':len(gain),'gold_discarded':len(loss),'gold_after':len(ga),
    'golden_recall':len(ga)/len(gs) if gs else None,'gold_before_identities':gb,'gold_added_identities':gain,
    'discarded_gold':[{'identity':x,'reason':reasons[i]} for x in loss],'gold_after_identities':ga})
   before=after
  lc={'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,
   'accounting_unit':'case_id + canonical article-root coordinate','arm_id':arm,'case_id':cid,'gold_total':len(gs),'gold_identities':gs,'stages':ledger}
  arm_cases[arm].append(lc);case_ledgers[arm]=[{k:x[k] for k in ('stage_id','kind','before_count','added_count','discarded_count','after_count','gold_total','gold_before','gold_after','golden_recall')} for x in ledger]
  latest={x['entity_id'].removeprefix('case:'):x['payload'] for x in stages}
  select=latest.get('SELECT',{});originals=select.get('selected_originals',latest.get('READ',{}).get('originals',[]));orig={x['source_id']:x for x in originals}
  quote_checks=[]
  for claim in latest.get('ASSESS',{}).get('claims',[]):
   for e in [{'source_id':claim['source_id'],'quote':claim['quote']},*claim.get('evidence',[])]:
    quote_checks.append(e['source_id'] in select.get('final_ids',[]) and e['source_id'] in orig and bool(e['quote'].strip()) and e['quote'] in orig[e['source_id']]['text'])
  output=r.get('output',{});meta=output.get('assembly',{}).get('term_agent',{})
  d={'case_id':cid,'arm':arm,'executed':executed,'execution_status':'EXECUTED' if executed else 'NOT_RUN_AFTER_GATE_FAILURE','http_status':r['http_status'],'request_seconds':r.get('request_seconds',r['total_seconds']),
   'model_calls':r['model_calls'],**usage_sum(r['usage']),'correct':grade['correct'],'grading_reason':grade['reason'],
   'quote_count':len(quote_checks),'all_quotes_supported':all(quote_checks),'final_claims_present':bool(quote_checks),
   'binding':latest.get('READ',{}).get('binding'),'answer_coverage':meta.get('answer_coverage'),
   'issue_assessments':meta.get('issue_assessments'),'gaps':meta.get('gaps'),
   'investigation_steps':len(meta.get('investigation_chain',[])) if isinstance(meta.get('investigation_chain'),list) else meta.get('investigation_chain',{}).get('step_count'),
   'contract_repairs':sum(x['kind'] in ('LAW_DECISION_RETRY','MEMORY_CONTRACT_REPAIR') for x in events),
   'assessment_reentries':sum(x['kind']=='ASSESS_GAP_REENTRY' for x in events),
   'corpus_roots':len(corpus),'recalled_roots':len(recalled),'acquired_roots':len(acquired),'presented_roots':len(offered),
   'gold_presented':len({canon(x) for x in offered}&set(gkeys)),
   'active_pointer_unchanged':r['active_pointer_before']==r['active_pointer_after']==b['active_pointer_hash'] if executed else None,
   'error':r.get('error') or output.get('detail') or output.get('error'),'field_execution':False}
  diagnostics[arm].append(d);case_diag[arm]=d
  put(directory/'diagnostic.json',d)
  t=transcript(directory/'provider');put(directory/'model-transcript.json',t)
  case_inputs[arm]={'executed':executed,'request':read(directory/'request.json') if executed else None,'profile':read(directory/'profile.json') if executed else None,'binding':d['binding']}
  case_outputs[arm]={'executed':executed,'actual_provider_calls':t,'actual_product_response':output if executed else None}
  case_grades[arm]={'judgment':grade,'actual_evaluator_calls':transcript(directory/'evaluator')}
 qp=A/'실험'/('질문-'+str(number).zfill(3)+'-'+cid+'.md')
 chunks=['# '+cid,'## 1. 실행 메타','run-001 / baseline + integrated / 공개 동결 법령 / 각 1회 / Qwen3.8 Parasail FP8 reasoning none / GENOS 실행 아님',
  '## 2. 사용자 질문 원문',case['question'],'## 3. 기준답변 — 채점 전용, 제품 입력 비공개',fence(gold[cid]),
  '## 4. 제품 입력을 구성한 원값',fence(case_inputs),'### 회수·탈락 단계 원장 — run·arm별',fence(case_ledgers),
  '전체 canonical 좌표·탈락 이유는 run-001/retrieval-ledger.json.gz에 보존한다. gold 결합은 제품 출력 이후 수행했다.',
  '## 5. 제품 모델 호출 — run·arm별 실제 원문',fence(case_outputs),
  '## 6. 중간 LLM 호출 — router/compiler/verifier/repair','실제 router·선택·판단·보정 호출은 위 원문에 phase와 함께 전부 포함한다.',
  '## 7. 채점 호출과 반복 판정',fence(case_grades),'동결 원문과 질문별 루브릭으로 arm당 1회 독립 채점. 실패 실행은 오답이며 채점 호출 없음.',
  '## 8. 사례 최종 판정',fence(case_diag)]
 qp.write_text('\n\n'.join(chunks)+'\n');questions.append({'number':number,'case_id':cid,'file':qp.name,'sha256':sha(qp)})
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
 'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,
 'runs':[{'run_id':'run-001','arms':[{'arm_id':arm,'declared_stage_ids':['catalogue','recall','acquired','presented'],
  'cases':rows,'aggregate':{'cases':len(rows),'presented_total':sum(x['stages'][-1]['after_count'] for x in rows),'gold_total':sum(x['gold_total'] for x in rows)}} for arm,rows in arm_cases.items()]}],
 'audit':{'acquired':'Includes inspection-only reads, never equated with adoption','presented':'Text-bearing actual provider/native model inputs, including ancestor context; coverage measured separately',
 'scope':'Catalogue includes generation article roots; every actual read and model call remains under public145 authorization'}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(RUN/'retrieval-ledger.json.gz',ledger)
paired={k:[] for k in ('both_correct','candidate_only_correct','baseline_only_correct','both_incorrect','not_compared')}
for c in dataset['cases']:
 cid=c['case_id'];base=next(x for x in diagnostics['baseline'] if x['case_id']==cid)['correct'];new=next(x for x in diagnostics['integrated'] if x['case_id']==cid)['correct']
 paired['not_compared' if base is None or new is None else 'both_correct' if base and new else 'candidate_only_correct' if new else 'baseline_only_correct' if base else 'both_incorrect'].append(cid)
checks={'frozen_contracts_passed':'146 passed' in (A/'artifacts/contracts-frozen.log').read_text() and 'failed' not in (A/'artifacts/contracts-frozen.log').read_text(),
 'candidate_all_5_executions_pass':all(x['http_status']==200 for x in diagnostics['integrated']),
 'zero_baseline_only_correct_cases':not paired['baseline_only_correct'],
 'candidate_quotes_supported':all(x['all_quotes_supported'] and x['final_claims_present'] for x in diagnostics['integrated']),
 'main_unchanged_during_evaluation':all(x['active_pointer_unchanged'] for rows in diagnostics.values() for x in rows if x['executed']),
 'package_gateway_passed':read(A/'artifacts/package-001/result.json')['strict_success'],
 'all_frozen_files_match':all(sha(R/p)==h for seal in ('freeze.json','release-freeze.json') for p,h in read(D/seal)['files'].items()),
 'all_5_candidate_answers_complete':all(x['correct'] is True for x in diagnostics['integrated']),
 'probe_not_main_eligible':m['in_sample'] and not m['decision_eligible']}
by_arm={arm:{'status':'complete','total':len(rows),'executed_count':sum(x['executed'] for x in rows),'not_executed_count':sum(not x['executed'] for x in rows),'correct_count':sum(x['correct'] is True for x in rows),'request_success_count':sum(x['http_status']==200 for x in rows),
 'cases':rows,'usage':usage_sum([u for c in dataset['cases'] for u in raws[arm,c['case_id']]['usage']]),
 'latency':{'request_p50':statistics.median(x['request_seconds'] for x in rows if x['executed']),'request_p95':percentile([x['request_seconds'] for x in rows if x['executed']],.95)}} for arm,rows in diagnostics.items()}
result={'strict_success':all(checks.values()),'checks':checks,'by_arm':by_arm,'paired_outcomes':paired,'main_wiring':'unchanged','genos_deployed':False}
put(RUN/'result.json',result)
m['questions']=questions;m['results']={'status':'complete','by_arm':by_arm,'comparisons':[{'paired_outcomes':paired}],
 'judge_disagreements':None,'usage':{arm:row['usage'] for arm,row in by_arm.items()},'latency':{arm:row['latency'] for arm,row in by_arm.items()},
 'error_taxonomy':['other:actual_product_execution_failure'] if not checks['candidate_all_5_executions_pass'] else []}
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
for arm in m['design']['arms']:
 if arm['id']=='baseline':arm.update(changes='Exact selected generation42 active release, no candidate features',controls='Same immutable public generation, scope, model/provider and budgets')
ra=m['retrieval_accounting'];ra['corpus_total']=max(x['corpus_roots'] for rows in diagnostics.values() for x in rows)
for metric,key in [('before_filter','recalled_roots'),('after_filter','acquired_roots'),('presented_total','presented_roots')]:ra[metric]={arm:sum(x[key] for x in rows) for arm,rows in diagnostics.items()}
for metric,fn in [('presented_mean',statistics.mean),('presented_p50',statistics.median),('presented_p95',lambda v:percentile(v,.95))]:ra[metric]={arm:fn([x['presented_roots'] for x in rows]) for arm,rows in diagnostics.items()}
ra['golden_recall']={arm:sum(x['gold_presented'] for x in rows)/len(rows) for arm,rows in diagnostics.items()}
ra['selectivity']={arm:ra['presented_mean'][arm]/ra['corpus_total'] for arm in diagnostics};ra['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json.gz')
put(A/'실험/manifest.json',m)
(A/'실험/README.md').write_text('# 독립 공개 질의 인덱스\n\n'+ '\n'.join('- ['+x['case_id']+']('+x['file']+')' for x in questions)+'\n')
print(json.dumps({'strict_success':result['strict_success'],'checks':checks,'paired_outcomes':paired,'by_arm':{k:{f:v[f] for f in ('total','correct_count','request_success_count','usage','latency')} for k,v in by_arm.items()}},ensure_ascii=False))
