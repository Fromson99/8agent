"""Assemble observations after all frozen requests; never modify product or gold."""
from pathlib import Path
import hashlib,json,re,sqlite3,statistics
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0817-risk-main76-live-e2e';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def unique(rows):return [json.loads(s) for s in sorted({canon(r) for r in rows})]
m=read(A/'실험/manifest.json');f=read(D/'freeze.json');cases=read(D/'cases.json');manual=read(O/'manual-review.json')
assert m['reservation']['status']=='in_progress'
assert all(sha(R/n)==h for n,h in f['files'].items())
observations={c['id']:read(O/c['id']/'audit.json') for c in cases}
reopens={c['id']:read(O/c['id']/'reopen-result.json') for c in cases}
summary=[];usage=[];ledger_cases=[];before_total=0;adopted_total=0;counts=[]
plans=m['design']['retrieval_stage_plan']['stages_by_arm']['observed']
for c in cases:
    cid=c['id'];a=observations[cid];run=read(O/cid/'result.json');usage.extend(run['usage'])
    read_rows=[r for child in a['children'].values() for r in child['canonical_read']]
    adopted=[r for child in a['children'].values() for r in child['canonical_adopted']]
    final=a['canonical_final'];before_total+=len(unique(read_rows));adopted_total+=len(unique(adopted));counts.append(len(unique(final)))
    stages=[];before=[];before_occ=0
    for plan,raw in zip(plans,(read_rows,adopted,final)):
        after=unique(raw);bm={canon(x):x for x in before};am={canon(x):x for x in after}
        added=[am[k] for k in sorted(am.keys()-bm.keys())];discarded=[bm[k] for k in sorted(bm.keys()-am.keys())]
        reason=('Not included in the final current child return; this includes superseded earlier results. No claim of legal irrelevance.' if plan['stage_id']=='child_adopted' else 'Not cited by a final comparison row; read/adopted text remains in native journals.')
        stages.append({**plan,'executed':True,'skip_reason':None,'before':before,'added':added,'discarded':discarded,'after':after,
            'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),
            'occurrence_counts':{'before':before_occ,'after':len(raw),'canonical_collapsed_before':before_occ-len(before),'canonical_collapsed_after':len(raw)-len(after)},
            'discard_receipts':[{'identity':x,'reason':reason} for x in discarded], 'discard_reason_counts':{reason:len(discarded)} if discarded else {},
            'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,'golden_recall':None,
            'gold_before_identities':[],'gold_added_identities':[],'discarded_gold':[],'gold_after_identities':[]})
        before=after;before_occ=len(raw)
    ledger_cases.append({'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,
        'accounting_unit':'case_id + canonical article-root coordinate','arm_id':'observed','case_id':cid,'gold_total':0,'gold_identities':[],'stages':stages})
    summary.append({'case_id':cid,'http_status':run.get('http_status'),'status':run.get('status'),'model_calls':run['model_calls'],
        'seconds':run['elapsed_seconds'],'peak_rss_kib':run['peak_rss_kib'],'comparison_rows':a['rows'],'reported_evidence':len(a['evidence_refs']),
        'children':{s:{'status':child['returned_status'],'read_observations':child['read_observations'],'current_adopted':len(child['returned_evidence_ids']),
                       'investigation_runs':len(child['runs'])} for s,child in a['children'].items()},
        'workflow_compare_calls':sum('workflow-compare' in v['call'] for v in a['calls']),
        'original_span_mismatches':sum(not v['exact_original_match'] for v in a['evidence_span_checks']),
        'fresh_status_passed':reopens[cid]['passed'],'manual_review':manual[cid]})
