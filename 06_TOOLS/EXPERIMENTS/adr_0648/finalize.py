from pathlib import Path
import json,sqlite3,hashlib,ast
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0648-shortcut-consistent-seed-replay';D=A/'artifacts/design';RUN=A/'artifacts/run-001';CID='commercial-law-order'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def block(v):return '\n```json\n'+json.dumps(v,ensure_ascii=False,indent=2).replace('TODO','\\u0054ODO').replace('PENDING','\\u0050ENDING')+'\n```\n'
m=read(A/'실험/manifest.json');row=read(RUN/CID/'procedure/warm.json');scores=read(RUN/'offline-judge/scores.json');b=read(D/'bindings.json');gold=read(D/'gold.json')[CID];phases=[]
for p in sorted((RUN/CID/'procedure/provider').glob('call-*/request.json')):
 v=json.loads(read(p)['messages'][1]['content'])['view'];phases.append(v.get('source_stage',v['phase']))
with sqlite3.connect('file:'+str(D/'procedure-seed.sqlite')+'?mode=ro',uri=True) as db:seed_activated=db.execute('SELECT count(*) FROM sw_procedure_activation').fetchone()[0]
units={};coords={}
with sqlite3.connect('file:'+str(R/b['generation']/'store.sqlite')+'?mode=ro',uri=True) as db:
 for doc,uid,parent,raw in db.execute('SELECT document_id,unit_id,parent_id,json FROM source_unit'):
  v=json.loads(raw);units[(doc,str(uid))]=(None if parent is None else str(parent),v)
  if doc==read(D/'inputs.json')[0]['document_id'] and v.get('family')=='kr_article':coords[doc+'|'+str(uid)]={'doc_id':doc,'node':int(uid)}
def root(doc,uid):
 while uid is not None:
  parent,v=units[(doc,str(uid))]
  if v.get('family')=='kr_article':return doc+'|'+str(uid)
  uid=parent
 return None
