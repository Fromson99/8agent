from common import *
import re
f=read(DES/'freeze-rev-001.json');s=read(DES/'staging-final.json');receipt=read(ART/'receipt-checks.json');reg=read(SOURCE/'regression-comparison.json')
checks=dict(receipt['checks']);checks.update(official_rebase_exact=read(DES/'release-rebase.json')['staged_files']==f['files'],only_six_products_plus31pins=len(s['products'])==6 and len(s['changed'])==37)
assert all(checks.values())
r={'status':'complete','strict_success':True,'checks':checks,'candidate':f['candidate_revision'],'files':466,'changed_files':37,'product_files_changed':6,'dependent_pins_changed':31,'technical_conditions':116,'working_conditions':116,'inherited_technical_evidence':read(DES/'inherited-evidence.json'),'receipt_conditions':9,'rollback_conditions':12,'regression':reg,'external_model_calls':0,'quality_certified':False,'performance_certified':False,'genos_deployed':False,'known_case_diagnostic_excluded_from_eligibility':True,'evidence':{p.name:bind(p) for p in [ART/'receipt-checks.json',ART/'rollback-compatibility.json',DES/'release-rebase.json']}}
put(RUN/'result.json',r)
m=read(ADR/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['design']['release_rebase']=bind(DES/'release-rebase.json')
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'verified':{'status':'complete','technical_success':True,'quality_certified':False}},comparisons=[reg],judge_disagreements=[],usage={'external_model_calls':0},latency={'performance_claim':False},error_taxonomy=['1196 raw failures retained: initial missing digest import, native fixture format/team corrections; finalrev002116/116 pass and211 exact comparison.', '1196 rollback writer wrongly passed .json to gzip-only writer; qualification missing evidence failed. Shell continued to mark reservation completed prematurely and final validation reported7 errors. Reopening denied by immutable history; original1196 is not a completed qualified arm.', '1197 repeats no product experiment or CM run. Identical466 bytes and immutable technical receipts verified; rollback writer suffix corrected and12 old-reader checks executed.'],main_wiring='promotion-candidate',quality_certified=False)
put(ADR/'실험/manifest.json',m)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
sections=[('결정 요약','MAIN116의 마지막 서술 재작성 손실을 막는1196 rev002와 동일한466파일을 검증 영수증으로 결속하고 MAIN117에 반영한다. 새로운 제품 수정·실모델 실행은 없다.'),
('문제와 변경 전 구조','COMPOSE가 claim ID만 유지한 채 이미 확보·판단한 분류 조건과 분모를 문장에서 누락했다. accepted-content-v1은 마지막 자유 재작성 호출을 생략하고 검증된 content/text를 서버가 조립한다.'),
('가설과 사전 판정 기준','[동결 기준](artifacts/design/criteria.json).1196의 미완료 메타 상태는 보존하고 동일 코드·동일 검증결과와 읽기 호환성을 새 영수증으로 검증한다. 법률 의미·속도 인증은 하지 않는다.'),
('실험 설계','완료된1194/integrated가 부모다.1196은 관련 오류/기술 증거이며 완료 부모로 사용하지 않았다.116 후보·116 작업 계약 및 동일211회귀를 재호출하지 않고 원본 경로·해시·내용을 확인했다. 별도9영수증 조건과 이전 릴리스 읽기12조건을 실행했다.'),
('데이터·모델·재현성','1196 rev002와466파일 전체 해시 일치. 같은MAIN116 데이터·Qwen3.8·Parasail/확정429 NearAI1회·40/1024/1800·개별180초·출력상한없음·온톨로지기본OFF. 새모델0. profile의 answer_presentation만 변경한다.'),
('결과','9영수증·12읽기호환검사 통과. 기존116/116 계약 통과와211회귀189통과/기존9실패/준비오류13·새회귀0 원본 확인. 제품/설정6+pin31변경. [결과](artifacts/run-001/result.json).'),
('사례별 오류 분석','1196에서 결과파일 작성 실패 뒤 쉘이 상태변경을 계속해 reservation만 먼저 completed가 됐다. 최종검사7오류와 재개거절을 보존한다.1196은 qualified 완료가 아니며 그 상태기록의12호환검사 문구도 증거가 아니다. 실제12검사는1197에서 실행했다.1196의 import/fixture/메타/진단 오류도 보존한다.'),
('비용·지연·회수 규모','새모델0·실제7번/9번0. 기존 COMPOSE 생성 호출을 없애지만 실제 전체 속도·비용 개선률은 측정하지 않았다. 완료 답변은 기존 workflow finish가 전달하며 생성 중 미검증 문장은 나오지 않는다.'),
('해석','claim의 content를 기존 컴파일러와 대조하고 ASSESS 해시에 결속한다. 임의 대체문장·조건 누락·중복ID·변조된 원문 receipt·stale 계획을 거절한다. 주장별 근거 검증·제한 답변·stop_reason·UNKNOWN·기존 저장 narrative-v1은 보존한다.'),
('한계와 일반화 가능 범위','ASSESS 자체가 빼먹거나 오판한 내용을 정답으로 고치는 것은 아니다. FINAL_REVIEW_SKIPPED/UNREVIEWED 유지. 자유로운 재서술 대신 전체 내용을 표시하여 답변이 길어질 수 있다. 저장007 재조립의 조건 보존은 인샘플 진단일 뿐 새 실제007 통과가 아니다.009실행 근거도 아니다.'),
('운영 결정·롤백 조건','accepted-answer-20261029-r1을 공식 선택하고 실제service OFF/ON미설정/ON빈DB를 확인한다. 이전MAIN116이 새 저장 composition을 그대로 검증하는12조건을 확인했다. 회귀 시 공식 rag_main_promotion.py rollback --confirm-main으로 이전final-answer-20261029-r1을 선택한다. GENOS 현장 배포는 하지 않는다.'),
('재현 명령','06_TOOLS/EXPERIMENTS/adr_1197의 setup/freeze/rollback_check/check/rebase/qualify/promote/finish. 완료 원본은 덮어쓰지 않는다. 원제품 구현 및116/211검사는1196 디렉터리의 저장 기록에 남는다.')]
(ADR/'README.md').write_text('---'+meta+'---\n\n# 최종 답변 보존 검증 영수증과 MAIN 반영\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 동일 코드 검증 영수증\n\n[동결 기준](../artifacts/design/criteria.json) · [결과](../artifacts/run-001/result.json). 새모델0·내용 재채점0.\n')
a=read(ART/'manifest.json');paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json']+list(Path(__file__).parent.glob('*.py'))+[ROOT/f['candidate_revision']['manifest_path']]
a['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact unchanged code and technical qualification receipts','contains_raw_prompts_and_outputs':False} for p in paths];(ART/'manifest.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
print('Qualified1197 with exact1196 rev002 bytes; no new model calls')
