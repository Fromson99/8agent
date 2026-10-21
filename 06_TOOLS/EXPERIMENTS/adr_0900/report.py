"""Finalize the unchanged one-question observation, including its failure."""
from pathlib import Path
import hashlib,json,re

R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0900-main87-charter-stateless-trace';D=A/'artifacts/design';O=A/'artifacts/run-001';C=O/'charter-quorum'
read=lambda p:json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
canon=lambda v:json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def unique(xs):return [json.loads(x) for x in sorted({canon(x) for x in xs})]
m=read(A/'실험/manifest.json');f=read(D/'freeze.json');audit=read(C/'audit.json');run=read(C/'result.json')
assert m['reservation']['status']=='in_progress'
assert all(sha(R/name)==h for name,h in f['files'].items())
plans=m['design']['retrieval_stage_plan']['stages_by_arm']['observed'];stages=[];before=[];before_occ=0
for plan in plans:
    raw=audit['canonical_sets'][plan['stage_id']];after=unique(raw)
    bm={canon(x):x for x in before};am={canon(x):x for x in after}
    added=[am[k] for k in sorted(am.keys()-bm.keys())];discarded=[bm[k] for k in sorted(bm.keys()-am.keys())]
    reason='Not present in the measured final response because assessment failed; not evidence of legal irrelevance.' if plan['stage_id']=='cited' else 'Not in committed SELECT final_ids.'
    stages.append({**plan,'executed':True,'skip_reason':None,'before':before,'added':added,'discarded':discarded,'after':after,
        'before_count':len(before),'added_count':len(added),'discarded_count':len(discarded),'after_count':len(after),
        'occurrence_counts':{'before':before_occ,'after':len(raw),'canonical_collapsed_before':before_occ-len(before),'canonical_collapsed_after':len(raw)-len(after)},
        'discard_receipts':[{'identity':x,'reason':reason} for x in discarded],
        'discard_reason_counts':{reason:len(discarded)} if discarded else {},
        'gold_total':0,'gold_before':0,'gold_added':0,'gold_discarded':0,'gold_after':0,'golden_recall':None,
        'gold_before_identities':[],'gold_added_identities':[],'discarded_gold':[],'gold_after_identities':[]})
    before=after;before_occ=len(raw)
case={'schema_version':'retrieval-stage-ledger-v1','computed_post_selection':True,'gold_visible_to_product':False,
    'accounting_unit':'case_id + canonical article-root coordinate','arm_id':'observed','case_id':'charter-quorum','gold_total':0,'gold_identities':[],'stages':stages}
