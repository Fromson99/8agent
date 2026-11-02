"""Publish measured results without another model call or MAIN promotion."""
from common import *
import re
P=ART/'live/gold-369';a=read(P/'audit.json');r=read(P/'result.json');review=read(P/'content-review.json');dup=a['duplicate']
gates={'error_contracts':read(ART/'checks-working-001.json')['passed']==20,
 'api_answer':a['http_status']==200 and a['answer_chars']>0,
 'persisted_answer':any(x['status']=='COMPLETE' and x['same_text'] for x in a['stored_responses']),
 'question_coverage':review['passed'],
 'original_acl':a['source_checks']>0 and not a['source_mismatches'] and not a['acl_violations'],
 'wire':len(a['attempts'])==a['physical_calls'] and not a['wire_mismatches'],
 'budget':a['physical_budget_matches'] and not a['output_cap_fields'],
 'unknown':a['unknown']==0 and a['post_unknown_calls']==0,
 'resource':a['resources']['resource_stop'] is None,
 'code_data':not a['changed_release_files'] and not a['changed_inputs'],
 'process':a['cleanup_completed'],
 'duplicate':bool(dup and dup['http_status']==200 and dup['same_answer'] and dup['extra_model_calls']==0)}
passed=all(gates.values());failed=[k for k,v in gates.items() if not v]
result={'status':'KNOWN_CASE_FUNCTIONAL_PASS' if passed else 'ERROR_REPAIR_VERIFIED_E2E_INCOMPLETE',
 'gates':gates,'actual':r,'audit_path':str((P/'audit.json').relative_to(ROOT)),
 'model_calls':a['physical_calls'],'unknown':a['unknown'],'model_seconds':a['model_seconds'],
 'reported_cost_usd':a['reported_cost_usd'],'missing_usage_calls':a['missing_usage_calls'],
 'content_review':review,'resources':a['resources'],'ontology_enabled':False,'oracle_access':False,
 'working_changes':read(ART/'working-integration.json'),'main_promoted':False,
 'quality_certified':False,'comparison_limit':'One known stochastic case; base MAIN129 vs previous MAIN128; no DB-only A/B or legal quality certification'}
put(RUN/'result.json',result)
text=f'''오류 처리 수정 후 SQLite 실제 재시험 — ADR1249 / 2026-10-30

결과: {result['status']}
실제 API HTTP {a['http_status']}, 최종 답변 {a['answer_chars']}자.
요청 실행 {r['seconds']:.3f}초, 실제 모델 {a['physical_calls']}회 / UNKNOWN {a['unknown']}회.
모델 통신 합계 {a['model_seconds']:.3f}초. 보고 비용 ${a['reported_cost_usd']:.8f}, 사용량 미보고 {a['missing_usage_calls']}회.
미통과 기준: {', '.join(failed) or '없음'}.

수정과 검증
1. 실험 연결기가 실제 시간 초과 원인과 부분응답 진단을 보존하도록 수정. 지원하지 않는 TransportError 생성자 인자 사용 제거, 기한 종료는 MODEL_DEADLINE_EXCEEDED/504.
2. 네이티브 예약 전송을 공통 연결기로 옮겨 숨은 공급자 재시도 방지. 확정429 전환은 네이티브 gateway가 담당.
3. ProposalError/일반 예외 처리에서 잘못 복사된 공급자 전환 코드를 제거. 원래 오류를 exc.unknown 접근 오류로 덮지 않으며 FAILED/UNKNOWN 보존.
기존 MAIN129에서 4결함 재현/5통과. 수정 후보 단위18+실제 API2 통과, 작업 반영 후 같은20 통과.
기한/연결/읽기/형식/정책오류·429/500·정상전송·예산만료·원인연결·실제 API504/502를 확인. 합성 검사는 모델0회.
합성판정 뒤 사용자 수정 지시로 작업3파일+해시pin31=34파일 반영. 선택 MAIN129 포인터/배포리비전은 유지.
후보497파일(선택495+실험연결기2)을 동결해 실제 native service에서 실행. 시험용 연결기 validate_model 누락 등 준비 실패 원본도 보존.

실제 실험 범위
질문: {read(DES/'cases.json')[0]['request']['json']['question']}
원문·검색·기록은 SQLite. 상법 document_id 7bbe815ff43b6635 한 문서 범위.
Qwen3.8/Parasail FP8, 확정429만 NearAI 전환. 모델40/도구1024/1800초, 호출별180초, 출력상한 없음.
현재 MAIN129 기반 수정 후보이며 온톨로지 OFF. 과거 Oracle ON 시험 또는 MAIN128 SQLite와 순수DB/수정 인과 A/B가 아님.
실모델 결과 후 같은 질문 재전송0. Oracle/NFS/GENOS 작업0, Git push/메일0.

원문·전송·내구성
확보 원문 {a['source_checks']}구간, 모델 입력 {a['delivered_checks']}구간 대조.
원문불일치 {len(a['source_mismatches'])}, 권한위반 {len(a['acl_violations'])}, 전송불일치 {len(a['wire_mismatches'])}.
모델 physical/reserved {a['physical_calls']}/{a['reserved']}; UNKNOWN 뒤 호출 {a['post_unknown_calls']}.
새 프로세스 저장응답 재조회: {json.dumps(a['stored_responses'],ensure_ascii=False)}.
동일 성공요청 재조회: {json.dumps(dup,ensure_ascii=False)}.
내용검토: {json.dumps(review,ensure_ascii=False)}.

자원·한계
실험 runtime {a['runtime_bytes']/1024**2:.3f}MiB, DB파일 {a['runtime_db_bytes']/1024**2:.3f}MiB.
자원: {json.dumps(a['resources'],ensure_ascii=False)}.
정상 정리: {a['cleanup_completed']}; 동결코드/입력 불일치 {len(a['changed_release_files'])}/{len(a['changed_inputs'])}; 선택 포인터 동일 {a['active_pointer_unchanged']}.
SQL 횟수/순수 SQL 시간은 이번에 계측하지 않음. 단일질문으로 평균/p95/법률 정답률을 인증하지 않는다.
원본: {ADR.relative_to(ROOT)}
'''
U=ROOT/'09_ARTIFACTS/AUDITS/20261030-model-error-sqlite-retest';U.mkdir(parents=True,exist_ok=True)
(U/'수정과_실제실험_결과.txt').write_text(text);put(U/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'synthetic_passed':5,'synthetic_failed':4,'new_model_calls':0,'source':'checks-before-002.json'},'repaired':result},comparisons=[],judge_disagreements=0,
 usage={'physical_model_calls':a['physical_calls'],'reported_input_tokens':a['reported_input_tokens'],'reported_output_tokens':a['reported_output_tokens'],'reported_cost_usd':a['reported_cost_usd'],'missing_usage_calls':a['missing_usage_calls']},
 latency={'request_seconds':r['seconds'],'model_seconds':a['model_seconds'],'p95':None,'reason':'One known case'},error_taxonomy=[{'category':'functional_gate','failed':failed}])
