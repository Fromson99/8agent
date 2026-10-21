"""Finalize the unchanged one-question observation, including its failure."""
from pathlib import Path
import hashlib,json,re

R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0907-closed-reference-charter-trace';D=A/'artifacts/design';O=A/'artifacts/run-001';C=O/'charter-quorum'
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
    reason='Not present in the actual final response; not evidence of legal irrelevance.' if plan['stage_id']=='cited' else 'Not in committed SELECT final_ids.'
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
        'failed_final_response':run.get('http_status')!=200,'gold':'No approved gold; zero gold_total means unmeasured, not perfect recall.',
        'selected_is_not_legal_adoption':audit['selection_basis'],'denominator':audit['corpus_basis']}}
ledger['artifact_sha256']=hashlib.sha256(canon(ledger).encode()).hexdigest();put(O/'retrieval-ledger.json',ledger)
from collections import Counter
usage=run['usage'];metrics=audit['execution_stats'];resources=read(A/'artifacts/resource-live.json');body=read(C/'response.json').get('body',{})
answer=body.get('answer',{});calls=read(C/'call-summary.json')
completed=run.get('http_status')==200 and bool(answer.get('text')) if isinstance(answer,dict) else False
batches=[{'call':r['call'],'selected_ranges':len(r['selected_read_targets']),'targets':r['selected_read_targets']} for r in calls if r.get('choice')=='READ']
first=next((r for r in calls if r.get('read_candidates')),None)
restored=[{k:r.get(k) for k in ('target','coordinate','article','title','preview')} for r in (first or {}).get('read_candidates',[]) if any(x in str(r.get('coordinate',''))+' '+str(r.get('article','')) for x in ('제433조','제434조'))]
previous=read(R/'04_EXPERIMENTS/ADR/ADR-0904-preserved-input-charter-trace/artifacts/run-001/result.json')
result={'status':'complete','execution_outcome':'answer_returned' if completed else 'partial_or_failed','answer_completed':int(completed),
 'http_status':run.get('http_status'),'answer_status':body.get('answer_status'),'product_model_calls':run['model_calls'],'offline_evaluator_calls':0,
 'request_seconds':run.get('request_seconds'),'transport_seconds':sum(c.get('seconds',0) for c in calls),'call_breakdown':dict(Counter(c['phase'] for c in calls)),
 'batch_reads':batches,'first_menu_stored_titles':restored,'source_checks':len(audit['span_checks']),
 'source_mismatches':sum(not x['exact_original_match'] for x in audit['span_checks']),
 'peak_group_rss_bytes':resources['peak_group_rss_bytes'],'minimum_available_bytes':resources['min_available_bytes'],'resource_stop':resources['stop_reason'],
 'actual_models':sorted({u['model'] for u in usage}),'actual_providers':sorted({u['upstream_provider'] for u in usage}),
 'usage':{'input_tokens':sum(u.get('input_tokens') or 0 for u in usage),'output_tokens':sum(u.get('output_tokens') or 0 for u in usage),'reported_cost_usd':sum(u.get('cost_usd') or 0 for u in usage)},
 'prior_known_observation':{'model_calls':previous['product_model_calls'],'request_seconds':previous['request_seconds'],'answer_completed':previous['answer_completed'],'controlled_comparison':False},
 'active_MAIN_changed':False,'active_generation':87,'working_code_integrated':True,'genos_executed':False,'quality_certified':False,
 'limitations':['One known public question, not unseen quality or causal performance evaluation.',
 'Explicit candidate app injection into exact service.py and native API. Selected active MAIN87 remains unchanged.',
 'Single stochastic run; choice variation and external provider timing prevent causal or general performance attribution.',
 'Local external Qwen3.8 Parasail FP8 differs from GENOS internal model and data. GENOS19call trace not available.',
 'gc.collect/malloc_trim after each generation and raw observation contribute to elapsed time. Peak RAM is this guarded run, not a production memory guarantee.',
 'Source integrity checks are not legal interpretation certification. No offline model evaluator.']}
put(O/'result.json',result)
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'observed':{'status':'complete','questions':1,'product_answer_successes':int(completed),'legal_accuracy':None,'result':str((O/'result.json').relative_to(R))}},comparisons=[],judge_disagreements=None,
 usage={'product_model_calls':run['model_calls'],'offline_evaluator_calls':0,**result['usage']},latency={'sample_size':1,'request_seconds':run.get('request_seconds'),'transport_seconds':result['transport_seconds'],'generalizable':False},error_taxonomy=[])
