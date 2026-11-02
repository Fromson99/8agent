"""Report the bounded live failure and independently verified implementation."""
from common import *
import re
P=ART/'live/gold-369';a=read(P/'audit.json');r=read(P/'result.json');review=read(P/'content-review.json');w=read(ART/'working-integration.json')
checks={n:read(ART/f'checks-{n}.json') for n in ('contracts-final-002','baseline-regression-001','frozen-api-001','integrated-regression-001')}
assert checks['contracts-final-002']['passed']==155 and checks['contracts-final-002']['failed']==2
assert checks['baseline-regression-001']['failed']==2 and checks['frozen-api-001']['passed']==8
assert checks['integrated-regression-001']['failed']==0
assert w['product_candidate_equal'] and w['main_pointer_unchanged']
result={'status':'GENERAL_CONTRACT_VERIFIED_LIVE_TIMEOUT_BEFORE_ASSESSMENT','implementation_verified':True,'live_completion_passed':False,
 'actual':r,'model_calls':a['physical_calls'],'unknown':a['unknown'],'model_seconds':a['model_seconds'],'reported_cost_usd':a['reported_cost_usd'],'missing_usage_calls':a['missing_usage_calls'],
 'checks':{n:{k:x[k] for k in ('passed','failed','real_model_calls')} for n,x in checks.items()},'test_count_policy':'Repeated/integrated tests overlap; do not add counts across runs.',
 'audit_path':str((P/'audit.json').relative_to(ROOT)),'content_review':review,'resources':a['resources'],'working_changes':w,
 'source_mismatches':a['source_mismatches'],'wire_mismatches':a['wire_mismatches'],'acl_violations':a['acl_violations'],
 'ontology_enabled':False,'oracle_access':False,'main_promoted':False,'quality_certified':False,'same_question_redispatch':0,
 'comparison_limit':'One known stochastic case; no DB-only A/B, legal quality or latency improvement claim.'}
