"""Post-run offline accounting only; never changes model inputs or answers."""
from common import *
from report_common import finish_documents,seal
import sys,statistics,sqlite3,gzip
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
raw=read(RUN/'result.json');reviews=read(ART/'offline/manual-review.json');m=read(ADR/'실험/manifest.json')
criteria=read(ART/'offline/criteria.json');cases=read(DES/'cases.json');arms=['baseline','candidate'];rows=[];graded=[]
sources={s['id']:s for s in read(DES/'curated-source-values.json')['sources']};extra=read(ART/'offline/extra-source.json');sources[extra['id']]=extra
for result in raw['results']:
 cid,arm=result['case_id'],result['arm'];p=RUN/'agent_layer'/arm/cid;a=read(p/'audit.json');review=reviews['cases'][cid][arm];delivery=read(p/'delivery-audit.json')
 assert len(review['required_status'])==len(criteria[cid]['required'])
 rec=StageLedgerRecorder(cid,arm,identity_canonicalizer);rec.record_stage('original_read','source',a['read_coordinates']);final={(x['doc_id'],x['node']) for x in a['final_coordinates']}
 rec.record_stage('final_cited','present',a['final_coordinates'],parent_stage_ids=['original_read'],discard_reasons=[{'coordinate':x,'reason':'Read source not cited in final output'} for x in a['read_coordinates'] if (x['doc_id'],x['node']) not in final]);capture=rec.capture();put(p/'retrieval-capture.json',capture)
 gold=[{'doc_id':sources[s]['document_id'],'node':int(sources[s]['node'])} for s in criteria[cid]['source_ids']];graded.append(grade_capture(capture,gold))
 checks=a['span_checks'];technical=all(x['exact_match'] and x['authorized'] for x in checks) and not a['unmapped_citations']
 reentries=[e for e in a['events'] if e['kind']=='ASSESSMENT_GAP_REENTRY_PLANNED'];closed=[e for e in a['events'] if e['kind']=='KNOWLEDGE_CLOSED_EVIDENCE_DECISION']
 failures=[]
 for f in (p/'raw').glob('*/response.json'):
  value=read(f)
  if isinstance(value,dict):
   for choice in value.get('choices',[]):
    if choice.get('finish_reason')=='length':failures.append(str(f.relative_to(ROOT)))
 prompt_checks=[]
 for f in (p/'wire').glob('*.gz'):
  with gzip.open(f,'rt') as stream:v=json.load(stream)
  system=v['messages'][0]['content']
  if '이번 요청은' in system:prompt_checks.append(('이번 평가는 현재 질문에 필요한 설명을 완성하는 작업이다.' in system)==(arm=='candidate'))
 novel=(extra['document_id'],int(extra['node']))
 rows.append({'case_id':cid,'arm':arm,'reuse_mode':result['reuse_mode'],'seconds':result['seconds'],'model_calls':result['model_calls'],'http_status':result.get('http_status'),
  'technical_source_check':technical,'verified_spans':sum(x['span_count'] for x in checks),'read_articles':len(a['read_coordinates']),'final_cited_articles':len(final),
  'required_items_met':review['required_status'].count('met'),'required_items_total':len(review['required_status']),'core_pass':all(x=='met' for x in review['required_status']) and not review['forbidden_violations'],
  'additional_research_reentries':len(reentries),'closed_gate_decisions':len(closed),'closed_gate_blocked_gaps':sum(len(e['payload']['blocked_gaps']) for e in closed),
  'length_failures':failures,'actual_prompt_verified':bool(prompt_checks) and all(prompt_checks),'assessment_prepared_refs_present':delivery['every_assessment_prepared_refs_present'],
  'novel_source_read':novel in {(x['doc_id'],x['node']) for x in a['read_coordinates']},'novel_source_cited':novel in final,'review':review})
