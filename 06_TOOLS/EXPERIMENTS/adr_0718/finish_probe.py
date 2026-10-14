from pathlib import Path
import json,hashlib,xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0718-main50-request-repair-integration';D=A/'artifacts';B=R/'02_BACKEND/lawrag/research/candidates/adr_0718/repaired'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(exist_ok=True,parents=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def cases(p):
 ts=list(E.parse(p).iter('testcase'));return {'tests':len(ts),'failed':sorted(t.get('name') for t in ts if t.find('failure') is not None or t.find('error') is not None)}
base=cases(D/'contracts/baseline/all.xml');candidate=cases(D/'contracts/rev-002/all.xml');new=cases(D/'contracts/rev-003/new.xml')
assert base['failed']==candidate['failed'] and not new['failed']
cm=json.loads((B/'candidate.json').read_text());rev=cm['revisions'][-1];code=B/'revisions'/rev['revision_id']/'snapshot'
prev=B/'revisions/rev-002/snapshot'
assert all((prev/x['target_path']).read_bytes()==(code/x['target_path']).read_bytes() for x in cm['files'] if x['target_path']!='05_TESTS/CONTRACTS/test_main50_request_repair.py')
baseinfo=json.loads((D/'design/baseline.json').read_text())
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseinfo['pointer_sha256']
assert all(sha(R/p)==h for p,h in baseinfo['manifest']['files'].items())
result={'status':'complete','probe_only':True,'decision_eligible':False,'external_model_calls':0,
 'new_contracts':new,'candidate_all':candidate,'baseline_all':base,'new_regressions':[],
 'inherited_failures':'15 identical failures verified on selected MAIN50: old unified-memory API/shortcut/auth/display fixture expectations and prior experience-reuse fixture. Not converted to passes or used as proof of those behaviors.',
 'candidate_revision':rev['revision_id'],'serving_code_matches_tested_rev002':True,'main_unchanged':True,'all_new_contracts_pass':True}
put(D/'run-001/result.json',result)
m=json.loads((A/'실험/manifest.json').read_text());m['results'].update(status='complete',by_arm={'repaired':{'status':'complete','contracts_passed':True,'new_tests':new['tests'],'new_regressions':0,'inherited_failures':15}},comparisons=[],usage={'model_calls':0},latency={'semantic_measurement':None},error_taxonomy=['15 verified inherited legacy fixture failures'])
m['runs'][0].update(status='complete',sha256=sha(D/'run-001/result.json'));put(A/'실험/manifest.json',m)
old=(A/'README.md').read_text();front=old.split('---',2)[1].replace('status: Proposed','status: Accepted')
sections=[('결정 요약','통합 후보 구현 완료. 신규20검사 통과, 기존271검사 대비 신규 실패0. probe이므로 운영 승격 근거로 쓰지 않고 별도 공개 holdout으로 진행한다. MAIN50 포인터·작업 코드는 그대로다.'),
('문제와 변경 전 구조','CM51에서 재개 시 이전 decision_retry가 남고, 부족 대상 대신 다른 조문을 읽거나 반복 gap이 재개되며, 조건 구조와 답변 조립에서 오류·설명 손실이 관찰됐다. 세부 목록은 설계 보고서와 ADR0717 정본을 따른다.'),
('가설과 사전 판정 기준','artifacts/design/criteria.json을 구현 전에 고정했다. 요청 epoch·불변 원문과 scope에 결속한 gap·실제 전달/채택 span·배경 인용·단일 답변 내용으로 재현 가능한 코드 결함을 차단한다. 의미 정확도나 지연 효과를 이 probe로 주장하지 않는다.'),
('실험 설계','MAIN50의287파일을 후보에 복사하고 필요한 파일만 수정했다. v5 프로필에만 새 의미 계약을 연결하고 과거 v1-v4 렌더링을 유지했다. 새 모듈은 기존7단계 및 엔진/프로필/실행 binding에 명시했다. 분리된 새 실행기는 제품에 추가하지 않았다.'),
('데이터·모델·재현성','모의 원문·합성 판단 계약20개와 기존 회귀271개. 외부 모델 호출0. 후보rev001 실패,rev002수정,rev003 추가 연결검사를 모두 불변 기록으로 보존했다. 데이터 generation은 변경하지 않았다.'),
('결과','최신 신규20/20 통과. 기존271개는 MAIN50 256통과/15실패, 후보도 동일15실패. rev002 전체273통과/15실패, rev003은 서빙 코드가 동일하고 신규20검사가 통과했다. 숨긴 실패나 제외한 검사 없이 XML·로그를 보존한다.'),
('사례별 오류 분석','rev001에서 부분 좌표 색인 부재를 원문 부재로 볼 위험과 기존 모의 객체의 profile 경로가 드러났다. 색인 완전성 확인과 실제 프로필 진입 경로로 수정했다. 옛 통합 API fixture는 현재 shortcut·인증·공개 오류 표시 계약과 다르며 baseline에서도15실패가 재현됐다.'),
('비용·지연·회수 규모','실제 모델 비용0. 합성 실행 시간은 검사 로그에만 남기며 서비스 성능으로 해석하지 않는다. 회수 효과 비교와 corpus golden recall은 해당 없음. request-window process RSS 샘플 peak를 추가했으며 요청 단독 메모리 할당으로 표기하지 않는다.'),
('해석','재조사 epoch에서 이전 수정 시도를 정리하되 요청 예산/원문을 유지한다. 같은 정확 대상의 optional material과 이유 표현은 gap identity를 바꾸지 않는다. 불완전 색인·다른 조문은 부재 증명이 아니다. 중첩 조건에서 코드가 IDs/root를 만들고 상세 비교·의무·예외를 최종 텍스트에 보존한다.'),
('한계와 일반화 가능 범위','법률 의미 오류, 주 근거와 관련 근거 구별, 제목의 간접 의미 연결은 모델 판단 영역으로 남는다. 규칙 구조를 보존한다고 법률 의미가 맞는 것은 아니다. CM51 재실행·GENOS·실제 지연 개선은 미검증이다.'),
('운영 결정·롤백 조건','현재 구현은 격리 후보다. 후속 신규 공개 분리 검증을 통과한 동일 코드만 작업 코드 선별 통합과 MAIN 승격으로 이어간다. 심각한 인용·권한·상태·해시·실제 서비스 연결은 계속 차단 기준이다. 실패한 원시 기록은 삭제하지 않는다.'),
('재현 명령','06_TOOLS/EXPERIMENTS/adr_0718/run_contracts.py --new-only 및 check_baseline_contracts.py. 완료 결과를 덮어쓰는 새 실행은 하지 않는다. 후속 모델 실험은 새 ADR로 동결한다.')]
(A/'README.md').write_text('---'+front+'---\n\n'+'\n\n'.join('## '+str(i)+'. '+h+'\n\n'+b for i,(h,b) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 합성 계약 구현 확인\n\n모의 원문과 명시한 결정만 사용했다. 신규20통과, 기존15실패는 MAIN50에서도 동일하게 확인했다. 실제 모델 품질 평가가 아니다. [결과](../artifacts/run-001/result.json)와 contracts의 불변 rev별 XML·로그를 따른다.\n')
put(D/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0718','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Synthetic contract and immutable code evidence','contains_raw_prompts_and_outputs':False} for p in D.rglob('*') if p.is_file() and p.name!='manifest.json']})
print(result)
