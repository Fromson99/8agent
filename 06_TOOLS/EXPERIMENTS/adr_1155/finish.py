from pathlib import Path
import json,hashlib,xml.etree.ElementTree as ET,difflib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1155-investigation-focus-offline';D=A/'artifacts/design';ART=A/'artifacts';T=Path(__file__).parent
read=lambda p:json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def bind(p):return {'path':str(p.relative_to(R)),'sha256':sha(p)}
f=read(D/'freeze.json');base=read(D/'baseline.json');S=R/f['code_root'];C=R/'02_BACKEND/lawrag/research/candidates/adr_1155/focused-r1';c=read(C/'candidate.json');rev=c['revisions'][-1]
assert sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
assert all(sha(S/n)==h for n,h in f['files'].items())
assert all(sha(R/n)==h for n,h in read(D/'source-worktree.json').items())
def tests(n):
 return {x.get('classname')+'::'+x.get('name'):('failed' if x.find('failure') is not None else 'error' if x.find('error') is not None else 'skipped' if x.find('skipped') is not None else 'passed') for x in ET.parse(ART/n).iter('testcase')}
u=tests('unit-rev002.xml');conn=tests('connection.xml');bc=tests('connection-baseline-qualified.xml');native=tests('native-offline.xml');new=tests('focus-final.xml')
assert conn==bc
assert set(native.values())=={'passed'} and len(native)==6
assert set(new.values())=={'passed'} and len(new)==8
failed=[k for k,v in u.items() if v!='passed'];assert len(failed)==1 and 'test_pages_partition_and_bind_schema[0]' in failed[0]
replay=read(ART/'run-001/replay.json');assert replay['view_count']==69
changed={n:h for n,h in f['files'].items() if (n in base['release']['files'] and base['release']['files'][n]!=h) or n.endswith('/investigation_focus.py')}
products=[n for n in changed if not n.startswith('02_BACKEND/ENGINES/') and n!='00_SYSTEM/PIPELINE.json']
assert len(products)==8
patch=''
for n in products:
 before=(R/base['release']['code_root']/n).read_text() if n in base['release']['files'] else ''
 patch+=''.join(difflib.unified_diff(before.splitlines(True),(S/n).read_text().splitlines(True),fromfile='a/'+n,tofile='b/'+n))