ledger=build_experiment_artifact('ADR-0996',m['experiment_id'],[build_run_artifact('run-001',graded,{a:['original_read','final_cited'] for a in arms})]);put(RUN/'retrieval-ledger.json',ledger)
usage={k:sum((u.get(k) or 0) for r in raw['results'] for u in r['usage']) for k in ['input_tokens','output_tokens','total_tokens','cost_usd']};by_arm={}
for arm in arms:
 rr=[r for r in rows if r['arm']==arm]
 by_arm[arm]={'status':'complete','evaluated':len(rr),'planned':5,'correct':sum(r['core_pass'] for r in rr),'total':len(rr),'accuracy':sum(r['core_pass'] for r in rr)/len(rr) if rr else None,
  'required_items_met':sum(r['required_items_met'] for r in rr),'required_items_total':sum(r['required_items_total'] for r in rr),'model_calls':sum(r['model_calls'] for r in rr),'total_seconds':sum(r['seconds'] for r in rr),
  'p50_seconds':statistics.median(r['seconds'] for r in rr) if rr else None,'p95_seconds':max((r['seconds'] for r in rr),default=None),'length_failures':sum(len(r['length_failures']) for r in rr)}
paired={'candidate_only':[],'baseline_only':[],'both_correct':[],'both_incomplete':[],'unpaired':[]};coverage_regressions=[]
for case in cases:
 pair={r['arm']:r for r in rows if r['case_id']==case['id']}
 if len(pair)!=2:paired['unpaired'].append(case['id']);continue
 b,c=pair['baseline'],pair['candidate'];paired['both_correct' if b['core_pass'] and c['core_pass'] else 'candidate_only' if c['core_pass'] else 'baseline_only' if b['core_pass'] else 'both_incomplete'].append(case['id'])
 if c['required_items_met']<b['required_items_met']:coverage_regressions.append(case['id'])
b,c=by_arm['baseline'],by_arm['candidate'];novel=next((r for r in rows if r['case_id']=='cm-new-lockup' and r['arm']=='candidate'),{})
success={'all_requests':raw['complete'],'coverage_improved':c['required_items_met']>b['required_items_met'],'no_coverage_regression':not coverage_regressions,
 'no_candidate_forbidden':all(not r['review']['forbidden_violations'] for r in rows if r['arm']=='candidate'),'closed_no_reentry':all(r['additional_research_reentries']==0 for r in rows if r['reuse_mode']=='CLOSED_EVIDENCE'),
 'new_question_reuse_and_extension':bool(novel.get('core_pass') and novel.get('novel_source_cited')),'source_integrity':all(r['technical_source_check'] for r in rows),'call_bound':c['model_calls']<=b['model_calls'],'latency_bound':c['total_seconds']<=1.5*b['total_seconds']}
summary={'status':'complete','all_requests_executed':raw['complete'],'native_api_requests':len(rows),'product_model_calls':sum(r['model_calls'] for r in rows),'usage':usage,'by_arm':by_arm,'rows':rows,'paired':paired,'coverage_regressions':coverage_regressions,'success_criteria':success,'all_success_criteria_met':all(success.values()),
 'main_changed_by_this_experiment':False,'active_pointer_change_observed':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')!=read(DES/'selected.json')['pointer_sha256'],'experiment_source_generation':100,'current_active_generation':read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')['generation'],
 'oracle_executed':False,'genos_executed':False,'holdout':False,'semantic_quality_certified':False,'scope':'Same source delivery and policy gate in both arms; assessment prompt difference. Closed gate begins after initial source acquisition, not a no-navigation initial fast path.'}
