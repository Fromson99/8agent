"""Post-run accounting only; never invokes a model or alters runtime selection."""
from pathlib import Path
import collections, hashlib, json, sqlite3

ROOT=Path('/home/jin/8-AGENT')
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0659-internal-accounting-manager-stop-probe'
A=ADR/'artifacts'; RUN=A/'run-001'
def read(p): return json.loads(p.read_text())
def put(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def canon(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def fenced(v): return '```json\n'+json.dumps(v,ensure_ascii=False,indent=2)+'\n```\n'
result=read(RUN/'result.json'); manifest=read(ADR/'실험/manifest.json')
c=sqlite3.connect(next((RUN/'runtime/legal-agent').rglob('journal.sqlite')))
c.row_factory=sqlite3.Row
events=[dict(r) for r in c.execute('select * from event order by seq')]
for r in events:r['payload']=json.loads(r.pop('payload_json'))
stages=[dict(r) for r in c.execute("select * from entity_version where kind='case_stage' order by created_seq")]
for r in stages:r['payload']=json.loads(r.pop('payload_json'))
put(A/'native-events.json',events); put(A/'native-case-stages.json',stages)
recalls=[r['payload'] for r in stages if r['entity_id']=='case:RECALL']
originals=[r['payload'] for r in stages if r['entity_id']=='case:READ']
nav=sqlite3.connect(ROOT/read(A/'design/bindings.json')['generation']/'navigation/navigation.sqlite')
source_rows={r[0]:json.loads(r[1]) for r in nav.execute('select id,json from source')}
def identities(ids):
    rows={canon({'doc_id':source_rows[s]['document_id'],'node':int(source_rows[s]['unit_id'])})
          for s in ids if source_rows[s]['unit_id'] is not None}
    return [json.loads(s) for s in sorted(rows)]
corpus=identities(recalls[0]['corpus_ids'])
recalled=identities(set().union(*(set(r['selected_for_read']) for r in recalls)))
read_ids={r[0] for r in c.execute('select distinct source_id from evidence_unit')}
acquired=identities(read_ids)
ledger_stages=[]; before=[]
names=['source','recall','select','present']
after_lists=[corpus,recalled,acquired,acquired]
reasons=['Available store catalogue','Not among actual recalled candidates',
         'Not acquired: first 12 groups only; navigation blocked continuation',
         'Not shown to a product selection model']
for i,(name,after) in enumerate(zip(names,after_lists)):
    plan=manifest['design']['retrieval_stage_plan']['stages_by_arm']['shipped-r1'][i]
    b={canon(x):x for x in before}; z={canon(x):x for x in after}
    added=[z[x] for x in sorted(z.keys()-b.keys())]
    discarded=[b[x] for x in sorted(b.keys()-z.keys())]
    row={**plan,'executed':True,'skip_reason':None,'before':before,'added':added,
         'discarded':discarded,'after':after,'before_count':len(before),
         'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),
         'occurrence_counts':{'before':len(before),'after':len(after),
                              'canonical_collapsed_before':0,'canonical_collapsed_after':0},
         'discard_receipts':[{'identity':x,'reason':reasons[i]} for x in discarded],
         'discard_reason_counts':{reasons[i]:len(discarded)} if discarded else {},
         'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,
         'golden_recall':None,'gold_before_identities':[],'gold_added_identities':[],
         'discarded_gold':[],'gold_after_identities':[]}
    ledger_stages.append(row); before=after
case={'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,
      'gold_visible_to_product':False,'accounting_unit':'case_id + canonical article-root coordinate',
      'arm_id':'shipped-r1','case_id':'accounting-manager','gold_total':0,'gold_identities':[],
      'stages':ledger_stages}
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':'ADR-0659',
        'experiment_id':manifest['experiment_id'],'accounting_unit':case['accounting_unit'],
        'computed_post_selection':True,'gold_visible_to_product':False,
        'runs':[{'run_id':'run-001','arms':[{'arm_id':'shipped-r1','declared_stage_ids':names,
                    'cases':[case],'aggregate':{'cases':1,'presented_total':len(acquired),'gold_total':0}}]}],
        'audit':{'source':'Store catalogue, including inactive/non-FTS entries; FTS allowed count separately recorded',
                 'unstructured_store_entries_excluded':[s for s in recalls[0]['corpus_ids'] if source_rows[s]['unit_id'] is None],
                 'raw_store_entries':len(recalls[0]['corpus_ids']),
                 'recall':'Union of actually recalled candidates, two attempts',
                 'select':'Executed READ acquisition selection, not successful SELECT stage commit',
                 'present':'Distinct original roots actually delivered to product triage/review models; not final answer',
                 'final_answer_originals':0,'selection_commit':False,'reference_gold':None,
                 'occurrences':'Canonical snapshots deduplicated across attempts; READ page counts separately recorded'}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest()
put(A/'stage-ledger.json',ledger)
logs=[]
for line in (A/'product.log').read_text().splitlines():
    try: logs.append(json.loads(line))
    except ValueError: pass
reviews=[r for r in events if r['kind']=='MEMORY_MODEL_OUTPUT' and r['payload']['phase']=='source-unit-review']
reference_inputs=[r for r in events if r['kind']=='MEMORY_MODEL_INPUT' and 'reference-batch' in r['payload']['phase']]
triages=[r['payload']['data'] for r in events if r['kind']=='MEMORY_MODEL_INPUT' and r['payload']['phase']=='source-unit-triage']
stops=[r['payload'] for r in events if r['kind']=='UNIT_CANDIDATE_ACQUISITION_STOPPED']
usage=result['usage']
diagnostic={'request_seconds':result['request_seconds'],'app_setup_seconds':result['app_setup_seconds'],
 'http_status':result['http_status'],'error':result['output'],'field_execution':False,
 'model_calls':len(usage),'model_seconds':round(sum(r['seconds'] for r in usage),3),
 'input_tokens':sum(r['input_tokens'] for r in usage),'output_tokens':sum(r['output_tokens'] for r in usage),
 'cost_usd':sum(r['cost_usd'] for r in usage),'fulltext_discovery_count':len(recalls),
 'sql_calls':sum(r.get('event')=='fulltext.sql.timings' for r in logs),
 'sql_seconds':sum(r.get('elapsed_ms',0) for r in logs if r.get('event')=='fulltext.sql.timings')/1000,
 'catalogue_roots':len(corpus),'fts_allowed_roots':next(r['allowed_count'] for r in logs if r.get('event')=='fulltext.sql.started'),
 'recalled_roots':len(recalled),'acquired_groups':12,'acquired_original_roots':len(acquired),
 'read_actions':c.execute('select count(*) from action_context').fetchone()[0],
 'read_evidence_pages':c.execute('select count(*) from evidence_unit').fetchone()[0],
 'read_action_statuses':dict(c.execute('select status,count(*) from action_context group by status')),
 'initial_form_groups':sum(u['coordinate'].startswith(('서식','별지')) for u in triages[0]['units']),
 'model_sufficiency_reviews':[r['payload'] for r in reviews],
 'stop_decisions':stops,'reference_batches':[{'seq':r['seq'],'phase':r['payload']['phase'],
  'offered':len(r['payload']['data']['groups']),'omitted':r['payload']['data']['omitted_groups'],
  'all_groups':r['payload']['data']['all_group_summaries']} for r in reference_inputs],
 'read_locations':[{'group':u['id'],'law':triages[0]['laws'][u['law']],
                    'heading':u['article'],'coordinate':u['coordinate']} for u in triages[0]['units']],
 'interpretation':'Both sufficient=true outputs vetoed by 10 omitted applicability checks. Same first 10 incoming groups repeated after fulltext reentry; no FOLLOW reference reads occurred.',
 'active_release_unchanged':True}
put(A/'diagnostic.json',diagnostic)
transcript=[]
for n,folder in enumerate(sorted((RUN/'provider').glob('call-*')),1):
    transcript.append({'call':n,'run_id':'run-001','arm_id':'shipped-r1',
      'request':read(folder/'request.json'),'provider_response':read(folder/'response.json'),
      'schema':read(folder/'validation-schema.json'),'binding':read(folder/'binding.json'),
      'usage_and_latency':usage[n-1]})
put(A/'model-transcript.json',transcript)
m=manifest
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results']={'status':'complete','by_arm':{'shipped-r1':{'diagnostic_complete':True,
 'request_success':False,'http_status':422,'answer_quality':None,'not_graded_reason':'No final answer; runtime diagnostic only'}},
 'comparisons':[],'judge_disagreements':None,'usage':{k:diagnostic[k] for k in ('model_calls','input_tokens','output_tokens','cost_usd')},
 'latency':{k:diagnostic[k] for k in ('request_seconds','app_setup_seconds','model_seconds','sql_seconds')},
 'error_taxonomy':['other:pending_relation_fulltext_reentry_loop']}