(ART/'MAIN110_조사수정_검토용.patch').write_text(patch)
checks={k:True for k in ['main110_exact_baseline','working_tree_product_unchanged','active_pointer_unchanged','frozen_candidate_exact','observed69_input_sources_questions_judgments_preserved','all_recorded_targets_reachable_across_pages','hidden_tool_targets_rejected','query_scope_and_resume_retention','exact_preview_substrings','goal_observation_no_automatic_handoff','missing_goal_observation_does_not_block_independent_read','existing_connection_failures_identical','native_synthetic_api6_pass','new_focus8_pass','external_model_calls_zero']}
result={'status':'complete','scope':'offline technical implementation validation; not MAIN promotion or legal-quality certification','checks':checks,'new_model_calls':0,'model_choice_improvement_verified':False,'quality_certified':False,'candidate_revision':rev['revision_id'],'changed_product_or_profile_files':products,'dependent_pin_changes':len(changed)-len(products),'new_focus_tests':8,'native_synthetic_api_tests':6,'existing_unit_group':{'passed':sum(v=='passed' for v in u.values()),'changed_display_expectation':failed,'replacement_contract':'focus-final.xml test_empty_read_menu_rejects_fabricated_target; no selectable READ removed'},'connection_regression':{'passed':17,'same_baseline_failures_or_errors':10,'new_failures':0},'saved_views':69,'replay':bind(ART/'run-001/replay.json'),'tests':{n:bind(ART/n) for n in ['unit.xml','unit-rev002.xml','focus-final.xml','connection.xml','connection-baseline-qualified.xml','native-offline.xml']},'limits':['No actual model choices after change','No legal answers evaluated','Stored views cover original visible rows, not unobserved hidden retrieval results','Menu paging may still use extra calls; no total call reduction claimed','New semantic progress is requested in the existing call; omission remains unassessed, not a blocker','Active MAIN110 and working product files unchanged; isolated reviewable implementation'], 'preserved_failures':['Initial pytest imported working code instead of snapshot; collection failed before tests','First 61 unit checks did not cover new profile setting; added its explicit validation before saved-view audit in rev002','Baseline serving-only tree lacked test builder modules; rerun with exact qualified665 tree','Native test collection missing conftest path; corrected runner','Sandbox TestClient stalled; owned process terminated; rerun with INET network blocked outside sandbox;6passed']}
put(ART/'run-001/result.json',result)
# The criteria file predates implementation; metadata references that unchanged record.
m=read(A/'실험/manifest.json');m['design'].update(primary_metric='Deterministic preservation and availability contracts in artifacts/design/criteria.json',failure_criteria='Changed evidence/ACL/binding; lost selectable targets; forced semantic handoff; new functional regression; any external model call',criteria_frozen_before_run=True)
m['design']['criteria_record']=bind(D/'criteria.json')
m['design']['arms'][0].update(changes='Exact MAIN110 selected implementation and recorded MAIN109 views as fixed observational fixtures',controls='No baseline product edits or new model calls')
m['design']['arms'][1]['controls']='MAIN110 unchanged modules, data, provider/model, budgets, strict evidence and ACL; observations and synthetic responses only'
m['design']['code_isolation'].update(mode='candidate_snapshot',reason='Explicit frozen research import only; no production registration',candidates=[{'candidate_id':C.name,'experiment_id':m['experiment_id'],'arm_id':'focused','run_ids':['run-001'],'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':str((T/'replay.py').relative_to(R)),'runner_sha256':sha(T/'replay.py')}])
m['dataset'].update(name='Known saved CM007/009 input fixtures and deterministic synthetic contracts',version='main110-focus-offline-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=False,reference_version_checked=False)
reason='No new corpus retrieval or model selection is executed. Audit reconstructs69 existing delivered views and verifies all same read/tool targets across pages, plus synthetic continuity fixtures. No corpus recall/selectivity claim; future live retrieval evaluation requires a new measured ledger.'
m['retrieval_accounting'].update(changed=False,not_applicable_reason=reason);m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
m['runs'][0].update(selection_rule='All69 saved navigation views from preselected CM007/009; no adaptive model calls; synthetic contracts defined in criteria record',status='complete',artifact_path=str((ART/'run-001/result.json').relative_to(R)),sha256=sha(ART/'run-001/result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','implementation':'Exact MAIN110; 10 legacy connection failures retained'},'focused':{'status':'complete','saved_views':69,'new_focus_tests':8,'synthetic_api_tests':6,'quality_certified':False}},comparisons=[{'kind':'offline_contracts','new_connection_regressions':0,'legacy_empty_read_schema_expectation_changed':1,'observed_wire_identity':True}],judge_disagreements=0,usage={'new_model_calls':0},latency={'performance_claim':False},error_taxonomy=[{'type':'legacy_fixture_contract','count':10},{'type':'empty_read_display_expectation','count':1}],main_wiring='unchanged',quality_certified=False)
put(A/'실험/manifest.json',m)
meta=(A/'README.md').read_text().split('---',2)[1]
sections=[('결정 요약','MAIN110 기반 격리 후보에 제품/프로필8파일과 종속pin31개 수정. 새 모델0회. 저장69입력, 신규8검사, 모의API6검사 통과. 상태Proposed, 인샘플, MAIN불변.'),('문제와 변경 전 구조','CM009 첫 후보8번 핵심 제13조를 지나친 후 제2조 연결을 탐색했다. CM007은28호출째 핵심 원문을 읽었으나 후속 목적 갱신과 최종 근거 연결에 실패했다. 원문 확보 진도와 질문 해결 진도가 분리되지 않은 입력 문제다.'),('가설과 사전 판정 기준','수정 전 criteria.json에 후보 유지·원문/권한/판단 보존·재개·페이지 허용대상·모델0회 조건을 고정했다. 실제 모델 행동 개선은 판정 대상이 아니다.'),('실험 설계','완료1154 integrated를 부모로 사용.1151은 중단된 관측 자료의 관계만 연결했다. rev001은61단위검사 후 프로필검증 누락을 코드 검토에서 발견했고 rev002에 설정 검증·관측 누락시 독립읽기 보존을 추가했다. 두 revision과 모든 실패를 보존한다.'),('데이터·모델·재현성','정답을 입력하지 않는다. 기존69개 전달 입력을 exact 재구성한 뒤 페이지 투영한다. 새 의미 판단·평가 모델 호출은0. 원문 전체와 원시 로그는1151 원경로에 보존한다.'),('결과','저장69입력의 질문·본문·판단과 모든 읽기/도구/연결 범위를 보존했다. 신규8검사·모의API6검사 통과. 관련 기존 단위113통과, 빈READ 표시 기대1차이는 신규 부정검사로 대체 확인. 연결17통과·10기존실패는 MAIN110과 동일.'),('사례별 오류 분석','7번/9번의 입력 첫 페이지 도구476→61,624→67. 실제 필요 조항 선택이나 정답 개선은 미확인. 목표 관측 미제출은UNASSESSED이며 임의로 충분성을 채우거나 독립원문 읽기를 막지 않는다.'),('비용·지연·회수 규모','외부호출0. 마지막 입력 문자204358→131532,266710→167706. 저장입력의 메뉴 투영만 비교했으며 전체 요청 시간·총 호출 감소·법률 회수율로 확대하지 않는다. 원문/판단 본문은 보존해 입력이 여전히 크다.'),('해석','검색 후보를 현재 권한·검색 바인딩으로 재제공하고 연결 후보와 섞어 유지한다. 적중 원문3개와 위치를 전달하며 현재 조항 전체로 오해하지 않게 한다. 기존 목표 검토를 관측 모드로 연결하고 자동종료하지 않는다. 큰 도구군을 페이지화하며 모든 대상을 유지한다.'),('한계와 일반화 가능 범위','질문에 맞는 후보를 실제 모델이 선택하는지, 목표 검토를 제출하는지, 호출이 줄어드는지는 추가 실모델 없이는 미인증이다. 최종 판단-주장 연결의 의미 오류 해결을 보장하지 않는다. 전체통합 MAIN승격 근거가 아닌 알려진실패 입력의 오프라인 검증이다.'),('운영 결정·롤백 조건','작업 제품 파일·선택 MAIN110·GENOS는 변경하지 않았다. 검토용 patch와 frozen snapshot을 보존한다. 다음 검증에서 권한·원문·상태·현재기능 회귀가 나오면 후보를 채택하지 않는다.'),('재현 명령','setup.py → edit.py/page_edit.py 및 보존된 rev002 → freeze.py. replay.py는 network block과 frozen hash 검사. pytest -o pythonpath=<rev002>/02_BACKEND test_focus.py. native_check.py는180초·INET차단 모의API. result.json이 모든 결과를 연결한다.')]
(A/'README.md').write_text('---'+meta+'---\n\n# MAIN110 조사 입력·탐색 연속성 수정\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(A/'실험/README.md').write_text('# 저장 입력과 합성 검증\n\n모델 호출0. CM007/009의 알려진 입력69개를 투영한다. 실제 새 답변은 만들지 않았다.\n\n'+ '\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
case_data=read(R/'04_EXPERIMENTS/ADR/ADR-1151-main109-cm51-qwen/artifacts/design/cases.json')
for q in m['questions']:
 case=next(x for x in case_data if x['id']==q['case_id']);question=case['request']['json']['question'];original=R/'04_EXPERIMENTS/ADR/ADR-1151-main109-cm51-qwen/artifacts/run-001'/q['case_id']
 text=f'''# {q['case_id']} — 저장 입력 검증

## 실행 메타
run-001 / baseline 및 focused. 관찰 원본은 ADR1151 MAIN109의 exact payload, 수정 코드 기준은 MAIN110. 새 제품/평가 모델 호출0.

## 사용자 질문
{question}

## 기준답변 — 제품 입력 비공개
이번 검증에서는 정답 채점하지 않음. 원본 evaluation-only/cases.json을 제품에 넣지 않음.

## 제품 입력 원값
{original.relative_to(R)}/canonical 및 wire를 그대로 읽는다. 해시는 artifacts/run-001/replay.json에 있다. 원문·입력·스키마·원응답은 원본 보관 경로를 정본으로 사용하며 복제하지 않는다.

## 모델 호출·중간 호출·채점
새 호출 없음. 실제 응답이 달라졌다고 가정하지 않는다. 새 페이지 메뉴에 과거 응답을 억지로 적용하지 않는다.

## 비교·판정
모든 원래 읽기/도구/연결 범위가 페이지에서 접근 가능하며 질문·전달원문·판단은 불변. 최초 페이지 크기만 변경된다. source retention 및 preview는 별도 합성 계약으로 검사한다. 골든 회수율이나 법률 정답률 없음.

## 비용·한계
추가 모델0회. 저장 입력69개 전체 결과와 모의API6결과는 result.json에 연결. 실제 모델 선택·목표 갱신·총 호출 감소는 미확인.
'''
 (A/'실험'/q['file']).write_text(text)
put(ART/'runner-and-test-hashes.json',{str(p.relative_to(R)):sha(p) for p in T.glob('*.py')})
# Explicitly preserve all preliminary failures, rather than reporting an all-green suite.
put(ART/'preliminary-failures.json',result['preserved_failures'])
summary='''MAIN110 기반 조사 방향 수정 — 2026-10-28

격리 수정본 구현 및 오프라인 검증. 새 모델 호출0, 활성 MAIN110·작업 제품 파일·GENOS 변경0.
변경: 최초 검색 미열람 후보를 동일 요청·검색·권한 범위에서 유지; 현재 연결 후보와 번갈아 제시. 검색 적중 최대3개를 원문 부분/위치와 함께 표시. 답변 진전 관측을 같은 조사 응답에 연결(강제종료 없음·미제출은미확인). 도구/연결 목록 페이지와 허용 schema를 함께 제한.

검증: 저장 실제 입력69개 전부 원문·질문·판단 보존 및 모든 기존 선택 대상 도달 가능. 신규8개·모의API6개 통과. 관련 기존113개 통과, 빈 READ의 이전 표시 기대1건은 별도 부정검사로 새 계약 확인. 연결 검사는17통과·10기존실패가 MAIN110과 동일.
7번 마지막 입력204358→131532자, 도구476→61. 9번266710→167706자, 도구624→67. 한 화면 비교이고 전체 호출 감소가 아니다.

아직 확인하지 않은 것: 새 모델의 실제 조항 선택·목표 검토 제출·호출 감소·최종 법률 답변 품질. 과거 응답을 새 행동처럼 만들지 않았다. MAIN 승격 및 작업 코드 반영은 하지 않았다. 검토용 patch와 rev002가 결과물이다.
'''
(ART/'수정과_검증결과.txt').write_text(summary)
print('Result recorded; isolated product/profile8 + pins31; newmodel0')
