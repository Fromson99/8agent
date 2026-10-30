from common import *
import re, subprocess

result=read(ART/'run-001/result.json')
assert result['strict_success'] and result['checks'] and all(v is True for v in result['checks'].values())
def bind(p): return {'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
m=read(ADR/'실험/manifest.json')
m.update(in_sample=False,decision_eligible=True)
m['design']['release_rebase']=bind(DES/'release-rebase.json')
m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','role':'Same-product completed1153 technical evidence'},'integrated':{'status':'complete','technical_conditions':226,'receipt_contract_checks':12,'quality_certified':False}},comparisons=[{'product_identical':True,'technical_receipt_only':True,'new_semantic_evaluation':False}],usage={'new_model_calls':0},latency={'performance_claim':False},error_taxonomy=['1152 test-path failures preserved','1153 missing formal checks field preserved; repaired in this receipt-only followup'],main_wiring='promotion-candidate',quality_certified=False)
put(ADR/'실험/manifest.json',m)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]: meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
sections=[
('결정 요약','동일 제품의 공식 승격 영수증을 별도 검증했다. 12개 결속 검사가 통과했고, 동일 코드의 226개 기술 조건을 원결과 해시로 상속한다. 제품 변경이나 법률 품질 재평가는 없다.'),
('문제와 변경 전 구조','1153의 226개 기술 조건은 통과했으나 결과에 공식 승격 계약이 요구하는 checks 사전이 없었다. prepare는 릴리스 생성 전 거절했고 MAIN109는 유지됐다. 완료된 결과를 덮어쓰지 않고 이 후속 ADR에 결속했다.'),
('가설과 사전 판정 기준','receipt-criteria.json을 실행 전에 동결했다. 동일 665개 제품 파일, 440개 공식 서빙 파일, 기존 226개 기술 조건과 선택된 MAIN109를 해시로 검증한다. 하나라도 불일치하면 승격하지 않는다.'),
('실험 설계','1153 완료 arm을 부모로 삼았다. 제품을 수정하지 않고 격리 snapshot/register/freeze 절차로 결속했다. 새 법률 질문이나 모델 호출은 없다. 기술 감사의 decision_eligible은 법률 정답 인증이 아니다.'),
('데이터·모델·재현성','374자 지침을 365자 지침으로 바꾼 기존 후보와 바이트가 같다. 최신 MAIN109 대비 제품 모듈의 PROMPT 하나와 종속 pin 31개만 다르다. 모델·프로필·데이터·출력 상한 없음·40/1024/1800 예산을 유지한다.'),
('결과','영수증 결속 12개 조건 통과. 1153의 216개 기존 프레임워크 조건과 10개 재실행 조건을 그대로 상속했다. 두 경로 강제 선택이 아니라 모델의 0~3개 경로 선택을 보존하는 합성 검사를 포함한다.'),
('사례별 오류 분석','1152 시험 경로 상수 충돌과 1153 영수증 필드 누락은 각각 원기록에 보존했다. 제품 오류나 새 모델 실패로 합산하지 않는다. 1150의 알려진 데이터 11/11 관찰과 제공자 대기 실패도 소급 변경하지 않는다.'),
('비용·지연·회수 규모','새 모델 호출 0회. 지연 개선이나 회수 품질 수치를 산출하지 않았다. 실제 데이터 로딩과 선택 서비스 확인은 하나씩 실행한다.'),
('해석','일반 성립·적용 요건 질문에서 성립과 제외·예외 경로를 함께 검토하도록 짧은 지침만 전달한다. 서버가 경로를 자동 삽입하거나 특정 질문의 답을 강제하지 않는다.'),
('한계와 일반화 가능 범위','1150의 알려진 원문 8질문·11반복 결과를 새 holdout이나 법률 품질 인증으로 표현하지 않는다. 온톨로지는 기본 OFF이고 ON이어도 데이터가 없으면 기존 탐색으로 진행한다. 데이터 게시·GENOS 현장 배포는 이 범위가 아니다.'),
('운영 결정·롤백 조건','사용자의 최신 MAIN 반영 명시 지시를 따른다. 다른 실험은 별도 사용자 요청으로 중지됐고 프로세스 종료가 확인됐다. 공식 prepare/apply 후 실제 서비스 OFF와 ON·빈 데이터 상태를 확인한다. 코드·권한·원문·상태 오류 시 MAIN109로 공식 롤백한다.'),
('재현 명령','setup.py → freeze.py → check.py → finish.py → validate --final 및 graph → promote.py. 원결과와 파일 해시는 artifacts/design/inherited-verification.json에 있다. 선택 서비스 결과와 롤백 정보는 09_ARTIFACTS/AUDITS/20261028-ontology-selection-main110에 보관한다.')]
(ADR/'README.md').write_text('---'+meta+'---\n\n# 온톨로지 선택 개선의 공식 승격 영수증 결속\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 영수증 감사\n\n226개 기술 조건 상속, 새 결속 검사 12개, 새 모델 0회. 법률 질문 재평가 없음.\n')
for args in [('hash','--path',str(ADR)),('status','--path',str(ADR),'--status','completed','--note','Same665product/440serving;226technicalconditionsinherited;12receiptcontractcheckspassed;no product/data/model change.')]:
    r=subprocess.run([str(ROOT/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_structure.py',*args],cwd=ROOT,capture_output=True,text=True)
    (ART/f'{args[0]}-final.txt').write_text(r.stdout+r.stderr)
    assert r.returncode==0,r.stdout+r.stderr
print('Qualified same product with formal checks dictionary; newmodel0')