m['retrieval_accounting'].update(corpus_total=len(corpus),before_filter=len(recalled),after_filter=len(acquired),
 presented_total=len(acquired),presented_mean=len(acquired),presented_p50=len(acquired),presented_p95=len(acquired),
 golden_recall=None,selectivity=len(acquired)/len(corpus))
m['retrieval_accounting']['stage_ledger']['sha256']=sha(A/'stage-ledger.json')
put(ADR/'실험/manifest.json',m)
old=(ADR/'README.md').read_text(); front=old.split('---',2)[1]
parts={
 '1. 결정 요약':'단일 질문 실제 진단 완료. 충분성 모델 오판보다 연결 보류를 전체 검색 재진입으로 취급하는 구현 문제가 재현됐다. 요청은 HTTP 422로 실패했다. Proposed, in-sample, decision_eligible=false이며 MAIN·현장 배포는 변경하지 않았다.',
 '2. 문제와 변경 전 구조':'발송 R1 검색·원문 읽기·연결·종료 코드를 격리해 실행했다. 12개 묶음을 읽고 연결 20개 중 10개를 판단한다. 나머지 적용 확인이 pending이 되지만 다음 연결 메뉴를 처리하지 않고 memory_rag가 RECALL로 되돌린다.',
 '3. 가설과 사전 판정 기준':'사전 가설은 직접 답할 원문이 있어도 충분성/연결 처리 때문에 지연될 수 있다는 것이다. 사전 성공 기준은 실제 API 응답·단계·시간·열람·종료 기록 확보, 실패 기준은 오류 보존이다. 답변 정확도·A/B·승격 평가를 하지 않는다. 설계 동결은 manifest/bindings와 candidate rev-004에 기록했다.',
 '4. 실험 설계':'shipped-r1 단일 arm, run-001 단일 실행. 기준 비교 arm 없음, 직접 부모 없음. 첫 실제 호출 전 준비 오류 4개는 setup-attempt-*에 별도로 보존했다. 각 준비 오류의 모델 호출은 0회다.',
 '5. 데이터·모델·재현성':'로컬 공개 generation term-source-1acfbe06921527e74a0b, 승인 public 문서 145개. Qwen3.8 / qwen/qwen3.8-27b, OpenRouter Parasail FP8, reasoning none, fallback 없음, ExperimentClient로 원문 입출력 보존. 기존 공개 cache를 읽기 위해 full_glossary.py와 종속 engine pins만 활성 로컬 compiler로 유지했다. 따라서 현장 ZIP 전체의 동일 환경 시험은 아니다. 법령 최신성·gold 기준답변·GENOS 내부 성능은 검증하지 않았다.',
 '6. 결과':f'질문 “내부 회계 관리자는 누가 지정하나요?” 요청 {result["request_seconds"]:.3f}초, app 초기화 {result["app_setup_seconds"]:.3f}초, HTTP 422. 모델은 두 차례 evidence_sufficient=true, needs_search=false를 출력했으나 실제 최종 답변은 생성되지 않았다. 반환 오류: additional source request remains unresolved after fulltext search.',
 '7. 사례별 오류 분석':'원인 한 사례: reverse/incoming 연결 20개에서 첫 10개 적용 확인은 모두 SKIP/DOES_NOT_APPLY. 나머지 10개의 메뉴가 제공되지 않아 pending이 남았다. FOLLOW가 없어서 frontier가 비고 다음 연결 round가 실행되지 않았다. 전체 검색 재진입 후 같은 10개를 반복 판단했다. 종료에는 REQUIRED_CONNECTION_PENDING이 기록됐다.',
 '8. 비용·지연·회수 규모':f'실제 모델 {len(usage)}회, 모델 대기 합 {diagnostic["model_seconds"]:.3f}초, SQL {diagnostic["sql_calls"]}회 합 {diagnostic["sql_seconds"]:.3f}초. 입력 {diagnostic["input_tokens"]}토큰, 출력 {diagnostic["output_tokens"]}토큰, USD {diagnostic["cost_usd"]:.8f}. Store catalogue {len(corpus)}곳 → 실제 후보 {len(recalled)}곳 → 12개 READ 묶음 / 원문 {len(acquired)}곳. READ action 17회(OK 14, PARTIAL 3), evidence page 17개. 원장 present는 선택 모델에 실제 제공한 원문이며 최종 답변 제시는 0이다. 최초 묶음의 서식/별지 8개는 모델의 최종 선택에서 채택되지 않았다. [단계 원장](artifacts/stage-ledger.json)에 실제 좌표별 추가·탈락을 보존했다. gold 없음.',
 '9. 해석':'사실: 모델은 외부감사법 제8조 제3항을 선택하고 충분하다고 판단했다. 코드가 남은 연결 검사 때문에 이를 거절했다. 추론: 충분성만 개선하는 프롬프트로는 이 경로가 해결되지 않는다. 불필요 서식 후보와 실제 필수 연결 보류를 구분하고, 남은 연결은 같은 메뉴 다음 batch에서 계속 처리해야 한다. 무조건 pending을 무시하면 조건·예외 검사를 잃을 수 있다.',
 '10. 한계와 일반화 가능 범위':'공개 자료/외부 모델 한 질문 한 번의 진단이다. 현장 내부 모델·데이터·compact compiler와 다르고 10분 지연을 재현한 것은 아니다. 시간 일반화나 통계 비교를 하지 않는다. 준비 오류 시간은 요청 131.157초에 합산하지 않는다.',
 '11. 운영 결정·롤백 조건':'MAIN 활성 포인터 및 제품 데이터 세대는 변경하지 않았다. 코드 수정·배포·메일 추가 발송은 이 진단에 포함하지 않는다. 후속 구현/효과 비교를 한다면 별도 ADR에서 이 완료 arm을 부모로 삼아 사전 기준을 동결한다. 원문 필수 조건을 삭제하는 우회는 사용하지 않는다.',
 '12. 재현 명령':'`PYTHONDONTWRITEBYTECODE=1 LAWRAG_WORKSPACE_ROOT=/home/jin/8-AGENT .venv/bin/python -u 06_TOOLS/EXPERIMENTS/adr_0659/run_probe.py`\n\n실행 디렉터리 exist=False가 기존 산출물 덮어쓰기를 방지한다. 추가 모델 호출 재실행은 새 ADR/runner 경로에서 사전 등록해야 한다. [진단](artifacts/diagnostic.json), [원시 artifact manifest](artifacts/manifest.json), [질문별 전체 입력·출력](실험/질문-001-accounting-manager.md).'}