put(RUN/'summary.json',summary);m['runs'][0].update(status='complete',artifact_path=str((RUN/'summary.json').relative_to(ROOT)),sha256=sha(RUN/'summary.json'))
m['results'].update(status='complete',by_arm=by_arm,comparisons=[paired],judge_disagreements=0,usage={'product_model_calls':summary['product_model_calls'],'offline_evaluator_calls':0,**usage},latency={'scope':'Single sequential observation per case/arm; no statistical certification','by_arm':by_arm},error_taxonomy=[{'case':r['case_id'],'arm':r['arm'],'type':'required_issue_omission' if r['http_status']==200 else 'other','note':r['review']['note']} for r in rows if not r['core_pass']])
selected=read(DES/'selected.json');docs=read(RUN/'binding.json')['public_documents'];nav=sqlite3.connect((ROOT/selected['release']['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True);corpus=nav.execute('select count(*) from source where document_id in ('+','.join('?' for _ in docs)+')',docs).fetchone()[0];nav.close()
a=m['retrieval_accounting'];counts={arm:[r['final_cited_articles'] for r in rows if r['arm']==arm] for arm in arms};a.update(corpus_total=corpus,before_filter={arm:sum(r['read_articles'] for r in rows if r['arm']==arm) for arm in arms},after_filter={arm:sum(counts[arm]) for arm in arms},presented_total={arm:sum(counts[arm]) for arm in arms},presented_mean={arm:statistics.mean(counts[arm]) if counts[arm] else 0 for arm in arms},presented_p50={arm:statistics.median(counts[arm]) if counts[arm] else 0 for arm in arms},presented_p95={arm:max(counts[arm],default=0) for arm in arms},golden_recall={},selectivity={arm:(statistics.mean(counts[arm]) if counts[arm] else 0)/corpus for arm in arms})
for arm in arms:
 hit=total=0
 for r in rows:
  if r['arm']!=arm:continue
  au=read(RUN/'agent_layer'/arm/r['case_id']/'audit.json');gold={(sources[s]['document_id'],int(sources[s]['node'])) for s in criteria[r['case_id']]['source_ids']};hit+=len(gold&{(x['doc_id'],x['node']) for x in au['final_coordinates']});total+=len(gold)
 a['golden_recall'][arm]=hit/total if total else 0
a['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json');put(ADR/'실험/manifest.json',m)
table='| 질문 | 기준 핵심항목 | 강화 핵심항목 | 기준 초·호출 | 강화 초·호출 |\n|---|---:|---:|---:|---:|\n'
for case in cases:
 pair={r['arm']:r for r in rows if r['case_id']==case['id']}
 if len(pair)<2:table+='| '+case['id']+' | 미완료 | 미완료 | — | — |\n';continue
 b,c=pair['baseline'],pair['candidate'];table+=f"| {case['id']} | {b['required_items_met']}/{b['required_items_total']} | {c['required_items_met']}/{c['required_items_total']} | {b['seconds']:.1f}·{b['model_calls']} | {c['seconds']:.1f}·{c['model_calls']} |\n"
parts=['MAIN100 기반 격리 후보로 비교했으며 본 실험은 MAIN을 변경하지 않았다. 종료 시 별도 경로로 MAIN101이 활성화된 것을 확인했다. 동결 코드·데이터는 그대로 사용했다. [실제 결과](artifacts/run-001/summary.json), [활성 포인터 변경 관찰](artifacts/concurrent-main-change.json). 사전 기준 판정: '+json.dumps(success,ensure_ascii=False),
 'ADR0993 원문 전달 후보에서, 근거를 받고도 설명 누락·반복 출력이 발생했다. 기존 프롬프트에도 설명 유지 지시가 있었으며, 이번에는 요구사항 대응 → 설명 작성 → 부족 특정 → 변경 이유 → 최종 점검의 순서를 추가했다.',
 '[사전 기준](artifacts/design/criteria.json), [프롬프트](artifacts/design/prompt.json), [동결](artifacts/design/freeze.json), [오프라인 채점 항목](artifacts/offline/criteria.json).',
 'CM051·008은 원문을 전달한 뒤 추가 탐색을 차단한다. CM010·007과 신규 복합 질문은 확장을 허용한다. 양 arm의 정책 게이트와 원문 전달은 동일하며 프롬프트만 다르다. 처음 조문에 진입하는 탐색까지 제거한 실험은 아니다.',
 'MAIN100 기반 부모 ADR0993의423파일 동결. 원문4단위와 온톨로지9레코드를 연구용 Gold에 재구성했다. 질문은 발견·조회 입력이며 저장 키가 아니다. Agent 저널·실제 wire를 분리 보존했다. Qwen3.8/Parasail FP8, reasoning none, 요청24호출900초, 순차 RSS6GiB·가용3GiB. 전문가 승인·Oracle·GENOS 실증 없음.',
 table+'\n'+json.dumps(paired,ensure_ascii=False),
 '\n\n'.join(r['case_id']+' '+r['arm']+': '+r['review']['note'] for r in rows),
 json.dumps({'by_arm':by_arm,'usage':usage,'corpus':corpus},ensure_ascii=False,indent=2)+'\n\n[회수 원장](artifacts/run-001/retrieval-ledger.json). 최종 인용 조문 수를 판단 입력 조문 수와 혼동하지 않는다. 입력 전달은 별도 delivery-audit로 확인한다.',
 '원문 투입, 모델의 항목 설명, 추가 탐색, 최종 인용을 각각 기록했다. 프롬프트는 기존 claims/gaps/issue_assessments를 사용하며 항목별 상태를 새 스키마로 강제하지 않는다. 재사용 조건의 자동 판정도 구현하지 않았고 사전에 동결한 질문 모드를 명시 주입했다.',
 '5문항 각1회의 인샘플 비교이며 작성자 검토다. 새 복합 질문도 개발자가 원문을 확인해 구성했으므로 holdout이 아니다. CM051·008 지식은 가정 성공 기록의 수동 보완이고 실제 성공 답변 재사용 인증이 아니다. 초기 계약의 전체 receipt 동일성 검사는 실패했으며, 캐시의 부분 구간 receipt 재결속 차이를 보존했다. 후속 검사는 같은 본문·추가 도구비용0·재결속 근거 검증을 확인했고 원문 동일성 기준을 낮추지 않았다.',
 '사용자 지시에 따라 MAIN·제품 작업 코드·GENOS·Git commit/push 모두 변경하지 않았다. 프롬프트 수정이나 모델 재호출은 새 ADR로 수행한다. 최초 계약 실패 기록도 보존한다.',
 '실행: `.venv/bin/python 06_TOOLS/EXPERIMENTS/resource_guard.py ... -- .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0996/e2e.py run`. 완료 run 재실행 금지. audit.py·delivery_audit.py는 모델0회 감사, summarize.py는 오프라인 집계. 압축 후 저널 감사는 archive receipt의 복원 명령을 따른다.']
cp={c['id']:['run-001, baseline/candidate; actual native API; in-sample.',c['question'],json.dumps(criteria[c['id']],ensure_ascii=False,indent=2),
 '[원문 등록](../artifacts/run-001/gold_layer/source-concept-registry.json), [전달](../artifacts/run-001/delivery-audit.json), [회수 원장](../artifacts/run-001/retrieval-ledger.json).',
 '`../artifacts/run-001/agent_layer/{baseline,candidate}/'+c['id']+'/`의 request.json·response.json·answer.txt·canonical/·wire/·raw/에 실제 원문을 보존했다. 기준답변은 제품 입력에 넣지 않았다.',
 '각 generations.json·calls.json·원시 저널에 실제 단계별 입출력·실패·사용량·지연을 기록했다. 전체 요청 재시도 없음.',
 '모델 judge0회. 사전 required/forbidden 기준을 작성자가 검토했다. 독립 사람 판정·모델간 보정 없음.',
 json.dumps([r for r in rows if r['case_id']==c['id']],ensure_ascii=False,indent=2)] for c in cases}
finish_documents(ADR,'원문 지식 우선 사용 프롬프트 비교',parts,cp);seal(ADR);print(table);print(json.dumps(success,ensure_ascii=False))