G=R/read(D/'baseline.json')['manifest']['data_path'];db=sqlite3.connect('file:'+str(G/'navigation/navigation.sqlite')+'?mode=ro',uri=True)
corpus=sum(json.loads(r[0]).get('unit_id') is not None for r in db.execute('select json from source'));db.close()
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate',
        'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':[{'arm_id':'observed','declared_stage_ids':[p['stage_id'] for p in plans],
        'cases':ledger_cases,'aggregate':{'cases':len(cases),'presented_total':sum(counts),'gold_total':0}}]}],
        'audit':{'scope':'All native read receipts across every child run; current adopted return and final row citations. Search menus are not measured.',
                 'denominator':'All canonical structured source roots in the pinned navigation index; not a golden or relevant-source denominator.',
                 'source_only_unmapped':{cid:{s:[e['evidence_id'] for e in child['all_read_evidence'] if e['canonical'] is None] for s,child in a['children'].items()} for cid,a in observations.items()},
                 'superseded_results':'Original child returns retained in workflow_call tables. A failed replacement can reduce current_adopted; recorded as observed, not justified.'}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json',ledger)
total_calls=sum(s['model_calls'] for s in summary)
call_records=[c for a in observations.values() for c in a['calls']]
span_checks=[c for a in observations.values() for c in a['evidence_span_checks']]
result={'status':'complete','product_complete_cases':sum(s['status']=='completed' for s in summary),'case_count':len(cases),'cases':summary,
        'product_model_calls':total_calls,'offline_evaluator_model_calls':0,'actual_models':sorted({v['model'] for v in usage}),
        'actual_upstream_providers':sorted({v['upstream_provider'] for v in usage}),
        'transport_error_receipts':sum(bool(c.get('error')) for c in call_records),
        'provider_error_responses':sum(bool(c.get('provider_error')) for c in call_records),
        'non_stop_responses':sum(c.get('finish') not in (None,'stop') for c in call_records),
        'successful_response_identity_verified':all(c.get('model')=='qwen/qwen3.8-27b' and c.get('provider')=='Parasail' for c in call_records if c.get('finish')),
        'stored_evidence_records_checked':len(span_checks),'original_span_mismatches':sum(not c['exact_original_match'] for c in span_checks),
        'usage':{'input_tokens':sum(v.get('input_tokens') or 0 for v in usage),'output_tokens':sum(v.get('output_tokens') or 0 for v in usage),
                 'reported_cost_usd':sum(v.get('cost_usd') or 0 for v in usage),'successful_response_receipts':len(usage)},
        'frozen_inputs_unchanged':True,'main_generation':76,'main_changed':False,'genos_accessed':False,'quality_certified':False,
        'limitations':['Known/question-only real requests; no approved expert gold or accuracy percentage.','Three original registered questions explicitly submitted to WORKFLOW_RUN; one original comparison uses LEGAL_AGENT. Not a normal standalone RAG benchmark.',
                       'Each case uses a fresh serial WSL process; elapsed time includes bootstrap and is not warm-service or GENOS latency.',
                       'Final answers are system-assembled from verified comparison state; no additional final prose model call.',
                       'Same-process status and fresh-process status observed; duplicate only tested for completed states by the frozen runner.']}
put(O/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'not_run','basis':'Historical technical qualification only; no live baseline calls'},'observed':{'status':'complete','cases':summary}},
                    comparisons=[],usage={'product_model_calls':total_calls,'offline_evaluator_calls':0,**result['usage']},latency={s['case_id']:s['seconds'] for s in summary},error_taxonomy=manual['error_taxonomy'])
m['retrieval_accounting'].update(corpus_total=corpus,before_filter={'observed':before_total},after_filter={'observed':adopted_total},
    presented_total={'observed':sum(counts)},presented_mean={'observed':statistics.mean(counts)},presented_p50={'observed':statistics.median(counts)},
    presented_p95={'observed':sorted(counts)[round((len(counts)-1)*.95)]},golden_recall={'observed':None},selectivity={'observed':statistics.mean(counts)/corpus})
