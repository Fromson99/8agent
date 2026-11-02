from common import *
import re
contracts=read(ART/'final-contracts-r6/result.json');native=read(ART/'final-native-r6/result.json');working=read(ART/'working-native/result.json')
f=read(DES/'freeze.json');C=ROOT/f['code_root']
for r in (contracts,native,working):assert r['failed']==0 and r['code_unchanged'] and r['active_unchanged']
assert contracts['passed']==269 and native['passed']==working['passed']==7
assert all(sha(ROOT/n)==sha(C/n)==h for n,h in f['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
reconciliation={'initial_contracts':bind(ART/'contracts/result.json'),
 'legacy_parsing_regression':'rev001 enabled scaled money parsing globally, changing old typed_value behavior. Restrict written_units to the v2 application path; legacy binding/comparison readers remain unchanged; old regression tests pass.',
 'initial_native':bind(ART/'native/result.json'),'native_fixture_collision':'Six first native failures were the new test_native module shadowing the old fixture helper. Renamed test module; historical helper unchanged.',
 'native_r2':bind(ART/'native-r2/result.json'),'consumer_repair':'Four rejection cases passed. Two success cases failed the internal ASSESS additionalProperties schema for new review_links/scenario_application_display. Added the fields to the actual internal consumer schema, then success/publication passed.',
 'later_changes':['Use review-link:<n> namespace to avoid source/locator aliases.','Reject malformed/wrong-signed KRW mentions, allow bound computed monetary results.','Preserve rejected shared-link proposal and use shared vocabulary for the existing single repair.'],
 'preserved_runs':[bind(p) for p in sorted(ART.glob('*/result.json'))],
 'support_files':{str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('*.py')) if p.name!='finalize.py'}}
put(ART/'verification-reconciliation.json',reconciliation)
result={'status':'TECHNICAL_PASS','candidate_revision':f['candidate_revision'],'candidate_files':527,'changed_files':41,'product_files':10,'pins':31,
 'contract_passed':269,'native_passed':7,'failed':0,'working_native_passed':7,'working_checks_overlap_candidate':True,
 'artifacts':{k:bind(ART/n/'result.json') for k,n in [('contracts','final-contracts-r6'),('native','final-native-r6'),('working_native','working-native')]},
 'integration':bind(ART/'working-integration.json'),'reconciliation':bind(ART/'verification-reconciliation.json'),
 'model_calls':0,'oracle_calls':0,'main_changed':False,'quality_certified':False,
 'limits':['Scenario ASSESS/repair only; ordinary generation and legacy receipts keep prior contracts.',
 'Shared claim/evidence relations do not merge independent adoption/exclusion/conflict judgments or redefine SATISFIED.',
 'Explicit KRW magnitudes are supported in v2 application prose; not a parser of all units/languages or a verifier of arbitrary legal meaning.',
 'No new Qwen quality/latency/token/cost comparison, Oracle E2E, GENOS or NFS validation.']}
put(ART/'verification.json',result)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 '수치 표현·검토 연결 후속 수정 기술 채택 및 작업 코드 통합. 제품10+pin31=41파일만 반영했고 검증후보 rev006/작업527파일 동일. MAIN132 선택·Gold·운영 데이터 유지. 실모델 품질 또는 배포 인증이 아니다.',
 'ADR1282는 입력의 전체본문 참조·서버 조건표 복원·gap 무절단 연결을 구현했다. 남은 문제는 여러 검토표에서 같은 claim_refs/basis_refs 반복 작성과 숫자 문자 등장/금지 검사에 의한 245만 원·변경 전후 비교 오거절이었다.',
 '[사전 기준](artifacts/design/criteria.json): 동일 관계1회 정의·독립 의미 판단 보존·전체 기존 검증 재실행, 현재/과거 역할 분리, 단위·부호·배율 정확성, UNKNOWN 유지, 과거 reader 호환, API 저장/표시/재조회 결속. 원문·사유 절단과 의미 추정 보정 금지.',
 '새 가정 ASSESS에 review_links와 scenario-application-v2를 연결했다. 공유관계는 판단/need/범위/요구 검토표에서 link_ref로 재사용하고 기존 내부형식으로 확장한 뒤 기존 검증을 모두 수행한다. 일반 사건과 과거 receipt는 이전 생성/reader를 유지한다. 신규46계약·native 가정6/일반gap1과 관련회귀를 수행했다.',
 'ADR1282 완료 arm을 부모로527파일 후보를 격리·동결했다. 모의 transport와 합성 원문으로 실제 native HTTP·SQLite 기록·게시 검증을 실행했다. 새 외부모델/Oracle0. 원문 판본·ACL·hash·예산·UNKNOWN 이후 무재전송 정책 변경0.',
 '최종동결 rev006 계약269+native7=276통과·실패0. 작업 통합 후 native7 재확인(후보와 중복). 현재245만 원/2,450,000원 허용, 변경전100만 원/현재245만 원 비교 보존, 옛값의 CURRENT 선택/잘못된 배율·부호/미확인 승인 확정 거절. 미확인 gap600자 끝부분과 동일요청 추가호출0 유지.',
 'rev001 계약67통과/1실패는 전역 금액파싱 변경이 과거 동작을 바꾼 문제로, v2에서만 확장 표기를 읽게 수정했다. 최초native6실패는 새 검사기 이름과 기존 fixture import 충돌이었다. rev002 native4통과/2실패는 저장 내부스키마가 새 필드를 거절한 제품 결함으로 수정했다. 모든 원본 실패와 후속 결과를 보존했다. 마지막 보완은 연결ID namespace, 수치경계, 원제안 보존/같은 형식 보완을 검증했다.',
 f'새 모델0·Oracle0·외부비용0. 최종계약 {contracts["seconds"]:.3f}초/native {native["seconds"]:.3f}초. 작업native {working["seconds"]:.3f}초는 반복검사다. 예시4검토표가 같은 관계1개를 재사용하는 것을 확인했으며 실제 Qwen 출력 토큰 감소율·속도 개선율은 측정하지 않았다. 회수/검색 정책 변경0.',
 '모델은 관계를 한 번 작성하고 각 검토의 의미를 독립적으로 결정한다. 서버는 관계를 그대로 복원한다. 숫자값·조건결과는 현재 가정에 결속하고, 비교는 같은필드의 과거값으로 분리한다. 수치 표시를 서버가 조립하므로 새 숫자를 자유문에 반드시 반복할 필요가 없다. 원문 인용·모델 사유는 자르거나 다시 쓰지 않는다.',
 '모든 검토표의 의미를 하나의 상태로 합친 것이 아니다. 채택/제외/보류/충돌·요구 범위·미확인은 기존 의미를 유지한다. 새로운 자유문 검증은 명시 KRW 표기와 연결된 값/계산 결과에 한정되며 모든 문장의 법률적 진실성이나 명시 역할의 의미상 정당성을 인증하지 않는다. 새 Qwen 실험과 Oracle/GENOS/NFS 검증은 없다.',
 '사용자 후속 수정 지시에 따른 작업 반영이며 MAIN132는 그대로다. 변경파일별 이전/이후 해시와 artifacts/working-before 백업을 보존했다. 원복은 이후 변경 없는 해당41파일에 한정하고 전체 작업 snapshot을 덮지 않는다. 새 writer의 출력은 새 reader와 함께 유지해야 하며 이미 저장한 새 기록을 구버전 reader로 검증했다고 주장하지 않는다. Git/메일/DB·DDL/현장배포0.',
 '.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1283/check.py --name <새결과경로> <검사파일...>; 작업 검사는 check_working.py. 정확한 검사 목록·해시는 artifacts/verification.json과 해당 result.json 참조. 완료 결과를 덮어쓰거나 실모델을 자동 재호출하지 않는다.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Accepted',front)
