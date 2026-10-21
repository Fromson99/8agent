"""Assemble observations after all frozen requests; never modify product or gold."""
from pathlib import Path
import hashlib,json,re,sqlite3,statistics
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0843-main80-live-comparison';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def unique(rows):return [json.loads(s) for s in sorted({canon(r) for r in rows})]
m=read(A/'실험/manifest.json');f=read(D/'freeze.json');cases=read(D/'cases.json');manual=read(O/'manual-review.json')
assert m['reservation']['status']=='in_progress'
assert all(sha(R/n)==h for n,h in f['files'].items())
observations={c['id']:read(O/c['id']/'audit.json') for c in cases}
reopens={c['id']:{'passed':read(O/c['id']/'result.json').get('checks',{}).get('status_answer_identical',False)} for c in cases}
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
        reason=('Not included in the final current child return; this includes superseded earlier results. No claim of legal irrelevance.' if plan['stage_id']=='child_adopted' else 'Not cited by final field or legal comparison rows; read/adopted text remains in native journals.')
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
        'seconds':run['elapsed_seconds'],'peak_rss_kib':run['peak_rss_kib'],'comparison_rows':a['rows'],'field_rows':len(a['field_rows']),'reported_evidence':len(a['evidence_refs']),
        'children':{s:{'status':child['returned_status'],'read_observations':child['read_observations'],'current_adopted':len(child['returned_evidence_ids']),
                       'investigation_runs':len(child['runs'])} for s,child in a['children'].items()},
        'workflow_compare_calls':sum('workflow-compare' in v['call'] for v in a['calls']),
        'unreviewed_sources':len(a['unreviewed_sources']), 'original_span_mismatches':sum(not v['exact_original_match'] for v in a['evidence_span_checks']),
        'saved_status_passed':reopens[cid]['passed'],'manual_review':manual[cid]})
G=R/read(D/'baseline.json')['manifest']['data_path'];db=sqlite3.connect('file:'+str(G/'navigation/navigation.sqlite')+'?mode=ro',uri=True)
corpus=sum(json.loads(r[0]).get('unit_id') is not None for r in db.execute('select json from source'));db.close()
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],'accounting_unit':'case_id + canonical article-root coordinate',
        'computed_post_selection':True,'gold_visible_to_product':False,'runs':[{'run_id':'run-001','arms':[{'arm_id':'observed','declared_stage_ids':[p['stage_id'] for p in plans],
        'cases':ledger_cases,'aggregate':{'cases':len(cases),'presented_total':sum(counts),'gold_total':0}}]}],
        'audit':{'scope':'All native read receipts across every child run; current adopted return and final row citations. Search menus are not measured.',
                 'denominator':'All canonical structured source roots in the pinned navigation index; not a golden or relevant-source denominator.',
                 'source_only_unmapped':{cid:{s:[e['evidence_id'] for e in child['all_read_evidence'] if e['canonical'] is None] for s,child in a['children'].items()} for cid,a in observations.items()},
                 'superseded_results':'Original child returns are retained in workflow_call tables. Last valid evidence and latest attempt are separate; displayed evidence is measured from the actual response.'}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json',ledger)
total_calls=sum(s['model_calls'] for s in summary)
call_records=[c for a in observations.values() for c in a['calls']]
span_checks=[c for a in observations.values() for c in a['evidence_span_checks']]
result={'status':'complete','product_complete_cases':sum(s['status']=='completed' for s in summary),'case_count':len(cases),'cases':summary,
    'product_model_calls':total_calls,'offline_evaluator_model_calls':0,'actual_models':sorted({v['model'] for v in usage}),
    'actual_upstream_providers':sorted({v['upstream_provider'] for v in usage}),
    'transport_error_receipts':sum(bool(c.get('error')) for c in call_records),
    'provider_error_responses':sum(bool(c.get('provider_error')) for c in call_records),
    'successful_response_identity_verified':all(c.get('model')=='qwen/qwen3.8-27b' and c.get('provider')=='Parasail' for c in call_records if c.get('finish')),
    'stored_evidence_records_checked':len(span_checks),'original_span_mismatches':sum(not c['exact_original_match'] for c in span_checks),
    'usage':{'input_tokens':sum(v.get('input_tokens') or 0 for v in usage),'output_tokens':sum(v.get('output_tokens') or 0 for v in usage),
        'reported_cost_usd':sum(v.get('cost_usd') or 0 for v in usage),'successful_response_receipts':len(usage)},
    'frozen_inputs_unchanged':True,'main_generation':80,'main_changed':False,'genos_accessed':False,'quality_certified':False,
    'app_injected':False,'fault_injection':False,
    'limitations':['One known committee question after MAIN80 promotion. No approved gold, holdout or accuracy percentage.',
        'Known834 uses the same liquidity question; new model draws and different code mean this is diagnostic, not controlled causal attribution.',
        'Actual workspace service.application bootstrap selects MAIN80. Single physical send instrumented with ExperimentClient; gateway, policy and authorization unchanged.',
        'Runtime storage is isolated for this observation. GENOS and resident server deployment not exercised.',
        'Source span integrity and saved consumer consistency do not certify legal interpretation or retrieval completeness.']}