m['retrieval_accounting']['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json')
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q,c,s in zip(m['questions'],cases,summary):
    cid=c['id'];p=A/'실험'/q['file'];parts=[f'run-001 / observed / {cid}. 실제 MAIN76 로컬 서비스. in_sample=true, decision_eligible=false.',c['question'],
        '승인 정답 없음. 사전 criteria.json의 원문 대조 기준을 사용한다. 수치 정답률·golden recall 미측정.',
        f'../artifacts/run-001/{cid}/request.json, binding.json. 질문 원문 유지, 실제 workflow 진입.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/run-001/retrieval-ledger.json 의 {cid}. 탐색 메뉴 전체가 아닌 실제 읽기→현재 자식 채택→최종 인용.',
        f'../artifacts/run-001/{cid}/raw/call-*/request.json 및 response.json. 공통 ExperimentClient 물리 전송 원값.',
        f'../artifacts/run-001/{cid}/audit.json 및 runtime의 불변 journal. 복구·실패 호출도 포함.',
        '평가 모델0회. 로컬 원문과 정확 span/hash 및 실제 응답의 적용 범위를 읽기 전용 대조. 재채점·추가 제품 호출 없음.',json.dumps(s,ensure_ascii=False,indent=2)]
    p.write_text(f'# {cid}\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,parts),1))+'\n');q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
sections=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Proposed. 실질문4건 실제 모델 관측 완료. 기술 검사와 정답 품질을 분리하며 MAIN 승격 판단으로 쓰지 않는다.',
       'MAIN76의 이전128개 유한 기술 계약·399개 회귀 검사는 실질문 전체 대사 품질 검증이 아니었다. 이번에는 현재 서비스가 선택한 동일338개 파일로 실제 입력을 실행했다.',
       '호출 전 design/criteria.json 동결. 원문 근거·두 조사·대사·최종 상태·저장 소비자 확인. 실패나 partial을 의미 정답 성공으로 세지 않는다.',
       '질문027·038·104와 기존 유동성 대사 각1회, 순차 프로세스. 기존 단계 복구만 허용, 실패 후 새 예산으로 재실행하지 않았다.',
       '정본 design/freeze.json, baseline.json, cases.json. Qwen3.8/Parasail FP8/reasoning none/no fallback; 공통 ExperimentClient. 실제 local active pointer bootstrap이며 _APP 주입 없음.',
       json.dumps(result,ensure_ascii=False,indent=2),json.dumps(manual,ensure_ascii=False,indent=2),
       '호출·토큰·비용·지연·메모리: run-001/result.json. 실제 회수 원장: retrieval-ledger.json. 원문과 모델 I/O를 보고서마다 복제하지 않는다.',
       'HTTP200, 저장 완료, 자식 completed는 의미 정답과 별개다. 최종 비교 행과 근거의 존재, 적용 범위 및 조사 중단을 함께 판정한다.',
       '\n'.join(result['limitations']), 'MAIN76과 GENOS를 변경하지 않았다. 발견한 결함은 새 ADR에서 일반 계약으로 수정하고 동일 실경로를 후속 검증해야 한다.',
       'prepare.py → candidate refresh/freeze/validate → freeze.py → live.py 각4건 → audit.py → reopen.py 각4건 → report.py → validate --final → status completed → validate --final → graph. 완료된 산출물 덮어쓰기 금지; 재실행은 신규 ADR.']
meta=(A/'README.md').read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$','status: Proposed',meta)
(A/'README.md').write_text('---'+meta+'---\n\n# MAIN76 실제 Risk 질의·대사 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(sections,texts),1))+'\n')
(A/'RESULT.txt').write_text('MAIN76 실제 Risk 질의·대사 검증\n\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n\n세부 근거: artifacts/run-001/manual-review.json 및 사례별 audit.json/answer.txt\n')
(A/'실험/README.md').write_text('# 실제 Risk 질문4건\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
print(json.dumps({'cases':len(summary),'model_calls':total_calls,'product_complete_cases':result['product_complete_cases'],'rows':[s['comparison_rows'] for s in summary]},ensure_ascii=False))
