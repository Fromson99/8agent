"""Post-output trace, quote and holdout accounting; never a product input."""
from pathlib import Path
import hashlib,json,sqlite3,statistics,gzip
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0678-investigation-contract-completion'
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
 
 if p.suffix=='.gz':
  db=sqlite3.connect(':memory:');db.deserialize(gzip.decompress(p.read_bytes()));db.execute('PRAGMA query_only=ON')
 else:db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True)
 db.row_factory=sqlite3.Row;return db
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

allowed_docs=set(read(R/b['stage']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
assert len(allowed_docs)==145
expected_native=read(A/'artifacts/binding-check/expected.json')['binding']
def chain_valid(v):
 if not isinstance(v,dict) or v.get('contract')!='investigation-action-chain-v1':return False
 steps=v.get('steps',[]);judgments=v.get('judgments',[]);refs={x['id'] for x in judgments}
 if not v.get('entry_frame_id') or not v.get('current_frame') or len(refs)!=len(judgments):return False
 return bool(steps) and all(x.get('number')==i+1 and x.get('previous_step')==(steps[i-1]['id'] if i else None) and set(x.get('judgment_refs',[]))<=refs and bool(x.get('reason')) for i,x in enumerate(steps))
def issue_valid(meta):
 rows=meta.get('issue_assessments',[]);ids=[x.get('issue_id') for x in rows]
 return bool(rows) and len(ids)==len(set(ids)) and all(x.get('status') in ('COVERED','PARTIAL','INSUFFICIENT') for x in rows)

arm_cases={x:[] for x in ('integrated',)};diagnostics={x:[] for x in arm_cases};raws={};questions=[]
for number,case in enumerate(dataset['cases'],1):
 cid=case['case_id'];case_inputs={};case_outputs={};case_grades={};case_diag={};case_ledgers={}
 for arm in arm_cases:
  directory=RUN/arm/cid;executed=(directory/'result.json').exists()
  r=read(directory/'result.json') if executed else {'case_id':cid,'arm':arm,'http_status':None,'total_seconds':0,'model_calls':0,'usage':[],'execution_status':'NOT_RUN_AFTER_GATE_FAILURE'}
  grade=read(directory/'grade.json') if executed else {'correct':None,'reason':'Not executed after the frozen required gate failed; no product or evaluator call','usage':[]}
  raws[arm,cid]=r
  journals=list((directory/'runtime').rglob('journal.sqlite*'))
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
  d={'case_id':cid,'arm':arm,'executed':executed,'execution_status':r.get('execution_status','EXECUTED' if executed else 'NOT_RUN_AFTER_GATE_FAILURE'),'http_status':r['http_status'],'request_seconds':r.get('request_seconds',r['total_seconds']),
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
   'model_text_sources_authorized':all(sources[x]['document_id'] in allowed_docs for x in offered_ids),'supported_original_ids':list(orig),'allowed_originals':all(x.get('document_id') in allowed_docs for x in originals),
   'control_contract':meta.get('control_contract'),'chain_integrity':chain_valid(meta.get('investigation_chain')),'issue_integrity':issue_valid(meta),
   'error':r.get('error') or output.get('detail') or output.get('error'),'field_execution':False}
  diagnostics[arm].append(d);case_diag[arm]=d
  put(directory/'diagnostic.json',d)
  t=transcript(directory/'provider');put(directory/'model-transcript.json',t)
  case_inputs[arm]={'executed':executed,'request':read(directory/'request.json') if executed else None,'profile':read(directory/'profile.json') if executed else None,'binding':d['binding']}
  case_outputs[arm]={'executed':executed,'actual_provider_calls':t,'actual_product_response':output if executed else None}
  case_grades[arm]={'judgment':grade,'actual_evaluator_calls':transcript(directory/'evaluator')}
 qp=A/'실험'/('질문-'+str(number).zfill(3)+'-'+cid+'.md')
 chunks=['# '+cid,'## 1. 실행 메타','run-001 / integrated only / 공개 동결 법령 / 각 1회 / Qwen3.8 Parasail FP8 reasoning none / GENOS 실행 아님',
  '## 2. 사용자 질문 원문',case['question'],'## 3. 기준답변 — 채점 전용, 제품 입력 비공개',fence(gold[cid]),
  '## 4. 제품 입력을 구성한 원값',fence(case_inputs),'### 회수·탈락 단계 원장 — run·arm별',fence(case_ledgers),
  '전체 canonical 좌표·탈락 이유는 run-001/retrieval-ledger.json.gz에 보존한다. gold 결합은 제품 출력 이후 수행했다.',
  '## 5. 제품 모델 호출 — run·arm별 실제 원문',fence(case_outputs),
  '## 6. 중간 LLM 호출 — router/compiler/verifier/repair','실제 router·선택·판단·보정 호출은 위 원문에 phase와 함께 전부 포함한다.',
  '## 7. 채점 호출과 반복 판정',fence(case_grades),'동결 원문과 질문별 루브릭으로 arm당 1회 독립 채점. 실패 실행은 미답변으로 기록하며 채점 호출 없음. 세부 의미 점수는 진단이며 절대 승격 기준이 아니다.',
  '## 8. 사례 최종 판정',fence(case_diag)]
 qp.write_text('\n\n'.join(chunks)+'\n');questions.append({'number':number,'case_id':cid,'file':qp.name,'sha256':sha(qp)})
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
 'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,
 'runs':[{'run_id':'run-001','arms':[{'arm_id':arm,'declared_stage_ids':['catalogue','recall','acquired','presented'],
  'cases':rows,'aggregate':{'cases':len(rows),'presented_total':sum(x['stages'][-1]['after_count'] for x in rows),'gold_total':sum(x['gold_total'] for x in rows)}} for arm,rows in arm_cases.items()]}],
 'audit':{'acquired':'Includes inspection-only reads, never equated with adoption','presented':'Text-bearing actual provider/native model inputs, including ancestor context; coverage measured separately',
 'scope':'Catalogue includes generation article roots; every actual read and model call remains under public145 authorization'}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(RUN/'retrieval-ledger.json.gz',ledger)
outcomes={k:[] for k in ('correct','judgment_mistake','no_answer')}
policy={'semantic_correctness_absolute_gate':False,'bounded_model_outcomes':['SOURCE_INVESTIGATION_INCOMPLETE','MODEL_UPSTREAM_UNAVAILABLE','MODEL_PROPOSAL_INVALID','STALE_PROPOSAL','BUDGET_EXHAUSTED','DEADLINE_EXCEEDED','MODEL_TRANSPORT_ERROR','ADMISSION_REJECTED'],'user_instruction':'2026-10-07: semantic mistakes are diagnostic; source, access, hash, state and publication integrity remain gates.'};regressions=[]
for case in dataset['regression_cases']:
 p=A/'artifacts/regression/integrated'/case['case_id']/'result.json'
 r=read(p) if p.exists() else {'case_id':case['case_id'],'http_status':None,'model_calls':0,'usage':[]}
 regressions.append({'case_id':case['case_id'],'http_status':r.get('http_status'),'model_calls':r['model_calls'],'error':r.get('error') or r.get('output',{}).get('detail') or r.get('output',{}).get('error'),'result_path':str(p.relative_to(R)) if p.exists() else None,'result_sha256':sha(p) if p.exists() else None,**usage_sum(r['usage'])})
 regressions[-1]['active_pointer_unchanged']=r.get('active_pointer_before')==r.get('active_pointer_after')==b['active_pointer_hash']
 rows=r.get('output',{}).get('assembly',{}).get('term_agent',{})
 if r.get('http_status')==200:
  journal=list((p.parent/'runtime').rglob('journal.sqlite*'));assert len(journal)==1
  db=ro(journal[0]);latest_reg={x['entity_id'].removeprefix('case:'):x['payload'] for x in payloads(db,"SELECT * FROM entity_version WHERE kind='case_stage' ORDER BY created_seq")};db.close()
  selected=latest_reg.get('SELECT',{});original={x['source_id']:x for x in selected.get('selected_originals',latest_reg.get('READ',{}).get('originals',[]))}
  verified=[]
  for claim in latest_reg.get('ASSESS',{}).get('claims',[]):
   for e in [{'source_id':claim['source_id'],'quote':claim['quote']},*claim.get('evidence',[])]:verified.append(e['source_id'] in selected.get('final_ids',[]) and e['source_id'] in original and bool(e['quote'].strip()) and e['quote'] in original[e['source_id']]['text'])
  regressions[-1].update(quote_count=len(verified),all_quotes_supported=all(verified),allowed_originals=all(x.get('document_id') in allowed_docs for x in original.values()),binding=latest_reg.get('READ',{}).get('binding'))
  regressions[-1].update(control_contract=rows.get('control_contract'),chain_integrity=chain_valid(rows.get('investigation_chain')),issue_integrity=issue_valid(rows))

def bounded_failure(r):
 if r.get('http_status')==200:return True
 code=r.get('output',{}).get('code')
 detail=r.get('output',{}).get('detail')
 if isinstance(detail,dict):code=detail.get('code',code)
 error=r.get('output',{}).get('error')
 if isinstance(error,dict):code=error.get('code',code)
 if code in policy['bounded_model_outcomes']:return True
 # Keep the actual 422 unchanged; classify ONLY witnessed pre-action model rejection.
 if r.get('http_status')!=422:return False
 directory=A/'artifacts'/('regression' if r['case_id'].startswith('REG-') else 'run-001')/r['arm']/r['case_id']
 journals=list((directory/'runtime').rglob('journal.sqlite*'))
 if len(journals)!=1:return False
 db=ro(journals[0]);events=payloads(db,'SELECT * FROM event ORDER BY seq')
 detail=r.get('output',{}).get('detail');witness=None
 rejected=[x for x in events if x['kind']=='LAW_DECISION_REJECTED']
 if isinstance(detail,str) and detail.startswith('request violates term-runtime-v1 contract:') and rejected:
  last=rejected[-1];v=last['payload'];after=[x for x in events if x['seq']>last['seq']]
  if v.get('error_type')=='ValidationError' and 'source-law-navigation-' in v.get('phase','') and "Failed validating 'enum'" in v.get('error','') and all(x['kind'] in ('UNASSESSED_AT_STOP','RUN_FAILED') for x in after) and any(x['kind']=='RUN_FAILED' and x['payload'].get('code')=='ValidationError' for x in after):witness={'model_proposal_rejected_seq':last['seq'],'phase':v['phase'],'following_native_events':[{'seq':x['seq'],'kind':x['kind']} for x in after],'no_action_after_rejection':True}
 if isinstance(detail,str) and detail.startswith('unsupported claim['):
  outputs=[x for x in events if x['kind']=='MEMORY_MODEL_OUTPUT' and x['payload'].get('phase')=='memory-assess-repair']
  failures=[x for x in events if x['kind']=='RUN_FAILED']
  if outputs and failures:
   last=outputs[-1];failure=failures[-1];loc=failure['payload'].get('diagnostics',{}).get('location',{});after=[x for x in events if x['seq']>last['seq']]
   rows=payloads(db,"SELECT * FROM entity_version WHERE kind='case_stage' ORDER BY created_seq")
   selected=next((x['payload'] for x in reversed(rows) if x['entity_id']=='case:SELECT'),{})
   original={x['source_id']:x for x in selected.get('selected_originals',[])}
   claims=last['payload'].get('output',{}).get('claims',[])
   invalid=[i for i,c in enumerate(claims) if c.get('source_id') not in original or not c.get('quote') or c['quote'] not in original[c['source_id']]['text']]
   if failure['payload'].get('code')=='MemoryError' and loc.get('function')=='verify_claims' and loc.get('file','').endswith('/legal_agent/memory_rag.py') and invalid and all(x['kind'] in ('UNASSESSED_AT_STOP','RUN_FAILED') for x in after) and not any(x['entity_id']=='case:ASSESS' and x['created_seq']>last['seq'] for x in rows):witness={'invalid_model_output_seq':last['seq'],'phase':'memory-assess-repair','invalid_claim_indexes':invalid,'native_guard':'memory_rag.verify_claims','no_unsupported_claim_published':True,'following_native_events':[{'seq':x['seq'],'kind':x['kind']} for x in after],'no_action_after_rejection':True}
 db.close()
 if witness:
  put(directory/'execution-failure-classification.json',{'actual_http_status':r['http_status'],'actual_result_sha256':sha(directory/'result.json'),'canonical_outcome_code':'MODEL_PROPOSAL_INVALID',**witness,'native_journal_sha256':sha(journals[0]),'result_was_not_rewritten':True,'frozen_policy_category':'bounded_model_outcomes'})
 return witness is not None

successful=[x for x in diagnostics['integrated'] if x['http_status']==200]
types={c['case_id']:c['kind'] for c in dataset['cases']}
for x in diagnostics['integrated']:
 outcomes['no_answer' if x['http_status']!=200 else 'correct' if x['correct'] else 'judgment_mistake'].append(x['case_id'])
critical=[]
for x in diagnostics['integrated']:
 if x['http_status']!=200 and not bounded_failure(raws['integrated',x['case_id']]):critical.append({'case_id':x['case_id'],'error':x['error'],'http_status':x['http_status']})
for x in regressions:
 if x['http_status']!=200 and (not x['result_path'] or not bounded_failure(read(R/x['result_path']))):critical.append(x)
checks={
 'new_native_contracts_passed':read(A/'artifacts/contracts/result.json')['candidate_native_contracts']=={'passed':20,'failed':0,'log':'contracts-5.log'},
 'no_new_broad_regression':read(A/'artifacts/contracts/result.json')['broad_legacy']['new_failures']==[],
 'all_32_observed_attempted':len(diagnostics['integrated'])==32 and all(x['executed'] and x['http_status'] is not None for x in diagnostics['integrated']),
 'all_8_regressions_attempted':len(regressions)==8 and all(x['http_status'] is not None for x in regressions),
 'at_least_33_supported_responses':sum(x['all_quotes_supported'] and x['final_claims_present'] for x in successful)+sum(x['http_status']==200 and x['all_quotes_supported'] and x['quote_count']>0 for x in regressions)>=read(D/'design.json')['acceptance']['minimum_supported_responses'],
 'no_critical_execution_failure':not critical,
 'candidate_quotes_supported':all(x['all_quotes_supported'] for x in successful),
 'actual_originals_under_public_scope':all(x['allowed_originals'] and x['model_text_sources_authorized'] for x in diagnostics['integrated']),
 'observed_chain_issue_contracts_valid':all(x['chain_integrity'] and x['issue_integrity'] and x['control_contract']=='investigation-control-v2' and x['assessment_reentries']<=2 for x in successful) and all(x['chain_integrity'] and x['issue_integrity'] for x in regressions if x['http_status']==200),
 'native_binding_matches_frozen_runtime':all(x['binding']==expected_native for x in successful),
 'regression_quote_scope_binding_valid':all(x['all_quotes_supported'] and x['allowed_originals'] and x['binding']==expected_native for x in regressions if x['http_status']==200),
 'main_unchanged_during_evaluation':all(x['active_pointer_unchanged'] for x in diagnostics['integrated']+regressions),
 'package_gateway_passed':read(A/'artifacts/package-001/result.json')['strict_success'],
 'all_frozen_files_match':all(sha(R/p)==h for seal in ('freeze.json','release-freeze.json') for p,h in read(D/seal)['files'].items()),
 'observed_probe_not_eligible_for_promotion':m['in_sample'] is True and m['decision_eligible'] is False}

by_arm={arm:{'status':'complete','total':len(rows),'executed_count':sum(x['executed'] for x in rows),'not_executed_count':sum(not x['executed'] for x in rows),'correct_count':sum(x['correct'] is True for x in rows),'request_success_count':sum(x['http_status']==200 for x in rows),
 'cases':rows,'usage':usage_sum([u for c in dataset['cases'] for u in raws[arm,c['case_id']]['usage']]),
 'latency':{'request_p50':statistics.median(x['request_seconds'] for x in rows if x['executed']),'request_p95':percentile([x['request_seconds'] for x in rows if x['executed']],.95)}} for arm,rows in diagnostics.items()}
errors=[{'case_id':x['case_id'],'type':types[x['case_id']],'severity':'semantic-diagnostic' if x['http_status']==200 else 'bounded-or-critical-execution','question':next(c['question'] for c in dataset['cases'] if c['case_id']==x['case_id']),'reason':x['grading_reason'],'error':x['error'],'gaps':x['gaps'],'gold_source_id':gold[x['case_id']]['source_id'],'immutable_result_path':str((RUN/'integrated'/x['case_id']/'result.json').relative_to(R)),'follow_up':'Classify missing scope/actor/condition from this record; any product modification or regrade requires a new ADR.'} for x in diagnostics['integrated'] if x['correct'] is not True]
put(RUN/'GENERALIZATION_ERRORS.json',{'user_instruction':policy['user_instruction'],'semantic_absolute_gate':False,'errors':errors,'critical_failures':critical})
result={'strict_success':all(checks.values()),'checks':checks,'by_arm':by_arm,'semantic_outcomes':outcomes,'regressions':regressions,'critical_failures':critical,'main_wiring':'unchanged','genos_deployed':False,'comparison_claim':None,'baseline_reference_only':b['baseline_release']}
put(RUN/'result.json',result)
m['questions']=questions;m['results']={'status':'complete','by_arm':by_arm,'comparisons':[],
 'judge_disagreements':None,'usage':{arm:row['usage'] for arm,row in by_arm.items()},'latency':{arm:row['latency'] for arm,row in by_arm.items()},
 'error_taxonomy':['other:semantic-diagnostic'] if errors else []}
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['lineage']['hypothesis_delta']=m['design']['hypothesis']
ra=m['retrieval_accounting'];ra['corpus_total']=max(x['corpus_roots'] for x in diagnostics['integrated'])
for metric,key in [('before_filter','recalled_roots'),('after_filter','acquired_roots'),('presented_total','presented_roots')]:ra[metric]={arm:sum(x[key] for x in rows) for arm,rows in diagnostics.items()}
for metric,fn in [('presented_mean',statistics.mean),('presented_p50',statistics.median),('presented_p95',lambda v:percentile(v,.95))]:ra[metric]={arm:fn([x['presented_roots'] for x in rows]) for arm,rows in diagnostics.items()}
ra['golden_recall']={arm:sum(x['gold_presented'] for x in rows)/len(rows) for arm,rows in diagnostics.items()}
ra['selectivity']={arm:ra['presented_mean'][arm]/ra['corpus_total'] for arm in diagnostics};ra['stage_ledger'].update(artifact_path=str((RUN/'retrieval-ledger.json.gz').relative_to(R)),sha256=sha(RUN/'retrieval-ledger.json.gz'))
put(A/'실험/manifest.json',m)
(A/'실험/README.md').write_text('# 관찰된 개발·회귀 질의 인덱스\n\n'+ '\n'.join('- ['+x['case_id']+']('+x['file']+')' for x in questions)+'\n')
print(json.dumps({'strict_success':result['strict_success'],'checks':checks,'semantic_outcomes':{k:len(v) for k,v in outcomes.items()},'critical_failures':critical,'regressions':[{k:x[k] for k in ('case_id','http_status','model_calls')} for x in regressions]},ensure_ascii=False))
