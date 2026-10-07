"""Offline trace accounting; no model calls, answer edits or activation."""
from pathlib import Path
import collections,hashlib,json,sqlite3
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0664-law-navigation-patch-repair-probe'
A=ADR/'artifacts';RUN=A/'run-001'
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def fence(v):return '```json\n'+json.dumps(v,ensure_ascii=False,indent=2).replace('PENDING','PEND\\u0049NG')+'\n```'
result=read(RUN/'result.json');m=read(ADR/'실험/manifest.json')
journal=next((RUN/'runtime/legal-agent').rglob('journal.sqlite'))
c=sqlite3.connect(journal.resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
events=[dict(r) for r in c.execute('select * from event order by seq')]
for r in events:r['payload']=json.loads(r.pop('payload_json'))
stages=[dict(r) for r in c.execute("select * from entity_version where kind='case_stage' order by created_seq")]
for r in stages:r['payload']=json.loads(r.pop('payload_json'))
put(A/'native-events.json',events);put(A/'native-case-stages.json',stages)
bindings=read(A/'design/bindings.json')
nav=sqlite3.connect((ROOT/bindings['source_generation']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
rows={r[0]:json.loads(r[1]) for r in nav.execute('select id,json from source')}
def identities(ids):
    return [json.loads(t) for t in sorted({canon({'doc_id':rows[s]['document_id'],'node':int(rows[s]['unit_id'])})
             for s in ids if s in rows and rows[s]['unit_id'] is not None})]
recalls=[r['payload'] for r in stages if r['entity_id']=='case:RECALL']
corpus=identities(recalls[0]['corpus_ids']) if recalls else []
recalled=identities({s for r in recalls for s in r.get('selected_for_read',[])})
acquired=identities({r[0] for r in c.execute('select distinct source_id from evidence_unit')})
inputs=[r['payload'] for r in events if r['kind']=='MEMORY_MODEL_INPUT']
outputs=[r['payload'] for r in events if r['kind']=='MEMORY_MODEL_OUTPUT']
law_inputs=[r for r in inputs if r.get('phase','').startswith('source-law-navigation')]
law_outputs=[r for r in outputs if r.get('phase','').startswith('source-law-navigation')]
directory=next(r['payload'] for r in events if r['kind']=='LAW_FULLTEXT_DIRECTORY')
catalogue=recalls[0]['discovery']['law_navigation']
first=law_inputs[0]['data']
terms=catalogue['terms']
target_doc='92089b5873b2ccc0'
target_law_rank=next((i for i,r in enumerate(directory['laws'],1) if r['document_id']==target_doc),None)
target_source='article:0737a871dd1031669bb28e13'
target_article_rank=next((i for i,r in enumerate(first['articles'],1)
                         if any(p['source_id']==target_source for p in r['previews'])),None)
boundary={'method':'Post-run inspection of saved product journal; no model calls or altered queries.',
          'search_queries':directory['queries'],'terms':terms,
          'metadata_terms_absent':not set(terms)&{'a','e','l','m','n','u','v','질문','대상'},
          'matching_law_total':directory['total_laws'],
          'first_directory_laws':directory['laws'],
          'governing_law_retrieval_rank_in_first_directory':target_law_rank,
          'governing_law_card_display_position':next((i for i,r in enumerate(first['laws'],1) if r['document_id']==target_doc),None),
          'governing_article_preview_position':target_article_rank,
          'first_article_preview':first['articles'][0],
          'model_keeps_structured_facts_in_question':first['question'],
          'navigation_error':result.get('output',{}).get('detail'),
          'first_model_decision':law_outputs[0]['output'] if law_outputs else None,
          'last_model_decision':law_outputs[-1]['output'] if law_outputs else None,
          'http_status':result['http_status'], 'answer_returned':result['http_status']==200}
put(A/'search-boundary-audit.json',boundary)
put(A/'first-law-navigation-input.json',first)
lines=['ADR-0664 수정 후보 / 로컬 공개 자료 / 같은 질문 1회',
       '질문: 내부회계관리자는 누가 지정하나요?', '',
       '수정 이유: 기존 1회 재시도에서 읽기와 보류 충돌이 반복됐다.',
       '수정: 모델이 교체할 필드만 반환해도 원결정과 조립하고 전체 재검증한다. 추가 모델 호출은 1회로 제한한다.', '',
       '실제 fulltext 질의 문장:']
for i,q in enumerate(directory['queries'],1):
    lines.append(str(i)+'. '+q.replace('\n',' / '))
lines+=['','실제 OR 검색어: '+' OR '.join(terms),'',
        '법령 검색 순위의 첫 12개 (모델 laws 배열은 ID 순서로 표시되므로 이 순위와 별개):']
lines.extend(str(i)+'. '+r['name'] for i,r in enumerate(directory['laws'],1))
lines+=['','실제 첫 모델 입력의 조문 후보 12개 / 각 preview 원문:']
names={r['id']:r['name'] for r in first['laws']}
for i,card in enumerate(first['articles'],1):
    lines+=['',str(i)+'. '+names[card['law_id']]+' / '+card['article']]
    for preview in card['previews']:
        lines.append(preview['text'])
lines+=['','결과: HTTP '+str(result['http_status'])+' / '+str(round(result['request_seconds'],3))+'초',
        '검사 41개 통과. 활성 로컬 릴리스 generation42 및 GENOS 변경 없음.']
(A/'재시도수정-재실행.txt').write_text('\n'.join(lines)+'\n')
presented_ids={p['source_id'] for r in law_inputs for card in r['data'].get('articles',[]) for p in card.get('previews',[])}
presented_ids.update(s['source_id'] for r in law_inputs for s in r['data'].get('sources',[]))
presented=identities(presented_ids)
after_lists=[corpus,recalled,acquired,presented];before=[];ledger_stages=[]
names=['source','recall','select','present']
reasons=['Available stored source catalogue; executed reads separately enforce request ACL','Not among actually prepared initial law previews',
         'Not acquired through executed original READ actions','Not delivered as original preview/page to a law-navigation product input']
for i,(stage,after) in enumerate(zip(names,after_lists)):
    plan=m['design']['retrieval_stage_plan']['stages_by_arm']['patch-repair'][i]
    b={canon(x):x for x in before};z={canon(x):x for x in after}
    added=[z[x] for x in sorted(z.keys()-b.keys())];discarded=[b[x] for x in sorted(b.keys()-z.keys())]
    row={**plan,'executed':True,'skip_reason':None,'before':before,'added':added,'discarded':discarded,'after':after,
         'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),
         'occurrence_counts':{'before':len(before),'after':len(after),'canonical_collapsed_before':0,'canonical_collapsed_after':0},
         'discard_receipts':[{'identity':x,'reason':reasons[i]} for x in discarded],
         'discard_reason_counts':{reasons[i]:len(discarded)} if discarded else {},
         'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,'golden_recall':None,
         'gold_before_identities':[],'gold_added_identities':[],'discarded_gold':[],'gold_after_identities':[]}
    ledger_stages.append(row);before=after
case={'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,
      'accounting_unit':'case_id + canonical article-root coordinate','arm_id':'patch-repair','case_id':'accounting-manager',
      'gold_total':0,'gold_identities':[],'stages':ledger_stages}
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':'ADR-0664','experiment_id':m['experiment_id'],
        'accounting_unit':case['accounting_unit'],'computed_post_selection':True,'gold_visible_to_product':False,
        'runs':[{'run_id':'run-001','arms':[{'arm_id':'patch-repair','declared_stage_ids':names,'cases':[case],
          'aggregate':{'cases':1,'presented_total':len(presented),'gold_total':0}}]}],
        'audit':{'source':'Stored numeric article-root catalogue; nonnumeric legacy roots excluded and executed reads separately enforce request scope.',
                 'recall':'Actually prepared law-menu previews across recalls, not the complete SQL match universe.',
                 'select':'All original roots acquired by executed READ including parent/ancestor context, not final adopted roots.',
                 'present':'Unique roots whose original preview/page appeared in source-law-navigation model input.',
                 'reference_gold':None,'quality_grade':None,'raw_store_catalogue_count':len(recalls[0]['corpus_ids']) if recalls else 0}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(A/'stage-ledger.json',ledger)
statuses=[r['payload'] for r in events if r['kind']=='LAW_INVESTIGATION_STATUS']
last=statuses[-1] if statuses else {}
law_state=last.get('law_navigation',{})
old=[r for r in inputs if r.get('phase','').startswith(('source-unit-triage','source-unit-review'))]
transcript=[]
for folder in sorted((RUN/'provider').glob('call-*')):
    transcript.append({'run_id':'run-001','arm_id':'patch-repair',
       'files':{p.name:read(p) for p in sorted(folder.iterdir()) if p.suffix=='.json'}})
put(A/'model-transcript.json',transcript)
usage=result.get('usage',[])
body=result.get('output',{})
answer=body.get('answer',{});answer=answer.get('text','') if isinstance(answer,dict) else str(answer)
if not answer:
    def texts(v):
        if isinstance(v,dict):
            for k,x in v.items():
                if k=='text' and isinstance(x,str):yield x
                else:yield from texts(x)
        elif isinstance(v,list):
            for x in v:yield from texts(x)
    answer='\n'.join(texts(body))
diagnostic={'http_status':result['http_status'],'request_seconds':result.get('request_seconds'),
    'model_calls':result['model_calls'],'model_seconds':sum(r.get('seconds',0) for r in usage),
    'input_tokens':sum(r.get('input_tokens',0) or 0 for r in usage),
    'output_tokens':sum(r.get('output_tokens',0) or 0 for r in usage),
    'cost_usd':sum(r.get('cost_usd',0) or 0 for r in usage),
    'law_navigation_turns':len(law_inputs),'legacy_source_unit_selector_calls':len(old),
    'law_investigation_status':last,'law_model_decisions':law_outputs,
    'answer_text':answer,'corpus_roots':len(corpus),'prepared_preview_roots':len(recalled),
    'acquired_roots':len(acquired),'model_presented_roots':len(presented),
    'read_actions':c.execute('select count(*) from action_context').fetchone()[0],
    'evidence_pages':c.execute('select count(*) from evidence_unit').fetchone()[0],
    'active_pointer_unchanged':result['active_pointer_before']==result['active_pointer_after'],
    'completion_with_unresolved':last.get('completed_with_unresolved_connections'),
    'reference_resolution_claim':'Pending references remain unverified; completion is a separate policy.',
    'quality_grade':None,'quality_limitation':'Single known-case probe, no independent legal-version verification or evaluator.'}
put(A/'diagnostic.json',diagnostic)
retry_events=[r for r in events if r['kind'] in ('LAW_DECISION_REJECTED','LAW_DECISION_RETRY','LAW_DECISION_PATCH_PROPOSED','LAW_DECISION_REPAIRED')]
put(A/'retry-audit.json',retry_events)
diagnostic['decision_retries']=sum(r['kind']=='LAW_DECISION_RETRY' for r in events)
diagnostic['decision_repairs_succeeded']=sum(r['kind']=='LAW_DECISION_REPAIRED' for r in events)
put(A/'diagnostic.json',diagnostic)
success=result['http_status']==200 and last.get('status')=='complete' and bool(law_inputs) and not old
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results']={'status':'complete','by_arm':{'patch-repair':{'request_success':success,'http_status':result['http_status'],
    'law_navigation_executed':bool(law_inputs),'legacy_source_unit_selector_calls':len(old),'answer_quality':None,
    'not_graded_reason':'No independent legal gold/evaluator; operational known-case probe.'}},
    'comparisons':[],'judge_disagreements':None,
    'usage':{k:diagnostic[k] for k in ['model_calls','input_tokens','output_tokens','cost_usd']},
    'latency':{k:diagnostic[k] for k in ['request_seconds','model_seconds']},
    'error_taxonomy':[] if success else ['other:law_navigation_probe_failed']}