ledger={'schema_version':'retrieval-stage-ledger-v1','adr_id':m['adr_id'],'experiment_id':m['experiment_id'],
    'accounting_unit':'case_id + canonical article-root coordinate','computed_post_selection':True,'gold_visible_to_product':False,
    'runs':[{'run_id':'run-001','arms':[{'arm_id':'observed','declared_stage_ids':[p['stage_id'] for p in plans],
        'cases':[case],'aggregate':{'cases':1,'presented_total':len(before),'gold_total':0}}]}],
    'audit':{'scope':'Acquired native evidence -> committed SELECT originals (fallback allowed) -> actual public-response citations. No search-menu recall measurement.',
        'failed_final_response':True,'gold':'No approved gold; zero gold_total means unmeasured, not perfect recall.',
        'selected_is_not_legal_adoption':audit['selection_basis'],'denominator':audit['corpus_basis']}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json',ledger)
usage=run['usage'];metrics=audit['execution_stats'];resources=read(A/'artifacts/resource-live.json')
result={'status':'complete','execution_outcome':'failed','case_count':1,'answer_completed':0,'http_status':run['http_status'],
    'error_code':'SOURCE_INVESTIGATION_INCOMPLETE','stage':'ASSESS','product_model_calls':run['model_calls'],'offline_evaluator_calls':0,
    'request_seconds':run['request_seconds'],'transport_seconds':metrics['llm_duration_ms']/1000,
    'other_seconds':run['request_seconds']-metrics['llm_duration_ms']/1000,
    'call_breakdown':{'request':1,'navigation_original':9,'navigation_repair':1,'assessment':1,'reference_judgment':0,'compose':0},
    'batch_observation':{'physical_call':3,'choice':'READ','coordinates':['제368조제1항','제368조제2항','제368조제3항'],
        'selected_ranges':3,'distinct_article_roots':1,'model_calls_for_selection':1},
    'findings':['The READ choice selected three paragraph ranges in one physical call; source cards 3 represented one article, not three separate articles.',
        'Read candidates already included articles 433 and 434, but the model browsed article 368 and repeatedly located article 368-2 / 368.',
        'Call 10 repeated an unchanged structure lookup. Call 11 received that explicit error and repeated the same choice; bounded stop preserved two read originals.',
        'Call 12 returned no supported claims and alleged a missing special-resolution provision at article 368 paragraph 3. Final response failed honestly.',
        'This run did not exercise the reference-judgment batching branch. Its multi-group capacity is code evidence only.'],
    'source_checks':len(audit['span_checks']),'source_mismatches':sum(not x['exact_original_match'] for x in audit['span_checks']),
    'peak_group_rss_bytes':resources['peak_group_rss_bytes'],'worker_ru_maxrss_kib':run['peak_rss_kib'],
    'minimum_available_bytes':resources['min_available_bytes'],'resource_stop':resources['stop_reason'],
    'actual_models':sorted({u['model'] for u in usage}),'actual_providers':sorted({u['upstream_provider'] for u in usage}),
    'usage':{'input_tokens':sum(u.get('input_tokens') or 0 for u in usage),'output_tokens':sum(u.get('output_tokens') or 0 for u in usage),'reported_cost_usd':sum(u.get('cost_usd') or 0 for u in usage)},
    'main_changed':False,'active_generation':87,'frozen_inputs_unchanged':True,'genos_executed':False,'quality_certified':False,
    'limitations':['One known public question; no approved gold or generalization claim.',
        'Local external Qwen3.8/Parasail and approved public scope differ from GENOS internal model/data. Not a reproduction of the exact GENOS 19-call trace.',
        'Low-memory runner explicitly calls gc.collect/malloc_trim after each generation and writes raw observations; non-model time includes this overhead. No attribution of all residual time to DB/search.',
        'Source span integrity is not legal semantic correctness. One completed observation includes a failed product answer.',
        'ADR0899 setup request was rejected before any model call; its failure is preserved separately. No further model rerun.']}
put(O/'result.json',result)
m['runs'][0].update(status='complete',artifact_path=str((O/'result.json').relative_to(R)),sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'observed':{'status':'complete','questions':1,'product_answer_successes':0,'legal_accuracy':None,'result':str((O/'result.json').relative_to(R))}},comparisons=[],judge_disagreements=None,
    usage={'product_model_calls':run['model_calls'],'offline_evaluator_calls':0,**result['usage']},
    latency={'sample_size':1,'request_seconds':run['request_seconds'],'transport_seconds':result['transport_seconds'],'p50_seconds':run['request_seconds'],'p95_seconds':run['request_seconds'],'generalizable':False},
    error_taxonomy=[{'type':'governing_rule_selection','count':1,'basis':'Wrong coordinate pursued despite relevant offered read targets.'},{'type':'other','count':1,'basis':'Repeated unchanged structure lookup including bounded correction.'}])
n=len(before);m['retrieval_accounting'].update(corpus_total=audit['corpus_total'],before_filter={'observed':len(unique(audit['canonical_sets']['native_read']))},after_filter={'observed':len(unique(audit['canonical_sets']['selected']))},
    presented_total={'observed':n},presented_mean={'observed':n},presented_p50={'observed':n},presented_p95={'observed':n},golden_recall={'observed':None},selectivity={'observed':n/audit['corpus_total']})
