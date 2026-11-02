"""Close the new live experiment from preserved records; no model call."""
from common import *
import re
P=ART/'live/review-whatif'
a=read(P/'audit.json');r=read(P/'result.json');f=read(DES/'freeze.json')
semantic=read(P/'semantic-review.json');wire=read(ART/'contract-wire-check.json');computation=read(ART/'computation-audit.json')
supplement=read(ART/'supplementary-observations.json')
def condition(label):
 rows=a['responses'].get(label,{}).get('comparison',{}).get('comparisons',[])
 return next((x['after']['status'] for x in rows if x['node_id']=='N2'),None)
checks={'baseline_claims':a['responses'].get('baseline-after',{}).get('claims',0)>0,
 'numeric_conditions':condition('low')=='TRUE' and condition('high')=='FALSE' and condition('rule')=='TRUE',
 'numeric_no_calls':all(any(t['label']==label and t['http_status']==200 and t['physical_calls']==0 for t in a['turns']) for label in ('low','high','rule')),
 'three_preregistered_semantic_answers':semantic['all_passed'],'baseline_preserved':r.get('baseline_preserved') is True,
 'duplicate_no_calls':all(t.get('duplicate',{}).get('extra_model_calls')==0 for t in a['turns']),
 'source_and_wire_integrity':not any(a[k] for k in ('source_mismatches','acl_violations','wire_mismatches','changed_release_files','changed_inputs','output_cap_fields')),
 'budget_matches':a['physical_budget_matches'],'unknown_zero':a['unknown']==0,
 'only_parasail_observed':set(a['provider_counts'])=={'parasail/fp8'},
 'resource_safe':not a['resources']['resource_stop'],'cleanup':a['cleanup_completed'],
 'main_unchanged':a['active_pointer_unchanged'],**wire['checks'],**computation['checks']}