(ADR/'README.md').write_text('---'+front+'---\n\n# ADR-0659: 내부 회계 관리자 지정 질문 실제 로컬 진단\n\n'+'\n\n'.join('## '+h+'\n\n'+v for h,v in parts.items())+'\n')
question='내부 회계 관리자는 누가 지정하나요?'
qh={
 '1. 실행 메타':'ADR-0659 / ADR-0659-experiment-v1 / accounting-manager / run-001 / shipped-r1. 2026-10-06 UTC, exact. 실제 모델 Qwen3.8/Parasail, judge 없음, 준비 시도는 별도이며 모델 0회.',
 '2. 사용자 질문 원문':'```text\n'+question+'\n```',
 '3. 기준답변 — 채점 전용, 제품 입력 비공개':'기준답변·gold·채점 없음. 사용자 요구는 실제 실행 시간·열람·종료 진단이며 답변 품질 인증이 아니다.',
 '4. 제품 입력을 구성한 원값':fenced({str((A/'native-case-stages.json').relative_to(ROOT)):stages})+'\n'+fenced({str((A/'stage-ledger.json').relative_to(ROOT)):ledger}),
 '5. 제품 모델 호출 — run·arm별 실제 원문':'모든 실제 system/user/schema/원응답/usage를 호출 순서대로 기록했다. 답변 compose는 실행되지 않았다.\n\n'+fenced({str((A/'model-transcript.json').relative_to(ROOT)):transcript}),
 '6. 중간 LLM 호출 — router/compiler/verifier/repair':'위 전체 10회가 intent, plan/recall 결정, triage, reference, review 호출이다. 별도 미기록 호출이나 offline 모델 호출은 없다.\n\n'+fenced({str((A/'native-events.json').relative_to(ROOT)):events}),
 '7. 채점 호출과 반복 판정':'judge system/user 없음, judge response 없음, 다수결 없음. 원답변이나 정답률이 없는 것을 품질 성공으로 집계하지 않는다.',
 '8. 사례 최종 판정':'진단 완료 / 실제 요청 실패 HTTP 422 / 유형 other:pending_relation_fulltext_reentry_loop. 모델 두 차례 충분=true, 필요검색=false. 20 incoming 그룹 중 10개 메뉴만 제시하고 나머지 보류를 검색 재진입으로 처리했다. 후속 가설은 동일 연결 메뉴의 다음 batch 진행과 필요 검색/조건 검사 사유 분리다. 비교쌍·회귀 판정 없음.\n\n'+fenced({str((A/'diagnostic.json').relative_to(ROOT)):diagnostic})}
