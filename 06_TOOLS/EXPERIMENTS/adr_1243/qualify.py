from common import *
import re
b=read(DES/'baseline.json');f=read(DES/'freeze.json')
checks={'records14':read(ART/'checks-final-records.json')['passed']==14 and read(ART/'checks-final-records.json')['exit_code']==0,
 'bare_oracle_api2':read(ART/'checks-final-api.json')['passed']==2 and read(ART/'checks-final-api.json')['exit_code']==0,
 'baseline_default_problem_reproduced':read(ART/'checks-baseline-api.json')['failed']==2,
 'original12_preserved':read(ART/'checks-baseline-records.json')['passed']==12,
 'same494':len(f['files'])==494 and all(sha(ROOT/n)==h for n,h in f['files'].items()),
 'exact_rebase':read(DES/'release-rebase.json')['staged_files']==f['files'],
 'main126_before_cutover':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==b['pointer_sha256']}
assert all(checks.values())
put(RUN/'result.json',{'status':'complete','strict_success':True,'checks':checks,'technical_tests_passed':16,'new_failures':0,
 'same_original_storage_contracts':12,'default_runtime_cases':2,'bare_oracle_service_cases':2,'candidate':f['candidate_revision'],
 'external_model_calls':0,'new_ddl':0,'new_gold_changes':0,'field_deployed':False})
m=read(ADR/'실험/manifest.json');m['design']['release_rebase']=bind(DES/'release-rebase.json')
m['runs'][0].update(status='complete',artifact_path=str((RUN/'result.json').relative_to(ROOT)),sha256=sha(RUN/'result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','storage_passed':12,'default_failures':4},
 'oracle-records':{'status':'complete','passed':16,'new_failures':0}},comparisons=[{'baseline_api_failed':2,'candidate_api_passed':2,'same_storage_passed':12,'new_default_cases_passed':2}],
 judge_disagreements=[],usage={'external_model_calls':0,'embedding_calls':0,'new_ddl':0},latency={'performance_claim':False},
 error_taxonomy=['MAIN126 service AD/report/recovery and chat defaults differ from Oracle Factory when GENOS_RUNTIME_DIR is missing'],main_wiring='promotion-candidate',quality_certified=False)
q=ADR/'실험/질문-001-contract.md'
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
values=['run-001 / baseline·oracle-records, MAIN126 부모.','지금 DP=oracle로 하면 전체 우리 오라클 디비만 쓰게 해주게 코드를 수정해줘 메인꺼',
 '법률 정답 평가 없음.','[사전 기준](../artifacts/design/criteria.json).\n\n### 회수·탈락 단계 원장 — run·arm별\n\n검색 회수 변경 없음. 런타임 목적지 동등성 검사.',
 '실제 모델0·ScriptedTransport.','실제 로컬 Oracle 원문/기록 SQL, 기존12 저장 계약.','baseline API2 실패 재현→후보2 통과·기존12 유지·기본 경로2 통과.',
 'DP=oracle만 설정하고 runtime 환경변수를 생략해도 저장·관리·로그·채팅에 같은 Oracle 논리 경로를 사용한다.']
q.write_text('# Oracle 기본 런타임 연결\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
m['questions']=[{'number':1,'case_id':'contract','file':q.name,'sha256':sha(q)}];put(ADR/'실험/manifest.json',m)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
sections=[('결정 요약','MAIN126에서 발견한 환경변수 생략 시 기본 경로 차이를 수정하여 MAIN127 후보로 채택한다. 제품3+pin31=34변경·494파일.'),
 ('문제와 변경 전 구조','Factory는 /__oracle_agent__/runtime을 쓰지만 service의 AD/보고서/복구와 chat 진행 포트는 ROOT/90_RUNTIME/semantic을 계산했다. GENOS_RUNTIME_DIR을 지정한1242 검증만으로 이 조건까지 확대하지 않는다.'),
 ('가설과 사전 판정 기준','[사전 기준](artifacts/design/criteria.json). DP만 Oracle로 설정한 경우 실제 게이트웨이 관리 목적지가 Factory와 같아야 한다. 기존 NFS 기본/명시 경로를 유지한다.'),
 ('실험 설계','완료1242 oracle-records를 직접 부모로 한다. 같은494파일/Agent 표/원문 fixture/모의 모델에서 runtime env만 생략했다. 이전 경로 실패를 먼저 재현하고 요청 메모리/Oracle 저장을 그대로 유지했다.'),
 ('데이터·모델·재현성','DB DDL/Gold/프로필/모델 변경0. runtime_directory(default) 공통 함수를 service와 chat이 사용한다. 기존 명시 절대 경로는 유지한다.'),
 ('결과','[결과](artifacts/run-001/result.json). 부모 기본관리경로 실패 API2 재현, 후보 실제Oracle 원문/기록 API2 통과. 기존 저장12 동일통과·기본 경로2 통과=16. 별도 실제root 진입과 MAIN 선택 검사는 운영 감사 영수증에 기록한다.'),
 ('사례별 오류 분석','이전 기능 성공을 모든 환경 조합 성공으로 확대하지 않았다. 기본값 분기만 좁혀 수정했고 ACL/LLM/근거 정책 변경이 없다. 전체 기존14 실패는 부모1242 범위에서 남으며 이번 작은 수정으로 해결했다고 하지 않는다.'),
 ('비용·지연·회수 규모','새 모델/임베딩0. 순수 경로 계산 수정이며 속도나 대용량 부하 개선 주장이 없다.'),
 ('해석','DP=oracle만으로 같은 논리 runtime이 선택된다. 연결/원문 게시/Agent DDL 권한은 여전히 준비해야 한다. 모든 SQL 재작성이나 실제 현장 이관 완료가 아니다.'),
 ('한계와 일반화 가능 범위','실제 Oracle19/ORDS·GENOS·LLM·현장 NFS 전량 이관/부하 미검증. 부모의 Oracle row 호환 실행 구조와 제한을 유지한다.'),
 ('운영 결정·롤백 조건','사용자 원래 메인 요청 범위에서 공식 MAIN127로 선택한다. MAIN126/125·NFS 원본/Gold 연결기를 보존하고 namespace·원본 절대 경로 유지. Oracle 신규 이력의 자동 NFS 역복사0.'),
 ('재현 명령','prepare→3 consumer edits→freeze→baseline/candidate records/API→integrate→qualify→공식 hash/status/validate→prepare/apply→실제선택entry. [산출물](artifacts/manifest.json).')]
(ADR/'README.md').write_text('---'+meta+'---\n\n# DP Oracle 기본 런타임 연결\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 검증\n\n[결과](../artifacts/run-001/result.json).\n')
print('Qualified16; bare-DP default mismatch reproduced and fixed')