n=len(before);m['retrieval_accounting'].update(corpus_total=audit['corpus_total'],before_filter={'observed':len(unique(audit['canonical_sets']['native_read']))},after_filter={'observed':len(unique(audit['canonical_sets']['selected']))},presented_total={'observed':n},presented_mean={'observed':n},presented_p50={'observed':n},presented_p95={'observed':n},golden_recall={'observed':None},selectivity={'observed':n/audit['corpus_total']})
m['retrieval_accounting']['stage_ledger']['sha256']=sha(O/'retrieval-ledger.json')
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
parts=['run-001 / observed / charter-quorum. 격리된 검증 코드의 service.py RAG_ASK. 인샘플 관측; 승격 아님.',read(D/'cases.json')[0]['question'],
 '승인 정답/평가 모델 없음. 실제 원문 span의 해시와 문자 범위를 기술 검사했다.',
 '../artifacts/design/freeze.json, baseline.json, cases.json 및 run-001/charter-quorum/request.json, binding.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/run-001/retrieval-ledger.json: 확보→선택→최종 인용. 검색 메뉴 정답 회수율은 미측정.',
 '../artifacts/run-001/charter-quorum/raw-runtime.tar.gz 및 archive-manifest.json. canonical/와 wire/의 gzip 기록은 실제 입력·출력이다.',
 '../artifacts/run-001/charter-quorum/call-summary.json과 audit.json에 물리 호출별 단계·대상·실패를 보존한다.',
 '평가 모델0회. 한 질문 한 실행, 재시도는 기존 제품의 예산 안에서만 수행. 원문 일치는 해석의 정답 인증이 아니다.',json.dumps(result,ensure_ascii=False,indent=2)]
q={'number':1,'case_id':'charter-quorum','file':'질문-001-charter-quorum.md'};qp=A/'실험'/q['file'];qp.write_text('# charter-quorum\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,parts),1))+'\n');q['sha256']=sha(qp);m['questions']=[q];put(A/'실험/manifest.json',m)
sections=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['완료 참조 판단 유지·복귀 재사용을 검증한 코드를 동일 사용자 질문으로 한 번 관측했다. MAIN 변경 없음.',
 '이전 로컬 관측11호출/171.430초에서 완료한 SKIP 참조가 다시 UNDETERMINED로 표시되고 RETURN_TO 뒤 재판단된 결함을 확인했다.',
 'design/criteria.json을 첫 호출 전 동결. 물리 호출·입출력·원문 일치·자원 한도·최종 결과를 보존한다.',
 '알려진 사용자 질문 1건, 단일 실행. 코드 변경·추가 후보·사후 재실행 없음.',
 'ADR0906 검증 코드, MAIN87 원문·프로필, 외부 Qwen3.8/Parasail FP8/reasoning none/fallback 없음. GENOS와 별도.',
 json.dumps(result,ensure_ascii=False,indent=2),
 'call-summary.json의 선택 원문과 단계별 판단을 확인한다. 완료 여부와 법률 의미 정확성은 별도다.',
 f"물리{run['model_calls']}회, 요청{run.get('request_seconds',0):.3f}초, 모델 전송 합계{result['transport_seconds']:.3f}초. 원문·원장·자원 자료 보존.",
 '완료 참조 판단 유지 수정 후의 단일 관측으로 설명한다. 이전 실행과의 수치 차이는 통제된 성능 검증이 아니다.',
 '\n'.join(result['limitations']),
 '작업 코드에 검증된 변경은 통합했다. 활성 MAIN87·GENOS 반영 없음. rollback은 09_ARTIFACTS/AUDITS/20261019-reference-continuity-fix/integration.json의 해시와 백업을 따른다.',
 'prepare.py → resource_guard.py 아래 live.py charter-quorum → observe.py → report.py → archive.py → artifacts manifest/hash/status/validate --final/graph. 원시 기록 덮어쓰기 금지.']
meta=(A/'README.md').read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$','status: Proposed',meta)
(A/'README.md').write_text('---'+meta+'---\n\n# 완료 참조 판단 유지 후 정관 질문 관측\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(sections,texts),1))+'\n')
(A/'실험/README.md').write_text('# 실제 질문 관측\n\n- [charter-quorum]('+q['file']+'): '+str(run['model_calls'])+'회, 답변 완료 '+str(completed)+'.\n')
print(json.dumps({k:result[k] for k in ('product_model_calls','request_seconds','answer_completed','source_checks','source_mismatches','peak_group_rss_bytes')},ensure_ascii=False))
