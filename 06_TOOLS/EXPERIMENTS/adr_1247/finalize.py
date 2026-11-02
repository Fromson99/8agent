"""Finalize actual evidence; never calls a model or changes product selection."""
from common import *
import re
P=ART/'live/gold-369';a=read(P/'audit.json');r=read(P/'result.json');review=read(P/'content-review.json');dup=a['duplicate']
gates={'api_answer':a['http_status']==200 and a['answer_chars']>0,'persisted_answer':any(x['status']=='COMPLETE' and x['same_text'] for x in a['stored_responses']),'question_coverage':review['passed'],'original_acl':a['source_checks']>0 and not a['source_mismatches'] and not a['acl_violations'],'wire':len(a['attempts'])==a['physical_calls'] and not a['wire_mismatches'],'budget':a['physical_budget_matches'] and not a['output_cap_fields'],'unknown':a['unknown']==0 and a['post_unknown_calls']==0,'resource':a['resources']['resource_stop'] is None,'code_data':not a['changed_release_files'] and not a['changed_inputs'],'process':a['cleanup_completed'],'duplicate':bool(dup and dup['http_status']==200 and dup['same_answer'] and dup['extra_model_calls']==0)}
passed=all(gates.values());result={'status':'KNOWN_CASE_FUNCTIONAL_PASS' if passed else 'INCOMPLETE_FUNCTIONAL_E2E','gates':gates,'actual':r,'model_calls':a['physical_calls'],'unknown':a['unknown'],'model_seconds':a['model_seconds'],'reported_cost_usd':a['reported_cost_usd'],'missing_usage_calls':a['missing_usage_calls'],'source_checks':a['source_checks'],'delivered_checks':a['delivered_checks'],'source_mismatches':len(a['source_mismatches']),'acl_violations':len(a['acl_violations']),'wire_mismatches':len(a['wire_mismatches']),'runtime_bytes':a['runtime_bytes'],'runtime_db_bytes':a['runtime_db_bytes'],'resources':a['resources'],'content_review':review,'provider_counts':a['provider_counts'],'finish_reasons':a['finish_reasons'],'ontology_enabled':False,'oracle_access':False,'product_changed':False,'active_pointer_unchanged':a['active_pointer_unchanged'],'quality_certified':False,'comparison_limit':'Different ontology/data provider paths and one stochastic case; not DB-only A/B or legal accuracy/p95 certification','preparation_failures':'Health interrupted in restricted process; missing team then overbroad team envelope refused before model dispatch. All original attempts saved, actual external model case only once.'}
put(RUN/'result.json',result)
U=ROOT/'09_ARTIFACTS/AUDITS/20261030-main128-sqlite-live';U.mkdir(parents=True,exist_ok=True)
failed=[k for k,v in gates.items() if not v]
text=f'''MAIN128 SQLite 실제 재시험 — ADR1247 / 2026-10-30

결과: {result['status']}
질문: {read(DES/'cases.json')[0]['request']['json']['question']}
실제 API HTTP {a['http_status']}, 답변 {a['answer_chars']}자.
요청 실행 구간 {r['seconds']:.3f}초(성공 시 중복요청 점검 포함); 앱 준비는 binding.json 별도.
실제 외부 모델 {a['physical_calls']}회, UNKNOWN {a['unknown']}회, 모델 통신 합계 {a['model_seconds']:.3f}초.
보고 비용 ${a['reported_cost_usd']:.8f}, 사용량 미보고 {a['missing_usage_calls']}회.
통과하지 않은 기준: {', '.join(failed) or '없음'}.

범위와 데이터
실제 현재 선택 MAIN128 495파일의 local service → SQLite 원문/검색 → 실제 Qwen → SQLite 실행기록 경로.
질문과 상법 document_id 7bbe815ff43b6635는 Oracle1245와 동일. 기본 SQLite 전체세대1547문서 중 현재 요청/모델 권한은 상법1문서로 제한.
모델 Qwen3.8/Parasail FP8, 확정429만 NearAI1전환. 출력상한없음,40모델/1024도구/1800초 예산.
SQLite 온톨로지 OFF; 이전 Gold Oracle 시험은 ON/DB였고 벡터 연결도 같지 않다. 순수 DB 교체 성능비교로 주장하지 않는다.
Oracle 접근/쓰기0, 실제 NFS/ORDS/GENOS 미실행. 제품/MAIN 선택을 이 작업에서 변경하지 않았다.

검증
확보 원문 {a['source_checks']}구간, 모델입력 원문 {a['delivered_checks']}구간 대조.
원문불일치 {len(a['source_mismatches'])}, 권한위반 {len(a['acl_violations'])}, 전송불일치 {len(a['wire_mismatches'])}.
새 프로세스의 SQLite 재조회로 저장 응답과 실제 반환 본문 대조: {json.dumps(a['stored_responses'],ensure_ascii=False)}.
성공 요청의 동일 재조회: {json.dumps(dup,ensure_ascii=False)}.
모델 physical/reserved: {a['physical_calls']}/{a['reserved']}.
내용검토: {json.dumps(review,ensure_ascii=False)}.

자원/저장
실험 runtime 총 {a['runtime_bytes']/1024**2:.3f}MiB, SQLite DB 파일 {a['runtime_db_bytes']/1024**2:.3f}MiB.
Oracle segment 할당증가205MiB와 파일 크기는 서로 다른 지표이므로 같은 비율로 비교하지 않는다.
자원: {json.dumps(a['resources'],ensure_ascii=False)}.
동결 release/입력 변경: {len(a['changed_release_files'])}/{len(a['changed_inputs'])}. 현재 선택 포인터 동일: {a['active_pointer_unchanged']}.
SQL 호출 수/순수 SQL 시간은 이번 실행에서 계측하지 않았다. 단일질문으로 평균성능·p95·정답률 인증 없음.

준비/승인 기록
자동 승인검토2회 거절은 프로세스 시작 전이었다. 사용자의 명시적 외부전송 승인 뒤 실행.
준비 실패는 HEALTH 제한환경중단, team_id누락, 팀 전체 envelope와 단일문서 승인 충돌. 모두 새 모델0회이며 원본 보존.
공개문서 필터를 상법1개로 제한해 네이티브 권한 검사를 통과한 뒤 실제 모델 시험1건을 실행. 제품 검증기 수정0.
실모델 결과 확인 뒤 같은 질문 재실행0. 실패를 성공으로 변경하지 않음.

원본: {ADR.relative_to(ROOT)}
'''
(U/'실제실험_결과.txt').write_text(text);put(U/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'historical_only':True,'new_model_calls':0,'source':'ADR1245 Oracle failure; conditions differ'},'sqlite':result},comparisons=[],judge_disagreements=0,usage={'physical_model_calls':a['physical_calls'],'reported_input_tokens':a['reported_input_tokens'],'reported_output_tokens':a['reported_output_tokens'],'reported_cost_usd':a['reported_cost_usd'],'missing_usage_calls':a['missing_usage_calls']},latency={'request_seconds':r['seconds'],'model_seconds':a['model_seconds'],'p95':None,'reason':'One known case; no robust percentile or causal DB-only effect'},error_taxonomy=[{'category':'functional_gate','failed':failed}])
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정'];vals=['run-001/sqlite, selectedMAIN128495, local SQLite, one actual model case.',read(DES/'cases.json')[0]['request']['json']['question'],'기준답변 제품전달0. 평가모델0; 사전 기준과 실행 후 확보원문/내용검토.', '[질문/설정](../artifacts/design/cases.json), [코드/데이터 동결](../artifacts/design/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n검색알고리즘 변경/회수율 비교 아님. 실제 원문 확보/전달은 audit.json.gz에 검증.', '[원시 입출력](../artifacts/live/gold-369/raw/), [압축 canonical](../artifacts/live/gold-369/canonical/). 경로별 gzip/reference 영수증에 전체 보존.', '[호출 원장](../artifacts/live/gold-369/calls.json), [생성/거절](../artifacts/live/gold-369/generations.json).', '[오프라인 내용검토](../artifacts/live/gold-369/content-review.json). judge0·실모델 결과 후 재실행0.',result['status']+' / failed='+', '.join(failed)]
for q in m['questions']:
 p=ADR/'실험'/q['file'];p.write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
(ADR/'실험/README.md').write_text('# 실험 인덱스\n\n- [gold-369](질문-001-gold-369.md): '+result['status']+'\n')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령'];vals=[result['status']+'; 알려진 단일질문 실제 SQLite 재시험.','Oracle 실제1245의 답변실패/저장증폭/충돌 뒤 사용자 요청으로 SQLite 경로를 확인.','[사전 기준](artifacts/design/criteria.json). 모델 결과 뒤 기준 변경0.','같은 질문·문서1개, SQLite 기본 경로 ONTOLOGY OFF. 실제 모델1건, 실패 뒤 재실행0.','MAIN128495·Qwen3.8·ParasailFP8·기본예산/출력상한없음; [동결](artifacts/design/freeze.json).',text,'[감사](artifacts/live/gold-369/audit.json), [내용검토](artifacts/live/gold-369/content-review.json).','실제 모델 호출·비용·시간·원문·메모리·저장량은 결과에 분리.','SQLite 경로의 관측결과이며 Oracle 문제 해결/순수DB가속으로 확대하지 않는다.','단일 in-sample; 미사용질문/법률현재성/부하/GENOS 미검증.','제품/MAIN/Oracle 변경0; 실험 폴더의 새 SQLite기록만 보존.','preflight → setup/freeze → live.py gold-369 → audit.py → offline content-review → finalize.py → ADR validate --final/graph. 완료 실제질문 재실행 금지.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: '+('Proposed' if passed else 'Rejected'),front)
(ADR/'README.md').write_text('---'+front+'---\n\n# ADR-1247: MAIN128 SQLite 실제 질문 재시험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
p=ADR/'artifacts/manifest.json';v=read(p);v['files']=[{'path':str(x.relative_to(ROOT)),'sha256':sha(x),'bytes':x.stat().st_size,'description':'Pre-dispatch frozen design, raw actual run, preserved preparation failure, or offline audit','contains_raw_prompts_and_outputs':any(t in str(x) for t in ('/raw/','/canonical/','/experiment-client/'))} for x in ART.rglob('*') if x.is_file() and x!=p];p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';old=index.read_text();entry='- [ADR1247 MAIN128 SQLite 실제 재시험](ADR-1247-main128-sqlite-live-retest/README.md) — '+result['status']+f', {a["physical_calls"]}물리/{r["seconds"]:.3f}초; 온톨로지OFF/단일질문·Oracle효과비교아님.\n';index.write_text(old.replace('# ADR workspace\n','# ADR workspace\n\n'+entry,1))
print(result['status'],gates);print(U/'실제실험_결과.txt')
