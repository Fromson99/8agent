from common import *
import re,subprocess
x=read(ART/'check-database-serving.json');assert x['failed']==1
summary='1158 생애주기22·기존화면1·공식453파일 DB HTTP3 통과. 정상HTTP의 답변은 성공했으나 판단 없는 시나리오 fixture에 수집 이벤트를 요구한 부가검사1실패. 판정 없는 입력에서 수집 시도가 오류기록을 남김. Oracle는 로컬컨테이너중지로 연결시간초과, DDL미실행. 후속에서 수집조건과 검증자료를 구분. 모델0·MAIN110유지.'
put(ART/'run-001/result.json',{'status':'complete','strict_success':False,'new_model_calls':0,'passed':26,'failed':1,'classification':'capture_fixture_has_no_accepted_judgment','quality_certified':False,'main_changed':False})
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'),success_criteria_met=False)
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','role':'historical MAIN110'},'connected':{'status':'complete','outcome':'DB API binding failure','passed':26,'failed':1}},comparisons=[],usage={'new_model_calls':0},latency={'seconds':x['seconds']},error_taxonomy=['No accepted judgment in scenario-selection fixture; Oracle test container stopped before connection'],quality_certified=False)
put(ADR/'실험/manifest.json',m)
head=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Rejected'),('decision_eligible','false'),('in_sample','false')]:head=re.sub(r'(?m)^'+k+':.*$',k+': '+v,head)
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[summary,'기존 MAIN110은 승인 화면·DB와 미연결이고 필수 스키마가 서빙에서 누락됐다.','artifacts/design/criteria.json의 생애주기·실패 계약을 구현 전에 고정했다.','680파일 격리 후보. 생애주기19·기존온톨로지216·DB HTTP2 통과; 테스트오류3. Oracle와 후속검증은 다음ADR로 이월.','artifacts/design/freeze.json 및 baseline.json. 원문·모델 정책·프로필 유지.','26통과1실패. check-workflow/check-database-serving/check-ui.json. Oracle 연결실패는 oracle-infrastructure-failure.log에 보존.','실제 화면 승인·게시 통과. 직접 시나리오 선택 fixture는 기존 읽기 판단이 비어 있어 수집 이벤트가 없는 것이 타당하다. 수집은 실제 승인된 읽기 판단 fixture로 검증한다. 원문 없는 순간은 수집을 건너뛰게 보완한다.','모델0. 성능·법률 품질 평가 없음.','격리 합성데이터의 승인·게시·DB조회·실제HTTP 답변을 확인했다. 전체 기술검증 완료로 확대하지 않는다.','기술 후보 실패. 법률 품질 인증 없음.','MAIN110 불변, 데이터 게시 없음. 실패 기록 보존.','check.py workflow. 완료 결과는 덮어쓰지 않는다.']
(ADR/'README.md').write_text('---'+head+'---\n\n# 온톨로지 연결 최초 검사\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(titles,texts),1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 검사\n\n'+summary+'\n')
for args in [('hash','--path',str(ADR)),('status','--path',str(ADR),'--status','completed','--note',summary)]:
 r=subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py',*args],capture_output=True,text=True);(ART/(args[0]+'-final.txt')).write_text(r.stdout+r.stderr);assert r.returncode==0
print(summary)