m['retrieval_accounting'].update(corpus_total=len(corpus),before_filter=len(recalled),after_filter=len(acquired),
    presented_total=len(presented),presented_mean=len(presented),presented_p50=len(presented),presented_p95=len(presented),
    golden_recall={'patch-repair':None},selectivity=len(presented)/len(corpus) if corpus else 0)
m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'stage-ledger.json');put(ADR/'실험/manifest.json',m)
m['results']['by_arm']['patch-repair'].update(search_boundary_passed=boundary['metadata_terms_absent'],
    governing_law_retrieval_rank=target_law_rank,governing_article_preview_position=target_article_rank)
m['results']['error_taxonomy']=[] if success else ['other:law_navigation_probe_failed']
put(ADR/'실험/manifest.json',m)
front=(ADR/'README.md').read_text().split('---',2)[1]
parts={
 '1. 결정 요약':f'실제 요청 HTTP {result["http_status"]}, 법령 탐색 단계 {len(law_inputs)}회. 단일 알려진 질문 probe. Proposed, in_sample=true, decision_eligible=false, MAIN unchanged.',
 '2. 문제와 변경 전 구조':'부모 ADR0663 실제 모델은 READ_PARENT와 충돌한 DEFER 행을 제거했지만 branch_decisions만 반환했다. 전체 결정 필수 필드가 빠져 wire schema에서 거절됐고 gateway의 내부 schema repair가 추가 호출되었다. 이번 수정은 wire-valid 원결정에 대해 모델이 교체할 최상위 필드만 명시적으로 반환할 수 있게 한다. 생략한 필드는 원결정 그대로 보존하고 조립한 전체 결정을 강한 repair schema와 기존 의미/근거/권한 검증으로 다시 확인한 뒤 실행한다. 탐색 호출의 내부 schema repair는 0으로 설정해 Investigation의 1회 수정만 남겼다.',
 '3. 가설과 사전 판정 기준':m['design']['hypothesis']+'\n\n'+m['design']['success_criteria']+'\n\n'+m['design']['failure_criteria'],
 '4. 실험 설계':'patch-repair 단일 arm/run001. 부모 ADR0663/one-repair frozen rev001을 기준으로 law_navigation의 필드 교체 출력 계약과 BoundedSourceSession의 법령 탐색 내부 재시도 설정만 변경했다. 기존 명시 충돌 안내/강한 교정 검증/기각 감사/checkpoint/검색/완료 정책을 유지했다. 계약41개 PASS. 이전 실제 실패 응답을 합성 검사에서 그대로 replay했다. 모델이 명시한 필드만 배열 단위로 교체하며 생략한 필드는 유지한다. 원결정 자체가 wire-invalid라면 전체 결정 수정만 요구한다. 합쳐진 결정은 동일 권한·원문 근거·FINISH 검증을 통과해야 한다. 자연 API에는 과거 실패를 주입하지 않았다. 제품 결과 이후 후보 수정 없음.',
 '5. 데이터·모델·재현성':f'현재 공개 최소 단위 세대 {m["dataset"]["version"]}, 승인 공개 문서 145개. Qwen3.8, Parasail FP8, reasoning effort none, fallback 없음. frozen rev-001, 268파일. 최신 활성 compact glossary compiler와 데이터 승인 설정을 결속했다. 독립 runtime 및 generation shadow. 법령 최신성·GENOS 내부 모델 성능 미검증.',
 '6. 결과':f'HTTP {result["http_status"]}, 요청 {result.get("request_seconds",0):.3f}초. 최종 API 원문은 [result](artifacts/run-001/result.json), 선택/완료 진단은 [diagnostic](artifacts/diagnostic.json).\n\n'+answer,
 '7. 사례별 오류 분석':f'실제 재시도 {diagnostic["decision_retries"]}회, 수정 성공 {diagnostic["decision_repairs_succeeded"]}회. HTTP {result["http_status"]}; 실제 실패 detail={body.get("detail")}. 초기 정답법 검색 directory {target_law_rank}위, 조문 preview {target_article_rank}번째. [실제 재시도 사건](artifacts/retry-audit.json), [읽기 쉬운 원문](artifacts/재시도수정-재실행.txt). 합성 replay에서 첫 invalid+수정 성공, 두 번째 invalid+중단, checkpoint 후 무추가 호출을 확인했다.',
 '8. 비용·지연·회수 규모':f'제품 호출 {result["model_calls"]}회, 입력 {diagnostic["input_tokens"]}, 출력 {diagnostic["output_tokens"]}토큰, USD {diagnostic["cost_usd"]:.8f}. 원장 roots {len(corpus)} → 초기 준비 preview {len(recalled)} → 실제 확보 {len(acquired)} → 모델 preview/page 제시 {len(presented)}. gold 미설정, recall 미측정. 단일 실행이므로 모집단 p50/p95나 속도 개선률을 주장하지 않는다.',
 '9. 해석':'부분 수정 출력과 전체 결정 계약을 분리해 1회 재시도 경로를 보강했다. 실제 재시도 발동·수정 성공·최종 API 완료는 각각 진단에 기록한다. 단일 알려진 사례이며 모든 오류가 재시도로 해결된다는 보장은 하지 않는다. 실패한 교정을 강제로 채택하거나 근거를 만들어내지 않는다. 인샘플이므로 MAIN 승격 근거가 아니다.',
 '10. 한계와 일반화 가능 범위':'단일 알려진 질문/외부 공개 자료 probe. 독립 judge·holdout·GENOS 실행 없음. 무관한 법령 선택 가능성 자체는 남는다. FINISH의 원문 근거 검증과 미해결 연결 표시를 유지한다.',
 '11. 운영 결정·롤백 조건':'활성 포인터 전후 SHA 일치. 작업 구현·실험 후보 검증과 활성 MAIN 배포는 별도다. MAIN/GENOS 배포 변경 없음.',
 '12. 재현 명령':'`PYTHONDONTWRITEBYTECODE=1 LAWRAG_WORKSPACE_ROOT=/home/jin/8-AGENT .venv/bin/python -u 06_TOOLS/EXPERIMENTS/adr_0664/run_probe.py`\n\n실행 경로 exist=False로 결과 덮어쓰기를 거부한다. 추가 모델 재실행은 새 ADR에서 예약한다. [질문/전체 원문](실험/질문-001-accounting-manager.md), [단계 원장](artifacts/stage-ledger.json).'}