put(O/'result.json',result)
m['runs'][0].update(artifact_path=str((O/'result.json').relative_to(R)),status='complete',sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'not_run','basis':'Completed0842 technical context only'},'observed':{'status':'complete','cases':summary}},
    comparisons=[],judge_disagreements=None,usage={'product_model_calls':total_calls,'offline_evaluator_calls':0,**result['usage']},latency={s['case_id']:s['seconds'] for s in summary},error_taxonomy=manual['error_taxonomy'])
m['retrieval_accounting'].update(corpus_total=corpus,before_filter={'observed':before_total},after_filter={'observed':adopted_total},
    presented_total={'observed':sum(counts)},presented_mean={'observed':statistics.mean(counts)},presented_p50={'observed':statistics.median(counts)},
    presented_p95={'observed':sorted(counts)[round((len(counts)-1)*.95)]},golden_recall={'observed':None},selectivity={'observed':statistics.mean(counts)/corpus})
m['retrieval_accounting']['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json')
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q,c,s in zip(m['questions'],cases,summary):
    cid=c['id'];p=A/'실험'/q['file']
    parts=[f'run-001 / observed / {cid}. MAIN80 실제 service.application 부팅과 WORKFLOW_RUN. in_sample=true, decision_eligible=false.',c['question'],
        '승인 정답 없음. 사전 criteria.json의 원문 대조 기준. 정답률·golden recall 미측정.',
        f'../artifacts/run-001/{cid}/request.json, binding.json, health.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/run-001/retrieval-ledger.json: 실제 읽기→자식 채택→최종 인용. 탐색 메뉴 전체는 미측정.',
        f'../artifacts/run-001/{cid}/raw/call-*/request.json 및 response.json: 공통 ExperimentClient 실제 전송 원값.',
        f'../artifacts/run-001/{cid}/audit.json 및 runtime의 원본 journal. 실패와 복구 포함.',
        '평가 모델0회. 정확 span/hash·출처·최종 적용 범위와 소비자를 읽기 전용 대조. 추가 제품 호출 없음.',json.dumps(s,ensure_ascii=False,indent=2)]
    p.write_text(f'# {cid}\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,parts),1))+'\n');q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
sections=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Proposed. MAIN80 실제 모델 관측 기록. 기술 무결성과 법률·검색 품질을 구분한다.',
    'MAIN80의 의미 판단 완화 후보53계약·84기술 상태·활성 서비스13검사 이후 실제 양측 조사와 비교를 확인한다.',
    '첫 호출 전 design/criteria.json 동결: 실제 선택 코드, 원문/출처, 항목 결과, 부분 결과 보존, 저장·중복 소비자를 확인한다.',
    '위원회 역할·심의사항 질문1건을 기존 승인 범위에서 각각1회 실행한다. 제품 코드·질문·예산을 도중 변경하지 않고 모든 성공·부분·실패를 기록한다.',
    'design/freeze.json 및 baseline.json, cases.json. Qwen3.8 / Parasail FP8 / reasoning none / fallback 없음. 앱 주입 없이 실제 로컬 service.application 선택, 물리 전송만 ExperimentClient로 계측.',
    json.dumps(result,ensure_ascii=False,indent=2),json.dumps(manual,ensure_ascii=False,indent=2),
    'run-001/result.json에 호출·토큰·비용·지연, retrieval-ledger.json에 실제 읽기/채택/최종 인용을 기록했다. 샘플1건으로 p50/p95 일반화 금지.',
    'HTTP200·원문 hash 일치·저장 성공은 법률 판단 성공과 별개다. 실제 항목별 확인 결과와 확보 못한 조건을 함께 확인한다.',
    '\n'.join(result['limitations']),
    '제품 코드·데이터·로컬 MAIN80 포인터를 변경하지 않았다. GENOS 미반영. 후속 수정/효과 비교는 새 ADR로 동결한다.',
    'prepare.py → candidate/ADR validate → live.py committee-duties-01 / public-liquidity-01 → audit.py → 읽기 전용 수동 검토 → report.py → hash → validate --final → status completed → validate --final → graph. 완료된 실행 디렉터리 재사용 금지.']
meta=(A/'README.md').read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$','status: Proposed',meta)
(A/'README.md').write_text('---'+meta+'---\n\n# MAIN80 실제 모델 관측\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(sections,texts),1))+'\n')
(A/'RESULT.txt').write_text('MAIN80 실제 모델 관측\n\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n\n세부 근거: artifacts/run-001/manual-review.json 및 사례별 audit.json/answer.txt\n')
(A/'실험/README.md').write_text('# MAIN80 실제 모델 관측\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
print(json.dumps({'cases':len(summary),'model_calls':total_calls,'product_complete_cases':result['product_complete_cases'],'rows':[s['comparison_rows'] for s in summary]},ensure_ascii=False))
