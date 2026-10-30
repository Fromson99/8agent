from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1108-genos-applied-mode-main'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
result={'strict_success':False,'checks':{'49_input_and_scope_contracts':True,'session_keep_replan':False,'workflow_test_hook_exists':False},'passed':49,'failed':2,'new_model_calls':0,'quality_certified':False,'failures':['Explicit source was applied after memory method normalization; KEEP-only RESEARCH_REPLAN was rejected before scope_state.','Test tried workflow.api.run but that function is install-local; fix test to inspect runtime.execute after real identity and routing.'],'logs':['tests.log','tests-collected.log','tests-collected.xml']}
put(A/'artifacts/run-001/result.json',result)
p=A/'실험/manifest.json';m=json.loads(p.read_text());m['runs'][0].update(status='complete',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)),sha256=sha(A/'artifacts/run-001/result.json'),success_criteria_met=False)
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','role':'immutable MAIN106 reference'},'integrated':{'status':'complete','passed':49,'failed':2}},comparisons=[],usage={'new_model_calls':0},latency={'performance_measured':False},error_taxonomy=result['failures'],main_wiring='unchanged',quality_certified=False)
put(p,m)
meta=(A/'README.md').read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$','status: Rejected',meta)
parts=[('결정 요약','기각. 합성51검사 중49통과·2실패. MAIN106·작업 제품 코드 유지.'),('문제와 변경 전 구조','GENOS applied_fields.mode가 요청 본문으로 연결되지 않았다. 전체 법령은 허용된 모든 분류를 검색해야 한다.'),('가설과 사전 판정 기준','design/criteria.json의 입력·권한·세션·대사 경로 전부 통과. 조건은 실행 전에 고정했다.'),('실험 설계','MAIN106429파일에 격리 후보37파일(제품6·pin31)을 덧붙였다. 합성 원문3개와 scripted transport만 사용.'),('데이터·모델·재현성','새 모델0회. 법률 품질·속도 실험이 아니다. 동결 rev-001과 전체 staged-code 해시를 실행 전후 확인했다.'),('결과','기본 입력·별칭·JSON/SSE·실제 전체/내규/외규 목록49검사 통과. 세션 변경1·검사 hook1 실패.'),('사례별 오류 분석','RESEARCH_REPLAN의 KEEP-only 입력이 scope_state 전에 normalize에서 거절됐다. 대사 검사는 install 내부 run을 모듈 함수로 오인했다. 실패 로그를 보존한다.'),('비용·지연·회수 규모','외부 모델0회. 합성 자료3개. 실제 데이터 검색·전체속도·회수율 미측정.'),('해석','초기 선택 연결은 확인했지만 지속 대화에서 UI 범위를 먼저 결속해야 한다.'),('한계와 일반화 가능 범위','기계 계약 결과이며 법률 정답과 GENOS 현장 상태의 근거가 아니다.'),('운영 결정·롤백 조건','MAIN106 유지. 결과를 본 후의 제품 수정·검사 수정은 새 ADR에서 수행한다. 실패 후보는 완료 부모로 사용하지 않는다.'),('재현 명령','06_TOOLS/EXPERIMENTS/adr_1108/run_tests.py 05_TESTS/CONTRACTS/test_genos_applied_mode.py. 원래 테스트 내용은 design/test-modes-original.py에 보존한다.')]
(A/'README.md').write_text('---'+meta+'---\n\n# GENOS 조회 방식 연결의 첫 검사\n\n'+'\n\n'.join(f'## {i}. {t}\n\n{v}' for i,(t,v) in enumerate(parts,1))+'\n')
(A/'실험/README.md').write_text('# 입력 계약 검사\n\n51검사49통과2실패. ../artifacts/run-001/tests-collected.xml과 result.json을 참조한다. 새 모델0회.\n')
(A/'artifacts/design/test-modes-original.py').write_bytes((R/'05_TESTS/CONTRACTS/test_genos_applied_mode.py').read_bytes())