(ADR/'실험/질문-001-accounting-manager.md').write_text('# 질문 001 — accounting-manager\n\n'+'\n\n'.join('## '+h+'\n\n'+v for h,v in qh.items())+'\n')
(ADR/'실험/README.md').write_text(f'# ADR-0659 실험 질문 인덱스\n\n단일 진단 run-001 / shipped-r1, 직접 부모 없음, 비교 없음. Proposed / probe / in_sample=true / decision_eligible=false / MAIN unchanged.\n\n[전체 질문·모델 원문](질문-001-accounting-manager.md): 요청 131.157초, HTTP 422; 충분 판단 true 두 번, 연결 보류로 전체 검색 재진입 한 번. 정답·gold·judge 없음. 원장은 숫자 root 좌표가 없는 비구조 legacy 56건을 제외한다. 단계별 원문 {len(corpus)} → {len(recalled)} → {len(acquired)} → 선택 모델 원문 {len(acquired)}; 최종 답변 0.\n\n[기계 판독 실험](manifest.json), [실제 좌표별 단계 원장](../artifacts/stage-ledger.json).\n')
# Avoid walking hard-linked generation-shadow trees or hashing public corpus again.
paths=list((A/'design').glob('*'))+[A/x for x in ('product.log','diagnostic.json','native-events.json','native-case-stages.json','stage-ledger.json','model-transcript.json')]
paths += [RUN/x for x in ('result.json','request.json','profile.json')]
paths += [f for f in (RUN/'provider').rglob('*') if f.is_file()]
paths += [next((RUN/'runtime/legal-agent').rglob('journal.sqlite'))]
for d in sorted(A.glob('setup-attempt-*')):paths += [d/x for x in ('result.json','error.txt') if (d/x).exists()]
put(A/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0659',
 'created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(ROOT)),
 'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact frozen design or actual runtime audit',
 'contains_raw_prompts_and_outputs':p.name in ('request.json','response.json','native-events.json','model-transcript.json','journal.sqlite')} for p in paths if p.is_file()]})
print({k:diagnostic[k] for k in ('request_seconds','model_seconds','sql_seconds','input_tokens','output_tokens','cost_usd','acquired_original_roots')})
