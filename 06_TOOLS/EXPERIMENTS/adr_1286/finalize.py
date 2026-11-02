"""Finalize recorded live evidence only; never send or alter model proposals."""
from common import *
import re

P=ART/'live/review-whatif'
a=read(P/'audit.json');r=read(P/'result.json');f=read(DES/'freeze.json')
semantic=read(P/'semantic-review.json');wire=read(ART/'contract-wire-check.json')
def condition(label):
    rows=a['responses'].get(label,{}).get('comparison',{}).get('comparisons',[])
    return next((x['after']['status'] for x in rows if x['node_id']=='N2'),None)
checks={
 'baseline_final_claims':a['responses'].get('baseline-after',{}).get('claims',0)>0,
 'numeric_conditions':condition('low')=='TRUE' and condition('high')=='FALSE' and condition('rule')=='TRUE',
 'numeric_no_calls':all(any(t['label']==label and t['http_status']==200 and t['physical_calls']==0 for t in a['turns']) for label in ('low','high','rule')),
 'three_semantic_answers':semantic['all_passed'],
 'baseline_preserved':r.get('baseline_preserved') is True,
 'duplicate_no_calls':all(t.get('duplicate',{}).get('extra_model_calls')==0 for t in a['turns']),
 'source_and_wire_integrity':not any(a[k] for k in ('source_mismatches','acl_violations','wire_mismatches','changed_release_files','changed_inputs','output_cap_fields')),
 'budget_matches':a['physical_budget_matches'],'unknown_zero':a['unknown']==0,
 'resource_safe':not a['resources']['resource_stop'],'cleanup':a['cleanup_completed'],
 'main_unchanged':a['active_pointer_unchanged'],**wire['checks']}
working_changes=[n for n,h in f['files'].items() if sha(ROOT/n)!=h]
script_changes=[n for n,h in f['scripts'].items() if sha(ROOT/n)!=h]
checks['working_and_runner_unchanged']=not working_changes and not script_changes
status='PASS' if all(checks.values()) else 'NOT_PASSED'
result={'status':status,'checks':checks,'semantic_passed':semantic['passed'],'semantic_total':semantic['total'],
 'physical_calls':a['physical_calls'],'seconds':r['seconds'],'model_seconds':a['model_seconds'],
 'reported_cost_usd':a['reported_cost_usd'],'missing_usage_calls':a['missing_usage_calls'],
 'reported_input_tokens':a['reported_input_tokens'],'reported_output_tokens':a['reported_output_tokens'],
 'unknown':a['unknown'],'post_unknown_calls':a['post_unknown_calls'],'turn_calls':a['turn_calls'],
 'initial_baseline_claims':a['responses'].get('initial',{}).get('claims',0),
 'baseline_followup_used':'rereview' in a['responses'],'resources':a['resources'],
 'source_checks':a['source_checks'],'delivered_checks':a['delivered_checks'],
 'source_mismatches':len(a['source_mismatches']),'acl_violations':len(a['acl_violations']),'wire_mismatches':len(a['wire_mismatches']),
 'candidate_revision':f['candidate_revision'],'candidate_files':len(f['files']),
 'working_changes':working_changes,'frozen_script_changes':script_changes,
 'main_changed':False,'quality_certified':False,'oracle_calls':0,
 'semantic_count_definition':semantic['count_definition'],
 'posthoc_quality_findings':semantic['posthoc_quality_findings'],
 'semantic_review':'artifacts/live/review-whatif/semantic-review.json',
 'output_quality_audit':'artifacts/output-quality-audit.json',
 'wire_check':'artifacts/contract-wire-check.json','record_inspection':'artifacts/record-inspection.json',
 'limits':'Single same synthetic in-sample workflow, not causal A/B or representative legal quality. Historical failures preserved; no model answer injection or terminal reruns.'}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True},'verified':result},judge_disagreements=0,
 usage={'physical_model_calls':a['physical_calls'],'reported_cost_usd':a['reported_cost_usd'],'input_tokens':a['reported_input_tokens'],'output_tokens':a['reported_output_tokens']},
 latency={'elapsed_seconds':r['seconds'],'model_seconds':a['model_seconds']},
 error_taxonomy=[{'type':'FAILED_CHECK','checks':[k for k,v in checks.items() if not v]}] if not all(checks.values()) else [])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 f'실제 Qwen {status}. 핵심 주장 채택 가정 {semantic["passed"]}/{semantic["total"]}, 저액에도 출력 품질 결함 잔존. MAIN132 유지·품질 미인증. [상세 결과](artifacts/run-001/result.json). '+semantic['count_definition'],
 'ADR1284는11물리호출에서 가정0/3이었다. 수정1285는 가정 연결 범위를 줄이고 비채택 빈 주장 목록을 서버가 복원하며, 현재 적용과 전체 비교문을 분리하고 질문을 task/facts에서 조립했다. 완료1285와 동일527파일을 변경 없이 시험했다.',
 '[호출 전 고정 기준](artifacts/design/criteria.json).735000원 금액충족·승인 미확인,1725000원 금액불충족·승인 별도 미확인,규칙2450000원에서 기존비용1380000원 금액충족·승인 미확인. 주장 채택·원문/권한/전송·예산·현재값·기준사건 보존을 분리 검증한다.',
 '동일 합성3조문/승인 온톨로지/금액·새 runtime. 기준 사건 뒤 숫자비교 모델0, 저액/고액/규칙 독립 분기. 기준 검토 미완료 시 사전선언 후속1회만 허용, 각 단계 기존 보완1회. UNKNOWN 이후 추가전송 금지. 실제 응답 주입·재작성0.',
 'Qwen3.8-27b/Parasail FP8 우선, 확정429만 사전허용 Near AI 전환 정책. reasoning none/출력 토큰 상한 없음. native FastAPI·SQLite 기록·정확 고정 전송기. [freeze](artifacts/design/freeze.json) · [실제 raw](artifacts/live/review-whatif/raw). Oracle/GENOS 미실행.',
 json.dumps({k:result[k] for k in ('status','semantic_passed','semantic_total','physical_calls','turn_calls','initial_baseline_claims','baseline_followup_used','unknown','checks')},ensure_ascii=False,indent=2),
 '\n\n'.join(row['label']+': '+row['observation'] for row in semantic['rows'])+'\n\n[검토](artifacts/live/review-whatif/semantic-review.json). HTTP200·JSON 형식 통과와 의미/주장 채택을 구분한다.',
 f'실제{a["physical_calls"]}호출/예산차감{a["reserved"]}, {r["seconds"]:.3f}초/모델통신{a["model_seconds"]:.3f}초, 보고${a["reported_cost_usd"]:.8f}. 사용량 미보고{a["missing_usage_calls"]}. 확보원문{a["source_checks"]}/입력span{a["delivered_checks"]}; 원문/ACL/wire불일치 {len(a["source_mismatches"])}/{len(a["acl_violations"])}/{len(a["wire_mismatches"])}. 순수DB·속도 개선율 아님.',
 semantic['interpretation']+'\n\n실제 전송의 중복·서버 확정값·공유 연결과 무손실 복원은 [입력 검사](artifacts/contract-wire-check.json), 스키마는 [wire 감사](artifacts/wire-schema-audit.json), 번호가 달라 기존 동일문자열 반복검사에서 잡히지 않는 gap 참조는 [추가 출력 검사](artifacts/output-quality-audit.json)에 보존했다. 이번 gap reason은433문자로, 과거600문자와 다르다. 전송 스키마는 최소1/최대600문자이며600자를 채우라고 요구하지 않는다. 반복 생성의 공급자 내부 원인은 미확인이다.',
 '동일 합성사례 단1회이며 일반 법률품질 인증이 아니다. 이전 실행과 자연 생성 경로·주장·보완 수가 달라 개선/악화의 인과율이나 대표 성공률을 추정하지 않는다. 숫자·역할 검사는 모든 자유문 의미의 증명이 아니다. Oracle/NFS/GENOS·실제 동시부하 미검증.',
 '이번 제품·MAIN132·Gold·운영DB/DDL·Git·메일·현장배포 변경0. 격리 실험 SQLite 기록만 작성했다. 작업527/동결527 동일, 이전 실패와 모델 원응답 보존. 결과 확인 후 같은 셀 재실행0. 선택 MAIN은 실험 후보와 별도이며 자동 승격하지 않는다.',
 'prepare.py→freeze.py→live.py review-whatif --preflight→live.py review-whatif 단1회→audit.py/wire_audit.py/contract_wire_check.py/inspect_records.py/output_quality_audit.py→기록 기반 의미검토→finalize.py→hash/status/validate/graph. live 재실행 금지; 전체 raw는 무손실gzip과 해시 참조로 보존. inspect_records/output_quality_audit/finalize는 결과 기록을 읽는 사후분석 코드이며 실제 호출 전에 동결한 전송기와 제품은 변경하지 않았다.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1]
