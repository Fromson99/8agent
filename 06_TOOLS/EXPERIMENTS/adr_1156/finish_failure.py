from common import *
import re,subprocess
x=read(ART/'check-workflow.json');assert x['failed']==8
summary='첫 생애주기 검사11통과8실패. Python3.14 SQLite가 :1 이름 바인드에 tuple을 거절. 입력/인용/순환/파일 계약 통과, DB 생애주기는 미완료. 모델0·MAIN110유지. 이름바인드 dict 수정 후 별도ADR 재검증.'
put(ART/'run-001/result.json',{'status':'complete','strict_success':False,'new_model_calls':0,'passed':x['passed'],'failed':x['failed'],'classification':'sqlite_named_parameter_sequence_incompatibility','quality_certified':False,'main_changed':False})
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'),success_criteria_met=False)
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','role':'historical MAIN110'},'connected':{'status':'complete','outcome':'DB API binding failure','passed':11,'failed':8}},comparisons=[],usage={'new_model_calls':0},latency={'seconds':x['seconds']},error_taxonomy=['SQLite Python3.14 named binding requires dict'],quality_certified=False)
put(ADR/'실험/manifest.json',m)
head=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Rejected'),('decision_eligible','false'),('in_sample','false')]:head=re.sub(r'(?m)^'+k+':.*$',k+': '+v,head)
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[summary,'기존 MAIN110은 승인 화면·DB와 미연결이고 필수 스키마가 서빙에서 누락됐다.','artifacts/design/criteria.json의 생애주기·실패 계약을 구현 전에 고정했다.','680파일 격리 후보, 합성19검사. 다른 UI·HTTP·Oracle 검사는 실패를 수정한 후속으로 이월한다.','artifacts/design/freeze.json 및 baseline.json. 원문·모델 정책·프로필 유지.','11통과8실패. 원결과 artifacts/check-workflow.json.','SQLite Python3.14에서 :1에 tuple 전달을 거절했다. Oracle 연결과 구별하여 dict 바인드로 수정할 예정이다.','모델0. 성능·법률 품질 평가 없음.','트랜잭션 실행 전에 중단됐다. 성공·승인·게시를 주장하지 않는다.','기술 후보 실패. 법률 품질 인증 없음.','MAIN110 불변, 데이터 게시 없음. 실패 기록 보존.','check.py workflow. 완료 결과는 덮어쓰지 않는다.']
(ADR/'README.md').write_text('---'+head+'---\n\n# 온톨로지 연결 최초 검사\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(titles,texts),1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 검사\n\n'+summary+'\n')
for args in [('hash','--path',str(ADR)),('status','--path',str(ADR),'--status','completed','--note',summary)]:
 r=subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py',*args],capture_output=True,text=True);(ART/(args[0]+'-final.txt')).write_text(r.stdout+r.stderr);assert r.returncode==0
print(summary)