m['retrieval_accounting']['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json')
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
parts=['run-001 / observed / charter-quorum. 실제 선택 MAIN87 service.service RAG_ASK. 인샘플 관측이며 승격 대상 아님.',read(D/'cases.json')[0]['question'],
    '승인 정답/정답률 없음. 원문과 source/span만 대조했으며 모델의 법률 해석을 승인하지 않는다.',
    '../artifacts/design/freeze.json, baseline.json, cases.json 및 run-001/charter-quorum/request.json, binding.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/run-001/retrieval-ledger.json: 원문 확보→ASSESS 전달→실제 공개 응답 인용(실패로0). 검색 메뉴 회수율 미측정.',
    '../artifacts/run-001/charter-quorum/raw-runtime.tar.gz의 raw/call-*/request.json 및 response.json. archive-manifest.json의 해시/복원 방법. canonical/*.json.gz와 wire/*.json.gz에 실제 단계 입력/출력도 보존.',
    '../artifacts/run-001/charter-quorum/call-summary.json, audit.json 및 압축 보존한 runtime journal. 수정 호출과 실패도 포함.',
    '평가 모델0회. 추가 모델 재실행 없음. 원문8레코드 불일치0은 법률 판단 정확도와 별개.',json.dumps(result,ensure_ascii=False,indent=2)]
q=m['questions'][0];qp=A/'실험'/q['file'];qp.write_text('# charter-quorum\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,parts),1))+'\n');q['sha256']=sha(qp)
put(A/'실험/manifest.json',m)
sections=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Proposed. 호출·묶음 전달 관측 완료, 제품 답변 실패. MAIN 변경 없음.',
    '사용자의 GENOS 약4분/19회 보고와 조문별 개별 호출 의문을 확인한다. GENOS 직접 접근은 불가하므로 실제 로컬 선택 서비스에서 공개 질문1건을 실행했다.',
    '첫 모델 호출 전 design/criteria.json 동결. 단계별 물리 호출, 입력/출력과 읽기 대상 수, 원문 무결성·자원 한도를 관측한다.',
    '한 질문·한 실제 모델 실행. ADR0899의 세션 입력 오류는 모델0회로 보존하고 이 ADR에서 단발 API 계약을 재동결했다.',
    'MAIN87 선택 frozen 코드·실행 입구·원문 manifest·모델 정책을 freeze.json에 결속. Qwen3.8/Parasail FP8/reasoning none/fallback 없음.',
    json.dumps(result,ensure_ascii=False,indent=2),
    '3번째 호출에서 제368조의 1·2·3항을 한 번에 선택했다. 제433·434조가 후보에 있었으나 다른 좌표를 반복 탐색했다. 같은 구조 검색의 수정 요청에도 같은 결정을 반복해 조사 종료 후 ASSESS에서 근거 부족 실패했다.',
    f'물리12호출, 요청 {run["request_seconds"]:.3f}초, 모델 전송 {result["transport_seconds"]:.3f}초. 나머지 시간은 검색/상태/계측/강제 메모리 회수 등을 포함하며 세부 귀속 미계측. 비용/토큰은 run-001/result.json. 모집단과 실제 읽기/전달/최종 인용은 ledger에 기록.',
    '조문·항마다 독립 모델 호출이 필수는 아니다. 묶어서 전달한 뒤에도 모델의 조사 행동 선택이 반복될 수 있다. 이번 한 건의 지연·실패를 GENOS 현장에 그대로 대입하지 않는다.',
    '\n'.join(result['limitations']),
    '제품 코드·원문·프로필·MAIN 포인터 변경 없음. 후속 효과 비교/개선은 새 ADR로 동결한다. 이번 원시 실패를 보존한다.',
    'prepare.py → resource_guard.py 아래 live.py charter-quorum → observe.py → report.py → archive.py → hash/status/validate --final/graph. 완료된 실행 폴더 재사용 금지; 새 모델 재실행은 새 ADR 필요.']
meta=(A/'README.md').read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$','status: Proposed',meta)
(A/'README.md').write_text('---'+meta+'---\n\n# 정관 변경 질문 호출·묶음 읽기 관측\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(sections,texts),1))+'\n')
(A/'실험/README.md').write_text('# 질문별 관측\n\n- [charter-quorum]('+q['file']+'): 모델12회, 답변 실패, 원문 묶음 읽기 확인.\n')
(A/'RESULT.txt').write_text('실제 로컬 MAIN87 정관 변경 질문 관측\n\n'+json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'model_calls':run['model_calls'],'request_seconds':run['request_seconds'],'transport_seconds':result['transport_seconds'],'answer_completed':0,'evidence_mismatches':result['source_mismatches']},ensure_ascii=False))
