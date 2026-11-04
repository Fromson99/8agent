from common import *
import re
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-target-connection-review'
matrix=read(ART/'accepted-test-matrix.json');integration=read(ART/'working-integration.json')
f=read(DES/'candidate-checked.json');baseline=read(DES/'baseline.json')
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']
assert all(sha(selected()/n)==h for n,h in baseline['release']['files'].items())
assert read(ART/'working-api/result.json')['failed']==0
summary={'status':'WORKING_FIXED_LIVE_PENDING','checklist_contracts':{'C1':True,'C2_wire':True,'C3':True,'C4':True,'C5':True,'C6_integration':True,'C6_live':False},
 'new_tests_passed':19,'unique_passed':matrix['passed'],'existing_failures_reproduced_before_patch':4,
 'product_files':5,'native_metadata_files':1,'pin_files':31,'changed_files':37,'same_candidate_working_files':528,
 'engine_preflight':integration['engine_preflight'],'sql':read(DES/'native-plan-equivalence.json'),
 'actual_mock_api':{'explanation_repair':2,'pager_regression':2,'working_recheck':2,'duplicate_extra_calls':0},
 'source_scope_behavior':'Only proposed answer basis with uninspected connection spans disables fast FINISH. Existing bounded supervisor decides investigation/limited handoff. This does not force all links or certify semantic completeness.',
 'new_live_model_calls':0,'selected_main':142,'selected_main_unchanged':True,'genos_oracle_tested':False,'quality_certified':False,
 'failed_fixture_preparations_preserved':['initial scope fixture missing new claim source-target linkage and ambiguous fixture import','nonexistent test path','test module-name collision','API expected canonical C99 but actual provider used bound C3 alias'],
 'frozen_product_revision_unchanged_after_tests':True}
