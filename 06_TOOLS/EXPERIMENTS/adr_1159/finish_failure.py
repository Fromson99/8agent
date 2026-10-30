from common import *
import re,subprocess
x={'seconds':0};assert read(ART/'check-oracle.json')['strict_success'] is False
summary='1159 실제 에이전트 판단 수집1·생애주기22 통과. 로컬Oracle5테이블 생성·승인대기배제·승인만으로노출안됨·트랜잭션게시4조건통과. Oracle JSON CLOB 조회가 dict를 반환하여 JSON 문자열 디코딩에서 실패. 기존 게시/활성데이터는 격리임시스키마이며 정리완료. dict/문자열 양형식 검증을 후속에서 수정. 모델0·MAIN110유지.'
put(ART/'run-001/result.json',{'status':'complete','strict_success':False,'new_model_calls':0,'passed':23,'failed':1,'classification':'oracle_json_clob_native_dict','quality_certified':False,'main_changed':False})
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'),success_criteria_met=False)
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','role':'historical MAIN110'},'connected':{'status':'complete','outcome':'DB API binding failure','passed':23,'failed':1}},comparisons=[],usage={'new_model_calls':0},latency={'seconds':x['seconds']},error_taxonomy=['Oracle JSON-constrained CLOB returns decoded dict with the installed driver'],quality_certified=False)
put(ADR/'실험/manifest.json',m)
head=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Rejected'),('decision_eligible','false'),('in_sample','false')]:head=re.sub(r'(?m)^'+k+':.*$',k+': '+v,head)
titles=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[summary,'기존 MAIN110은 승인 화면·DB와 미연결이고 필수 스키마가 서빙에서 누락됐다.','artifacts/design/criteria.json의 생애주기·실패 계약을 구현 전에 고정했다.','680파일 격리 후보. 생애주기19·기존온톨로지216·DB HTTP2 통과; 테스트오류3. Oracle와 후속검증은 다음ADR로 이월.','artifacts/design/freeze.json 및 baseline.json. 원문·모델 정책·프로필 유지.','생애주기22·실제판단수집1통과. Oracle4선행조건통과 후 조회1실패. check-oracle.json 및 oracle-failure.txt.','무판단 수집 건너뜀을 수정하고 실제 판단 fixture 수집에 성공했다. Oracle JSON CLOB의 실제 반환 타입이 문자열이 아닌 dict였으며 내용을 임의 변환하지 않고 양형식에 같은 해시·스키마 검사를 적용하는 후속이 필요하다.','모델0. 성능·법률 품질 평가 없음.','격리 합성데이터의 승인·게시·DB조회·실제HTTP 답변을 확인했다. 전체 기술검증 완료로 확대하지 않는다.','기술 후보 실패. 법률 품질 인증 없음.','MAIN110 불변, 데이터 게시 없음. 실패 기록 보존.','check.py workflow. 완료 결과는 덮어쓰지 않는다.']
(ADR/'README.md').write_text('---'+head+'---\n\n# 온톨로지 연결 최초 검사\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(titles,texts),1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 검사\n\n'+summary+'\n')
for args in [('hash','--path',str(ADR)),('status','--path',str(ADR),'--status','completed','--note',summary)]:
 r=subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py',*args],capture_output=True,text=True);(ART/(args[0]+'-final.txt')).write_text(r.stdout+r.stderr);assert r.returncode==0
print(summary)
