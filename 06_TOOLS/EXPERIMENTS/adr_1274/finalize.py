from common import *
import re
full=read(ART/'full-recovery-001/result.json');extra=read(ART/'followup-display-002/result.json');new=read(ART/'contracts-005/result.json')
assert full['passed']==637 and full['failed']==4 and full['code_unchanged']
assert extra['failed']==0 and extra['exit_code']==0 and extra['code_unchanged']
assert new['passed']==17 and new['failed']==0
failed=[r['test'].split('::',1)[1] for r in full['rows'] if r['outcome']=='failed']
assert all(any(r['test'].endswith('::'+n) and r['outcome']=='passed' for r in extra['rows']) for n in failed),failed
f=read(DES/'freeze.json');C=ROOT/f['code_root'];assert all(sha(C/n)==h for n,h in f['files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256']
before=read(DES/'working-before.json');delta=[n for n,h in f['files'].items() if h!=before[n]]
put(ART/'verification-reconciliation.json',{'first_full':bind(ART/'full-recovery-001/result.json'),'initial_passed':637,'initial_failed':failed,
 'cause':'Fixture selected the first journal by filesystem order after duplicate re-entry, sometimes the fresh empty journal. Actual response.run_id journals retain all expected original judgments. Corrected exact run binding; product bytes unchanged.',
 'rerun':bind(ART/'followup-display-002/result.json'),'all_four_now_passed':True,'rev002_change':'Only timeout marker display plus exact engine pins; semantic recovery modules unchanged from full641 run; full current display/followup104 rerun','full_contracts_verified_across_runs':641,
 'harness_failures_001_004':'New test fixture corrected response field, request routing, command-check and updated-current-context assertions; candidate unchanged; all original failures preserved.',
 'tests_final':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__).parent/'test_recovery.py',ROOT/'05_TESTS/CONTRACTS/need_continuity_fixture.py']}})
result={'status':'PASS','full_recovery_contracts':641,'new_contracts':17,'followup_display_checks':extra['passed'],'counts_overlap':True,
 'baseline_full_passed':637,'baseline_full_failed_then_resolved':4,'final_revision':'rev-002','candidate_files':len(f['files']),'changed_files':delta,
 'model_calls':0,'oracle_calls':0,'main_changed':False,'quality_certified':False,
 'structural_binding_extra_model_calls':0,'simulated_followup_model_calls':4,'simulated_followup_research_calls':0,'same_request_repost_calls':0,
 'candidate':bind(DES/'freeze.json'),'reconciliation':bind(ART/'verification-reconciliation.json'),
 'limitations':['Actual Qwen is separate ADR1275; Oracle/GENOS/NFS not executed','Source-only incomplete output is not an accepted legal conclusion','Provider UNKNOWN remains a controlled terminal error without replay','Semantic routing and command checks still use separate model calls']}