working_changes=[n for n,h in f['files'].items() if sha(ROOT/n)!=h]
script_changes=[n for n,h in f['scripts'].items() if sha(ROOT/n)!=h]
checks['working_and_runner_unchanged']=not working_changes and not script_changes
observed=[x for x in computation['responses'] if x.get('has_calculation')]
# Missing responses are coverage gaps, not observed invention of permission.
checks['no_legal_conclusion_inferred']=bool(observed) and all(x['legal_conclusion_confirmed'] is False for x in observed)
status='PASS' if all(checks.values()) else 'NOT_PASSED'
result={'status':status,'checks':checks,'semantic_passed':semantic['passed'],'semantic_total':3,
 'core_passed':semantic['core_passed'],'claims_adopted_branches':sum(x.get('claims_adopted',0)>0 for x in semantic['rows']),
 'physical_calls':a['physical_calls'],'seconds':r['seconds'],'model_seconds':a['model_seconds'],
 'reported_cost_usd':a['reported_cost_usd'],'missing_usage_calls':a['missing_usage_calls'],
 'reported_input_tokens':a['reported_input_tokens'],'reported_output_tokens':a['reported_output_tokens'],
 'unknown':a['unknown'],'post_unknown_calls':a['post_unknown_calls'],'turn_calls':a['turn_calls'],
 'initial_baseline_claims':a['responses'].get('initial',{}).get('claims',0),'baseline_followup_used':'rereview' in a['responses'],
 'resources':a['resources'],'source_checks':a['source_checks'],'delivered_checks':a['delivered_checks'],
 'source_mismatches':len(a['source_mismatches']),'acl_violations':len(a['acl_violations']),'wire_mismatches':len(a['wire_mismatches']),
 'candidate_revision':f['candidate_revision'],'candidate_files':len(f['files']),'working_changes':working_changes,'frozen_script_changes':script_changes,
 'main_changed':False,'quality_certified':False,'oracle_calls':0,'semantic_count_definition':semantic['count_definition'],
 'structured_gap_choices':semantic['structured_gap_choices'],'gap_expansion_live_verified':False,
 'attempted_semantic_branches':semantic['attempted_semantic_branches'],
 'supplementary_observations':supplement,
 'semantic_review':'artifacts/live/review-whatif/semantic-review.json','computation_audit':'artifacts/computation-audit.json',
 'output_quality_audit':'artifacts/output-quality-audit.json','wire_check':'artifacts/contract-wire-check.json','record_inspection':'artifacts/record-inspection.json',
 'limits':'Single known synthetic in-sample workflow, not causal A/B or representative legal quality. Historical failures preserved; no model injection or terminal reruns.'}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True,'completed_code_parent':'ADR1289/verified'},'verified':result},judge_disagreements=0,
 usage={'physical_model_calls':a['physical_calls'],'reported_cost_usd':a['reported_cost_usd'],'input_tokens':a['reported_input_tokens'],'output_tokens':a['reported_output_tokens']},
 latency={'elapsed_seconds':r['seconds'],'model_seconds':a['model_seconds'],'p50_seconds':supplement['p50_seconds'],'p95_seconds':supplement['p95_seconds']},error_taxonomy=[{'type':'FAILED_CHECK','checks':[k for k,v in checks.items() if not v]}] if not all(checks.values()) else [])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 f'실제 Qwen {status}. 주장 채택 {result["claims_adopted_branches"]}/3, 핵심 의미 {semantic["core_passed"]}/3, 사전조건 확인 {semantic["passed"]}/3. MAIN133 유지·품질 미인증. '+semantic['count_definition'],
 'ADR1286 실제8호출은 주장채택1/3이나 저액gap 반복, 고액의 올바른 과거 비교 과차단, 규칙의 옛한도 재사용이 남았다. ADR1289는 서버 계산·전후 비교를 직접 표시하고 미확인 사실은 제공된 ID를 모델이 명시적으로 고르게 했다. 이번에는 완료1289와 같은528파일을 변경 없이 실제 시험했다.',
 '[호출 전 기준](artifacts/design/criteria.json).735000원 금액충족·승인미확인,1725000원 금액불충족·승인 별도미확인,한도2450000원에서 기존비용1380000원 금액충족·승인미확인. 모든 새 가정에 서버 계산표·원문/권한·명시적 미확인ID·무손실 입력·현재값·재조회/기준사건 보존을 검증한다. 계산표만 맞고 주장이 채택되지 않으면 의미 성공이 아니다.',
 '같은 합성3조문·기존 승인 온톨로지·금액을 사용해 새 기준 사건과 세 독립 가정을 한 번씩 실행했다. 기준 검토가 미완료이면 사전 선언한 REVIEW_AGAIN1회만 허용한다. 각 ASSESS의 기존 최초+보완1회, 전체 물리호출20·호출180초·RSS4GiB·가용RAM3GiB·swap증가128MiB 한도를 유지했다. 응답 주입·가정 결과를 보고 같은 셀 다시 실행·온톨로지 자동 승인0.',
 'Qwen3.8-27b/Parasail FP8 우선, reasoning none/출력 토큰 상한 없음. 고정한 기존 routing에는 확정429 시 Near AI1회 전환 승인 규칙이 있고 이번 판정은 Parasail만 관측됐는지 별도로 검사한다. 실제 전환 여부와 공급자는 provider_counts/calls.json에 보존한다. native FastAPI·격리 SQLite·해시 고정 전송기, 운영 Oracle/GENOS 미실행.',
 json.dumps({k:result[k] for k in ('status','semantic_passed','core_passed','claims_adopted_branches','physical_calls','turn_calls','unknown','checks')},ensure_ascii=False,indent=2),
 '\n\n'.join(x['label']+': '+x['observation'] for x in semantic['rows'])+'\n\n[전체 수동 검토](artifacts/live/review-whatif/semantic-review.json). HTTP200·모델 JSON 통과·서버 계산·최종 주장 채택·표현 품질은 각각 구분한다.',
 f'실제{a["physical_calls"]}호출/예산차감{a["reserved"]}, {r["seconds"]:.3f}초/모델통신{a["model_seconds"]:.3f}초, 보고${a["reported_cost_usd"]:.8f}. 입력{a["reported_input_tokens"]}/출력{a["reported_output_tokens"]}토큰, 사용량 미보고{a["missing_usage_calls"]}호출. 확보원문{a["source_checks"]}/전달span{a["delivered_checks"]}, 원문/ACL/wire불일치 {len(a["source_mismatches"])}/{len(a["acl_violations"])}/{len(a["wire_mismatches"])}. 미보고1호출은 UNKNOWN이며 보고 비용은 전체 확정 비용이 아니다. p50/p95는 supplementary-observations.json에 전체6물리호출(기한종료 포함) 기준으로 기록했다. 이전 실험과 속도·비용 개선율을 추정하지 않는다.',
 semantic['interpretation']+'\n\n새 프로세스에서 저장된 기준/저액 답변과 저액 계산표를 검증했다. 고액은 최종답변0, 규칙은 미실행으로 계산표 저장의 실제 확인 범위도 저액1건이다. 제공된 미확인ID의 구조화 선택0으로 전개 경로는 NOT_EXERCISED이며, 제공되지 않은 ID를 고르지 않았다는 빈 집합 검사 통과를 기능 성공으로 확대하지 않는다. 실제 전송은 contract-wire-check/wire-schema-audit/computation-audit, 원응답의 반복·없는 번호는 output-quality-audit, 전체 본문과 오류는 record-inspection 및 raw/canonical에 있다. 전체 원문과 자유문을 그대로 보존하며 출력에 없는 내용으로 결과를 보정하지 않았다.',
 '이미 알려진 합성사례 단1회·고정 순서이며 인과 A/B나 일반 법률품질 인증이 아니다. 과거1286과 자연 생성 경로가 다르므로 단순 전후 성공률·토큰·시간을 인과 효과로 해석하지 않는다. 금액·승인 식은 승인된 것만 실행하고, 최종 효과 N1은 미등록/UNKNOWN이다. 임의 자유문 의미·등록되지 않은 gap·요구문 속 옛값 표시·정상 비교문 과차단의 일반적 해결을 주장하지 않는다. 실제 Oracle/NFS/GENOS·동시부하 미검증.',
 '이번 제품 코드/MAIN133/Gold/운영DB/DDL/Git push/메일/현장배포 변경0. 격리 실험 기록만 작성했고 작업528/동결528/완료1289가 동일하다. 이전 실패를 고쳐 쓰거나 실제 결과 후 같은 셀을 재실행하지 않았다. 완료된 시험 runtime은 원래 파일/전체 SHA를 검증한 무손실 압축으로 보존한다. 자동 MAIN 승격0.',
 'prepare→freeze→live.py review-whatif --preflight→실제 live.py 단1회→audit.py/wire_audit.py/contract_wire_check.py/inspect_records.py/output_quality_audit.py/computation_audit.py→기록 기반 의미검토→finalize→runtime 무손실보관→hash/status/validate/graph. 정확한 파일/정책/입력/전송기/실행기 SHA는 design/freeze.json. 실제 호출 재실행은 새 ADR로 분리하며 이 실행의 live 경로는 다시 쓰지 않는다.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1]
