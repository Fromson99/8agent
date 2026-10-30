from common import *
import re,subprocess
x=read(ART/'check-database.json');assert x['failed']==2
summary='1157 생애주기19·기존온톨로지216·DB사용HTTP2 통과. OFF/ON빈DB HTTP2는 테스트 함수 proposal을 dict로 가린 오류; UI1은 테스트 sys.path 복원으로 Streamlit 누락. 제품오류와 구분하고 후속에서 검증한다. 모델0·MAIN110유지.'
put(ART/'run-001/result.json',{'status':'complete','strict_success':False,'new_model_calls':0,'passed':237,'failed':3,'classification':'test_callable_shadow_and_streamlit_import_path','quality_certified':False,'main_changed':False})
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'),success_criteria_met=False)
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','role':'historical MAIN110'},'connected':{'status':'complete','outcome':'DB API binding failure','passed':237,'failed':3}},comparisons=[],usage={'new_model_calls':0},latency={'seconds':x['seconds']},error_taxonomy=['Test proposal function shadowed by dict; Streamlit test path removed'],quality_certified=False)
put(ADR/'실험/manifest.json',m)
head=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Rejected'),('decision_eligible','false'),('in_sample','false')]:head=re.sub(r'(?m)^'+k+':.*$',k+': '+v,head)
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[summary,'기존 MAIN110은 승인 화면·DB와 미연결이고 필수 스키마가 서빙에서 누락됐다.','artifacts/design/criteria.json의 생애주기·실패 계약을 구현 전에 고정했다.','680파일 격리 후보. 생애주기19·기존온톨로지216·DB HTTP2 통과; 테스트오류3. Oracle와 후속검증은 다음ADR로 이월.','artifacts/design/freeze.json 및 baseline.json. 원문·모델 정책·프로필 유지.','237통과3실패. 원결과 check-workflow/check-database/check-ui/check-ontology.json.','SQLite 바인드 수정 후19통과. DB 정상·복수선택 HTTP 성공. 추가한 fixture의 proposal 지역변수가 함수이름을 가렸고, UI runner에서 sys.path 복원으로 Streamlit 경로가 사라졌다.','모델0. 성능·법률 품질 평가 없음.','격리 합성데이터의 승인·게시·DB조회·실제HTTP 답변을 확인했다. 전체 기술검증 완료로 확대하지 않는다.','기술 후보 실패. 법률 품질 인증 없음.','MAIN110 불변, 데이터 게시 없음. 실패 기록 보존.','check.py workflow. 완료 결과는 덮어쓰지 않는다.']
(ADR/'README.md').write_text('---'+head+'---\n\n# 온톨로지 연결 최초 검사\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(titles,texts),1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 검사\n\n'+summary+'\n')
for args in [('hash','--path',str(ADR)),('status','--path',str(ADR),'--status','completed','--note',summary)]:
 r=subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py',*args],capture_output=True,text=True);(ART/(args[0]+'-final.txt')).write_text(r.stdout+r.stderr);assert r.returncode==0
print(summary)
