"""Post-run report from preserved actual outputs and separate manual review; no model calls."""
from common import *
import re,statistics,math
P=ART/'live/review-whatif';a=read(P/'audit.json');r=read(P/'result.json');f=read(DES/'freeze.json')
semantic=read(P/'semantic-review.json');wire=read(ART/'contract-wire-check.json')
computation=read(ART/'computation-audit.json');display=read(ART/'display-audit.json')
supplement=read(ART/'supplemental-audit.json')
prior=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1295-main134-scenario-display-live/artifacts/run-001/result.json')
def condition(label):
 rows=a['responses'].get(label,{}).get('comparison',{}).get('comparisons',[])
 return next((x['after']['status'] for x in rows if x['node_id']=='N2'),None)
checks={'baseline_claims':a['responses'].get('baseline-after',{}).get('claims',0)>0,
 'numeric_conditions':condition('low')=='TRUE' and condition('high')=='FALSE' and condition('rule')=='TRUE',
 'numeric_no_calls':all(any(t['label']==label and t['http_status']==200 and t['physical_calls']==0 for t in a['turns']) for label in ('low','high','rule')),
 'three_semantic_answers':semantic['all_passed'],'baseline_preserved':r.get('baseline_preserved') is True,
 'all_duplicate_no_calls':bool(a['turns']) and all(t.get('duplicate',{}).get('extra_model_calls')==0 for t in a['turns']),
 'source_and_wire_integrity':not any(a[k] for k in ('source_mismatches','acl_violations','wire_mismatches','changed_release_files','changed_inputs','output_cap_fields')),
 'budget_matches':a['physical_budget_matches'],'unknown_zero':a['unknown']==0,
 'no_calls_after_unknown':a['post_unknown_calls']==0,
 'resource_safe':not a['resources']['resource_stop'],'cleanup':a['cleanup_completed'],
 'main_unchanged':a['active_pointer_unchanged'],**wire['checks'],**computation['checks'],
 'all_three_ui_observed':display['all_three_observed'],
 'observed_history_separated':display['observed_history_separated'],
 'observed_exact_ids_absent':display['observed_exact_ids_absent']}