front=re.sub(r'(?m)^status:.*$','status: '+('Proposed' if status=='PASS' else 'Rejected'),front)
p.write_text('---'+front+'---\n\n# ADR1290 서버 계산·비교·미확인 입력 수정본 실제 Qwen\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
question=read(DES/'cases.json')[0]['request']['json']['question']
sections=[('실행 메타','run-001/verified/review-whatif. 후보·정책·입력 고정: artifacts/design/freeze.json. 시각/요청/응답은 raw/call-*.'),('사용자 질문 원문',question),('기준답변 — 채점 전용, 제품 입력 비공개','외부 기준답변/평가모델0. criteria.json의 사전 동결 의미·보존 기준으로 수동 검토하며 제품에는 합성 원문/승인 온톨로지/사실만 전달.'),('제품 입력을 구성한 원값','design/source.json/ontology-input.json/cases.json 및 실제 raw/canonical 전부를 무손실gzip으로 보존.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n검색 효과 비교 없음. stage_ledger not_applicable. 확보·전달 좌표/ACL 대조는 audit.json.gz. 비공개 정답 좌표로 모델 선택을 보정하지 않음.'),('제품 모델 호출 — run·arm별 실제 원문','raw/call-*/request.json.gz·response.json.gz·finished.json. 주입/재작성0. 파일 옆 reference에 압축전후 SHA가 있다.'),('중간 LLM 호출 — router/compiler/verifier/repair','모든 단계/보완 calls.json/generations.json/turns.json. 숫자비교·재조회 추가모델0은 별도 확인.'),('채점 호출과 반복 판정','외부 채점0. 수동 의미검토 및 새 프로세스 저장/원문/전송 대조. 중복 요청은 확률 반복이 아니다. semantic-review.json에 근거 위치를 명시.'),('사례 최종 판정',f'{status}: 주장채택{result["claims_adopted_branches"]}/3, 핵심의미{semantic["core_passed"]}/3, 사전조건 확인{semantic["passed"]}/3. ../artifacts/run-001/result.json. MAIN133 유지.')]
(ADR/'실험/질문-001-review-whatif.md').write_text('# 실제 Qwen 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 검증 기록\n\n[질문](질문-001-review-whatif.md) · [manifest](manifest.json) · [결정](../README.md)\n')
report=ROOT/'09_ARTIFACTS/AUDITS/20261103-scenario-server-computation-live';report.mkdir(exist_ok=False)
(report/'실제실험과_검증결과.txt').write_text('\n\n'.join(h+'\n'+v for h,v in zip(heads,values))+'\n')
print(json.dumps({k:result[k] for k in ('status','physical_calls','semantic_passed','core_passed','claims_adopted_branches','seconds','reported_cost_usd','unknown')},ensure_ascii=False))
