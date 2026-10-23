"""Offline accounting for the completed frozen native run; never rerun models."""
from common import *
from report_common import finish_documents,seal
import sys,statistics,sqlite3
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
raw=read(RUN/'result.json');reviews=read(ART/'offline/manual-review.json');m=read(ADR/'실험/manifest.json')
criteria=read(ART/'offline/criteria.json');cases=read(DES/'cases.json');arms=['baseline','candidate'];rows=[];graded=[]
sources={s['id']:s for s in read(DES/'curated-source-values.json')['sources']}
for result in raw['results']:
 cid,arm=result['case_id'],result['arm'];p=RUN/'agent_layer'/arm/cid
 a=read(p/'audit.json');review=reviews['cases'][cid][arm];delivery=read(p/'delivery-audit.json')
 assert len(review['required_status'])==len(criteria[cid]['required'])
 rec=StageLedgerRecorder(cid,arm,identity_canonicalizer)
 rec.record_stage('original_read','source',a['read_coordinates'])
 final={(x['doc_id'],x['node']) for x in a['final_coordinates']}
 rec.record_stage('final_cited','present',a['final_coordinates'],parent_stage_ids=['original_read'],discard_reasons=[{'coordinate':x,'reason':'Acquired in native journal but not cited in final output'} for x in a['read_coordinates'] if (x['doc_id'],x['node']) not in final])
 capture=rec.capture();put(p/'retrieval-capture.json',capture)
 gold=[{'doc_id':sources[s]['document_id'],'node':int(sources[s]['node'])} for s in criteria[cid]['source_ids']]
 graded.append(grade_capture(capture,gold))
 checks=a['span_checks'];technical=all(x['exact_match'] and x['authorized'] for x in checks) and not a['unmapped_citations']
 rows.append({'case_id':cid,'arm':arm,'seconds':result['seconds'],'model_calls':result['model_calls'],'http_status':result.get('http_status'),
  'model_seconds':a['model_seconds'],'prepare_seconds':a['prepare_seconds'],'technical_source_check':technical,'verified_spans':sum(x['span_count'] for x in checks),
  'read_articles':len(a['read_coordinates']),'final_cited_articles':len(final),'required_items_met':review['required_status'].count('met'),'required_items_total':len(review['required_status']),
  'core_pass':all(x=='met' for x in review['required_status']) and not review['forbidden_violations'],
  'all_prepared_ref_witnesses_in_wire':delivery['all_prepared_ref_witnesses_in_wire'],'delivery_expected_count':delivery.get('expected_count'),
  'delivery_count':delivery.get('delivered_count'),'review':review,'whole_answer_certified':False})
ledger=build_experiment_artifact('ADR-0993',m['experiment_id'],[build_run_artifact('run-001',graded,{a:['original_read','final_cited'] for a in arms})]);put(RUN/'retrieval-ledger.json',ledger)
usage={k:sum((u.get(k) or 0) for r in raw['results'] for u in r['usage']) for k in ['input_tokens','output_tokens','total_tokens','cost_usd']}
by_arm={}
for arm in arms:
 rr=[r for r in rows if r['arm']==arm]
 by_arm[arm]={'status':'complete','evaluated':len(rr),'planned':4,'correct':sum(r['core_pass'] for r in rr),'total':len(rr),'accuracy':sum(r['core_pass'] for r in rr)/len(rr) if rr else None,
  'required_items_met':sum(r['required_items_met'] for r in rr),'required_items_total':sum(r['required_items_total'] for r in rr),'model_calls':sum(r['model_calls'] for r in rr),
  'mean_seconds':statistics.mean(r['seconds'] for r in rr) if rr else None,'p50_seconds':statistics.median(r['seconds'] for r in rr) if rr else None,'p95_seconds':max((r['seconds'] for r in rr),default=None)}
comparisons={'candidate_only':[],'baseline_only':[],'both_correct':[],'both_incomplete':[],'unpaired':[]}
for case in cases:
 pair={r['arm']:r for r in rows if r['case_id']==case['id']}
 if len(pair)!=2:comparisons['unpaired'].append(case['id']);continue
 b,c=pair['baseline']['core_pass'],pair['candidate']['core_pass']
 comparisons['both_correct' if b and c else 'candidate_only' if c else 'baseline_only' if b else 'both_incomplete'].append(case['id'])
