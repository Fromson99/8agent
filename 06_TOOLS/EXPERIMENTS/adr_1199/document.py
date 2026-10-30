from common import *
import re
O=ROOT/'09_ARTIFACTS/AUDITS/20261029-supervisor-route-recovery';O.mkdir(parents=True,exist_ok=True)
f=read(DES/'freeze-rev-001.json');b=read(DES/'baseline.json')
c=read(ART/'check-rev-001-fixture-corrected.json');w=read(ART/'check-working.json')
reg=read(ART/'existing-contract-comparison.json');replay=read(ART/'replay-checkpoint-receipt.json');integration=read(ART/'working-integration.json')
assert c['returncode']==w['returncode']==0 and replay['passed'] and not reg['new_regressions']
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']
result={'status':'complete','candidate_revision':f['candidate_revision'],'serving_files':len(f['files']),
 'candidate_contracts':c['passed'],'working_contracts':w['passed'],'existing_contract_comparison':reg,
 'native_api_tests':['new original read after rejected directive; final publication and duplicate request','normal path unchanged'],
 'replay_checkpoint':replay,'working_integration':integration,'main117_unchanged':True,
 'new_model_calls':0,'quality_certified':False,'genos_deployed':False,
 'prior_failures_preserved':{'initial_check':'57 passed / 2 test-preparation failures; corrected on same product bytes',
 'replay_runner':'intended boundary BaseException caused TestClient portal cleanup RuntimeError; runner remains failed; separate checkpoint receipt only'},
 'ontology_documents':[bind(ROOT/'07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4/CONTROLLED_KNOWLEDGE.md'),bind(ROOT/'07_DOCS/REFERENCE/ARCHITECTURE/ONTOLOGY_V4.md')],
 'domain_runtime_changed':False,'cm007_live_retested':False,'cm009_executed':False}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json');m['in_sample']=True;m['decision_eligible']=False
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'recovered':{'status':'complete','technical_contracts_passed':True,'candidate_contracts':c['passed'],'working_contracts':w['passed'],'quality_certified':False,'replay_runner_exit_success':False}},comparisons=[reg],judge_disagreements=[],usage={'physical_requests':0,'new_model_calls':0,'stored_responses_replayed':4,'cost_usd':0},latency={'p50_seconds':None,'p95_seconds':None,'not_measured_reason':'Technical recovery contracts; no latency or provider performance claim'},error_taxonomy=['other: initial_test_preparation_errors','other: replay_boundary_cleanup_error'])
put(ADR/'실험/manifest.json',m)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','unchanged'),('in_sample','true'),('decision_eligible','false')]:meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
sections=[
 ('결정 요약','감독 행동 충돌 뒤 독립 원문 조사 복구를 작업 코드에 통합했다. MAIN117 선택 포인터·릴리스는 유지한다. 기술 계약 통과이며 새 법률 답변 품질 인증은 아니다.'),
 ('문제와 변경 전 구조','1198의 감독은 FINISH를 RESEARCH로 바꾸면서 CONTINUE_TARGETED를 보냈다. 명시 source_targets가 비어 있어 원문 선집행도 없었고, 일관성 오류가 전체 감독 handoff로 이어졌다. 코스닥 시행세칙15 세부 기준이 미확보인 채 ASSESS로 넘어갔다.'),
 ('가설과 사전 판정 기준','[동결 기준](artifacts/design/criteria.json). 잘못된 지시는 거절하되 별도로 유효한 비종료 조사 행동은 기존 검증·한도 안에서 실행한다. 같은 경로 반복, 종료·권한·상태·기한·도구 한도 우회는 허용하지 않는다.'),
 ('설계와 구현','investigation_supervisor.gate → recover_changed_route → 기존 expand/Investigation.validate → authorize(recovery=True) → 기존 before_execute/execute/after_execute 경로다. CONTINUE+다른 경로만 대상으로 하며 REDIRECT+같은 경로는 계속 거절한다. 모델의 실제 target/query를 사용하고 설명문에서 목표·조문·법률 판단을 만들지 않는다.'),
 ('실패·복구 계약','SUPERVISOR_DIRECTIVE_REJECTED에 응답/경로 hash·오류·remaining_scope를 보존한다. 허용되면 SUPERVISOR_INDEPENDENT_ROUTE_RECOVERED를 기록하며 directive_accepted=false/legal_sufficiency_approved=false다. 요청당 서로 다른 복구 경로 최대2, 기존 감독2회·도구/시간/최종화 예산 유지·추가 모델 보완0. 재개 receipt, 반복 route, 가짜ID, 숨긴 후보, stale/hash/권한 오류와 만료는 기존 경계를 유지한다.'),
 ('검증 결과',f'후보{c["passed"]}·작업{w["passed"]} 검사 통과. 기존44 동일 감독/페이지/API 정상 경로는 MAIN117과 후보 모두 통과·새 회귀0. 실제 native API가 거절된 감독 지시 이후 새 원문을 읽고 내용/원문/저장/재조회 소비자 검사를 통과했다. 전체211 회귀나 새 실모델 성능 시험을 수행한 것으로 확대하지 않는다.'),
 ('저장1198 진단','같은65문서·466후보·native HTTP에서 저장 응답4개를 전송 계약에 재생했다. 잘못된 감독 응답을 바꾸지 않고 RESEARCH가 APPLIED되어 새 결과와 시행세칙15 후보가 생겼고 다음 조사 선택에 도달했다. 새 모델이 필요한 경계에서 종료했으므로15조 본문 확보·답변 완성은 미검증이다. [12조건 체크포인트 영수증](artifacts/replay-checkpoint-receipt.json).'),
 ('보존한 실패','최초59검사 중57통과·2실패는 반복 충돌 trigger 미설정 및 정상 답변 fixture를 PARTIAL로 잘못 지정한 준비 오류였다. 초기 검사·입력 보존 후 같은 제품으로59통과. 실제 저장 재생은 중단용 BaseException 뒤 TestClient portal 정리 RuntimeError가 남아 실행기 실패로 보존했다. 별도 읽기 전용12조건 영수증은 이미 완료된 복구·검색 상태만 확인하며 재생 전체 성공으로 바꾸지 않는다.'),
 ('온톨로지 문서 반영','CONTROLLED_KNOWLEDGE의 의무·적용 조건·이행 기준 절에 양태/행위/대상/조건/기한/분모/예외/위임을 원문 판본·span에 연결하는 기준을 추가하고 v4 진입점에 연결했다. 스키마 확장·승인·매핑·적재·RAG 의미 판단 배선은 별도이며 이번 ASSESS 의미 오류를 자동 수정하지 않았다.'),
 ('적용 상태와 한계','제품1파일과pin31을 작업 코드에 통합하고 다른434서빙파일·기존 작업 hunk를 보존했다. 동결후보와 작업의 제품 내용은 같으며 MAIN117·GENOS·모델·프로필·온톨로지기본OFF는 유지했다. 원문 취득 이후 모델의 선택/충분성/최종 의미 판단까지 보장하지 않는다. 새CM007/009·Git·메일0.'),
 ('롤백','작업 변경은 artifacts/working-targeted.patch의 해당 hunk만 역적용하고 현재 작업 파일로 엔진 pin을 다시 산출한다. working-backup은 수정 전 파일을 보존한다. 이후 작업을 덮어쓰지 않는다. 활성 MAIN117에는 이번 변경이 들어가지 않아 릴리스 롤백이 필요하지 않다.'),
 ('재현','06_TOOLS/EXPERIMENTS/adr_1199의 setup/freeze/check/recheck/baseline_check/replay/replay_audit/integrate/document와 각 결과 JSON을 참조한다. replay를 자동 반복하지 않으며 외부 통신은 차단한다. 새 실행은 별도 runtime/기록을 사용한다.')]
(ADR/'README.md').write_text('---'+meta+'---\n\n# 감독 행동 충돌 후 독립 원문 조사 복구\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 계약과 저장 응답 진단\n\n합성 native API와 저장1198 재생을 구분한다. 새 모델·법률 채점0. [결과](../artifacts/run-001/result.json).\n')
a=read(ART/'manifest.json');paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and 'runtime' not in p.parts and 'test-runtime' not in p.parts]
paths+=list(Path(__file__).parent.glob('*.py'))+[ROOT/f['candidate_revision']['manifest_path']]
a['files']=[{**bind(p),'bytes':p.stat().st_size,'description':'Recovery contract, source binding and preserved diagnostic failure evidence','contains_raw_prompts_and_outputs':p.suffix=='.gz'} for p in paths]
(ART/'manifest.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
text='의무·조건 온톨로지 문서 반영 및 조사 복구 수정\n\n'+'\n\n'.join(h+'\n'+v for h,v in sections)+'\n'
(O/'수정과_검증결과.txt').write_text(text)
print('Documented candidate59 / working59 / existing44; stored replay checkpoint verified, runner failure preserved')
