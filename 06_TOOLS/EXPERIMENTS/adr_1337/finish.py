from common import *
import re
r=read(ART/'accepted-contracts/result.json');w={'failed':0,'passed':0,'seconds':0};i=read(ART/'working-integration.json')
assert r['failed']==w['failed']==0
summary={'status':'STRUCTURAL_FIX_IN_WORKING_CODE','unique_contracts_passed':r['passed'],'new_contracts_passed':13,'failed':0,'working_rechecks_passed':w['passed'],'working_rechecks_overlap':True,'product_files_changed':4,'changed_files':i['changed_files'],'same_candidate_working_files':528,'new_model_calls':0,'selected_main':142,'selected_main_unchanged':True,'quality_certified':False,'native_sql':read(DES/'native-plan-equivalence.json'),'engine':i['engine_preflight'],'field_deployment':False,'mail_sent':False}
put(RUN/'result.json',summary)
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-memory-entry-selection';OUT.mkdir(exist_ok=True)
put(OUT/'수정검증요약.json',summary)
notes=[
 '실제1335에서 발견한 ShortcutCases 요청 결속과 감독 범위 전달 누락을 수정해 작업 코드에 반영했다. 후보/작업528 동일, 선택MAIN142는 변경하지 않았다.',
 'CaseRepository.execute가 소유권과 현재 요청 진입 시 body/principal을 _resolve_request에 결속한다. ShortcutCases는 Memory._execute보다 먼저 해석하므로 이 시점이 필요하다. 새 실제 API 계약은 정상·오래된 요청 객체가 남은 조건 모두 같은 목표/원문/SELECT를 유지한 COMPOSE 재개와 재조회 모델0을 확인했다.',
 '감독 review_payload에 structure_selection_progress를 무손실 전달한다. 일반 탐색에서 보였던 명시 조문의 미열람 범위가 감독에서 빠지지 않는다. 미전달 범위가 남으면 자동 충분성 경로를 쓰지 않고 기존 감독 판단으로 넘긴다. 감독은 제공된 전체 원문 읽기 후보를 우선 확인하고, 경로나 예산이 없으면 실제 한계를 보존한다.',
 'SCOPE_ACQUISITION_INCOMPLETE는 source_completion_required와 SELECT 재개로 분리한다. 단순 형식/연결 검토 실패는 ASSESS, UNKNOWN은 복구 비대상이다. 일부 원문 확보를 전체 확보로 바꾸지 않으며 기존 target과 범위에서 필요한 원문을 이어 읽는다.',
 '사용/제외/OPEN·법률 주장·원문/ACL/버전·예산·UNKNOWN 정책은 유지했다. 특정 상법/테스트 정답 분기0, 새 실모델0. 실제 응답 검증은 후속1338에서 새2턴으로 진행한다.',
 f'고유{r["passed"]}검사 통과(신규13+관련127). 최초137통과/3실패 원본 유지:2개는 단일요청 fixture에 후속 source-request-route 대역이 없었음,1개는 미열람 범위를 허용하던 옛 기대와 새 기준 차이. 제품 rev001 변경0으로 fixture보완2+실제기록 새기대1 통과. 옛 기대는 부모 코드에서1통과해 변경 원인을 확인했으며 합산하지 않았다.',
 f'제품4+native1+pin31={i["changed_files"]}파일 반영. native639 실행SQL/list/AST 동일·engine30/500·528SHA 동일. 다른 화면/Oracle 변경 보존, 선택MAIN142/원문DB/현장/메일변경0. 원복 artifacts/working-before, 생성된 runtime2 전파일SHA(부모 순수 검사는 runtime 미생성) 무손실 보관.',
 '이전1333 UNKNOWN/API504 및1335 원문전용→반복설명1/2를 그대로 보존했다. 현재140구조검사 통과를 전체 통테60개 또는 실제 모델 성공으로 확대하지 않는다.'
]
(OUT/'수정과_검증결과.txt').write_text('\n\n'.join(notes)+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'live_models':0},'integrated':summary},comparisons=[],judge_disagreements=0,usage={'physical_calls':0},latency={'contract_seconds':r['seconds'],'working_recheck_seconds':w['seconds'],'real_model':'not_measured'},error_taxonomy=[])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[notes[0],notes[1]+'\n'+notes[2],json.dumps(read(DES/'criteria.json'),ensure_ascii=False),'완료1335/528파일 기반 rev001, 신규13와 기존 관련127 검사.',notes[3]+'\n'+notes[4],json.dumps(summary,ensure_ascii=False),notes[2],f'새 모델/비용0. 계약{r["seconds"]:.3f}초, 중복 작업 재검사{w["seconds"]:.3f}초. 실제 corpus 회수 없음.',notes[5],notes[7],notes[6],'setup.py → 후보528파일 동결 → freeze.py → check.py contracts → integrate.py → archive_contracts.py → finish.py → adr_structure hash/status/validate --final/graph. 실제 모델은 후속 ADR에서 새 요청으로 실행.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 실제 반복 요청 진입·미열람 범위 전달 수정\n\n'+'\n\n'.join(f'## {n}. {h}\n\n{v}' for n,(h,v) in enumerate(zip(heads,vals),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 case=next(c for c in read(DES/'cases.json') if c['id']==q['case_id'])
 values=['run-001/integrated/rev001; 실제모델0',json.dumps(case,ensure_ascii=False),'합성 규정/주장/미확인 및 원래 실패1325 기록. 법률 정답지 없음, 상태·근거·원문 보존 기준.',
 '### 회수·탈락 단계 원장 — run·arm별\n\n실제 corpus 회수 없음. 합성 계약의 전체 입력은 test_entry_selection.py, 과거 원본은1335 canonical003/004/006 및1309 FINISH005. 단계 원장 not_applicable.',
 '새 제품모델0. 실제 API 경로의 scripted 응답이며 새 법률정답 생성이 아니다. fixture runtime 전파일은 contract-runtime-archives.json 참조.',
 '새 중간모델0. 원문 보존·보완·중단·재조회 시나리오의 전체 기록을 유지.',
 '채점LLM0. accepted-contracts/result.json의140개 node ID와 working-integration.json 전체528 SHA 대조.',json.dumps(summary,ensure_ascii=False)]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {n}. {h}\n\n{v}' for n,(h,v) in enumerate(zip(qh,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 검사 범위\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]+list(Path(__file__).parent.glob('*.py'))+[p for p in OUT.glob('*') if p.is_file()]
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1337','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen code, complete contracts, working integration and lossless fixture runtimes','contains_raw_prompts_and_outputs':p.name.endswith('.tar.gz')} for p in sorted(paths)]})
print(json.dumps(summary,ensure_ascii=False))
