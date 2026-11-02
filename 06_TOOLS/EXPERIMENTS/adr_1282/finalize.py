from common import *
import re
f=read(DES/'freeze.json');C=ROOT/f['code_root'];integration=read(ART/'working-integration.json')
names=['contracts-r3','reference-output-r3','compact-r3','native-r3'];checks={name:read(ART/name/'result.json') for name in names}
working=read(ART/'working-native/result.json');baseline=read(ART/'baseline-compact/result.json')
assert working['passed']==7 and working['failed']==0 and working['code_unchanged'] and working['active_unchanged']
assert all(r['code_unchanged'] and r['active_unchanged'] for r in checks.values())
failures=lambda r:{x['test'] for x in r['rows'] if x['outcome']=='failed'}
assert failures(checks['compact-r3'])==failures(baseline) and len(failures(baseline))==2
assert sum(x['passed'] for x in checks.values())==200 and sum(x['failed'] for x in checks.values())==2
assert all(sha(ROOT/n)==sha(C/n)==h for n,h in f['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
reconciliation={
 'initial_native':bind(ART/'native/result.json'),'initial_native_passed':1,'initial_native_failed':6,
 'cause':'Two new wire assertions observed the request before minimal-output projection. Four native scenario failures exposed compound condition constants not translated into navigation aliases. Recorder boundary and product constant mapping corrected; native7 then pass.',
 'corrected_native':bind(ART/'native-r3/result.json'),
 'preexisting_compact_failures':sorted(failures(baseline)),
 'baseline':bind(ART/'baseline-compact/result.json'),'final_compact':bind(ART/'compact-r3/result.json'),
 'preexisting_detail':'Both existing SQL-log assertions also fail on ADR1281. This change does not repair those assertions; original failures are preserved.',
 'offline_audit_preparation_error':'First audit attempted to restore ordinary call003 without a scenario projection and correctly failed invalid assessment input receipt. Added applies filter; five scenario requests audited. No historical data changed.',
 'test_binding_note':'After rev003 freeze, the added namespace unit fixture was corrected to register both opaque condition IDs before tests ran; product rev003 remained byte-identical. Final executed test files are bound below and at integration preflight.',
 'tests_final':{str(p.relative_to(ROOT)):sha(p) for p in sorted(Path(__file__).parent.glob('test_*.py'))},
 'writer_note':'Initial small summaries were exclusive JSON writes; new/final summaries use maintenance/experiment_json.write_summary. Existing artifacts preserved.'}
put(ART/'verification-reconciliation.json',reconciliation)
result={'status':'TECHNICAL_PASS_WITH_PREEXISTING_FAILURES','first_phase_only':True,'candidate_files':525,'changed_files':41,'product_files':10,'pins':31,
 'candidate_revision':f['candidate_revision'],'new_checks':41,'related_existing_passed':159,'preexisting_failed':2,
 'candidate_total_passed':200,'working_native_passed':7,'working_checks_overlap_candidate':True,
 'check_artifacts':{name:bind(ART/name/'result.json') for name in names},'working_native':bind(ART/'working-native/result.json'),
 'offline_audit':bind(ART/'offline-wire-projection.json'),'integration':bind(ART/'working-integration.json'),
 'reconciliation':bind(ART/'verification-reconciliation.json'),'model_calls':0,'oracle_calls':0,'main_changed':False,'quality_certified':False,
 'limits':['Input sharing currently applies only to scenario ASSESS and ASSESS repair with minimal input enabled.',
 'Full unification of semantic review links and numeric prose validation is not implemented in this first phase.',
 'The 245만원 formatting and old/new comparison prose restrictions still require the planned typed-application redesign.',
 'No new Qwen run, causal quality comparison, Oracle E2E, GENOS or NFS validation.']}
put(ART/'verification.json',result)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 '계획의 1차 수정 기술 채택·작업 코드 반영. 검증한 rev003의 제품10+pin31=41파일만 통합했고 동결후보/작업525파일이 일치한다. MAIN132·Gold·운영데이터는 유지한다. 모델 품질/전체 계획 완료 인증이 아니다.',
 'ADR1281은 실제8호출·가정3중1만 최종통과했다. 기준 질문8회/원문6회 중복, 확정 condition_results 재작성, 긴 gap.reason의 요구검토 연결 실패가 관측됐다. 기존 reconcile_material_gaps는 reason을500자로 자르는 함수가 아니라, 검토표에 원문을 다시 복사하려다500자 초과면 복구를 포기하는 함수였다.',
 '[사전 기준](artifacts/design/criteria.json): 입력 원문·공백·Unicode·끝부분 예외의 정확 복원, 현재 사실/가정과 과거 이력 구분, 서버 조건값 보존, 모호성·외래근거 거절, gap의 미확인 상태 보존, API/저장/재조회 연결. 법률 의견 추론·삭제·요약·문자열 절단 금지.',
 '완료된 ADR1281을 역사 부모로 한 격리후보 rev001~003. 신규34계약+native7, 관련159회귀와 기존실패2 대조. 실제 provider 기록5개에는 표시 변환만 수행했다. 원래 실모델 응답을 새 모델의 결과로 취급하거나 재전송하지 않았다.',
 '합성 문서/모의 transport의 실제 native HTTP·SQLite 저장경로를 사용했다. 현재 최소입력v2는 사건 입력을 current_case로 모으고 동일한80자 이상 문자열만 전체본문 참조로 공유한다. 80자는 공유 여부 기준이며 본문 상한이 아니다. v1 기록 검증은 기존 표시 형식을 유지한다.',
 '최종 후보200통과·기존실패2(부모에서도동일), 그중 신규41통과. 작업 통합 후 native7 재검증통과이며 후보7과 중복이므로 합산하지 않는다. 600자 사유의 끝 예외까지 답변·저장·재조회 일치, 승인미확인은 UNRESOLVED 유지, 동일요청 추가모델0. 사전 wire 자료5개의 질문8→1회/원문6→1회, 모두 정확 복원.',
 '초기native1통과/6실패를 보존했다. 2건은 검사기가 최소출력 변환 이전 schema를 관찰했고, 4건은 복합조건 const의 내부/모델 ID 변환 누락이었다. 실제 데이터처럼 복합const의 식별자를 변환하도록 수정, 원문 인용은 유지했다. 기존 SQL로그 검사2실패는 부모16통과/2실패와 동일하다. 상세는 verification-reconciliation.json.',
 '새 실모델0·Oracle0·외부비용0. 역사 wire의 view UTF8 bytes: 29110→25542,37178→32705,29122→25554,29175→25607,37902→34334. 전체요청/토큰/속도 개선률이 아니며5개는 동일역사실험의 요청이다. 입력·근거 회수 정책 변화없음.',
 '서버 확정 조건표는 생성 schema에서 제외하고 같은분기·같은참조공간으로 복원한다. gap 사유는 원래 gaps에 그대로 남고 검토행은 gap_indices로 연결한다. 현재 이유/주장의 의미를 새로 생성하거나 승인·충족으로 바꾸지 않는다. 전검증과 원제안/hash는 유지한다.',
 '최소입력ON의 가정ASSESS/보완에 우선 적용. 모든 의미검토표의 단일 review_links 전환, 245만원 동치표기 및 변경전후 비교문장 판정개선, 반복문장 생성 자체의 개선은 미구현이다. Qwen 통과율 개선·중복과 실패 인과는 미검증이다. Oracle/GENOS/NFS·법률품질 미인증.',
 '사용자 수정 지시에 따라 검증한 변경파일만 작업 반영했다. MAIN132 선택포인터 불변, 제품승격/현장배포/DB·DDL/Git/메일0. 이전파일은 artifacts/working-before에 보존. 원복은 working-integration.json의 현재해시가 여전히 일치하는41파일에 한해 백업복원/신규1파일해제를 검토한다. 병행변경이나 이후산출물을 일괄덮어쓰지 않는다.',
 '.venv/bin/python 06_TOOLS/EXPERIMENTS/adr_1282/check.py --name <새경로> <검사파일>; 작업경로는 check_working.py. 정확한 실행묶음/해시는 verification.json과 검사별 result.json 참조. 완료된 이름으로 결과를 덮어쓰지 않고 실모델 호출은 포함하지 않는다.'
]
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Accepted',front)
p.write_text('---'+front+'---\n\n# ADR1282 무손실 입력·서버 조건값·gap 참조 수정\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 검증\n\n[범위와 한계](../README.md) · [검증결과](../artifacts/verification.json) · [실행계보](manifest.json)\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',artifact_path=str((ART/'verification.json').relative_to(ROOT)),sha256=sha(ART/'verification.json'))
m['results'].update(status='complete',by_arm={'baseline':{'historical_adr1281':True,'compact_passed':16,'compact_failed':2},'verified':result},
 judge_disagreements=0,usage={'model_calls':0,'oracle_calls':0},latency={n:checks[n]['seconds'] for n in names},
 error_taxonomy=[{'type':'PREEXISTING_COMPACT_SQL_ASSERTION','count':2},{'type':'COMPOUND_CONSTANT_NAMESPACE_REPAIRED','count':4},{'type':'WIRE_OBSERVER_BOUNDARY_REPAIRED','count':2}])
put(ADR/'실험/manifest.json',m)
p=ART/'manifest.json';am=read(p);am['files']=[dict(bind(x),bytes=x.stat().st_size,description='Frozen design, preserved failure, verification or reversible working integration',contains_raw_prompts_and_outputs=False) for x in sorted(ART.rglob('*')) if x.is_file() and x!=p and '/runtime/' not in str(x) and '/__pycache__/' not in str(x)]
p.write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
print('Final technical scope: 200 passed,2 unchanged baseline failures; working native7 passed; MAIN132 unchanged')