put(RUN/'result.json',summary);put(OUT/'검증요약.json',summary)
notes=[
 '질문 대상 원문의 연결 확인을 건너뛰던 빠른 종료와 설명 주장 보완·미검증 판단 표시를 수정했다. 제품5+native metadata1+pin31=37파일 작업 반영, 후보/작업528 SHA동일. 선택 MAIN142는 그대로다.',
 'C1: connection_scope가 실제 선택 범위와 현재 원문 span을 대조해 source_inspections를 전달한다. 다른 원문의 조회나 좁은 구간의 조회가 해당 답변 근거 전체의 확인을 대신하지 않는다. investigation_supervisor.ready_for_assessment는 미확인 답변 근거가 있으면 빠른 FINISH를 허용하지 않고 기존 감독 검토를 실행한다. 조회불가/예산소진은 기존 bounded handoff를 유지한다. 모든 연결을 강제 조사하거나 서버가 특별규정의 존재·부재를 판단하지 않는다.',
 'C2: 질문 대상의 수치 부재만으로 일반규정 적용을 확정하지 않고 다른 정함·예외·특칙·INCOMING을 확인하는 공통 지침을 선택/감독/최종 실제 wire에 연결했다. 특정 조문번호·정답은 제품에 넣지 않았다. 지침 전달은 법률 정답 성공을 의미하지 않는다.',
 'C3/C4: 설명 주장별 인용·채택 근거와 관련 판단행을 정확히 보완 입력에 제공한다. 실제1341 C3 오류2개를 그대로 진단하며, 재개에도 같은 피드백을 복원한다. 자동 채택/주장 변경0, 검증기·원문/ACL·예산·UNKNOWN·기존1회보완 유지. 모의 API 보완성공 COVERED, 동일오류반복 INSUFFICIENT/원문전용, 중복 요청 추가호출0을 확인했다.',
 'C5: 최종 검토가 실패한 잠정 판단·충돌의 법률 결론을 공개 제한사항에 그대로 넣지 않는다. 내부 receipt의 원문 판단과 실패 이력은 유지하고 공개에는 검토 항목·미완료 상태를 표시한다. 검증된 최종 미확인 이유와 원문·후속 재검토 안내는 유지한다.',
 f"신규19통과, 관련 고유{matrix['passed']}통과/기존4실패. 기존3개 preview 대역이 preparation 인수를 받지 못하는 오류와 이미1337에서 변경된 미완독 FINISH 기대1개는 수정 전1341 코드에서도 동일 재현했다. 작업 API2개는 중복 재확인으로 고유 수에 더하지 않았다. 기존 페이지 반복 API2도 통과했다.",
 '최초 신규1개 실패와 API2개 실패, 경로/수집 준비2회 실패를 보존했다. fixture의 SOURCE_GOAL 검토 연결·정확한 fixture import·provider 주장 별칭 대조를 수정했으며 제품rev001은 바꾸지 않았다. 성공/실패 runtime은 전체파일SHA 검증 후 무손실 압축 보존했다.',
 '639 native SQL 실행문/list/계획은 동일, completion_execution 소스해시 metadata1개만 변경. engine30/500 확인. 통합 전 작업528 SHA가 기준과 같은지 확인한 뒤 변경37파일만 반영했다. 원복은 artifacts/working-before 및 integration-preflight의 before/after를 대조한다.',
 '실제 모델 검증은 후속 별도 동결에서 수행한다. 이번 기술검사만으로 정관 질문 정답률·반복 안정성·Oracle/GENOS 현장 효과를 인증하지 않는다. MAIN/원문DB/현장/메일 변경0.'
]
(OUT/'수정과_검증결과.txt').write_text('\n\n'.join(notes)+'\n')
p=OUT/'수정_체크리스트.txt';text=p.read_text()
for key in ('C1','C2','C3','C4','C5'):text=text.replace('[ ] '+key,'[x] '+key)
text=text.replace('[ ] C6 통합·실제 확인','[진행] C6 통합·실제 확인')
text+='\n기술 검증 결과: 신규19통과, 관련 고유'+str(matrix['passed'])+'통과/수정전동일4실패. 작업 API2 재확인. 후보/작업528동일, SQL639실행동일, engine30/500. C2는 입력 전달 통과이며 의미적 실효는 후속 실모델로 확인한다.\n'
p.write_text(text)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'prior_failures':4},'checked':summary},comparisons=[],judge_disagreements=0,usage={'physical_live_calls':0},latency={'not_measured':'Contract validation only'},error_taxonomy=[])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
values=[notes[0],notes[1],json.dumps(read(DES/'criteria.json'),ensure_ascii=False),notes[2],notes[7],json.dumps(summary,ensure_ascii=False),notes[5]+'\n'+notes[6],'모델0·SQL실행변경0·지연 개선 미측정',notes[3]+'\n'+notes[4],notes[8],notes[7],'setup.py → candidate수정 → freeze.py → check.py → integrate.py → working-api → archive_contracts.py → finish.py → adr_structure hash/status/validate --final/graph']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 질문 대상 연결과 종료·최종 검토 수정\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,values),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
    case=next(c for c in read(DES/'cases.json') if c['id']==q['case_id'])
    vals=['run-001/checked/rev001',json.dumps(case,ensure_ascii=False),'의미 정답 비교 없음. 실제1341 실패는 재현용이며 정답 주입 없음.','### 회수·탈락 단계 원장 — run·arm별\n\nControl/diagnostic projection only. Retrieval not_applicable. test_completion_review.py/test_completion_api.py와 runtime archives에 실제 입력/출력 보존.','새모델0. scripted mock API 원시 요청·응답은 무손실runtime 저널.', '같은 실제 제품 경로와 engine pin; 최초/보완/중복 검증.', 'accepted-test-matrix.json 및 개별 result.json. 기존4실패는 parent-control에서 재현.',json.dumps(summary,ensure_ascii=False)]
    (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qh,vals),1))+'\n')
(ADR/'실험/README.md').write_text('# 체크리스트 검사\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
put(ART/'final-test-source-hashes.json',{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')})
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]+list(Path(__file__).parent.glob('*.py'))+[p for p in OUT.glob('*') if p.is_file()]
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1342','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Checklist, frozen candidate, original failures, contracts, exact integration and lossless runtimes','contains_raw_prompts_and_outputs':p.name.endswith('.tar.gz')} for p in sorted(paths)]})
print(json.dumps(summary,ensure_ascii=False))
