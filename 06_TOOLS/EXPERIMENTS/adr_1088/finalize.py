"""Finalize an audit truthfully, including rejected partial integration evidence."""
from pathlib import Path
import json,hashlib,sys
R=Path(__file__).resolve().parents[3];number=sys.argv[1];slug=sys.argv[2];A=R/f'04_EXPERIMENTS/ADR/ADR-{number}-{slug}';ART=A/'artifacts';D=R/f'06_TOOLS/EXPERIMENTS/adr_{number}'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
x=json.loads((ART/'check-001.json').read_text());f=json.loads((ART/'freeze.json').read_text());ok=not(x['failed'] or x['import_leaks'] or x['changed_files']);status='complete' if ok else 'failed'
m=json.loads((A/'실험/manifest.json').read_text());m['runs'][0].update(status='complete',artifact_path=str((ART/'check-001.json').relative_to(R)),sha256=sha(ART/'check-001.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','scope':'Two exact completed frozen parents; no new baseline model call'},'integrated':{'status':status,'contract_passed':x['passed'],'contract_failed':x['failed'],'quality_certified':False,'decision_eligible':False}},usage={'new_model_calls':0,'input_tokens':0,'output_tokens':0,'cost_usd':0},latency={'synthetic_contract_seconds':x['seconds'],'service_measured':False},error_taxonomy=[{'test':r['test'],'detail':r['error'][-1600:]} for r in x['rows'] if r['status']=='failed'])
put(A/'실험/manifest.json',m)
header=(A/'README.md').read_text().split('---',2)[1]
header=header.replace('status: Proposed','status: '+('Proposed' if ok else 'Rejected'))
outcome=f"합성 검사 {x['passed']}개 통과·{x['failed']}개 실패다. "+('공통 압축·페이지·SQL과 온톨로지 A1/A2의 실제 HTTP 모의 경로를 결합해 통과했다.' if ok else 'catalogue_choice_prompt 변수명 병합 오류로 HTTP 네 검사가 실패했다. 성공 후보로 사용하지 않으며 오류 수정은 새 ADR에서 수행한다.')
sections=[('결정 요약',outcome+' 실모델0회, 법률 품질 미인증이다. 이 작업에서는 작업코드·MAIN·GENOS에 반영하지 않았다.'),
('문제와 변경 전 구조','1086의 공통 입력·근거 SQL과1079→1087의 온톨로지 실행·판단 상태는 별도 후보였다. 온톨로지4파일의 반복검증·컴파일·ID조회·전달이력·표시메타데이터 수리를 유지하며 공통8모듈과 두 프로필 설정을 선별 결합했다. 전체 후보 덮어쓰기는 하지 않았다.'),
('가설과 사전 판정 기준','[사전 기준](artifacts/criteria.json): 같은 원문·관계·값·선택 가능 대상·권한·판단·재개 상태를 유지한다. 현재 페이지에 없는 대상은 거절하고 페이지 이동은 판단 완료가 아니다. 보완은 기존 한도·담당을 유지한다. 실패는 숨기지 않는다.'),
('실험 설계','완료된1087/optimized와1086/compact를 정확한 두 부모로 쓴다. 6충돌 파일의 조합은 실험manifest integration에 기록했다. 페이지별 최소 행동 양식과 검증·보완 담당을 묶고 canonical 저장원문→공통 압축→선택적 기존 압축을 실제 요청과 독립 대조한다. 최초 색인을 외부 transaction에서 만든 경우 commit/rollback 뒤 재확인한다.'),
('데이터·모델·재현성','작은 합성 원문, 승인묶음, 요청 SQLite journal만 사용한다. 실제 corpus·golden 정답·외부 모델을 읽지 않았다. [동결 코드](artifacts/freeze.json)의 import 경로와 전체 파일 해시를 실행 전후 확인했다. 기존 API fixture는 이전 표현을 명시적으로 선택하고 별도 A1/A2 fixture는 실제 압축 입력으로 모의 행동을 고른다. 단계 이름만 모의 transport의 라우팅에 전달하며 숨겨진 원문·선택을 보충하지 않는다.'),
('결과',outcome+f" [전체 검사](artifacts/check-001.json), import 혼입 {len(x['import_leaks'])}, 동결파일 변경 {len(x['changed_files'])}."),
('사례별 오류 분석','실패의 원문·trace는 check-001.json에 보존했다. '+('1088의 변수명 오류만 수정한 제품으로 재검증했다. 완료된 부모는1086/1087이며 실패1088을 완료 부모로 승격하지 않았다.' if number!='1088' else '189검사가 통과했어도 HTTP4실패 때문에 통합 완료로 판정하지 않았다.')),
('비용·지연·회수 규모',f"합성 검사 {x['seconds']:.3f}초, 새 모델0·비용0이다. 서비스 지연·전체 입력 토큰·법률정답률 측정이 아니다. 후보 목록 페이지 크기는20이며 새 원문 획득과 페이지 이동을 구분한다. 본 실험에1087의 국소 절감율을 재측정 성과로 합산하지 않는다."),
('해석','전용 온톨로지 처리의 중복 감소와 공통입력 결합을 계약 수준에서 다룬다. LLM이 A1에서 올바른 원문만 선택하는지, 불필요한 조사를 줄이는지는 별도 실제모델 비교가 필요하다. 보이는 원문·묶음·관계가 그대로라는 사실만으로 의미 판단 향상을 주장하지 않는다.'),
('한계와 일반화 가능 범위','이 SQL은 로컬 요청 journal 경로이며 Oracle 지식 조회 전체나 GENOS 현장을 검증하지 않았다. 초기 색인 구축 비용은 미측정이다. 합성 HTTP는 두 조문 모의 상황이다. A1 외부 모델 선택 적절성·전체 성능·법률 품질은 미검증이다.'),
('운영 결정·롤백 조건','후보에만 저장했다. 현재 다른 작업의 공통 최적화·승격은 별도 상태다. 이 후보는 MAIN 자동 선택 대상이 아니다. 원문·범위·선택·권한·상태가 달라지면 사용하지 않고 exact1086/1087 부모를 복구점으로 유지한다. 후속 A1 실모델은 별도ADR에서 질문·비교조건·성공기준을 먼저 동결한다.'),
('재현 명령',f"```bash\n.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_{number}/check.py new-check.json\n.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-{number}-{slug} --final\n```\n\n완료 결과를 다시 비교하거나 변경 후보를 검증할 때는 새ADR을 선점한다.")]
(A/'README.md').write_text('---'+header+'---\n\n# 온톨로지 A1 공통입력 결합\n\n'+'\n\n'.join(f'## {i}. {title}\n\n{text}' for i,(title,text) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 합성 계약 검사\n\n'+outcome+'\n\n[코드·검사 결속](../artifacts/freeze.json), [실행 결과](../artifacts/check-001.json). 실모델0회.\n')
am=json.loads((ART/'manifest.json').read_text());am['files']=[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Preserved prospective criteria, frozen binding, code or contract result','contains_raw_prompts_and_outputs':False} for p in list(ART.iterdir())+list(D.glob('*.py')) if p.is_file() and p.name!='manifest.json'];put(ART/'manifest.json',am)
print(outcome)