front=re.sub(r'(?m)^status:.*$','status: '+('Accepted' if status=='PASS' else 'Rejected'),front)
p.write_text('---'+front+'---\n\n# ADR1286 가정 연결 범위 수정본 실제 Qwen 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
question=read(DES/'cases.json')[0]['request']['json']['question']
sections=[('실행 메타','run-001/verified/review-whatif. 후보·정책·입력 고정은 artifacts/design/freeze.json. 실제 시각/요청/응답은 raw/call-*.'),('사용자 질문 원문',question),('기준답변 — 채점 전용, 제품 입력 비공개','별도 기준답변/평가모델0. 동결한 기술 의미기준은 criteria.json. 제품에는 합성 원문·승인 온톨로지와 실제 사실만 전달.'),('제품 입력을 구성한 원값','design/source.json/ontology-input.json/cases.json 및 실제 raw/canonical을 보존.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n검색효과 비교 없음. stage_ledger not_applicable. 확보·전달 좌표와 ACL 대조는 audit.json.gz.'),('제품 모델 호출 — run·arm별 실제 원문','raw/call-*/request.json.gz·response.json.gz·finished.json. 실제 응답 주입·재작성0.'),('중간 LLM 호출 — router/compiler/verifier/repair','모든 단계·보완은 calls.json/generations.json/turns.json. 숫자비교·재조회 모델0을 별도 확인.'),('채점 호출과 반복 판정','외부 채점0. 실제 기록·최종답변의 수동 의미검토와 새 프로세스 저장/원문/전송 검증. 중복 요청 조회는 확률 반복이 아니다.'),('사례 최종 판정',f'{status}, 가정{semantic["passed"]}/{semantic["total"]}. ../artifacts/run-001/result.json 및 semantic-review.json. 미실행·실패를 성공으로 바꾸지 않았다.')]
(ADR/'실험/질문-001-review-whatif.md').write_text('# 실제 Qwen 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 실제 검증 기록\n\n[질문](질문-001-review-whatif.md) · [manifest](manifest.json) · [결정](../README.md)\n')
report=ROOT/'09_ARTIFACTS/AUDITS/20261102-scenario-scope-contract-live';report.mkdir(exist_ok=False)
(report/'실제실험과_검증결과.txt').write_text('\n\n'.join(h+'\n'+v for h,v in zip(heads,values))+'\n')
put(ART/'support-files.json',{str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('*.py'))})
print(json.dumps(result,ensure_ascii=False))
