from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0809-system-mechanics-qualification';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-0808-workflow-mechanical-boundaries'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');pf=read(P/'artifacts/design/freeze.json');v=read(D/'criteria.json');consumer=read(A/'artifacts/candidate-consumer-v2.json')
checks={'identical_338_serving_files':f['serving_files']==pf['serving_files'],
 'frozen_code_and_runner_hashes':all(sha(R/n)==h for n,h in f['files'].items()),
 'prospective_cases_8_passed':'8 passed' in (A/'artifacts/qualification-tests.txt').read_text(),
 'inherited_regressions_269_passed':sha(R/v['parent_regressions']['path'])==v['parent_regressions']['sha256'] and '269 passed' in (R/v['parent_regressions']['path']).read_text(),
 'actual_service_consumers':consumer['status']=='PASS' and all(consumer['checks'].values()),
 'actual_service_no_model_calls':consumer['model_calls']==0,
 'active_pointer_unchanged_before_promotion':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256']}
assert all(checks.values()),checks
limits=['Finite software boundary qualification only; not legal answer accuracy certification.',
 'ADR0807 actual full Qwen run: 24 calls, partial, 0 comparison rows; actual restart9 and duplicate4 pass.',
 'ADR0808 fixed recorded BASIS replay: one call, 3 canonical-valid pairs and3 system DEFERRED rows, zero additional compare calls; no full workflow rerun.',
 'Required internal originals, annex10, complete scope and applicable document versions remain unconfirmed. GENOS not deployed.']
result={'status':'complete','strict_success':True,'checks':checks,'prospective_tests':8,'inherited_regression_tests':269,
 'actual_service_checks':consumer['checks'],'new_model_calls':0,'quality_certified':False,'limitations':limits}
put(A/'artifacts/run-001/result.json',result)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'));m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','basis':'Completed ADR0808 exact code and269 regressions; no repeated model calls'},'connected':{'status':'complete','strict_success':True,'checks':checks}},usage={'product_model_calls':0,'offline_evaluator_calls':0},error_taxonomy=[])
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Accepted, promotion-candidate. ADR0808과 같은338파일의 유한 기술 경계와 실제 로컬 서비스 연결을 검증했다. 법률 품질 인증은 아니다.',
 'LLM이 원문 복사·고정 필드 작성·자식 재계획·문장화·보류 재판단을 수행했고 기계적 형식 오류에 호출 예산을 사용했다.',
 '첫 실행 전에 criteria.json, 신규8사례 코드, 원문 세대·후보338파일·검사 실행기를 동결했다. 새 사례/소비자 실패 시 승격 불가. 의미 정답의 미확인을 기술 성공으로 바꾸지 않는다.',
 '완료 ADR0808/connected 코드 변경 없이 진행. 5·11개 쟁점/양측/두 사용자 사실, Unicode11·12001·24003자, 세 독립 쟁점의 성공/수정 소진/자동 보류/재개 조합. 이전269검사는 회귀 증거이며 신규 표본으로 세지 않는다.',
 'MAIN74 원문·정의·최신 선택·프로필 고정. 새로운 모델 호출0. 기존 Qwen3.8/Parasail/none/no-fallback 기록은 참조 증거만 보존. 코드/데이터/검색 정책은 design/freeze.json 및 candidate-consumer-v2.json.',
 f"신규 유한 경계8검사 통과, 부모와338파일 동일, 부모269회귀 통과 증거 확인. 실제 후보 로컬 서비스{len(consumer['checks'])}검사 통과. 실제 유동성 전 구간 정답 성공은 미확인.",
 '원문 문자열·서로 다른 근거 ID·쟁점·사용자 사실 보존, 후속 쟁점 실패 후 앞 행 보존, 재구성한 상태에서 추가 모델 호출0 확인. 실제 서비스의 문서 권한·최신 선택·부모/자식 범위·상태 응답·선택 코드 해시 검사.',
 '모델/검색 효과 비교가 아니다. 회수 단계 원장은 해당 없음: 부모와 동일한 정책 및 소프트웨어 경계 검증. 입력/결과 중복 복사 대신 원본 해시를 참조한다.',
 '시스템은 기계적 결속·상태·보류·표시를 책임진다. 모델은 의미 쟁점·원문 채택·내용 차이·법률 적용 판단을 한다. 코드가 임의로 답이나 근거 부재를 만들어 통과시키지 않는다.',
 '\n'.join(limits),
 '동일 후보의 작업 코드 통합→해시 고정 MAIN 계획→명시적 confirm-main 적용→활성 포인터 및 실제 로컬 서비스 확인을 수행한다. 원복은 이전MAIN74 포인터/코드/데이터를 보존한다. Git병합·GENOS배포와 구분한다.',
 '06_TOOLS/EXPERIMENTS/adr_0809: prepare.py → repin.py → adr_candidate freeze/validate → freeze.py → run_tests.py(test_qualification.py)/consumer_check.py candidate → close.py → final validate → prepare_promotion.py → rag_main_promotion apply → consumer_check.py active.']
meta=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Accepted').replace('main_wiring: unchanged','main_wiring: promotion-candidate')
(A/'README.md').write_text('---'+meta+'---\n\n# ADR-0809 시스템 소유 처리 기술 자격검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n');(A/'RESULT.txt').write_text('\n\n'.join(texts)+'\n')
qh=['1. 실행 메타','2. 사용자 질문 원문','3. 기준답변 — 채점 전용, 제품 입력 비공개','4. 제품 입력을 구성한 원값','5. 제품 모델 호출 — run·arm별 실제 원문','6. 중간 LLM 호출 — router/compiler/verifier/repair','7. 채점 호출과 반복 판정','8. 사례 최종 판정'];questions=[]
for i,(cid,desc) in enumerate(v['cases'].items(),1):
 qt=[cid+' 신규 유한 소프트웨어 경계. 법률 정답 holdout 아님.',desc,'의미 정답 없음. 문자열·ID·상태·호출수 불변 조건을 검사한다. 제품 LLM에 정답을 전달하지 않는다.','동결 test_qualification.py의 신규 값/조합.\n\n### 회수·탈락 단계 원장 — run·arm별\n\n해당 없음: 코드/검색 정책 변경 없는 기술 경계 검증.','모델 호출0. ../artifacts/qualification-tests.txt 및 import-receipt.json.','중간 모델0. 이전 실제 질의는 별도 한계로만 인용.','채점 모델0. 사전 동결 검사만 수행.','통과. 상세 기술 결과 ../artifacts/run-001/result.json. 법률 정확도 인증 없음.']
 p=A/f'실험/질문-{i:03d}-{cid}.md';p.write_text('\n\n'.join('## '+h+'\n\n'+t for h,t in zip(qh,qt))+'\n');questions.append({'number':i,'case_id':cid,'file':p.name,'sha256':sha(p)})
m['questions']=questions;put(A/'실험/manifest.json',m);(A/'실험/README.md').write_text('# 기술 경계 검증\n\n'+'\n'.join(f"- [{q['case_id']}]({q['file']})" for q in questions)+'\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm','.lock'))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0809','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen software boundary and actual service evidence','contains_raw_prompts_and_outputs':'runtime' in p.parts} for p in files]})
print('Qualified unchanged candidate; new8, inherited269, actual service',len(consumer['checks']))
