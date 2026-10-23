"""Post-run accounting; no calls, product edits, or changes to frozen criteria."""
from common import *
from report_common import finish_documents, seal
import sys, statistics, sqlite3
sys.path.insert(0, str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder, identity_canonicalizer, grade_capture, build_run_artifact, build_experiment_artifact

raw=read(RUN/'result.json'); assert raw['complete'] and len(raw['results'])==8
m=read(ADR/'실험/manifest.json'); cases=read(DES/'cases.json')
criteria=read(ART/'offline/criteria.json'); reviews=read(ART/'offline/manual-review.json')
sources={s['id']:s for s in read(DES/'curated-source-values.json')['sources']}
arms=['baseline','knowledge']; rows=[]; graded=[]; counts={a:[] for a in arms}; original={a:[] for a in arms}; recalls={a:[0,0] for a in arms}
for result in raw['results']:
    cid,arm=result['case_id'],result['arm']; p=RUN/'agent_layer'/arm/cid
    audit=read(p/'audit.json'); review=reviews['cases'][cid][arm]
    assert len(review['required_status'])==len(criteria[cid]['required'])
    rec=StageLedgerRecorder(cid,arm,identity_canonicalizer)
    rec.record_stage('original_read','source',audit['read_coordinates'])
    final={(x['doc_id'],x['node']) for x in audit['final_coordinates']}
    discarded=[{'coordinate':x,'reason':'Read in native journal but not cited in final answer; no unrecorded model intent inferred'} for x in audit['read_coordinates'] if (x['doc_id'],x['node']) not in final]
    rec.record_stage('final_cited','present',audit['final_coordinates'],parent_stage_ids=['original_read'],discard_reasons=discarded)
    capture=rec.capture();put(p/'retrieval-capture.json',capture)
    gold=[{'doc_id':sources[s]['document_id'],'node':int(sources[s]['node'])} for s in criteria[cid]['source_ids']]
    graded.append(grade_capture(capture,gold)); counts[arm].append(len(final));original[arm].append(len(audit['read_coordinates']))
    gset={(x['doc_id'],x['node']) for x in gold};recalls[arm][0]+=len(final&gset);recalls[arm][1]+=len(gset)
    checks=audit['span_checks']; technical=bool(checks) and all(x['exact_match'] and x['authorized'] for x in checks) and not audit['unmapped_citations']
    rows.append({'case_id':cid,'arm':arm,'cohort':result['cohort'],'http_status':result['http_status'],
      'seconds':result['seconds'],'model_calls':result['model_calls'],'model_seconds':audit['model_seconds'],
      'prepare_seconds':audit['prepare_seconds'],'seconds_excluding_prepare':audit['seconds_excluding_prepare'],
      'read_articles':len(audit['read_coordinates']),'final_cited_articles':len(final),'read_blocks':audit['read_block_count'],
      'core_route_used':audit['core_route_used'],'knowledge_route_bound':audit['knowledge_route_bound'],
      'guidance_in_actual_inputs':sum(x['guidance_in_actual_input'] for x in audit['model_views']),
      'actual_input_count':len(audit['model_views']),'verified_evidence_units':len(checks),'verified_spans':sum(x['span_count'] for x in checks),
      'technical_source_check':technical,'required_items_met':sum(x=='met' for x in review['required_status']),
      'required_items_total':len(review['required_status']),
      'core_pass':all(x=='met' for x in review['required_status']) and not review['forbidden_violations'],
      'review':review,'whole_answer_certified':False})
ledger=build_experiment_artifact('ADR-0987',m['experiment_id'],[build_run_artifact('run-001',graded,{a:['original_read','final_cited'] for a in arms})])
put(RUN/'retrieval-ledger.json',ledger)
usage={k:sum((u.get(k) or 0) for r in raw['results'] for u in r['usage']) for k in ['input_tokens','output_tokens','total_tokens','cost_usd']}
by_arm={a:{'status':'complete','correct':sum(r['core_pass'] for r in rows if r['arm']==a),'total':4,
    'accuracy':sum(r['core_pass'] for r in rows if r['arm']==a)/4,'criteria_met':all(r['core_pass'] for r in rows if r['arm']==a),
    'mean_seconds':statistics.mean(r['seconds'] for r in rows if r['arm']==a),
    'mean_model_seconds':statistics.mean(r['model_seconds'] for r in rows if r['arm']==a),
    'model_calls':sum(r['model_calls'] for r in rows if r['arm']==a),
    'required_items_met':sum(r['required_items_met'] for r in rows if r['arm']==a),
    'required_items_total':sum(r['required_items_total'] for r in rows if r['arm']==a)} for a in arms}
receipt=read(RUN/'gold_layer/publication-receipt.json')
summary={'status':'complete','native_api_requests':8,'product_model_calls':sum(r['model_calls'] for r in rows),'usage':usage,
 'primary_unit':'document version + source coordinate + concept; questions are discovery provenance',
 'publication':{'source_units':4,'ontology_records':len(receipt['records']),'guards':len(receipt['contract_checks']),
   'condition_truth_table_rows':len(receipt['condition_checks']),'expert_approved':False,'scope':'local research only'},
 'rows':rows,'by_arm':by_arm,'answers_with_all_required_items':sum(r['core_pass'] for r in rows),
 'source_span_checks_pass':all(r['technical_source_check'] for r in rows),
 'latency_scope':'One observation per pair; native initialization and network/provider variance remain. No causal or statistical certification.',
 'review_scope':'Frozen required/forbidden criteria, author source review only. Quote-only fallback does not answer the question; available quoted evidence is recorded separately.',
 'main_changed':False,'oracle_executed':False,'genos_executed':False,'holdout':False}
put(RUN/'summary.json',summary)
m['runs'][0].update(status='complete',artifact_path=str((RUN/'summary.json').relative_to(ROOT)),sha256=sha(RUN/'summary.json'))
m['results'].update(status='complete',by_arm=by_arm,comparisons=[],judge_disagreements=0,
 usage={'product_model_calls':summary['product_model_calls'],'offline_evaluator_calls':0,**usage},
 latency={'basis':summary['latency_scope'],'by_arm':{a:by_arm[a]['mean_seconds'] for a in arms}},
 error_taxonomy=[{'case':r['case_id'],'arm':r['arm'],'note':r['review']['note']} for r in rows if not r['core_pass']])
binding=read(RUN/'binding.json'); selected=read(DES/'selected.json'); docs=binding['public_documents']
nav=sqlite3.connect((ROOT/selected['release']['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
corpus=nav.execute('select count(*) from source where document_id in ('+','.join('?' for _ in docs)+')',docs).fetchone()[0];nav.close()
account=m['retrieval_accounting'];account.update(corpus_total=corpus,
 before_filter={a:sum(original[a]) for a in arms},after_filter={a:sum(counts[a]) for a in arms},
 presented_total={a:sum(counts[a]) for a in arms},presented_mean={a:statistics.mean(counts[a]) for a in arms},
 presented_p50={a:statistics.median(counts[a]) for a in arms},presented_p95={a:max(counts[a]) for a in arms},
 golden_recall={a:recalls[a][0]/recalls[a][1] for a in arms},selectivity={a:statistics.mean(counts[a])/corpus for a in arms},
 not_applicable_reason=None)
account['stage_ledger']['sha256']=sha(RUN/'retrieval-ledger.json');put(ADR/'실험/manifest.json',m)
table='| 질문 | 구분 | 기준 초/호출 | 지식 초/호출 | 핵심 항목 기준→지식 |\n|---|---|---:|---:|---|\n'
for c in cases:
 b=next(r for r in rows if r['case_id']==c['id'] and r['arm']=='baseline');k=next(r for r in rows if r['case_id']==c['id'] and r['arm']=='knowledge')
 table+=f"| {c['id']} | {b['cohort']} | {b['seconds']:.2f}/{b['model_calls']} | {k['seconds']:.2f}/{k['model_calls']} | {b['required_items_met']}/{b['required_items_total']} → {k['required_items_met']}/{k['required_items_total']} |\n"
parts=[
 '원문 중심 지식4단위와 온톨로지9레코드를 실제 저장·발행하고, 네이티브 `/v1/rag/ask`로4문항×2조건을 실행했다. 조회와 원문 경로 재사용은 작동했다. 필수 답변 항목을 모두 충족한 경우는 두 조건 모두0/4여서 정답 도달 개선은 입증하지 못했다.',
 '기존 실패 로그를 정답 이력으로 바꾸지 않고, 정상적으로 조사했다는 가정 아래 실제 원문에서 보완한 검토 후보를 만들었다. 질문 단위의 답변 캐시 대신 원문·판본·위치·개념을 일차 단위로 저장했다.',
 '[동결 기준](artifacts/design/criteria.json)과 [질문별 항목](artifacts/offline/criteria.json). 기술적 조회·소비, 응답 지연·호출 수, 핵심 항목 충족을 구분했다. 온톨로지 hit을 정답이나 오류 확률로 취급하지 않았다.',
 'CM051·008에서 찾은 지식을 저장한 뒤 같은 질문과 관련 질문 CM010·007에 사용했다. baseline consumer off와 knowledge consume을 같은 동결 후보 API·모델·공개 범위에서 비교했다. 답변 캐시 없이 새 요청·세션. 순서는 사전 교차 배치했다.',
 '[동결](artifacts/design/freeze.json), [실제 binding](artifacts/run-001/binding.json). MAIN99의419파일과 연구 도구3파일을 동결한422파일 후보. Qwen3.8/Parasail FP8, reasoning none, fallback 없음. Agent 로그와 Gold 자료는 연구용 경로·SQLite이며 Dataiku Oracle 구현 인증이 아니다.',
 table+'\n[기계 판독 요약](artifacts/run-001/summary.json). 각 시간은 한 번의 관측값이다. 모든 HTTP200을 법률 답변 성공으로 세지 않았다.',
 'CM051은 CB 환산·단수 처리를 빠뜨렸고 지식 조건에서는 조합등을 면제 대상으로 혼동했다. CM008은3년·2년·구체 사유를 빠뜨리고 가목을 혁신기술기업으로 잘못 설명했다. CM010은 양쪽 모두 결론 대신 원문만 반환했다. CM007은 지식 조건에서도 사모 취득·잔여 인수 포함을 빠뜨렸다. [항목별 검토](artifacts/offline/manual-review.json).',
 json.dumps({'by_arm':by_arm,'product_model_calls':summary['product_model_calls'],'usage':usage,'corpus_articles':corpus},ensure_ascii=False,indent=2)+'\n\n[회수·탈락 원장](artifacts/run-001/retrieval-ledger.json). 원문 읽기·최종 인용·모델 입력 노출은 별개다. 총시간·모델시간·준비시간을 각 audit에 나눴으며 첫 요청의 초기화와 공급자 지연이 섞여 있다.',
 'SourceAnchor 저장과 숏컷이 필요한 원문을 확보해도, 원문별 검토 항목이 실제 선택·판단·답변에 끝까지 연결되지 않으면 누락은 남는다. 다음 구현 단위는 원문 확보 후 검토 항목 조회, 연결 원문 전달, 항목별 적용·해결 상태, 답변 주장과의 연결이다. 의미 불확실성을 일괄 중단이나 무한 재조사의 이유로 삼지 않는다.',
 'CM은 이미 노출된4문항이며 독립 holdout이 아니다. 과거 실패 로그의 가정 성공 보완은 수작업 원문 큐레이션이다. 자동 추출 품질, 모든 신규 질문, B→C→A 창의적 추론, Oracle·GENOS 현장 성능은 검증하지 않았다. AND 식은 계약 진리표 검사이며 라이브 사건 사실의 자동 추출·대입 검증이 아니다. 전체 원문 블록 미노출은 부분 인용 부재의 증명이 아니다.',
 'MAIN 선택·작업 엔진·GENOS는 승격하지 않았다. 격리 후보와 원시 실패·성공 경로를 보존했다. ADR0986의 코드 핀 차단(model0)을 지우지 않고 본 ADR에서 수정했다. 기술적 발행 상태는 법률 전문가 승인과 구분한다.',
 '실제 실행은 `06_TOOLS/EXPERIMENTS/resource_guard.py` 하에서 `06_TOOLS/EXPERIMENTS/adr_0987/e2e.py run`으로 완료했다. 완료된 run은 덮어쓰지 않는다. `audit.py`는 모델 호출 없이 보존된 저널·원문·입력을 대조한다. 후속 모델 비교는 새 ADR로 동결한다.'
]
cp={c['id']:[
 'run-001, baseline/knowledge; native API; Qwen3.8; 같은 질문 또는 이전 노출 관련 질문.', c['question'],
 json.dumps(criteria[c['id']],ensure_ascii=False,indent=2),
 '[원문 중심 registry](../artifacts/run-001/gold_layer/source-concept-registry.json), [사전 동결](../artifacts/design/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n[원장](../artifacts/run-001/retrieval-ledger.json). 원문 읽기→최종 인용 단계의 실제 좌표를 후처리로 복원했다.',
 f'`artifacts/run-001/agent_layer/{{baseline,knowledge}}/{c["id"]}/`의 request.json, response.json, answer.txt, calls.json, canonical/*.json.gz, wire/*.json.gz에 실제 원문·출력을 보존한다.',
 '네이티브 investigate/compose와 gateway repair는 calls.json·generations.json·journal·console에 기록했다. ExperimentClient 보정0, 전체 사례 임의 재실행0.',
 '채점 모델0회. 동결 항목을 작성자가 원문과 대조. 독립 심사 아님. 원문만 인용한 fallback은 해당 원문 확보와 별개로 질문의 결론 미완료로 기록한다.',
 json.dumps([r for r in rows if r['case_id']==c['id']],ensure_ascii=False,indent=2)
] for c in cases}
finish_documents(ADR,'CM 원문 중심 지식 저장·재사용 네이티브 E2E 결과',parts,cp)
seal(ADR)
print(table);print(json.dumps({'by_arm':by_arm,'calls':summary['product_model_calls'],'usage':usage,'corpus':corpus},ensure_ascii=False))