p.write_text('---'+front+'---\n\n# ADR1283 타입 적용값·공유 검토 연결\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 검증\n\n모의 모델의 계약/API 검증으로 별도 법률 질문 채점은 없다.\n\n[결과·한계](../README.md) · [검증 묶음](../artifacts/verification.json) · [실행 계보](manifest.json)\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',artifact_path=str((ART/'verification.json').relative_to(ROOT)),sha256=sha(ART/'verification.json'))
m['results'].update(status='complete',by_arm={'baseline':{'historical_adr1282':True},'verified':result},judge_disagreements=0,
 usage={'model_calls':0,'oracle_calls':0},latency={'contracts_seconds':contracts['seconds'],'native_seconds':native['seconds']},
 error_taxonomy=[{'type':'LEGACY_PARSER_REGRESSION_REPAIRED','count':1},{'type':'FIXTURE_IMPORT_COLLISION_REPAIRED','count':6},{'type':'INTERNAL_SCHEMA_REPAIRED','count':2}])
put(ADR/'실험/manifest.json',m)
p=ART/'manifest.json';am=read(p);am['files']=[dict(bind(x),bytes=x.stat().st_size,description='Frozen code/design, preserved failure and verified working integration',contains_raw_prompts_and_outputs=False) for x in sorted(ART.rglob('*')) if x.is_file() and x!=p and '/runtime/' not in str(x) and '/__pycache__/' not in str(x)]
p.write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
print('Final: 269 contracts +7 native PASS; working native7 PASS; MAIN132 unchanged')