put(RUN/'result.json',result)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[
 '기술 후보 채택. 제품5파일과 pin31을 수정한518파일 후보 rev-002에서 복구·멀티턴 계약을 확인했다. 이 감사 시점 MAIN131은 유지하며 별도1276에서 명시 사용자 MAIN 반영을 수행한다.',
 'ADR1269의 실제 실패는 C1·해당 원문·USE 검토가 이미 명시됐지만 필요 항목의 target_refs만 빠져 NEED_TARGET_CLAIM_LINK가 반복된 사례다. 일반 최종 검토 실패도 제한된 보완 뒤 422로 끝나 사용자가 후속 대화를 이어가기 어려웠다.',
 '[사전 기준](artifacts/design/criteria.json): 유일한 명시 연결만 결속, 전 검증 재수행, 불명확·외래·제외·미확보·미검토 원문 거절, 실패 결론 미채택, 동일 요청 재전송0, 사실 보완의 동일 사건 유지.',
 '동결한 역사 실패와 변조14종·모호성·네이티브2턴 신규17검사. 기존 전체641회귀와 후속 대화·화면검사를 수행했다. 답변 품질을 맞추는 조문별 예외 또는 추가 모델 재시도는 없다.',
 '작업/선택MAIN131을 보존한 후보 rev-002. 역사 Qwen 출력은 재전송 없이 읽었다. 합성 원문과 모의 모델로 API 흐름을 검증했고 외부 모델·Oracle0. 스키마·ACL·hash·CAS·40/1024/1800 예산은 유지한다.',
 f'기존641항목 확인(최초637통과·검사기4실패, 정확 실행ID로 수정 후 해당4통과), 신규17통과, 후속/화면 묶음{extra["passed"]}통과. 묶음 사이 중복이 있어 독립 표본으로 합산하지 않는다. 원문만 응답→사실 보완→동일 사건 판단, 두 요청 각각 재조회0호출을 확인했다.',
 '최초 신규 검사001~004의 fixture 준비 차이와 전체검사의 잘못된 journal 선택4건을 원본 보존했다. rev-001 추가 화면 검사에서 timeout 표식 누락6건과 새 안내 시작문 기대 차이2건을 발견했다. rev-002는 안내에 오류 표식을 보존했고 기존 안내 시작문 기대2건도 새 안내 계약으로 고쳤다. 범위 검사3건은 MAIN131에서도 동일 실패였으며 필수 body 좌표를 fixture에 채웠다. 검토 실패 제안은 REJECTED로 남으며 원문 응답은 INCOMPLETE·claims=[]·LIMITED_ANSWER로 구분한다.',
 f'외부 비용0. 전체검사{full["elapsed_seconds"]:.3f}초, 추가검사{extra["seconds"]:.3f}초. 과거 정확 구조 오류는 모델 추가0회로 정합 결속. 모의 첫턴9회·후속4회, 후속 원문 재검색0. 실제 속도·비용 절감률 아님.',
 '확정 가능한 구조를 코드로 연결해 불필요한 모델 보완을 피한다. 불완전 판단을 받아들이는 대신 검증 원문과 남은 상태를 전달한다. 사용자 사실 부족과 내부 검토 실패를 혼동하지 않는다.',
 '실제 Qwen 두 턴은 별도1275. 공급자 UNKNOWN/504 내부 원인은 해결되지 않았다. 현장GENOS·Oracle·NFS·법률품질 미검증. 후속 분류/명령작성/검증의 세 모델 경계는 여전히 남는다.',
 '현재 후보만 기술 채택. MAIN 반영은 별도1276에서 정확 후보만 선택한다. 기존 MAIN131과 layout4 읽기·기록을 보존하며 원복 시 Gold binding도 함께 복원한다.',
 'check.py --name <새경로>, maintenance/check_agent_loop_recovery.py --code-root <동결후보> --output <새경로>. 완료 결과를 덮어쓰지 않는다. 실제 모델 실험을 이 명령으로 재실행하지 않는다.'
]
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'historical_failure':True},'repaired':result},judge_disagreements=0,usage={'model_calls':0,'oracle_calls':0},latency={'full_seconds':full['elapsed_seconds'],'extra_seconds':extra['seconds']},error_taxonomy=[{'type':'HARNESS_SELECTION_CORRECTED','count':4}]);put(ADR/'실험/manifest.json',m)
p=ADR/'README.md';front=p.read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Accepted',front)
p.write_text('---'+front+'---\n\n# ADR1274 최종 검토 복구와 멀티턴\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 기술 검사\n\n[결과와 한계](../README.md) · [실행 manifest](manifest.json) · [산출물](../artifacts/manifest.json)\n')
p=ART/'manifest.json';am=read(p);files=[x for x in ART.rglob('*') if x.is_file() and x!=p and '/runtime/' not in str(x) and '/__pycache__/' not in str(x)]
am['files']=[dict(bind(x),bytes=x.stat().st_size,description='Preserved frozen design and contract audit',contains_raw_prompts_and_outputs=False) for x in sorted(files)];p.write_text(json.dumps(am,ensure_ascii=False,indent=2)+'\n')
print('Technical PASS',result['full_recovery_contracts'],result['new_contracts'],result['followup_display_checks'])