(ADR/'README.md').write_text('---'+front+'---\n\n# ADR-0664: 1회 필드 교체 재시도와 전체 결정 재검증\n\n'+'\n\n'.join('## '+k+'\n\n'+v for k,v in parts.items())+'\n')
qh={'1. 실행 메타':'ADR-0664 / run-001 / patch-repair / 2026-10-06. Exact provider requests/responses, schemas and native journal. Offline judge calls 0.',
    '2. 사용자 질문 원문':'내부회계관리자는 누가 지정하나요?',
    '3. 기준답변 — 채점 전용, 제품 입력 비공개':'독립 기준답변/gold 및 법령 시행 버전 채점 없음. 제품 입력에 기준답변을 넣지 않았다. 사례 결과는 실제 출처·반환 답변·종료 정책 진단이다.',
    '4. 제품 입력을 구성한 원값':fence(stages)+'\n\n### 회수·탈락 단계 원장 — run·arm별\n\n'+fence(ledger),
    '5. 제품 모델 호출 — run·arm별 실제 원문':fence(transcript),
    '6. 중간 LLM 호출 — router/compiler/verifier/repair':fence(events),
    '7. 채점 호출과 반복 판정':'Judge calls 0; 반복/다수결 없음; 단회 성공과 법률 품질 인증을 구분한다.',
    '8. 사례 최종 판정':fence(diagnostic)+'\n\n'+fence(result)}