working=[n for n,h in f['files'].items() if sha(ROOT/n)!=h]
scripts=[n for n,h in f['scripts'].items() if sha(ROOT/n)!=h]
checks['working_and_frozen_runner_unchanged']=not working and not scripts
calls=read(P/'calls.json');seconds=sorted(c['seconds'] for c in calls)
percentile=lambda p:seconds[max(0,math.ceil(p*len(seconds))-1)] if seconds else None
status='PASS' if all(checks.values()) else 'NOT_PASSED'
result={'status':status,'checks':checks,'semantic_passed':semantic['passed'],'semantic_total':3,
 'claims_adopted_branches':sum(x.get('claims_adopted',0)>0 for x in semantic['rows']),
 'physical_calls':a['physical_calls'],'unknown':a['unknown'],'post_unknown_calls':a['post_unknown_calls'],
 'seconds':r['seconds'],'model_seconds':a['model_seconds'],'reported_cost_usd':a['reported_cost_usd'],
 'missing_usage_calls':a['missing_usage_calls'],'input_tokens':a['reported_input_tokens'],'output_tokens':a['reported_output_tokens'],
 'provider_counts':a['provider_counts'],'finish_reasons':a['finish_reasons'],'turn_calls':a['turn_calls'],
 'resources':a['resources'],'source_checks':a['source_checks'],'delivered_checks':a['delivered_checks'],
 'source_mismatches':len(a['source_mismatches']),'acl_violations':len(a['acl_violations']),'wire_mismatches':len(a['wire_mismatches']),
 'candidate_files':len(f['files']),'candidate_revision':f['candidate_revision'],'working_changes':working,'frozen_script_changes':scripts,
 'initial_baseline_claims':a['responses'].get('initial',{}).get('claims',0),'baseline_rereview_used':'rereview' in a['responses'],
 'current_publication_checks':a['current_publication_checks'],
 'supplemental_saved_ui_checks':supplement['rows'],
 'unique_acquired_spans':supplement['unique_acquired_spans'],
 'semantic_display_live_status':'NOT_EXERCISED',
 'failed_check_interpretation':'False display/calculation/no-conclusion checks represent missing semantic answers, not observed ID leakage, historical mixing, wrong calculations or invented permission.',
 'structured_gap_choices':sum(len(x['selected']) for x in computation['wire']),
 'raw_offered_id_leak_calls':[x['call'] for x in display['raw_proposals'] if x['exact_offered_id_in_reason_indexes']],
 'semantic_review':str((P/'semantic-review.json').relative_to(ROOT)),
 'previous_failed_observer':{'adr':'ADR1295','physical_calls':prior['physical_calls'],'physical_unknown':prior['physical_unknown'],
  'product_unknown':prior['product_unknown'],'reported_cost_usd':prior['reported_cost_usd']},
 'task_total_physical_calls':a['physical_calls']+prior['physical_calls'],
 'task_total_reported_cost_usd':a['reported_cost_usd']+prior['reported_cost_usd'],
 'latency':{'p50_seconds':statistics.median(seconds) if seconds else None,'p95_seconds_nearest_rank':percentile(.95),'denominator':'Every physical request including confirmed errors and timeouts'},
 'quality_certified':False,'oracle_calls':0,'main_changed':False,
 'limits':'Known synthetic in-sample probe, one fixed branch order; no causal A/B, browser, field GENOS, Oracle live or general legal-quality claim.'}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True,'completed_code_parent':'ADR1292/verified'},'verified':result},judge_disagreements=0,
 usage={'physical_model_calls':a['physical_calls'],'reported_cost_usd':a['reported_cost_usd'],'input_tokens':a['reported_input_tokens'],'output_tokens':a['reported_output_tokens']},
 latency={'elapsed_seconds':r['seconds'],'model_seconds':a['model_seconds'],**result['latency']},
 error_taxonomy=[{'type':'FAILED_CHECK','checks':[k for k,v in checks.items() if not v]}] if status!='PASS' else [])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 f'실제 Qwen {status}. 주장 채택 {result["claims_adopted_branches"]}/3, 사전 의미·표현 확인 {semantic["passed"]}/3. MAIN134 유지. '+semantic['count_definition'],
 'ADR1292는 RAG·온톨로지·공통 화면의 연결을 MAIN134에 반영했고, 현재 가정의 미확인 사유와 기준 사건 이력을 분리했다. 정확히 제공한 computed_gap_ref를 자유문에 넣으면 원제안은 보존하고 기존 보완1회를 사용한다. 앞선 ADR1295는 정상 HTTP200 뒤 실험기 calls.json 재작성 예외로 제품UNKNOWN/502가 됐다. 그 실패를 보존하고 이번에는 관측기만 고쳐 새로운 격리 사건에서 실행했다.',
 '[호출 전 기준](artifacts/design/criteria.json). 저액735000원 금액TRUE, 고액1725000원 FALSE, 한도2450000원으로 변경 시 기존1380000원 TRUE. 승인UNKNOWN/최종효과 미확정 유지. 현재 설명과 기준 이력 분리, 정확한 미확인ID 선택, 원문/권한/실제 전송/저장/재조회/기준사건 보존.',
 '합성3조문과 기존 승인 온톨로지로 기준 사건+독립3가정. 기준 검토가 미완료인 경우 명시 재검토1회만 허용. 각 새 가정 최초/기존보완, 전체 물리20/호출180초. UNKNOWN 뒤 추가모델0. 429 확인 시 기존 정책의 NearAI1회 전환만 허용. 실행 전 observer 정상/429/예외 로컬3검사 및 자원8검사 통과. 같은 실패 journal을 열어 재실행하지 않았다.',
 'Qwen3.8-27b, Parasail FP8 우선·확정429에만 NearAI FP8, reasoning none/출력상한없음. 선택 MAIN134 서빙515파일 모두 후보539에 정확 결속. immutable transport/import/정책/입력/실행기 해시 고정. native FastAPI·격리SQLite, 실제 요청/전체 원응답·상태와 비용 보존. 새 모델의 컴파일·승인·게시나 운영 Oracle은 이번 실험에 포함하지 않는다.',
 json.dumps({k:result[k] for k in ('status','claims_adopted_branches','semantic_passed','physical_calls','unknown','turn_calls','checks')},ensure_ascii=False,indent=2),
 '\n\n'.join(x['label']+': '+x['observation'] for x in semantic['rows'])+'\n\n[전체 의미 검토](artifacts/live/review-whatif/semantic-review.json). HTTP200, 구조 통과, 서버 계산, 최종 주장 채택, 화면 표시를 분리한다.',
 f'이번 실제{a["physical_calls"]}회·{r["seconds"]:.3f}초(모델통신{a["model_seconds"]:.3f}초)·보고${a["reported_cost_usd"]:.8f}, 입력{a["reported_input_tokens"]}/출력{a["reported_output_tokens"]}, 사용량 미보고{a["missing_usage_calls"]}회. 초기 관측기 실패1295를 포함하면 총{result["task_total_physical_calls"]}호출·보고${result["task_total_reported_cost_usd"]:.8f}. 확보원문{a["source_checks"]}/전달span{a["delivered_checks"]}, 원문/ACL/wire불일치{len(a["source_mismatches"])}/{len(a["acl_violations"])}/{len(a["wire_mismatches"])}. 사용량 미보고 호출 비용은 미확정이며 보고액을 실제 총 청구액으로 보장하지 않는다. 검색 정책 변경/효율 비교0, 인과 개선율 없음.',
 semantic['interpretation']+'\n\n이번 숫자비교는 승인된 N2/N3만 실행한다. 최종효과N1은 미등록/UNKNOWN으로 남는다. 기준/숫자비교/복원5응답은 새 프로세스에서 저장 검증 및 화면 함수 투영을 확인했다. 가정 의미답변이 없어 display-audit의 표시·ID·현재/과거 검사는 미관측이며 semantic-*-ui.txt는 생성되지 않았다. false 판정은 미도달이며 실제 값 오류/ID누출/허용추론을 관측했다는 뜻이 아니다. 무손실 입력·서버 값 재작성 여부는 contract-wire-check/computation-audit, 원응답과 오류는 raw/canonical/record-inspection, 숫자 화면은 supplemental-audit 및 low/high/rule-ui.txt에 보존했다. 저장 원문 대조18건은 복제 journal을 포함하고 고유원문span은2개다. 수동 검토는 제품 답변을 수정하지 않는다.',
 '이미 알려진 합성 사례의 고정 순서1회, 인샘플 probe다. 임의 문장 의미·미등록ID·법률품질 일반화나 이전 실험 대비 인과율을 주장하지 않는다. UI는 실제 답변을 동결된 표시 함수에 연결해 확인했으며 브라우저 클릭/GENOS 현장 배포 검증은 아니다. 실제 Oracle/NFS/동시부하는 별도 범위다. 구조화gap 선택·ID 보완이 미발생했다면 NOT_EXERCISED로 구분한다.',
 '이번 제품/MAIN134/Gold/운영DB/DDL/Git push/메일/현장 변경0. 작업539/완료1292/동결539 및 서빙515 대조, runtime 무손실 SHA 보관. 원래1295의실패·제품UNKNOWN은 성공으로 고치지 않았다. 추가 모델은 이 실험 종료 뒤 호출하지 않는다.',
 'prepare→observer_check(외부0)→freeze→다른실험 종료/자원확인→preflight→live.py 단1회→audit/wire_audit/contract_wire_check/inspect_records/output_quality_audit/computation_audit/display_audit→수동기록→finalize→runtime 보관→hash/status/validate/graph. 정확한 파일 SHA는 design/freeze.json. 완료한 live 셀 재실행 금지; 새 가설은 새 ADR.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1]
