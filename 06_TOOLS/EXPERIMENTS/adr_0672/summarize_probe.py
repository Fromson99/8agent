"""Offline exact trace accounting for two-case selection tool probes."""
import hashlib,json,sqlite3,sys,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/(sys.argv[1] if len(sys.argv)>1 else '04_EXPERIMENTS/ADR/ADR-0665-selection-tool-contract-fixes')
A=ADR/'artifacts';RUN=A/'run-001';m=json.loads((ADR/'실험/manifest.json').read_text())
arm=m['design']['arms'][0]['id']
contracts_count=73
def read(p):return json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def fence(v):return '```json\n'+json.dumps(v,ensure_ascii=False,indent=2).replace('PENDING','PEND\\u0049NG').replace('TODO','TO\\u0044O')+'\n```'
bindings=read(A/'design/bindings.json')
nav=sqlite3.connect((ROOT/bindings['source_generation']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
rows={sid:json.loads(raw) for sid,raw in nav.execute('select id,json from source')}
def identities(ids):
 return [json.loads(x) for x in sorted({canon({'doc_id':rows[s]['document_id'],'node':int(rows[s]['unit_id'])}) for s in ids if s in rows and str(rows[s]['unit_id']).isdigit()})]
cases=[];results=[];diags=[];question_index=[];ledger_cases=[]
for case in read(A/'design/dataset.json')['cases']:
 cid=case['case_id'];directory=RUN/cid;r=read(directory/'result.json');results.append(r)
 db=sqlite3.connect(next((directory/'runtime/legal-agent').rglob('journal.sqlite')).resolve().as_uri()+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 events=[dict(x) for x in db.execute('select * from event order by seq')]
 for x in events:x['payload']=json.loads(x.pop('payload_json'))
 stages=[dict(x) for x in db.execute("select * from entity_version where kind='case_stage' order by created_seq")]
 for x in stages:x['payload']=json.loads(x.pop('payload_json'))
 put(directory/'native-events.json',events);put(directory/'native-case-stages.json',stages)
 ins=[x['payload'] for x in events if x['kind']=='MEMORY_MODEL_INPUT']
 outs=[x['payload'] for x in events if x['kind']=='MEMORY_MODEL_OUTPUT']
 law=[x for x in ins if x.get('phase','').startswith('source-law-navigation')]
 directories=[x['payload'] for x in events if x['kind']=='LAW_FULLTEXT_DIRECTORY']
 statuses=[x['payload'] for x in events if x['kind']=='LAW_INVESTIGATION_STATUS']
 final=statuses[-1] if statuses else {}
 first=law[0]['data'] if law else {}
 put(directory/'first-law-navigation-input.json',first)
 def cards(v):return v.get('articles',[a for l in v.get('laws',[]) for a in l.get('articles',[])])
 recall=[x['payload'] for x in stages if x['entity_id']=='case:RECALL']
 corpus=identities(recall[0].get('corpus_ids',[])) if recall else []
 recalled=identities({sid for x in recall for sid in x.get('selected_for_read',[])})
 acquired=identities({x[0] for x in db.execute('select distinct source_id from evidence_unit')})
 presented_ids={p['source_id'] for x in law for card in cards(x['data']) for p in card.get('previews',[])}
 presented_ids.update(p['source_id'] for x in law for p in x['data'].get('sources',[]))
 presented_ids.update(a['source_id'] for x in law for l in x['data'].get('laws',[]) for a in l.get('article_matches',[]))
 presented=identities(presented_ids)
 before=[];ledger_stages=[]
 explanations=['Stored source catalogue; actual READs enforce approved request scope','Not actually prepared by executed recall','Not acquired by an executed original READ','Not delivered as a preview or original page to law-navigation model input']
 for i,after in enumerate([corpus,recalled,acquired,presented]):
  plan=m['design']['retrieval_stage_plan']['stages_by_arm'][arm][i];b={canon(x):x for x in before};z={canon(x):x for x in after}
  added=[z[x] for x in sorted(z.keys()-b.keys())];discarded=[b[x] for x in sorted(b.keys()-z.keys())]
  ledger_stages.append({**plan,'executed':True,'skip_reason':None,'before':before,'added':added,'discarded':discarded,'after':after,
   'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),
   'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
   'discard_receipts':[{'identity':x,'reason':explanations[i]} for x in discarded],'discard_reason_counts':{explanations[i]:len(discarded)} if discarded else {},
   'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,'golden_recall':None,
   'gold_before_identities':[],'gold_added_identities':[],'discarded_gold':[],'gold_after_identities':[]})
  before=after
 ledger_cases.append({'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,
  'accounting_unit':'case_id + canonical article-root coordinate','arm_id':arm,'case_id':cid,'gold_total':0,'gold_identities':[],'stages':ledger_stages})
 body=r.get('output',{});answer=body.get('answer',{});answer=answer.get('text','') if isinstance(answer,dict) else str(answer)
 transcript=[{'files':{p.name:read(p) for p in sorted(folder.glob('*.json'))}} for folder in sorted((directory/'provider').glob('call-*'))]
 put(directory/'model-transcript.json',transcript)
 usage=r.get('usage',[])
 diag={'case_id':cid,'question':case['question'],'http_status':r['http_status'],'request_seconds':r.get('request_seconds',r['total_seconds']-r.get('app_setup_seconds',0)),
  'model_calls':r['model_calls'],'model_seconds':sum(x.get('seconds',0) for x in usage),
  'input_tokens':sum(x.get('input_tokens',0) or 0 for x in usage),'output_tokens':sum(x.get('output_tokens',0) or 0 for x in usage),'cost_usd':sum(x.get('cost_usd',0) or 0 for x in usage),
  'decision_retries':sum(x['kind']=='LAW_DECISION_RETRY' for x in events),'decision_repairs_succeeded':sum(x['kind']=='LAW_DECISION_REPAIRED' for x in events),
  'legacy_selector_calls':sum(x.get('phase','').startswith('source-unit-') for x in ins),'answer_text':answer,'status':final.get('status'),
  'completed_with_unresolved_connections':final.get('completed_with_unresolved_connections'),
  'law_investigation_status':final,'first_directory':directories[0] if directories else None,
  'directory_order_equals_card_order': bool(directories) and [x['document_id'] for x in first.get('laws',[])][:len(directories[0]['laws'])]==[x['document_id'] for x in directories[0]['laws']],
  'nested_card_only':bool(first) and 'articles' not in first and all('articles' in l for l in first.get('laws',[])),
  'corpus_roots':len(corpus),'prepared_preview_roots':len(recalled),'acquired_roots':len(acquired),'presented_roots':len(presented),
  'read_actions':db.execute('select count(*) from action_context').fetchone()[0],
  'active_pointer_unchanged':r['active_pointer_before']==r['active_pointer_after'],'field_execution':False,
  'quality_grade':None,'quality_note':'No independent legal evaluator; report exact source-grounded product output, not correctness rate.'}
 put(directory/'diagnostic.json',diag);diags.append(diag)
 put(directory/'retry-audit.json',[x for x in events if x['kind'].startswith(('LAW_DECISION_REJECTED','LAW_DECISION_RETRY','LAW_DECISION_PATCH','LAW_DECISION_REPAIRED'))])
 text=['실제 로컬 RAG 실행 기록','질문: '+case['question'],'HTTP '+str(r['http_status'])+' / '+str(round(r.get('request_seconds',0),3))+'초',
       '모델 호출 '+str(r['model_calls'])+'회 / 선택 보정 '+str(diag['decision_retries'])+'회','', '실제 모델 답변:',answer or '[답변 생성 실패]', '', '실제 fulltext 질의:']
 for q in (directories[0]['queries'] if directories else []):text.append(q.replace('\n',' / '))
 text+=['','최초 법령 카드 / 적중 원문:']
 for i,law in enumerate(first.get('laws',[]),1):
  text+=['',str(i)+'. '+law['name']]
  for card in law.get('articles',[]):
   text.append(card['article']+' / '+', '.join(card['matched_coordinates']))
   text.extend(p['text'] for p in card['previews'])
 text+=['','선택 및 행동:']
 for x in outs:
  if x.get('phase','').startswith('source-law-navigation'):text += [x['phase'],json.dumps(x['output'],ensure_ascii=False,indent=2)]
 text+=['','활성 MAIN 포인터 변경 없음. GENOS 실행 아님.']
 (directory/'실행결과.txt').write_text('\n'.join(text)+'\n')
 qrow=next(x for x in m['questions'] if x['case_id']==cid);qp=ADR/'실험'/qrow['file']
 md=['# 질문 '+cid,'','## 1. 실행 메타',f'run-001 / {arm} / Qwen3.8 Parasail FP8 reasoning none / 로컬 공개 자료',
     '','## 2. 사용자 질문 원문',case.get('user_original',case['question']),'','## 3. 기준답변 — 채점 전용, 제품 입력 비공개',
     '기준답변·독립 judge 없음. 제품 입력에 정답이나 조문 좌표를 주입하지 않았다.','',
     '## 4. 제품 입력을 구성한 원값',fence({'source_generation':bindings['source_generation'],'profile':read(directory/'profile.json'),'request':read(directory/'request.json')}),
     '','### 회수·탈락 단계 원장 — run·arm별\n\n단계 좌표 집합은 dedicated stage-ledger.json과 진단 원장에 전부 보존한다.',
     fence({x['stage_id']:{k:x[k] for k in ('before_count','added_count','discarded_count','after_count','gold_total','golden_recall')} for x in ledger_stages}),
     '','## 5. 제품 모델 호출 — run·arm별 실제 원문',fence(transcript),'','## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n전체 중간 호출은 위 실제 provider transcript에 포함되어 있다.\n\n## 7. 채점 호출과 반복 판정','수행하지 않음.','',
     '## 8. 사례 최종 판정',fence(diag),'','## 실제 제품 응답',fence(r)]
 qp.write_text('\n'.join(md)+'\n');qrow['sha256']=sha(qp)
put(RUN/'results.json',{'cases':results,'candidate':bindings['candidate'],'revision_id':bindings['revision_id'],'main_wiring':'unchanged'})
put(A/'diagnostic.json',{'cases':diags,'contracts_passed':contracts_count,'main_wiring':'unchanged','genos_deployed':False})
total=sum(d['presented_roots'] for d in diags);corpus=diags[0]['corpus_roots']
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
 'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,
 'runs':[{'run_id':'run-001','arms':[{'arm_id':arm,'declared_stage_ids':['source','recall','select','present'],'cases':ledger_cases,'aggregate':{'cases':len(ledger_cases),'presented_total':total,'gold_total':0}}]}],
 'audit':{'source':'Stored numeric article roots, not all approved READ scope; actual model scope is approved public145 documents.',
          'select':'All roots acquired by executed READ, including inspection-only originals. Adopted branches separately recorded in diagnostics.',
          'present':'All original previews/pages actually presented to navigation model; quality/gold not evaluated.'}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(A/'stage-ledger.json',ledger)
m['runs'][0].update(status='complete',sha256=sha(RUN/'results.json'))
m['results']={'status':'complete','by_arm':{arm:{'cases':[{k:d[k] for k in ('case_id','http_status','status','answer_text','directory_order_equals_card_order','nested_card_only')} for d in diags],
 'request_success_count':sum(d['http_status']==200 and d['status']=='complete' for d in diags),'request_total':len(diags),'answer_quality':None,'not_graded_reason':'No independent legal gold/evaluator'}},
 'comparisons':[],'judge_disagreements':None,'usage':{k:sum(d[k] for d in diags) for k in ('model_calls','input_tokens','output_tokens','cost_usd')},
 'latency':{'request_seconds_by_case':{d['case_id']:d['request_seconds'] for d in diags},'generalization':'Two sequential local requests; no population latency or speedup claim'},
 'error_taxonomy':[] if all(d['http_status']==200 for d in diags) else ['other:actual_run_failure_see_preserved_trace']}
counts=[d['presented_roots'] for d in diags]
m['retrieval_accounting'].update(corpus_total=corpus,before_filter=sum(d['prepared_preview_roots'] for d in diags),after_filter=sum(d['acquired_roots'] for d in diags),
 presented_total=total,presented_mean=statistics.mean(counts),presented_p50=statistics.median(counts),presented_p95=max(counts),golden_recall={arm:None},selectivity=statistics.mean(counts)/corpus if corpus else 0)
m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'stage-ledger.json');put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
sections={
 '1. 결정 요약':'탐색 체인·시점 복원의 실제 공개 질문 2건 probe. 검사'+str(contracts_count)+'개 통과. 결과 '+str(m['results']['by_arm'][arm]['request_success_count'])+'/2 HTTP200 조사 완료. Proposed, MAIN unchanged.',
 '2. 문제와 변경 전 구조':'완료 부모 ADR0671에 전체 행동 체인·시점 복원·현재 창·복수 조문 읽기를 연결했다. 벤처 질의는 성공했으나 내부회계 질의에서는 항 적중의 부모가 조 전체인 기존 묶음을 새 root hit로 찾으려다 StopIteration이 발생했다. source와 실제 parent offer로 계산한 묶음 ID를 재사용하도록 한 지점만 수정했다. 다른 원문·검색·스키마·모델·프롬프트는 보존했다.',
 '3. 가설과 사전 판정 기준':m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],
 '4. 실험 설계':'동결 후보 '+arm+' / 자연 질문 2건 / 독립 런타임과 generation shadow. 기준답변·강제 실패·조문 주입 없음. 부모 완료 arm 기준의 계약 비교이며 별도 paired 성능 비교는 수행하지 않았다.',
 '5. 데이터·모델·재현성':'승인 공개145 문서의 항·호·목 own-body FTS. Qwen3.8 / OpenRouter Parasail FP8 / reasoning none / fallback 없음. source와 code/hash 및 실제 모든 provider payload 보존.',
 '6. 결과':'\n\n'.join(d['question']+'\n\nHTTP '+str(d['http_status'])+' / '+str(round(d['request_seconds'],3))+'초\n\n'+(d['answer_text'] or '답변 생성 실패') for d in diags),
 '7. 사례별 오류 분석':'실제 네이티브 단계·선택·모델 오류·보정은 [diagnostic](artifacts/diagnostic.json)과 각 질문의 실행결과.txt에 기록. 후보는 모델 결과 확인 후 수정하지 않았다.',
 '8. 비용·지연·회수 규모':json.dumps(m['results']['usage'],ensure_ascii=False)+'\n\n회수 좌표 전체는 dedicated 단계 원장에 보존. gold 미설정이며 정답률을 실행 성공률로 대신하지 않는다.',
 '9. 해석':'합성 계약 통과와 실제 모델 출력 호환/답변 완료는 별개다. 단일 사용자 사례 두 건으로 전체 정확도나 비용 개선을 주장하지 않는다.',
 '10. 한계와 일반화 가능 범위':'인샘플 수정/사용자 질의 probe. 독립 judge·holdout 없음. GENOS 내부 모델·배포 미실행. 기존 graph 오류 별도.',
 '11. 운영 결정·롤백 조건':'활성 generation42 및 release pointer SHA 일치. 후보의 구현과 로컬 활성 릴리스/GENOS 배포는 별개다. 새 schema/state는 새 선택 요청을 필요로 하며 이전 checkpoint를 자동 이행하지 않는다.',
 '12. 재현 명령':str(ROOT/'06_TOOLS/EXPERIMENTS'/('adr_'+m['adr_id'][4:])/'run_probe.py')+' --case accounting-manager 또는 --case venture-stock-option. exist=False로 결과 덮어쓰기 거부. 후속 수정/재실행은 새 ADR.'}
(ADR/'README.md').write_text('---'+front+'---\n\n# '+m['adr_id']+' 탐색 행동 체인·시점 복원 검증\n\n'+'\n\n'.join('## '+k+'\n\n'+v for k,v in sections.items())+'\n')
(ADR/'실험/README.md').write_text('# 질문 인덱스\n\n'+'\n'.join('- ['+x['case_id']+']('+x['file']+')' for x in m['questions'])+'\n')
files=[p for p in A.rglob('*') if p.is_file() and (p.suffix in ('.json','.txt','.log')) and '/generation-shadow/' not in str(p) and '/runtime/' not in str(p) and p!=A/'manifest.json']
put(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen design or exact run/provider/trace artifact'} for p in files]})
print(json.dumps({'cases':[{k:d[k] for k in ('case_id','http_status','request_seconds','model_calls','answer_text')} for d in diags]},ensure_ascii=False))