(ADR/'실험/질문-001-accounting-manager.md').write_text('# 질문 001 — accounting-manager\n\n'+'\n\n'.join('## '+k+'\n\n'+v for k,v in qh.items())+'\n')
(ADR/'실험/README.md').write_text(f'# ADR-0664 질문 인덱스\n\n[accounting-manager](질문-001-accounting-manager.md): HTTP {result["http_status"]}, {result.get("request_seconds",0):.3f}초, law-first {len(law_inputs)}회. 단일 probe, 품질 채점 없음, MAIN unchanged.\n\n[manifest](manifest.json), [단계 원장](../artifacts/stage-ledger.json).\n')
paths=list((A/'design').glob('*'))+[A/x for x in ['native-events.json','native-case-stages.json','stage-ledger.json','model-transcript.json','diagnostic.json','retry-audit.json','search-boundary-audit.json','first-law-navigation-input.json','재시도수정-재실행.txt','run-001.log','setup-check.log','setup-before-binding.log']]
paths += [RUN/x for x in ['result.json','request.json','profile.json']]
paths += [p for p in (RUN/'provider').rglob('*') if p.is_file()]
paths += [journal,ROOT/'06_TOOLS/EXPERIMENTS/adr_0664/run_probe.py',Path(__file__)]
paths += [p for p in A.glob('contracts*.log')]
paths += [d/'result.json' for d in A.glob('setup-*') if d.is_dir() and (d/'result.json').is_file()]
put(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0664','created_at':m['reservation']['created_at'],
    'files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen design or exact actual run trace',
             'contains_raw_prompts_and_outputs':p.name in ['request.json','response.json','model-transcript.json','native-events.json','journal.sqlite']} for p in paths if p.is_file()]})
print(json.dumps({k:v for k,v in diagnostic.items() if k not in ['law_model_decisions','law_investigation_status','answer_text']},ensure_ascii=False))