front=re.sub(r'(?m)^status:.*$','status: '+('Proposed' if status=='PASS' else 'Rejected'),front)
p.write_text('---'+front+'---\n\n# ADR1297 MAIN134 실제 모델·가정·표시 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
question=read(DES/'cases.json')[0]['request']['json']['question']
sections=[('실행 메타','run-001/verified/review-whatif. 동결코드/입력/정책: design/freeze.json. 실제시각/공급자: raw/call-*/started/finished.json.'),('사용자 질문 원문',question),('기준답변 — 채점 전용, 제품 입력 비공개','외부 정답/채점모델0. 동결 criteria의 합성 의미·보존 기준과 실제 원문으로 사후 수동검토. 기준답변을 제품 입력에 넣지 않음.'),('제품 입력을 구성한 원값','design/source.json/ontology-input.json/cases.json, raw/call-*/request.json.gz 및 canonical 전체 보존.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n회수효과 비교 없음, 변경0·고정된 기존source/index 사용. 원문/ACL 좌표 대조는 audit.json.gz.'),('제품 모델 호출 — run·arm별 실제 원문','실제 system/user/schema·전체 원응답: raw/call-*/*.json.gz. 각 reference의 압축전후 SHA로 복원 확인. 기준답변 주입·실제 출력수정0.'),('중간 LLM 호출 — router/compiler/verifier/repair','전체 calls/generations/turns.json, canonical/*-summary.json과 raw 원문. 모든 물리429/전환/UNKNOWN도 포함. 수치비교·재조회 모델0 별도 검증.'),('채점 호출과 반복 판정','외부 채점0. 수동 의미검토 semantic-review.json과 새프로세스 저장검증. 실제 출력의 채택/실패/미실행을 구분; 중복조회는 확률 반복 아님.'),('사례 최종 판정',f'{status}: 주장채택{result["claims_adopted_branches"]}/3, 사전 의미·표현{semantic["passed"]}/3. ../artifacts/run-001/result.json. MAIN134 유지.')]
(ADR/'실험/질문-001-review-whatif.md').write_text('# 실제 Qwen 기록\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 검증\n\n[질문](질문-001-review-whatif.md) · [manifest](manifest.json) · [결정](../README.md)\n')
report=ROOT/'09_ARTIFACTS/AUDITS/20261103-main134-display-live';report.mkdir(exist_ok=True)
(report/'실제실험과_검증결과.txt').write_text('\n\n'.join(h+'\n'+v for h,v in zip(heads,values))+'\n')
print(json.dumps({k:result[k] for k in ('status','physical_calls','seconds','reported_cost_usd','task_total_reported_cost_usd','claims_adopted_branches','semantic_passed','unknown')},ensure_ascii=False))