put(RUN/'result.json',result)
text=f'''일반화된 원문 범위 검토·주장 연결 수정과 SQLite 실제 실험 — ADR1251 / 2026-10-30

최종 판정
일반화 수정과 계약/API 검증은 완료. SQLite 실제 실험은 최종 판단 전 모델 시간 초과로 미통과.
실제 요청 {r['seconds']:.3f}초, API HTTP {a['http_status']}, 최종 답변 {a['answer_chars']}자.
Parasail {a['physical_calls']}회(정상1/UNKNOWN1), 공급자 전환0, UNKNOWN 뒤 호출0, 질문 재실행0.
보고 비용 ${a['reported_cost_usd']:.8f}; 시간 초과 요청의 비용·토큰은 미보고. 전체 비용으로 단정하지 않는다.

문제와 일반화 수정
기존 계약은 전체 원문 목표의 모든 조각이 주장·채택 판단 교집합에 들어갈 것을 요구했다. 실제로는 표제를 포함한 전체 원문을 읽어도 필요한 항만 인용하면 NEED_TARGET_INCOMPLETE가 됐다. 최초 읽기 목적의 쟁점을 후속 모든 사용에 강제해 다른 쟁점에 필요한 원문 사용도 거절했다.
1. 확보·전달 영수증, 전체 범위의 사용/제외/보류 검토, 주장별 근거 연결을 분리했다. 전체 확보와 검토를 유지하면서 실제 인용은 관련 부분만 허용한다.
2. target마다 제공된 모든 근거를 정확히 한 번 검토한다. 제외에는 이유, 보류에는 같은 쟁점의 중요한 공백이 필요하다. 이미 채택한 근거를 동시에 제외할 수 없다.
3. 의미상의 필요는 같은 쟁점의 실제 주장·그 주장에 채택한 판단·현재 원문으로 연결한다. 다른 판단의 근거를 빌려 해결로 표시할 수 없다.
4. 자료 읽기 작업의 최초 목적은 이력으로 보존한다. 같은 자료를 여러 쟁점에서 쓰거나 여러 자료로 한 주장을 뒷받침할 수 있다. 읽기 완료 자체를 의미 필요의 해결로 인정하지 않는다.
5. 누락 범위/잘못된 주장·쟁점 연결을 오류에 구체적으로 기록한다. 같은 오류 반복을 식별해 저장하며 기존 보완1회/모델40회 예산을 늘리지 않았다.
6. 검토 영수증 v2와 입력 hash를 저장한다. 이전 실패 출력이 자동 성공으로 바뀌지 않는다. 원문 hash·판본·권한과 제외 원문 검증을 유지한다.
특정 법률명/조문번호/정답 문자열에 의존하는 분기 없음. 일반 운영 문서·복수 문서/쟁점, ID/순서 변경과 구간 분할 사례로 확인했다. 제외 이유의 법률적 타당성까지 구조 검사로 증명하지는 않는다.

검증
- 계약·회귀 155통과/기존2실패. 입력 압축 검사 repair/stale 2건은 선택 MAIN129에서도 동일 실패(기준40통과/2실패). 새 실패0.
- 실제 네이티브 API+모의 모델8통과: 정상, 최초 거절 뒤1회 보완, 반복 거절422, 부분답변, 저장 영수증, 중복 요청 추가 호출0, 기존504/502 오류 경로.
- 저장소 회귀 검사 반영 후 {checks['integrated-regression-001']['passed']}통과/0실패. 앞선 검사와 중복이 있으므로 합산 독립 표본으로 세지 않는다.
- 준비 중 fixture 이름 충돌/잘못된 기대값, 반복 오류 식별자 보존 누락은 실패 기록을 보존하고 수정 후 재검증했다.
- 종료된 ADR1249의 실제 거절 출력은 v1에서 기존5오류를 재현하고 v2 필수 검토 없이 수락하지 않음을 확인했다.

실제 SQLite 실험
질문: {read(DES/'cases.json')[0]['request']['json']['question']}
현재 MAIN129 기반+ADR1249 오류 수정+이번 검토 계약을 고정 후보497파일로 실제 service에 연결했다. 원문·검색·기록은 SQLite, 허용 원문은 상법1문서(7bbe815ff43b6635), 온톨로지OFF.
첫 모델 요청은 정상. 두 번째 원문 탐색 선택 요청에서 HTTP200 헤더 후 공백60조각/660바이트만 받고 179.929초에 절대 기한 종료.
AbsoluteDeadlineExceeded → MODEL_DEADLINE_EXCEEDED → UNKNOWN/API504로 보존, 모델 worker 회수, run FAILED 저장·정상 프로세스 종료.
이번에는 TypeError/AttributeError가 원래 오류를 덮지 않았다. 최종 ASSESS 입력/새 scope_reviews 실제 전송/최종 답변0이다.
따라서 이번 새 계약의 실모델 효과는 아직 미검증이다. 공급자 내부 원인은 알 수 없으며 SQLite나 최종 검증기 탓으로 확정하지 않는다.

감사·자원
확보 원문 {a['source_checks']}구간 대조·불일치0/권한위반0. 감사 대상 canonical 원문 spans 전달 {a['delivered_checks']}구간, 최종 입력0. 탐색 후보 미리보기 전체의 법률 내용 검증을 의미하지 않는다.
저장 요청→실제 전송2개 대조 불일치0, 예약/물리2/2, 출력 토큰 상한 추가0.
코드497파일/고정 입력 불일치0, 선택MAIN 포인터 동일, cleanup 완료.
최대 RSS {a['resources']['peak_RSS_GiB']:.3f}GiB, 최소 호스트 가용 {a['resources']['min_available_GiB']:.3f}GiB, 호스트 swap 최대 증가 {a['resources']['max_swap_growth_MiB']:.3f}MiB, 자원 중단 없음.
SQLite DB 파일 {a['runtime_db_bytes']/1024**2:.3f}MiB, runtime 전체 {a['runtime_bytes']/1024**2:.3f}MiB. SQL 횟수/순수SQL 시간은 이번 계측 범위가 아니다.

반영·격리·한계
작업 제품3파일+pin31+회귀 검사/fixture5=39파일 반영. 제품3파일은 검증한 고정 후보와 동일.
동시 작업의 온톨로지10파일 변경 때문에 최초 동결이 차단됐다. 현재 upstream을 기록한 새 후보를 만들고 이미 검증한 실험 범위를 명시적으로 유지했다. 원래 후보·실패 증거 보존, 다른 작업 코드 rollback0. 작업 메타데이터는 이번 제품3파일의 pin만 갱신했다.
선택 MAIN129 승격/배포0, Oracle/GENOS/NFS 변경0, Git push/메일0. 다른 작업 전체의 검증을 대신하지 않는다.
단일 알려진 질문으로 평균/p95·법률 정답률·SQLite 대비 Oracle 성능을 주장하지 않는다.
후속 과제는 공급자 공백 응답의 원인 분리와 최종 판단까지 도달하는 별도 실제 재검증이다. 이번 실패 요청은 자동 재시도하지 않는다.
원본: {ADR.relative_to(ROOT)}
'''
U=ROOT/'09_ARTIFACTS/AUDITS/20261030-general-evidence-review';U.mkdir(parents=True,exist_ok=True)
(U/'수정과_실제실험_결과.txt').write_text(text);put(U/'result.json',result)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'historical':'ADR1249 HTTP422 NEED_TARGET_INCOMPLETE/NEED_RESOLUTION_CLAIM; no fresh baseline model','checks':result['checks']['baseline-regression-001']},'generalized':result},comparisons=[],judge_disagreements=0,
 usage={'physical_model_calls':a['physical_calls'],'reported_input_tokens':a['reported_input_tokens'],'reported_output_tokens':a['reported_output_tokens'],'reported_cost_usd':a['reported_cost_usd'],'missing_usage_calls':a['missing_usage_calls']},latency={'request_seconds':r['seconds'],'model_seconds':a['model_seconds'],'p95':None,'reason':'One failed known case'},error_taxonomy=[{'category':'MODEL_DEADLINE_EXCEEDED','stage':'SELECT','unknown':True,'final_assessment_reached':False}])
