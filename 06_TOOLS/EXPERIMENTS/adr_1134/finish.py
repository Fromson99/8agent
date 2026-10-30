from common import *
import ast,subprocess,datetime
f=read(ART/'freeze.json');C=ROOT/f['code_root'];old=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1133/scenario-r1/revisions/rev-001/snapshot'
prompt=lambda root:next(n.value.value for n in ast.parse((root/'02_BACKEND/semantic_runtime/legal_agent/ontology_scenarios.py').read_text()).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='PROMPT' for t in n.targets))
c=read(ART/'check-001.json');changed=[n for n,h in f['files'].items() if sha(C/n)!=h]
result={'status':'complete','contract_checks':{'passed':c['passed'],'failed':c['failed'],'seconds':c['seconds'],'prior_total':140,'added_case_count':17,'native_http_modes':['normal','multi','repair','conditional','reselect','no_match','still_insufficient','empty_catalog','twice_invalid']},'prompt':{'prior_chars':len(prompt(old)),'current_chars':len(prompt(C)),'unit':'Unicode characters, system instructions only, not total input tokens','prior_multi_selection':'여러 경로를 비교해야 하는 질문이면 필요한 복수 경로를 선택한다.','current_multi_selection':'질문에 필요한 사전 시나리오를 복수 선택할 수 있다.'},'new_model_calls':0,'new_evaluator_calls':0,'quality_certified':False,'decision_eligible':False,'live_route_accuracy':None,'selected_main_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256'],'changed_frozen_files':changed,'import_leaks':c['import_leaks'],'scope':'Synthetic contracts and real local HTTP with deterministic model transport; no external model or live real-corpus retrieval experiment.'}
assert c['status']==0 and not changed and not c['import_leaks'] and result['selected_main_unchanged']
put(ART/'run-001/result.json',result)
summary='복수 선택 안내를 짧게 바꾸고 충분성에 따른 재선택1회·기존 SELECT 복귀를 연결했다.157계약검사(모의 HTTP9모드 포함) 통과, 새 모델0회, MAIN107 불변. 실제 선택 정확도는 이번에 미측정.'
report='''온톨로지 선택·충분성·기존 탐색 복귀 — ADR1134

기존 프롬프트 확인
1133의 실제 CM023 입력에는 “여러 경로를 비교해야 하는 질문이면 필요한 복수 경로를 선택한다.”가 있었다. path_ids도 배열이어서 복수 선택이 가능했다. 다만 비교 질문으로 표현을 좁혔다. 일반 성립 질문에서2개를 반드시 고르라는 지시는 없었고, 기대2개는 평가 기준에만 있었다. 이전 실험의3/4와 실패 기록은 바꾸지 않는다.

이번 변경
1. “질문에 필요한 사전 시나리오를 복수 선택할 수 있다. 조건·계산·예외 등 필요한 범위를 함께 확인하고 무관한 경로는 고르지 않는다.”로 바꿨다. 특정 질문/경로ID/선택개수2를 강제하지 않는다.
2. 같은 선택 응답에서 충분성에 따라 next_action=ANSWER/RESELECT/SEARCH와 missing_scope를 받는다. 별도 평가 모델 호출을 추가하지 않았다. 일반 규정 설명과 사건 사실 부족(CONDITIONAL/missing_facts)은 구분한다.
3. 현재 경로를 더 검토할 필요가 있으면 이전 선택과 부족 범위를 전달해1회 재선택한다. 두 번째도 부족하거나 경로가 없으면 기존 탐색으로 넘어간다. 선택된 경로가 일부 있어도 남은 원문 부족은 숨기지 않는다.
4. 검색 복귀는 기존 ASSESS_GAP_REENTRY → SELECT를 사용한다. 기존 권한·원문·상태·gap·예산 검사를 그대로 거친다. 복귀 이후 같은 요청에서는 시나리오 선택을 반복하지 않고 일반 원문 조사/판단으로 진행한다. 새 질문에서는 기존 상태 수명에 따라 초기화된다.
5. 현재 원문에 결속된 경로가0개면 선택 모델을 호출하지 않고 기존 조사로 넘어간다. 온톨로지 설정/묶음 자체가 없을 때도 기존 경로가 유지된다. 사용자 사건 사실만 부족한 경우에는 법령 탐색으로 그 사실을 대신 만들지 않는다.
6. 정상 시나리오 답변은 저장된 본문을 그대로 발행한다. 탐색으로 복귀한 경우 추가 확보 원문에 대한 답변은 기존 RAG가 담당한다. 앞선 선택의 원문·부족·검토 기록은 보존한다.

오류·예산
선택 구조 오류는 기존 output.bounded_decision이1회 보완한다. 충분성 재선택은 별개의 의미 판단으로 최대1회다. 두 선택 라운드 각각의 구조 보완까지 합쳐 최대4물리호출이며 실제 요청 공통 예산·deadline을 사용한다. 재선택 전에 추가 조사/마무리 여유를 확인한다.
두 번 형식 실패하면 실패 출력을 채택하지 않고 원인과 미확정을 보존해 기존 조사로 돌아간다. 모델 전송 결과 불명·권한·원문해시 오류는 이 전환으로 덮지 않는다. 예산이 없으면 기존 제한 답변/중단 계약을 적용하며 완료를 꾸미지 않는다.

프롬프트 규모
선택용 system문자538→374. Unicode 문자수이며 전체 입력 토큰/서비스속도 개선율이 아니다. 원문 입력을 줄인 실험은 아니다.

검증
총157검사 통과(이전140개 대비17검사 사례 추가/확장),0실패·후보 외 import0·동결파일 변경0.
실제 로컬 HTTP 진입점을 모의 모델로9모드 검사: 정상, 복수 선택, 형식 보완, 사건 사실 부족, 재선택 성공, 경로 없음, 반복 부족, 결속된 경로0, 연속 형식 실패.
경로 없음/반복 부족/경로0/연속 형식 실패는 SELECT 복귀 후 FOLLOW_CONNECTION·READ_LINK로 실제 합성 원문을 추가 읽고 일반 ASSESS로 답변했다. 같은 요청 재호출은 답변과 호출수를 그대로 재사용했다.
단위 검사는 재선택의 이전 선택 전달, 두 번째 부족의 claim·gap 보존, 부분 쟁점의 기존 claim 유지, 모델/시간 여유 부족, 저널을 닫고 다시 열었을 때 중복 호출0, 알 수 없는 전송 결과의 무조건 재호출 차단을 확인했다.

범위와 남은 한계
새 실모델0·평가0. 실제 모델의 복수 선택 정확도/CM023 재실행 결과는 이번에 측정하지 않았다. 충분성 판단은 선택 모델이 같은 응답에서 수행한다. 모델이 부족을 놓치고 ANSWER라고 판단하는 오류까지 독립 검출하는 평가기는 아니다.
MAIN107 기반 격리 후보에서의 구현이다. 활성 MAIN107·GENOS·Dataiku/S3/Oracle 게시를 변경하지 않았다. 자동 시나리오 작성·승인/게시 및 입력량 최소화는 별도다.
ADR1134 최종 문서 검증 및 전체 계보 검사 결과는 completion-audit.json을 따른다. 전역 계보의 과거 오류를 이번 기능의 성공으로 계산하지 않는다.

주요 위치
02_BACKEND/lawrag/research/candidates/adr_1134/scenario-r1/revisions/rev-001/snapshot
06_TOOLS/EXPERIMENTS/adr_1134/test_sufficiency.py
06_TOOLS/EXPERIMENTS/adr_1134/test_scenario_native.py
artifacts/check-001.json / run-001/result.json / freeze.json
'''
(ART/'실험결과.txt').write_text(report)
m=read(ADR/'실험/manifest.json');m['results'].update(status='complete',by_arm={'baseline':{'status':'not_run','reason':'Historical1133 reference, not rerun'},'scenario':{'status':'complete','contract_passed':157,'contract_failed':0,'quality_certified':False,'decision_eligible':False}},comparisons=[{'paired_quality_comparison':False,'reason':'Synthetic implementation contracts only'}],usage={'new_model_calls':0,'new_evaluator_calls':0},latency={'contract_check_seconds':c['seconds'],'service_latency_measured':False},error_taxonomy=[]);m['runs'][0].update(status='complete',sha256=sha(ART/'run-001/result.json'));put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
sections=[summary,'1133은 복수 선택을 비교 질문으로 안내했고 NO_MATCH를 제한 답변으로 끝냈다. 충분성 재선택 및 기존 탐색 복귀가 빠져 있었다.','[사전 기준·실패 계약](artifacts/criteria.json). 짧은 안내·복수 선택·재선택1회·SELECT복귀·최종 원문/본문·요청/예산 보존을 요구했다.','부모1133/scenario 완료 arm.662파일 격리 후보; history baseline 미실행. 합성 계약검사와 모의 모델 실제HTTP9모드. 실모델 질문 실험 없음.','[동결](artifacts/freeze.json), [부모 결속](artifacts/parent-binding.json). 기존 합성 원문·상태·모델전송 fixture와 추가 실패 주입. 신규 외부 호출0.','157통과/0실패·후보 외 import0. 새로 추가/확장된 사례17개. [검사](artifacts/check-001.json) · [정리](artifacts/실험결과.txt).','복수 선택·재선택 성공·NO_MATCH/반복부족/빈목록/형식실패의 실제 조사 복귀를 확인했다. 전송 결과 불명은 자동 재실행하지 않는다. 현재 미통과 검사0.','새 모델/평가0. system538→374문자. 검사34.806초는 서비스 응답시간이 아니다. 합성 상태/원문 fixture이므로 실제 corpus 회수/정답률·토큰 효과 미측정.','프롬프트를 늘리지 않고 모델의 선택+충분성 판단과 기존 조사 복귀를 결합했다. 형식 수정, 의미 재선택, 추가 원문 조사의 담당과 한도를 구분했다.','실제 모델의 충분성 판단 정확도 미측정. ANSWER로 잘못 판단한 누락을 독립 판정하는 평가기는 아니다. 사전 조립과 저장 승인·전체 입력량은1133범위 그대로.','Proposed/decision_eligible=false: 기술 구현검사 완료, 운영 MAIN107/GENOS/데이터 게시 미반영. 후속 품질·MAIN 검증은 별도ADR. 과거1133 결과 불변.','`06_TOOLS/EXPERIMENTS/adr_1134/check.py`는 동결 후보를 명시적으로 import한다. 완료 check-001을 덮어쓰지 않는다. [산출물 색인](artifacts/manifest.json) · [실험 manifest](실험/manifest.json).']
head=(ADR/'README.md').read_text().split('---',2)[1];(ADR/'README.md').write_text('---'+head+'---\n\n# 온톨로지 충분성·재선택·기존 탐색 복귀\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{s}' for i,(h,s) in enumerate(zip(heads,sections),1))+'\n')
(ADR/'실험/README.md').write_text('# 합성 계약·HTTP 연결검사\n\n'+summary+'\n\n실제 법률 질문별 모델 실험이 아니므로 질문 파일은 없다. [157검사 상세](../artifacts/check-001.json) · [실행 결과](../artifacts/run-001/result.json).\n')
idx=ROOT/'04_EXPERIMENTS/ADR/README.md';s=idx.read_text();line='- [ADR1134 온톨로지 충분성·재선택·기존 탐색 복귀](ADR-1134-scenario-sufficiency-search-return/README.md) — 157계약검사/모의HTTP9모드 통과, 새 모델0·MAIN107 불변.\n'
if 'ADR1134 온톨로지 충분성' not in s:idx.write_text(s.replace('# ADR workspace\n','# ADR workspace\n\n'+line,1))
for args in [('hash','--path',str(ADR)),('status','--path',str(ADR),'--status','completed','--note',summary)]:
 r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),'adr_structure.py',*args],capture_output=True,text=True);(ART/f'{args[0]}-final.txt').write_text(r.stdout+r.stderr);print(args[0],r.returncode)
a=read(ART/'manifest.json');a['files']=[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen implementation or synthetic contract evidence; no external model calls','contains_raw_prompts_and_outputs':False} for p in sorted(set([p for p in ART.rglob('*') if p.is_file() and p.name!='manifest.json']+list(Path(__file__).parent.glob('*.py'))))];put(ART/'manifest.json',a)
r=subprocess.run([str(ROOT/'.venv/bin/python'),str(ROOT/'06_TOOLS/run_tool.py'),'adr_structure.py','validate','--path',str(ADR),'--final'],capture_output=True,text=True);(ART/'validate-final.txt').write_text(r.stdout+r.stderr);print('validate',r.returncode,r.stdout+r.stderr)