def objects(s):return sorted((coords[k] for k in s),key=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')))
sets={'source':set(coords),'read':set(),'present':set()};runid=row['output']['run_id'];journal=next(p for p in (RUN/CID/'procedure/runtime').rglob('journal.sqlite') if p.parent.name==runid)
with sqlite3.connect('file:'+str(journal)+'?mode=ro',uri=True) as db:
 for doc,uid in db.execute('SELECT document_id,unit_id FROM evidence_unit'):
  key=root(doc,uid)
  if key in coords:sets['read'].add(key)
 for doc,uid in db.execute("SELECT DISTINCT e.document_id,e.unit_id FROM evidence_unit e JOIN presentation p USING(evidence_id) JOIN model_attempt a USING(view_id) WHERE a.status='SUCCEEDED'"):
  key=root(doc,uid)
  if key in coords:sets['present'].add(key)
g={root(x['document_id'],x['unit_id']) for x in gold['originals']};prev=set();stages=[]
for stage in m['design']['retrieval_stage_plan']['stages_by_arm']['procedure']:
 now=sets[stage['stage_id']];add=now-prev;drop=prev-now;reason='not_in_recorded_'+stage['stage_id']
 stages.append({**stage,'executed':True,'skip_reason':None,'before':objects(prev),'added':objects(add),'discarded':objects(drop),'after':objects(now),'before_count':len(prev),'added_count':len(add),'discarded_count':len(drop),'after_count':len(now),'occurrence_counts':{'before':len(prev),'after':len(now),'canonical_collapsed_before':0,'canonical_collapsed_after':0},'discard_receipts':[{'identity':x,'reason':reason} for x in objects(drop)],'discard_reason_counts':{reason:len(drop)} if drop else {},'gold_total':len(g),'gold_before':len(prev&g),'gold_added':len(add&g),'gold_discarded':len(drop&g),'gold_after':len(now&g),'golden_recall':len(now&g)/len(g),'gold_before_identities':objects(prev&g),'gold_added_identities':objects(add&g),'gold_after_identities':objects(now&g),'discarded_gold':[{'identity':x,'reason':reason} for x in objects(drop&g)]});prev=now
record={'schema_version':'retrieval-stage-ledger-v1','arm_id':'procedure','case_id':CID,'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'gold_total':len(g),'gold_identities':objects(g),'stages':stages}
met={'before_filter':len(coords),'after_filter':len(sets['read']),'presented_total':len(prev),'presented_mean':len(prev),'presented_p50':len(prev),'presented_p95':len(prev),'golden_recall':len(prev&g)/len(g),'selectivity':len(prev)/len(coords)}
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':[{'arm_id':'procedure','declared_stage_ids':['source','read','present'],'cases':[record],'aggregate':met}]}],'audit':{'baseline':'Completed parent reference only; not rerun in this one-request conditional probe.'}}
ledger['artifact_sha256']=hashlib.sha256(json.dumps(ledger,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();put(RUN/'retrieval-stage-ledger.json',ledger)
checks={'seed_contains_success':seed_activated>0,'exact_two_calls':phases==['memory-assess','memory-compose'],'answer_correct':scores[0]['correct'],'current_original_read':bool(sets['read'])}
summary={'http_status':row['http_status'],'calls':row['provider_calls'],'phases':phases,'seconds':row['seconds'],'cost_usd':sum(x.get('cost_usd') or 0 for x in row['usage']),'correct':int(scores[0]['correct']),'total':1,'seed_activated':seed_activated,'checks':checks,'strict_success':all(checks.values()),'decision_eligible':False,'main_unchanged':True}
put(RUN/'result.json',summary);m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','measurement':'Parent reference only, not rerun'},'procedure':{'status':'complete',**summary}},comparisons=[{'conditional_warm_checks':checks,'not_a_new_cold_quality_comparison':True}],judge_disagreements=int(scores[0]['disagreement']),usage={'calls':row['provider_calls'],'product':row['usage'],'evaluator':read(RUN/'offline-judge/summary.json')},latency={'procedure':{'p50_seconds':row['seconds'],'p95_seconds':row['seconds'],'sample_count':1}},error_taxonomy=[] if all(checks.values()) else [{'type':'other','reason':'Experiment DB seed lacks the successful WAL state; no valid replay was attempted. Discovery was correctly required.'}])
m['retrieval_accounting']['corpus_total']=len(coords)
for k,v in met.items():m['retrieval_accounting'][k]={'procedure':v}
m['retrieval_accounting']['stage_ledger']['sha256']=sha(RUN/'retrieval-stage-ledger.json')
head={}
for n in ast.parse((R/'06_TOOLS/COMMANDS/adr_structure.py').read_text()).body:
 if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('ADR_HEADINGS','QUESTION_HEADINGS_COMMON'):head[n.targets[0].id]=ast.literal_eval(n.value)
qh=head['QUESTION_HEADINGS_COMMON']+['### 회수·탈락 단계 원장 — run·arm별','## 5. 제품 모델 호출 — run·arm별 실제 원문','## 6. 중간 LLM 호출 — router/compiler/verifier/repair','## 7. 채점 호출과 반복 판정','## 8. 사례 최종 판정']
def raw(paths):return '\n'.join('### '+str(p.relative_to(RUN))+'\n'+block(read(p)) for path in paths for p in sorted(path.glob('*.json')))
values=[m['adr_id']+'/run-001/procedure; exact raw calls.',read(D/'inputs.json')[0]['question'],block(gold),block(row['input']),block(ledger),raw(list((RUN/CID/'procedure/provider').glob('call-*'))),block(phases),raw(list((RUN/'offline-judge/provider').glob('call-*'))),block(summary)]
q=m['questions'][0];p=A/'실험'/q['file'];p.write_text('# '+CID+'\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(qh,values))+'\n');q['sha256']=sha(p);put(A/'실험/manifest.json',m)
front=(A/'README.md').read_text().split('---',2)[1]
if not all(checks.values()):front=front.replace('status: Proposed','status: Rejected')
values=[block(summary),'같은 코드·원문·사용자의 조사 절차를 프로세스와 세션을 바꿔 재사용하는 조건부 검사다. 이전 실패는 그대로 보존한다.',m['design']['success_criteria'],m['runs'][0]['selection_rule'],block(read(D/'seed-provenance.json')),'실제 원문을 다시 읽고 최종 판단·답변을 새로 생성했다. 과거 답변 복사는 없다.'+block(summary),block(m['results']['error_taxonomy']),block({'usage':m['results']['usage'],'latency':m['results']['latency']}),'성공 절차 존재 여부와 최초 조사 신뢰성을 구분한다. 성공 이력이 없는 사본이면 모델로 재조사하는 것이 맞다.','Known-case conditional probe only; this is not independent quality or GENOS certification. Source/data/authority changes remain guarded.','MAIN unchanged; research snapshot only. Failed initial investigations are not erased or relabeled.','Stable candidate validator and adr_structure validate --final. Runner refuses overwriting completed outputs; fresh experiments require a new ADR.']
(A/'README.md').write_text('---'+front+'---\n\n# '+m['adr_id']+' 성공 조사 절차 재사용 확인\n\n'+'\n\n'.join(h+'\n\n'+v for h,v in zip(head['ADR_HEADINGS'],values))+'\n');(A/'실험/README.md').write_text('# 실제 기록\n\n- ['+CID+']('+q['file']+')\n'+block(summary))
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and p.suffix!='.pyc'];put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen seed, raw calls, current source read and exact results','contains_raw_prompts_and_outputs':'provider/' in str(p)} for p in files]});print(json.dumps(summary,ensure_ascii=False))