m['design']['code_isolation']['working_integration_after_synthetic_decision']={'path':str((ART/'working-integration.json').relative_to(ROOT)),'reason':'Verified generalized fix requested by user; selected MAIN unchanged. Actual model completion judged separately.'}
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
vals=['run-001/generalized, MAIN129 base+isolated candidate; SQLite.',read(DES/'cases.json')[0]['request']['json']['question'],'기준답변 제품전달0/평가 모델0. 최종 답변0으로 법률 내용 채점 미실시.','[입력](../artifacts/design/cases.json) · [동결](../artifacts/design/freeze.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n검색 변경/회수율 비교 아님. 확보/전달은 감사에 별도 기록.','[원시 입출력](../artifacts/live/gold-369/raw/) · [canonical](../artifacts/live/gold-369/canonical/). gzip과참조 보존.','[물리호출](../artifacts/live/gold-369/calls.json) · [생성 기록](../artifacts/live/gold-369/generations.json). 최종/보완 미도달.','[오프라인 검토](../artifacts/live/gold-369/content-review.json). 질문 재전송0.',result['status']]
for q in m['questions']:
 p=ADR/'실험'/q['file'];p.write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n');q['sha256']=sha(p)
put(ADR/'실험/manifest.json',m)
(ADR/'실험/README.md').write_text('# 실험 인덱스\n\n- [gold-369](질문-001-gold-369.md): '+result['status']+'\n')
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=['일반화 수정 기술검증 완료; 실제 SQLite 모델은 최종 판단 전 timeout으로 전체 미통과.','전체 확보와 모든 주장 인용을 혼동; 자료의 최초 쟁점을 후속 모든 사용에 강제.','[사전 기준](artifacts/design/criteria.json) · [승인 계획](artifacts/design/approved-plan.txt). 결과 뒤 기준 변경0.','일반 문서 계약/실제API 모의 모델/기존 기준 비교→고정 후보 실제 질문1회.','497파일·SQLite·허용1문서·온톨로지OFF·Qwen3.8/Parasail. 동시 작업 변경은 [격리 기록](artifacts/design/isolation.json) 참고.',text,'[감사](artifacts/live/gold-369/audit.json) · [원인 검토](artifacts/live/gold-369/content-review.json).','실제2호출/207.350초/보고$0.0014738; timeout사용량 미보고. SQL성능 미계측.','코드 계약의 일반화는 합성검증. 최종 판단까지 도달하지 않아 실모델 효과 결론 불가.','식별자/순서/범위 변경 검증은 법률 의미 정확성 인증이 아니다. Oracle·현장·부하 미검증.','작업3제품+31pin+5검사 반영, 선택MAIN129 유지. 검증 코드/백업/실패원본 보존. 다음 실제 실험은 새ADR.','check.py candidate → live.py gold-369 → audit.py → review.py → finalize.py → 공식 최종검사. 완료 질문 재실행 금지.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Rejected',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# ADR-1251: 일반화 원문 검토·주장 연결과 SQLite 재실험\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
p=ART/'manifest.json';v=read(p);v['files']=[{'path':str(x.relative_to(ROOT)),'sha256':sha(x),'bytes':x.stat().st_size,'description':'Frozen design, checks, integration, actual run or offline audit','contains_raw_prompts_and_outputs':any(t in str(x) for t in ('/raw/','/canonical/','/experiment-client/'))} for x in ART.rglob('*') if x.is_file() and x!=p];p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
index=ROOT/'04_EXPERIMENTS/ADR/README.md';old=index.read_text();entry='- [ADR1251 일반화 원문 검토·SQLite 재실험](ADR-1251-general-evidence-review/README.md) — 계약155/API8통과·기존2동일; 실제2물리/207.350초/UNKNOWN1·HTTP504, 최종 미도달; MAIN129유지.\n';index.write_text(old.replace('# ADR workspace\n','# ADR workspace\n\n'+entry,1))
print(result['status']);print(U/'수정과_실제실험_결과.txt')
