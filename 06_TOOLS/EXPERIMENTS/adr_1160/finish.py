from common import *
import re,subprocess
r=read(ART/'run-001/result.json');assert r['strict_success'] and all(v is True for v in r['checks'].values())
def bind(p):return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
m=read(ADR/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['design']['release_rebase']=bind(DES/'release-rebase.json')
m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','role':'MAIN110 historical release plus completed1159 failure evidence'},'connected':{'status':'complete','technical_conditions':254,'quality_certified':False}},comparisons=[{'technical_integration_only':True,'legal_quality_comparison':False}],usage={'new_model_calls':0},latency={'performance_claim':False},error_taxonomy=['1156 SQLite named bind failure preserved','1157 test variable/import failure preserved','1158 capture fixture and stopped Oracle preserved','1159 Oracle native JSON return incompatibility preserved'],quality_certified=False,main_wiring='promotion-candidate')
put(ADR/'실험/manifest.json',m)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
sections=[('결정 요약','생성 입력·기존 화면 승인·DB 게시·RAG 사용을 연결한 후보의 기술254조건을 통과했다. 244 pytest 사례와 실제 로컬 Oracle10조건이다. 공식서빙453파일에 누락 스키마가 포함되고 데이터는 포함하지 않는다.'),
('문제와 변경 전 구조','MAIN110의 RAG 시나리오 선택 프레임워크는 있지만 스키마가 서빙에서 제외되고 관리 화면·DB 게시/조회가 연결되지 않았다. 원문에 도착했을 때 운영 승인 게시본을 읽는 경로가 필요했다.'),
('가설과 사전 판정 기준','1156부터 생성·수정·승인·게시·원문·권한·중복·실패·ON/OFF의 계약을 사전 동결했다. 이번 후속은 Oracle JSON CLOB의 실제 dict/문자열 반환을 같은 해시·스키마 검증으로 처리한다. 하나라도 새 실패하면 승격하지 않는다.'),
('실험 설계','684파일 후보를 격리·등록·동결했다. 기존216계약, 새22생애주기, 기존화면1, 실제판단수집1, 최종서빙 DB HTTP4를 새로 실행했다. 별도의 로컬 Oracle 임시 스키마에서10조건을 확인하고 스키마를 정리했다.'),
('데이터·모델·재현성','합성 원문·판단·경로만 사용했다. 제품모델 호출0, 평가모델0. 기존 MAIN110 원문·모델·프로필·예산을 유지한다. 실제 생성 모델의 의미 품질 실험이 아닌 코드 계약 검증이다. 코드·기준·실행기 해시는 artifacts/design/freeze.json.'),
('결과','244/244 테스트와 Oracle10/10 통과. 최종453서빙파일만 사용한 정상·복수선택·OFF·ON빈DB HTTP4모드가 모두 답변까지 성공했다. 기존 화면 버튼으로 생성·승인·DB게시·두 경로 선택을 확인했다. 공식preview453파일 일치, MAIN110대비50변경.'),
('사례별 오류 분석','앞선1156~1159실패를 보존했다. SQLite named bind, 테스트함수 shadow/Streamlit경로, 무판단fixture수집 기대값, 중지된 로컬Oracle, OracleJSON dict 반환을 구분한다. 무판단 순간은 수집을 건너뛰고 실제 저장된 판단 fixture로 수집을 확인했다.'),
('비용·지연·회수 규모','새 모델0, 실제 사용자 데이터 게시0. 전체 서비스 지연이나 법률 회수 품질을 산정하지 않는다. Oracle 검증은 명시된 작업용 로컬 컨테이너의 임시 전용 스키마에서 수행했다.'),
('해석','원문 중심 레시피를 사전에 펼쳐 승인·게시하고, A1은 현재 원문과 결속된 시나리오 ID만 선택한다. 일반/예외 복수선택과 충분성·재선택·기존 탐색 복귀를 유지한다. 모델이나 서버가 사건 법률 결론을 자동 승인하지 않는다.'),
('한계와 일반화 가능 범위','Dataiku SDK 스트림은 로컬 어댑터, Oracle은 실제 로컬DB다. 현장 S3/Flow/GENOS/SIDDA 권한과 실제 생성 모델 응답은 미검증이다. 스키마/메타 후보 작성은 메타마이너·DBA 승인 완료가 아니다. 법률품질과 unseen 질문 정확도는 미인증이다.'),
('운영 결정·롤백 조건','사용자의 연결 구현 요청과 기존 최신MAIN반영 승인을 따른다. ON/OFF 기본OFF와 데이터미포함을 유지해 공식승격하고 실제선택서비스를 확인한다. 권한/원문/해시/선택불일치면 공식MAIN110 롤백. 변경 파일만 통합하고 동시작업은 보존한다.'),
('재현 명령','setup.py → freeze.py → stage.py → check.py workflow/ui/capture/ontology, ONTOLOGY_TEST_SERVING=1 check.py database, oracle.py → qualify.py → finish.py → stable validate --final/graph → 공식prepare/apply. 예전결과를 덮어쓰지 않는다.')]
(ADR/'README.md').write_text('---'+meta+'---\n\n# 온톨로지 생성·승인·게시·RAG 연결 기술 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 운영 경로 기술 검증\n\n244테스트 + 실제로컬Oracle10조건 통과, 모델0. 법률품질 인증과 현장 배포는 별도다.\n')
for args in [('hash','--path',str(ADR)),('status','--path',str(ADR),'--status','completed','--note','254technicalconditions passed;453officialserving files;defaultOFF;no ontologydata;model0;fielddeploymentfalse.')]:
 x=subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py',*args],capture_output=True,text=True);(ART/(args[0]+'-final.txt')).write_text(x.stdout+x.stderr);assert x.returncode==0,x.stdout+x.stderr
print('Completed technical qualification254, no legal quality certification')
