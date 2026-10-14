from pathlib import Path
import json, hashlib, xml.etree.ElementTree as E
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0724-source-recovery-boundary-fix';D=A/'artifacts'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def cases(p):
    tests=list(E.parse(p).iter('testcase'))
    return {'tests':len(tests),'failed':sorted(t.get('name') for t in tests if t.find('failure') is not None or t.find('error') is not None)}
base=read(R/'04_EXPERIMENTS/ADR/ADR-0723-source-target-recovery-complete/artifacts/contract-result.json')['baseline_all']
candidate=cases(D/'contracts/rev-001/all.xml');new=cases(D/'contracts/rev-001/new.xml')
assert new['tests']==40 and not new['failed'] and candidate['failed']==base['failed']
result={'status':'complete','probe_only':True,'decision_eligible':False,'external_model_calls':0,
        'new_contracts':new,'candidate_all':candidate,'baseline_all':base,'new_regressions':[],
        'candidate_revision':'rev-001','all_new_contracts_pass':True,'main_unchanged':True,
        'fixed_reproduced_boundaries':['outside-catalogue exact target','accepted partial batch resume','equivalent failed query','failure state version'],
        'additional_contracts':['scope rejection','transient partial acquisition preserves original without adoption']}
put(D/'run-001/result.json',result);put(D/'contract-result.json',result)
m=read(A/'실험/manifest.json');m['results'].update(status='complete',by_arm={'integrated':{'status':'complete','contracts_passed':True,'new_tests':40,'new_regressions':0,'inherited_failures':15}},comparisons=[],usage={'model_calls':0},latency={'semantic_measurement':None},error_taxonomy=['15 identical pre-existing MAIN50 failures'])
m['runs'][0].update(status='complete',sha256=sha(D/'run-001/result.json'));put(A/'실험/manifest.json',m)
front=(A/'README.md').read_text().split('---',2)[1].replace('status: Proposed','status: Accepted')
sections=[('결정 요약','재현된 네 경계를 보완했다. 신규40/40, 전체311개 중296통과와 기존 동일15실패. 모델 호출0이며 이 결과만으로 승격하지 않는다.'),
('문제와 변경 전 구조','ADR0723은 초기34검사 통과 후 목록 밖 정확한 조문 실행·부분 배치 재개·동등 실패 질의·실패 상태 버전의 결함을 발견해 거절했다. 모델 결과와 실패 기록을 보존했다.'),
('가설과 사전 판정 기준','artifacts/design/criteria.json에 수정 범위와 원문·권한·상태·회귀 기준을 구현 전에 동결했다.'),
('실험 설계','완료한 ADR0723/integrated의 정확한 코드 위에서 request_repair.py와 law_navigation.py, 계약 검사를 수정했다. 동일 모의 원문으로 실제 Investigation 실행·중단·재개 경로를 검사했다.'),
('데이터·모델·재현성','합성 데이터만 사용하고 외부 모델 호출0. rev-001의 코드와 프로필·엔진 해시를 고정했다. 실제 데이터 세대와 로컬 MAIN50은 유지한다.'),
('결과','40개 새 계약 전부 통과. 기존271검사 대비 신규 실패0. 전체311검사296통과/15실패. 기존 실패를 통과로 바꾸지 않았다.'),
('사례별 오류 분석','법령 목록 밖 조문은 허용 범위를 확인해 조사 상태에 등록한다. 읽기 중 획득 실패도 INTERRUPTED 계획으로 보존한다. 승인된 배치 재개는 완료 대상과 원문 상태를 보존해 다시 획득하지 않는다. 구조 검색의 공백 변형을 같은 실패로 취급한다. 복구 가능한 실패의 상태 버전과 행동 영수증을 갱신한다.'),
('비용·지연·회수 규모','외부 호출·비용0. 부분 획득에 실제 진전이 있으면 진전으로 기록하고 실패만 반복할 때는 무진행 제한을 유지한다. 모델 지연은 측정하지 않았다.'),
('해석','실패를 부재로 바꾸지 않으며 읽기와 채택을 분리한다. 이미 확보한 원문과 완료 기록이 복구 이후에도 이어진다. 코드 오류·권한·해시 위반은 여전히 즉시 차단한다.'),
('한계와 일반화 가능 범위','과거 CM의 의미 오류가 이 합성 검사로 해결됐다고 주장하지 않는다. 기존15실패, 전체 CM51·GENOS 현장은 미검증이다.'),
('운영 결정·롤백 조건','동일 코드를 별도 공개 분리 검증한 뒤 선별 통합·로컬 MAIN 승격·실제 service 진입점 확인을 수행한다. 그 전에는 MAIN50을 유지한다.'),
('재현 명령','06_TOOLS/EXPERIMENTS/adr_0724/run_contracts.py. 완료 기록을 덮어쓰지 않으며 후속 비교는 새 ADR을 사용한다.')]
(A/'README.md').write_text('---'+front+'---\n\n'+'\n\n'.join(f'## {i}. {title}\n\n{body}' for i,(title,body) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 경계 계약 검증\n\n[결과](../artifacts/run-001/result.json): 신규40통과, 전체311개296통과와 기존15실패, 모델 호출0.\n')
put(D/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0724','created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen boundary implementation and native synthetic validation','contains_raw_prompts_and_outputs':False} for p in D.rglob('*') if p.is_file() and p.name!='manifest.json']})
print('Completed boundary probe: 40 passed; no new failures across311 contracts')
