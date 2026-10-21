"""Post-run exact evidence accounting; never changes product input or frozen design."""
from pathlib import Path
import copy, gzip, hashlib, json, sqlite3, statistics, sys
R=Path(__file__).resolve().parents[3];A=R/sys.argv[1]
read=lambda p:json.loads(p.read_text());canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def ungz(p):
 with gzip.open(p,'rt',encoding='utf8') as f:return json.load(f)
def ro(p):
 c=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row;return c
f=read(A/'artifacts/design/frozen.json');m=read(A/'실험/manifest.json')
for p,h in f['bindings'].items():assert sha(R/p)==h,p
scope=set(read(R/f['release']['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
with ro(R/f['release']['data_path']/'navigation/navigation.sqlite') as db:
 sources={r['id']:json.loads(r['json']) for r in db.execute('SELECT id,json FROM source WHERE document_id IN ('+','.join('?' for _ in scope)+')',tuple(scope))}
def identities(ids):
 return [json.loads(k) for k in sorted({canon({'doc_id':sources[s]['document_id'],'node':int(sources[s]['unit_id'])}) for s in ids if s in sources and str(sources[s]['unit_id']).isdigit()})]
def text_sources(v):
 out={}
 def walk(x):
  if isinstance(x,dict):
   if x.get('source_id') in sources and isinstance(x.get('text'),str) and x['text']:out[x['source_id']]=x['text']
   for c in x.values():walk(c)
  elif isinstance(x,list):
   for c in x:walk(c)
 walk(v);return out
corpus=identities(sources);rows=[];lruns=[]
plan=m['design']['retrieval_stage_plan']['stages_by_arm']['baseline']
for number,case in enumerate(f['cases'],1):
 D=A/'artifacts'/case['run_id'];record=m['runs'][number-1]
 if not (D/'result.json').exists():
  record.update(status='invalid',artifact_path='',sha256=None,note='Not executed after prerequisite harness failure; follow-up reserved before corrected run.')
  row={'case_id':case['case_id'],'run_id':case['run_id'],'executed':False,'model_calls':0,'error':'Preflight harness failure in first case; second case not executed.'};rows.append(row)
  (A/'실험'/m['questions'][number-1]['file']).write_text('# '+case['case_id']+'\n\n## 실행 메타\n\n미실행. 첫 사례의 준비 단계 연결 누락으로 이 실행은 취소했다. 후속 ADR0855에서 별도 동결했다.\n\n## 사용자 질문 원문\n\n'+case['question']+'\n\n제품 모델 호출·원응답·채점·회수 기록 없음. 기준답변 없음.\n')
  continue
 result=read(D/'result.json');calls=read(D/'calls.json');generations=read(D/'generations.json')
 response=read(D/'response.json') if (D/'response.json').exists() else {};output=response.get('body') or {};answer=output.get('answer') or {};answer_text=answer.get('text') or ''
 events=[];stages=[];acquired=set()
 for journal in (D/'runtime').rglob('journal.sqlite'):
  with ro(journal) as db:
   events.extend({'seq':r['seq'],'kind':r['kind'],'payload':json.loads(r['payload_json'])} for r in db.execute('SELECT seq,kind,payload_json FROM event ORDER BY seq'))
   stages.extend({'entity_id':r['entity_id'],'payload':json.loads(r['payload_json'])} for r in db.execute("SELECT entity_id,payload_json FROM entity_version WHERE kind='case_stage' ORDER BY created_seq"))
   acquired.update(r[0] for r in db.execute('SELECT DISTINCT source_id FROM evidence_unit'))
 recalled={s for stage in stages if stage['entity_id']=='case:RECALL' for s in stage['payload'].get('selected_for_read',[])}
 presented=set()
 for call in calls:
  if call.get('http_status')!=200:continue
  canonical=D/'canonical'/f"{call['canonical_generation']:03d}.json.gz"
  if canonical.exists():
   view=ungz(canonical)['view'];wire=ungz(D/'wire'/f"{call['call']:03d}-before-provider.json.gz")
   messages='\n'.join(msg['content'] for msg in wire['messages'])
   # Compare serialized exact strings with the actual attempted wire. Source
   # coordinates are recovered from that call's canonical view, never guessed.
   for sid,text in text_sources(view).items():
    if json.dumps(text,ensure_ascii=False)[1:-1] in messages:presented.add(sid)
 fulltext=read(D/'fulltext-preflight.json') if (D/'fulltext-preflight.json').exists() else None
 schema_errors=[e for e in events if e['kind']=='OUTPUT_SCHEMA_INVALID']
 rejected=[e for e in events if 'REJECT' in e['kind'] or 'REPAIR' in e['kind'] or 'RETRY' in e['kind']]
 trace={'schema_errors':schema_errors,'rejected_or_repaired':rejected,'minimal_output':[e for e in events if e['kind'] in ('MODEL_MINIMAL_OUTPUT_CONTRACT','MODEL_OUTPUT_RECONSTRUCTED')],'fulltext_directories':[e for e in events if e['kind']=='LAW_FULLTEXT_DIRECTORY'],'stages':[{'entity_id':s['entity_id'],'keys':list(s['payload'])} for s in stages]}
 with gzip.open(D/'trace.json.gz','wt',encoding='utf8') as z:json.dump(trace,z,ensure_ascii=False)
 row={'case_id':case['case_id'],'run_id':case['run_id'],'executed':True,'http_status':result.get('http_status'),'model_calls':result['model_calls'],'seconds':result['seconds'],'answer_emitted':bool(answer_text.strip()),'answer_chars':len(answer_text),'fulltext_preflight_ok':bool(fulltext and fulltext['sample_hits']),'fulltext_law_count':(fulltext or {}).get('law_page',{}).get('total'),'fulltext_discovery_events':len(trace['fulltext_directories']),'navigation_calls':sum(c['stage'].startswith('source-law-navigation-') for c in calls),'schema_errors':len(schema_errors),'accepted_generations':sum(g.get('accepted',False) for g in generations),'generation_rejections':[g for g in generations if not g.get('accepted',False)],'wire_schema_range_bytes':[min((c['schema_bytes'] for c in calls),default=0),max((c['schema_bytes'] for c in calls),default=0)],'raw_schema_errors':[c for c in calls if c.get('raw_output_schema_errors')],'error':result.get('exception') or output.get('detail') or output.get('error'),'presented_roots':len(identities(presented)),'active_pointer_unchanged':result['pointer_before']==result['pointer_after'],'usage':{k:sum(u.get(k,0) or 0 for u in result['usage']) for k in ('input_tokens','output_tokens','cost_usd')}}
 assert row['active_pointer_unchanged'] and not (presented-set(sources))
 rows.append(row);put(D/'diagnostic.json',row)
 lcases=[]
 for scheduled in f['cases']:
  current=scheduled['case_id']==case['case_id'];before=[];ledger=[]
  sets=[corpus,identities(recalled),identities(acquired),identities(presented)] if current else [[],[],[],[]]
  reasons=['Approved public scope catalogue','Not in observed recall','No acquired source receipt','Exact original text not observed in a successful physical model input']
  for j,after in enumerate(sets):
   bm={canon(x):x for x in before};am={canon(x):x for x in after};added=[am[k] for k in sorted(am.keys()-bm.keys())];discarded=[bm[k] for k in sorted(bm.keys()-am.keys())]
   ledger.append({**plan[j],'executed':current,'skip_reason':None if current else 'Frozen separate-case process '+scheduled['run_id'],'before':before,'added':added,'discarded':discarded,'after':after,'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},'discard_receipts':[{'identity':x,'reason':reasons[j]} for x in discarded],'discard_reason_counts':{reasons[j]:len(discarded)} if discarded else {},'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,'golden_recall':None,'gold_before_identities':[],'gold_added_identities':[],'discarded_gold':[],'gold_after_identities':[]});before=after
  lcases.append({'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate','arm_id':'baseline','case_id':scheduled['case_id'],'gold_total':0,'gold_identities':[],'stages':ledger})
 lruns.append({'run_id':case['run_id'],'arms':[{'arm_id':'baseline','declared_stage_ids':[p['stage_id'] for p in plan],'cases':lcases,'aggregate':{'cases':len(lcases),'executed_cases':1,'skipped_cases':len(lcases)-1,'presented_total':len(identities(presented)),'gold_total':0}}]})
 record.update(status='complete',sha256=sha(D/'result.json'))
 summary_text=json.dumps(row,ensure_ascii=False,indent=2)
 (A/'실험'/m['questions'][number-1]['file']).write_text('# '+case['case_id']+'\n\n## 1. 실행 메타\n\n'+case['run_id']+' / baseline / MAIN82 / 로컬 실제 서비스 / 외부 Qwen3.8 Parasail FP8 reasoning none / 단일 실행. 원문 상태 exact.\n\n## 2. 사용자 질문 원문\n\n'+case['question']+'\n\n## 3. 기준답변 — 채점 전용, 제품 입력 비공개\n\n공개 합성 질문이다. 정답·gold 좌표·의미 채점 없음. 스키마와 실행 경계만 검증한다.\n\n## 4. 제품 입력을 구성한 원값\n\n[동결 설계](../artifacts/design/frozen.json), [실제 요청](../artifacts/'+case['run_id']+'/request.json), [프로필](../artifacts/'+case['run_id']+'/profile.json), [서비스 선택](../artifacts/'+case['run_id']+'/health.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[회수 원장](../artifacts/retrieval-ledger.json.gz)에 전체 article-root 좌표와 단계별 탈락 이유를 기록했다. fulltext-preflight는 제품 입력으로 주입하지 않은 별도 조회다.\n\n## 5. 제품 모델 호출 — run·arm별 실제 원문\n\n../artifacts/'+case['run_id']+'/provider/call-* 의 request.json(시스템·사용자), validation-schema.json, response.json과 usage.json에 원값을 보존한다. canonical/*.json.gz는 요청별 원본 계약, wire/*json.gz는 provider 변환 전 실제 압축 스키마다. 산출물 목록의 SHA256으로 결속한다. 모델 호출이 0이면 해당 원응답이 없다.\n\n## 6. 중간 LLM 호출 — router/compiler/verifier/repair\n\n[calls.json](../artifacts/'+case['run_id']+'/calls.json), [generations.json](../artifacts/'+case['run_id']+'/generations.json), [trace.json.gz](../artifacts/'+case['run_id']+'/trace.json.gz)에 실패와 수정 호출을 모두 남겼다.\n\n## 7. 채점 호출과 반복 판정\n\n채점0회·질문당1회·단일 arm. A/B 성능 비교와 법률 정답률이 아니다.\n\n## 8. 사례 최종 판정\n\n```json\n'+summary_text+'\n```\n\n최종 응답 전체는 response.json에 보존하며, 없으면 준비 단계 실패다.\n')
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,'runs':lruns,'audit':{'gold':'No legal correctness scoring; gold unavailable','sets':'Aggregate observed canonical source sets; independent preflight excluded. Original text checked against physical model request after reversible projection. Failed transport presentation unconfirmed and excluded.'}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();lp=A/'artifacts/retrieval-ledger.json.gz'
with gzip.open(lp,'wt',encoding='utf8') as z:z.write(canon(ledger))
first=lruns[0]['arms'][0]['cases'];counts=[x['stages'][-1]['after_count'] for x in first];after=sum(x['stages'][1]['after_count'] for x in first)
m['retrieval_accounting'].update(corpus_total=len(corpus),before_filter=len(corpus),after_filter=after,presented_total=sum(counts),presented_mean=statistics.mean(counts),presented_p50=statistics.median(counts),presented_p95=max(counts),golden_recall=None,selectivity=statistics.mean(counts)/len(corpus));m['retrieval_accounting']['stage_ledger']['sha256']=sha(lp)
executed=[x for x in rows if x['executed']]
summary={'adr_id':m['adr_id'],'cases':rows,'model_calls':sum(x['model_calls'] for x in rows),'answer_count':sum(x.get('answer_emitted',False) for x in rows),'schema_error_count':sum(x.get('schema_errors',0) for x in rows),'main_unchanged':all(x['active_pointer_unchanged'] for x in executed),'usage':{k:sum(x['usage'][k] for x in executed) for k in ('input_tokens','output_tokens','cost_usd')},'latency':{'p50':statistics.median(x['seconds'] for x in executed),'p95':max(x['seconds'] for x in executed),'n':len(executed)}}
put(A/'artifacts/summary.json',summary)
m['results'].update(status='complete',by_arm={'baseline':{'total_count':len(executed),'correct_count':None,'answer_count':summary['answer_count'],'schema_error_count':summary['schema_error_count'],'interpretation':'Technical observations only; missing transport or unreached stage is inconclusive, not a pass.'}},comparisons=[],judge_disagreements=0,usage=summary['usage'],latency=summary['latency'],error_taxonomy=[{'case_id':x['case_id'],'type':'other','reason':str(x.get('error') or x.get('generation_rejections'))} for x in rows if x.get('error') or x.get('generation_rejections')])
put(A/'실험/manifest.json',m)
front=(A/'README.md').read_text().split('---',2)[1]
table='| 질문 | 실행 | 모델 호출 | fulltext 사전 조회 | 탐색 호출 | 스키마 거절 | 답변 |\n|---|---|---:|---|---:|---:|---|\n'+'\n'.join('| '+str(x['case_id'])+' | '+str(x['executed'])+' | '+str(x['model_calls'])+' | '+str(x.get('fulltext_preflight_ok'))+' | '+str(x.get('navigation_calls',0))+' | '+str(x.get('schema_errors',0))+' | '+str(x.get('answer_emitted',False))+' |' for x in rows)
sections={'1. 결정 요약':f"모델 {summary['model_calls']}회, 답변 {summary['answer_count']}/{len(f['cases'])}, 출력 스키마 거절 {summary['schema_error_count']}회. 실제 상세 판정은 summary.json·질문별 기록과 아래 해석을 따른다. MAIN82·GENOS·기존 ZIP 변경 없음.",'2. 문제와 변경 전 구조':'현장 사진은 source-law-navigation-1에서 약180초 대기 후 transport timeout이며 response_format 78,856B다. 이전 압축 검사는 합성 계약 크기 측정으로 실제 fulltext 모델 검증을 대신하지 않는다. 현재 MAIN82를 변경하지 않고 확인한다.','3. 가설과 사전 판정 기준':f['hypothesis']+'\n\n'+f['success_criteria']+'\n\n'+f['failure_criteria'],'4. 실험 설계':'완료 부모 ADR0853/integrated. baseline 한 arm, 사전 동결한 공개 질문2개, 질문당1회. 제품 코드·프롬프트·검색 정책 변경 없음. 전송 감사와 원값 기록만 추가.','5. 데이터·모델·재현성':'[동결 설계](artifacts/design/frozen.json)에 MAIN82 코드370파일·세대·fulltext·서비스·실행기 SHA256을 묶었다. 승인 공개65문서, Qwen3.8/Parasail FP8 reasoning none, fallback 없음, 최대40물리호출/질문·1800초, 실험 재시도0. 법령 효력·정답 검증은 수행하지 않았다.','6. 결과':table+'\n\n[전체 결과](artifacts/summary.json) / [질문별 기록](실험/README.md)','7. 사례별 오류 분석':'원시 실패를 generations.json·calls.json·trace.json.gz 및 로그에 보존한다. 실제 fulltext DB 실패, 모델 전송 실패, JSON/복원 실패, 판단 제안 거절을 구분한다.','8. 비용·지연·회수 규모':json.dumps({'usage':summary['usage'],'latency':summary['latency'],'corpus_article_roots':len(corpus)},ensure_ascii=False)+'\n\n회수 원장은 artifacts/retrieval-ledger.json.gz. 승인 scope 전체→회수→확보→실제 모델 입력 원문 집합을 기록한다. 금표준 부재로 golden recall은 미측정.','9. 해석':'한 번의 실행에서 도달한 단계만 검증한다. 미도달 단계나 전송 실패는 스키마 통과로 해석하지 않는다. 현장 timeout을 모델 busy 또는 스키마 오류로 단정하지 않는다.','10. 한계와 일반화 가능 범위':'\n\n'.join(f['limitations']),'11. 운영 결정·롤백 조건':'제품 코드·선택 포인터·데이터·GENOS는 그대로다. 후보 승격 없음. 실험 상태만 격리되며 재실행·개선 후보는 새 ADR로 사전 동결한다.','12. 재현 명령':'WSL /home/jin/8-AGENT에서 .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_'+m['adr_id'].split('-')[1]+'/run_probe.py run-001 (또는 run-002). 완료 디렉터리는 덮어쓰지 않는다. 추가 호출은 새 ADR 필요. 최종 검사: stable runner adr_structure.py hash, validate --final, graph.'}
(A/'README.md').write_text('---'+front+'---\n\n# '+m['adr_id']+' MAIN82 fulltext 스키마 감사\n\n'+'\n\n'.join('## '+k+'\n\n'+v for k,v in sections.items())+'\n')
(A/'실험/README.md').write_text('# 질문별 실행 인덱스\n\n'+table+'\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
idx=R/'04_EXPERIMENTS/ADR/README.md';link='['+m['adr_id']+' MAIN82 fulltext 스키마 감사]('+A.name+'/README.md)'
if link not in idx.read_text():idx.write_text(idx.read_text()+'\n- '+link+' — 실제 호출 '+str(summary['model_calls'])+'회, MAIN 불변.\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']+list((R/'06_TOOLS/EXPERIMENTS'/('adr_'+m['adr_id'].split('-')[1])).glob('*.py'))
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size} for p in sorted(files)]})
print(json.dumps({k:v for k,v in summary.items() if k!='cases'},ensure_ascii=False))