m['design']['code_isolation']['working_integration_after_synthetic_decision']={'path':str((ART/'working-integration.json').relative_to(ROOT)),'reason':'User requested fixes before retest; candidate tests18+API2 passed before working changes; selected MAIN unchanged. Error repair decision separate from actual answer completion.'}
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
vals=['run-001/repaired, MAIN129 base + frozen candidate, SQLite.',read(DES/'cases.json')[0]['request']['json']['question'],
 '기준답변 제품전달0, 평가모델0. 사전 기준과 확보 원문으로 사후 확인.',
 '[입력](../artifacts/design/cases.json), [동결](../artifacts/design/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n검색 변경/회수율 비교 아님. 원문 확보/전달은 audit에 별도 기록.',
 '[전체 원시 입출력](../artifacts/live/gold-369/raw/), [canonical](../artifacts/live/gold-369/canonical/). gzip 원본과 reference 영수증 보존.',
 '[물리호출](../artifacts/live/gold-369/calls.json), [생성/거절](../artifacts/live/gold-369/generations.json).',
 '[내용검토](../artifacts/live/gold-369/content-review.json). 실제 모델 결과 후 질문 재전송0.',result['status']]
for q in m['questions']:
 p=ADR/'실험'/q['file'];p.write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
(ADR/'실험/README.md').write_text('# 실험 인덱스\n\n- [gold-369](질문-001-gold-369.md): '+result['status']+'\n')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[result['status']+'; 오류수정 기술검증과 실제 답변 완성을 구분한다.',
 'ADR1247 실제 모델 공백 기한종료 뒤 실험 TypeError와 gateway AttributeError가 원인을 덮음.',
 '[사전 기준](artifacts/design/criteria.json). 결과 후 기준변경0.',
 'MAIN129 동일 실패주입 비교→수정 후보18+API2→작업 반영20→실제 같은 질문1건.',
 '후보497파일/상법1문서/Qwen3.8/Parasail, [동결](artifacts/design/freeze.json).',text,
 '[감사](artifacts/live/gold-369/audit.json), [내용검토](artifacts/live/gold-369/content-review.json).',
 '모델비용·통신시간·요청시간·저장량을 결과에 분리. SQL성능 계측 없음.',
 '오류 보존 수정은 검증됨. 실제 답변 품질/공급자 내부 원인은 별도 판정.',
 '단일 알려진 질문. Oracle/법률현재성/부하/GENOS 미검증.',
 '작업 코드3+pin31 반영, 선택MAIN129 불변. 백업과 실패원본 보존. 후속실험은 새ADR.',
 'check.py baseline/candidate/working → live.py gold-369 → audit.py → offline content-review → finalize.py → ADR final validate/graph. 완료 실제질문 재실행 금지.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: '+('Proposed' if passed else 'Rejected'),front)
(ADR/'README.md').write_text('---'+front+'---\n\n# ADR-1249: 모델 오류 처리 수정과 SQLite 재시험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
p=ART/'manifest.json';v=read(p);v['files']=[{'path':str(x.relative_to(ROOT)),'sha256':sha(x),'bytes':x.stat().st_size,'description':'Frozen design, synthetic test, working integration, actual run or offline audit','contains_raw_prompts_and_outputs':any(t in str(x) for t in ('/raw/','/canonical/','/experiment-client/'))} for x in ART.rglob('*') if x.is_file() and x!=p];p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';old=index.read_text();entry='- [ADR1249 오류 처리 수정·SQLite 재시험](ADR-1249-model-error-sqlite-retest/README.md) — '+result['status']+f', 합성20통과/실제{a["physical_calls"]}물리·{r["seconds"]:.3f}초; MAIN129선택 유지.\n';index.write_text(old.replace('# ADR workspace\n','# ADR workspace\n\n'+entry,1))
print(result['status'],gates);print(U/'수정과_실제실험_결과.txt')