summary={'status':'complete','all_requests_executed':raw['complete'],'native_api_requests':len(rows),'product_model_calls':sum(r['model_calls'] for r in rows),'usage':usage,'by_arm':by_arm,'rows':rows,'paired':comparisons,
 'source_span_checks_pass':all(r['technical_source_check'] for r in rows),'latency_scope':'One observation per case/arm, initialization/provider variation and completeness differ; no statistical speed claim',
 'primary_unit':'source document version + article + concept','source_units':4,'ontology_records':9,'baseline':'MAIN100 + same ontology with exact delivery off','candidate':'Same code + bounded exact delivery on',
 'main_changed':False,'oracle_executed':False,'genos_executed':False,'holdout':False,'semantic_quality_certified':False}
put(RUN/'summary.json',summary)
m['runs'][0].update(status='complete',artifact_path=str((RUN/'summary.json').relative_to(ROOT)),sha256=sha(RUN/'summary.json'))
m['results'].update(status='complete',by_arm=by_arm,comparisons=[comparisons],judge_disagreements=0,usage={'product_model_calls':summary['product_model_calls'],'offline_evaluator_calls':0,**usage},latency={'scope':summary['latency_scope'],'by_arm':by_arm},error_taxonomy=[{'case':r['case_id'],'arm':r['arm'],'type':('model_output_contract' if r['http_status']!=200 else 'required_issue_omission'),'note':r['review']['note']} for r in rows if not r['core_pass']])
selected=read(DES/'selected.json');docs=read(RUN/'binding.json')['public_documents'];nav=sqlite3.connect((ROOT/selected['release']['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True);corpus=nav.execute('select count(*) from source where document_id in ('+','.join('?' for _ in docs)+')',docs).fetchone()[0];nav.close()
a=m['retrieval_accounting'];counts={arm:[r['final_cited_articles'] for r in rows if r['arm']==arm] for arm in arms}
a.update(corpus_total=corpus,before_filter={arm:sum(r['read_articles'] for r in rows if r['arm']==arm) for arm in arms},after_filter={arm:sum(counts[arm]) for arm in arms},presented_total={arm:sum(counts[arm]) for arm in arms},presented_mean={arm:statistics.mean(counts[arm]) if counts[arm] else 0 for arm in arms},presented_p50={arm:statistics.median(counts[arm]) if counts[arm] else 0 for arm in arms},presented_p95={arm:max(counts[arm],default=0) for arm in arms},golden_recall={},selectivity={arm:(statistics.mean(counts[arm]) if counts[arm] else 0)/corpus for arm in arms})
for arm in arms:
 hit=total=0
 for r in rows:
  if r['arm']!=arm:continue
  au=read(RUN/'agent_layer'/arm/r['case_id']/'audit.json');gold={(sources[s]['document_id'],int(sources[s]['node'])) for s in criteria[r['case_id']]['source_ids']}
  hit+=len(gold & {(x['doc_id'],x['node']) for x in au['final_coordinates']});total+=len(gold)
 a['golden_recall'][arm]=hit/total if total else 0
 a['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json')
put(ADR/'실험/manifest.json',m)
table='| 질문 | 기준 항목 | 후보 항목 | 기준 초·호출 | 후보 초·호출 |\n|---|---:|---:|---:|---:|\n'
for case in cases:
 pair={r['arm']:r for r in rows if r['case_id']==case['id']}
 if len(pair)<2:table+='| '+case['id']+' | 미완료 | 미완료 | — | — |\n';continue
 b,c=pair['baseline'],pair['candidate'];table+=f"| {case['id']} | {b['required_items_met']}/{b['required_items_total']} | {c['required_items_met']}/{c['required_items_total']} | {b['seconds']:.1f}·{b['model_calls']} | {c['seconds']:.1f}·{c['model_calls']} |\n"
parts=[
 '사용자 지시대로 격리 실험만 실행했다. MAIN100·GENOS는 변경하지 않았다. [실행 요약](artifacts/run-001/summary.json). 원문 전달과 최종 설명 성공을 구분한다.',
 'ADR0987에서는 원문을 읽고도 선택된 판단 근거에서 빠지는 문제가 있었다. MAIN100에는 이미 material gap 추가조사 수정이 있다. 따라서 이번 비교는 양쪽 모두 같은 MAIN100·온톨로지를 사용하고 원문 전달만 바꿨다.',
 '[사전 기준](artifacts/design/criteria.json), [동결](artifacts/design/freeze.json), [오프라인 항목](artifacts/offline/criteria.json). 실제 전송 원문, 핵심 설명, 호출·시간을 각각 평가한다.',
 '원문4단위·온톨로지9레코드. CM051·008은 가정 성공 로그에서 수동 보완한 지식의 원래 질문, CM010·007은 관련 질문 재사용. 모두 이전 노출이며 holdout 아님. 원문 확인 항목의 모든 좌표를 두 조건에 동일하게 등록했다.',
 'MAIN100의419파일 + 연구 도구3파일 + knowledge_delivery.py를 동결했다. Qwen3.8/Parasail FP8, reasoning none, fallback 없음. 요청별24호출·900초, 순차 실행, RSS6GiB·가용3GiB 제한. Agent 기록과 Gold는 연구용 SQLite·파일이며 Oracle/GENOS 검증이 아니다.',
 table+'\n'+json.dumps(comparisons,ensure_ascii=False)+'\n\n원문 인용만 반환한 경우 설명 항목을 충족한 것으로 세지 않았다.',
 '\n\n'.join(r['case_id']+' '+r['arm']+': '+r['review']['note'] for r in rows),
 json.dumps({'by_arm':by_arm,'usage':usage,'corpus':corpus},ensure_ascii=False,indent=2)+'\n\n[회수 원장](artifacts/run-001/retrieval-ledger.json), [실제 wire 원문 대조](artifacts/run-001/delivery-audit.json). 최종 인용과 판단 입력은 별도로 기록한다.',
 '실제 구현은 knowledge_delivery.enrich가 SELECT 산출물에 원문 묶음과 evidence ID를 연결하고, 기존 ASSESS·COMPOSE·출처 검증기가 소비한다. PREPARED·INPUT_RETURNED·INPUT_FAILED를 구분한다. 연결 원문의 전달은 자동 법률 적용이나 모든 설명의 보장이 아니다.',
 '4문항·각1회·작성자 검토이며 법률 정답 인증이 아니다. 원문을 전달해도 모델이 다시 미확보라고 판단하거나 후속 판단에서 이전 주장을 잃을 수 있다. source-anchor 도달 후 자동 조회, 항목별 적용·설명 상태 계약, 장대 지식 회귀는 별도 검증이 필요하다. 추가 무적중 계약 검사에서 빈 plan.binding을 읽는 TypeError도 발견했다([기록](artifacts/no-match-contract.json)). 이 후보는 운영 가능한 완성품으로 취급하지 않는다.',
 '사용자가 메인 반영을 금지했다. 후보는 연구 snapshot에서만 명시 주입한다. 선택 MAIN·작업 엔진·GENOS·Git commit/push 모두 본 실험으로 변경하지 않았다. 후속 수정·모델 재실행은 별도 ADR로 남긴다.',
 '실제 실행: `06_TOOLS/EXPERIMENTS/resource_guard.py` → `06_TOOLS/EXPERIMENTS/adr_0993/e2e.py run`. 완료 run 재실행 금지. 원문 대조는 `audit.py`·`delivery_audit.py`, 결과 집계는 `close_results.py`. 저널 압축 시 복원 안내를 따른다.'
]
cp={c['id']:['run-001, baseline/candidate; isolated MAIN100 native API; previously exposed.',c['question'],json.dumps(criteria[c['id']],ensure_ascii=False,indent=2),
 '[원문 등록](../artifacts/run-001/gold_layer/source-concept-registry.json), [전달 대조](../artifacts/run-001/delivery-audit.json), [회수·탈락 원장](../artifacts/run-001/retrieval-ledger.json).',
 '`artifacts/run-001/agent_layer/{baseline,candidate}/'+c['id']+'/`의 request/response/answer/canonical/wire/raw가 실제 기록이다. wire는 실제 전송 payload의 무손실 압축이다.',
 '각 calls.json·generations.json·journal에 단계별 입출력·사용량·상태를 보존한다. 전체 사례 재시도 없음.',
 '모델 judge0회. 사전 동결 required/forbidden을 작성자가 검토했으며 독립 심사가 아니다.',
 json.dumps([r for r in rows if r['case_id']==c['id']],ensure_ascii=False,indent=2)] for c in cases}
finish_documents(ADR,'원문 중심 검토 지식의 판단 입력 전달 실험',parts,cp);seal(ADR);print(table)
