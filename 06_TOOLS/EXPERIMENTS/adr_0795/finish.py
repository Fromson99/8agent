from pathlib import Path
import hashlib,json,subprocess
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0795-main72-workflow-comparison';O=A/'artifacts/live-v2';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
d=read(O/'diagnostic.json');s=read(O/'static-findings.json');r=read(O/'retrieval-summary.json');m=read(A/'실험/manifest.json');f=read(D/'freeze-v2.json');size=read(O/'context-size.json')
assert d['checks']['pointer_and_frozen_code_unchanged']
put(A/'artifacts/frozen-verification.json',{'status':'PASS','files':len(f['files']),'freeze_sha256':sha(D/'freeze-v2.json'),'checked_before_manifest_finalization':True})
passed=d['status']=='PASS';decision='Accepted' if passed else 'Rejected'
why='양쪽 RAG 결과를 실제 COMPARE가 소비하고 대사표를 반환했다.' if passed else '실제 실행에서 대사 비교 완료 가설을 충족하지 못했다. 실패 위치와 제한을 보존한다.'
rows=d['comparison_rows'];substantive=sum(row['verdict']!='DEFERRED' for row in rows)
summary=f'''MAIN72 실제 내규·외규 대사 확인 — 2026-10-15

결과: {why}
- 질문: 대사: 유동성비율 관련 외부규정은 무엇이고 내부 규정에는 어떻게 되어 있나?
- 실제 WSL 로컬 service.py → 선택 MAIN72 → 내규 RAG → 외규 RAG → 근거 관계 → 비교 → 보고서 경로를 관찰했다.
- 실제 최종 단계: {d['final_stage']}, 반환 상태: {d['workflow_status']}, 오류: {d['error_code']}.
- 실제 COMPARE 호출: {d['checks']['compare_called']}, 검증 통과: {d['checks']['compare_model_accepted']}.
- 비교 행 {len(rows)}개, 확정 판정 {substantive}개. DEFERRED는 확정 부합/상충 판정이 아니다.
- 실제 모델 호출 {d['model_calls']}회, {d['elapsed_seconds']:.1f}초. Qwen3.8/Parasail FP8, reasoning none, fallback 없음.
- 각 단계 성공/실패, 양쪽 입력 동일성, 저장 결과 재사용: artifacts/live-v2/diagnostic.json.
- 원응답: artifacts/live-v2/response.json. 호출 원문: artifacts/live-v2/raw. 부모·자식 SQLite journal은 같은 runtime에 보존.

직접 중단 원인
- 내규 24건 + 외규 70건의 원문 근거와 메타데이터, 양쪽 답변·조사 기록을 한 입력으로 합쳤다.
- 근거 관계 검토 VERIFY_BASIS 직전 입력은 재구성 기준 {size['character_count']:,}자다.
  현재 max_context_chars={size['limit_characters']:,}를 {size['excess_characters']:,}자 초과해 Runtime.view에서 BudgetExhausted를 발생시켰다.
- BASIS와 COMPARE의 모델 호출은 모두 0건이다. 제공자에 해당 입력을 보내기 전에 우리 코드가 중단했다.
- 모델 호출 예산은 40회 중 16회만 사용했다. 호출 수 소진이나 이번 실행의 메모리 부족이 아니다.
- 중단을 받아 기존 원문만 붙인 partial 보고서를 저장했다. HTTP200/END/답변 존재는 대사 완료의 증명이 아니다.
- 큰 비교 입력의 분할·순차 검토 경로가 현재 연결돼 있지 않다. 원문·기록은 journal에 보존되어 있다.

확인한 연결 문제
1. 내규/외규 검색식을 생성하지만 자식 호출은 양쪽을 묻는 원질문을 그대로 사용한다.
   내규 전용 문서 scope에서 외규까지 답하려고 하여 외규 부족을 자기 미완료 사유로 기록했다.
2. 현재 scope 문서 {s['scope_document_count']}개 중 비교용 workflow_version 메타데이터 {s['workflow_version_metadata_count']}개,
   검증된 버전 {s['verified_workflow_version_count']}개. 요청 기준일도 미지정이다.
   비교 검증기는 검증된 적용 버전과 명시 근거 관계가 있어야 부합/상충을 확정할 수 있게 되어 있다.
   따라서 단순히 모델이 더 잘 판단하면 해결되는 문제가 아니며 데이터와 비교 계약의 연결이 필요하다.

실행 한도와 범위
- 선택된 코드·데이터·모델·프롬프트·40회/1800초 한도는 바꾸지 않았다.
- 일반화나 법률 정답률 검증이 아닌, 알려진 질문 1건의 실제 배선 관찰이다.
- 최초 실행 스크립트의 실험 모듈 import 오류는 모델 호출 전 발생했다. 기존 파일/로그를 보존하고
  공통 ExperimentClient 경로를 연결한 live_v2를 별도 동결했다. 제품 코드 변경 없음.
- MAIN72 포인터 유지. 신규 승격·GENOS 반영·Git main 병합 없음.
'''
(A/'MAIN_RESULT.txt').write_text(summary)
m['runs'][0].update(status='complete',artifact_path=str((O/'diagnostic.json').relative_to(R)),sha256=sha(O/'diagnostic.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','workflow_status':d['workflow_status'],'execution_checks_passed':sum(d['checks'].values()),'execution_checks_total':len(d['checks']),'comparison_called':d['checks']['compare_called'],'comparison_rows':len(rows),'substantive_verdicts':substantive,'semantic_accuracy':None}},comparisons=[],usage={'product_model_calls':d['model_calls'],'offline_evaluator_calls':0,'input_tokens':sum(u.get('input_tokens',0) or 0 for u in d['usage']),'output_tokens':sum(u.get('output_tokens',0) or 0 for u in d['usage'])},latency={'single_case_seconds':d['elapsed_seconds'],'p50_seconds':d['elapsed_seconds'],'p95_seconds':d['elapsed_seconds'],'sample_size':1},error_taxonomy=['WORKFLOW_CONTEXT_SIZE_EXHAUSTED_BEFORE_BASIS','CHILD_SIDE_OBJECTIVE_NOT_SEPARATED','WORKFLOW_VERSION_METADATA_UNCONNECTED']+[e.get('code') or e.get('type','WORKFLOW_STOP') for e in d['workflow_stops']])
ra=m['retrieval_accounting'];ra.update(corpus_total=r['corpus_total'],before_filter={'baseline':r['corpus_total']},after_filter={'baseline':r['workflow_acquired']},golden_recall={'baseline':None},selectivity={'baseline':r['comparison_presented']/r['corpus_total'] if r['corpus_total'] else None})
for k in ('presented_total','presented_mean','presented_p50','presented_p95'):ra[k]={'baseline':r['comparison_presented']}
ra['stage_ledger']['sha256']=sha(A/'artifacts/retrieval-ledger.json.gz')
headings=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
bodies=['ADR0795/run001/baseline. 알려진 유동성 질문의 실제 선택 MAIN72 배선 관찰, exact 원본 보존.',read(D/'criteria.json')['service_request']['question'],'법률 기준답변·LLM 채점 없음. 양쪽 답변/근거/기록 전달, 실제 COMPARE 호출, 대사표 생성, 저장 재사용을 결정적으로 검사한다.','제품에 원질문만 입력. 정답 조문 ID나 평가 기준을 입력하지 않았다. design/criteria.json과 freeze-v2.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n../artifacts/retrieval-ledger.json.gz; 부모 workflow에 돌아온 원문과 실제 비교 입력의 canonical article-root 집합. 원래 native 검색 전체 입력은 journal/raw에 보존한다.','../artifacts/live-v2/raw의 모든 request.json, response.json, binding.json 및 usage.json에 원문을 보존한다.','워크플로우와 자식 호출 모두 같은 raw에 순서대로 보존. 단계/복구 오류는 diagnostic.json과 SQLite journal에서 확인한다.','오프라인 채점 호출 0건. 알려진 질문 1건이며 정답률·paired delta·일반화 판정 해당 없음.',why+' 실제 비교 행 '+str(len(rows))+'개, 확정 판정 '+str(substantive)+'개. 실패 및 한계는 ../MAIN_RESULT.txt.']
q=A/'실험/질문-001-W01.md';q.write_text('\n\n'.join(f'## {i}. {h}\n\n{b}' for i,(h,b) in enumerate(zip(headings,bodies),1))+'\n');m['questions'][0]['sha256']=sha(q);put(A/'실험/manifest.json',m)
sections=[('결정 요약',why+' MAIN 변경 없음.'),('문제와 변경 전 구조','MAIN72의 기존 서비스 검사 8건은 모델 미사용 검사였다. 실제 내규/외규 대사 판단까지 검증했는지 별도 확인이 필요했다.'),('가설과 사전 판정 기준',read(D/'criteria.json')['hypothesis']+' 기준은 최초 호출 전에 동결했다. DEFERRED 행은 비교 실행과 확정 판정을 구분한다.'),('실험 설계','단일 baseline arm: 선택 MAIN72 불변 코드·데이터·모델 그대로. 구현 후보나 정책 변경 없음. 이전 완료 ADR0794/connected를 retests 부모로 고정했다.'),('데이터·모델·재현성','design/baseline.json과 freeze-v2.json. Qwen3.8, Parasail FP8 only, reasoning none, no fallback. 외부 전송은 선택된 기존 workflow_authorization과 공통 ExperimentClient를 사용했다.'),('결과',json.dumps(m['results']['by_arm'],ensure_ascii=False)),('사례별 오류 분석',json.dumps(s,ensure_ascii=False)),('비용·지연·회수 규모',json.dumps({'usage':m['results']['usage'],'seconds':d['elapsed_seconds'],'delivery':r},ensure_ascii=False)+'\n\n### 단계별 회수·탈락 원장\n\nartifacts/retrieval-ledger.json.gz. Native 검색 정책은 변경하지 않았으며 부모 workflow로 전달된 근거와 실제 비교 입력의 canonical 집합을 계수했다. 승인된 의미 gold 없음.'),('해석','실제 비교 호출과 대사표 생성, 법적 부합/상충의 확정 판정은 별개로 기록한다. 저장된 partial 결과를 비교 성공으로 간주하지 않는다.'),('한계와 일반화 가능 범위','알려진 질문 1건. 법률 정답률·타 질문 일반화 미검증. 비교용 버전 메타데이터 연결 문제와 자식 질문 범위 문제가 확인됐다. GENOS 미접근.'),('운영 결정·롤백 조건','현행 MAIN72 유지. 제품 파일/활성 포인터 수정 없음. 추가 변경·재실험은 별도 ADR로 동결한다. 실패 원본은 보존한다.'),('재현 명령','실행 진입점: .venv/bin/python 06_TOOLS/EXPERIMENTS/adr_0795/live_v2.py. 최초 입력 hash를 검증하며 완료 산출물 덮어쓰기를 거절한다. 새 호출은 별도 ADR 필요. 후처리는 diagnose.py와 finish.py. stable adr_structure.py validate --final 및 graph 확인.')]
meta=f"---\nadr_id: ADR-0795\ntitle: MAIN72 실제 내규 외규 RAG 대사 종단 확인\nstatus: {decision}\ndecision_date: 2026-10-15\nphase: probe\nin_sample: true\ndecision_eligible: false\nmain_wiring: unchanged\ncreated_at: {m['reservation']['created_at']}\nupdated_at: {m['reservation']['updated_at']}\nowner: Codex\nwork_status: in_progress\n---\n\n"
(A/'README.md').write_text(meta+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# MAIN72 실제 대사 실행 관찰\n\n[W01](질문-001-W01.md), [결과](../MAIN_RESULT.txt). 단일 알려진 질문, 법률 정답률 인증 없음.\n')
subprocess.run(['.venv/bin/python','06_TOOLS/run_tool.py','adr_structure.py','status','--path',str(A),'--status','completed','--note','Actual unchanged MAIN72 workflow observed; stage outcomes and unresolved wiring limits preserved; no MAIN promotion'],check=True)
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p!=A/'artifacts/manifest.json' and 'runtime' not in p.parts]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0795','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact selected-release workflow observation and post-execution diagnosis','contains_raw_prompts_and_outputs':'raw' in p.parts} for p in files]})
print(why)
