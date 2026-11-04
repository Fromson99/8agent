from common import *
import re
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-ontology-repair'
matrix=read(ART/'accepted-test-matrix.json');integration=read(ART/'working-integration.json')
f=read(DES/'candidate-repaired.json');baseline=read(DES/'baseline.json')
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']
assert all(sha(selected()/n)==h for n,h in baseline['release']['files'].items())
assert read(ART/'working-api/result.json')['passed']==3 and read(ART/'working-api/result.json')['failed']==0
summary={'status':'WORKING_FIXED_QWEN_PENDING','new_tests_passed':23,'unique_passed':matrix['passed'],
 'existing_fixture_failures_reproduced_before_patch':2,'actual_mock_api':{'ontology_delivery_revocation_replay':3,'final_assessment_repair':2,'working_recheck_duplicate':3},
 'product_files':3,'pin_files':31,'changed_files':34,'same_candidate_working_files':528,
 'engine_preflight':integration['engine_preflight'],'sql':read(DES/'native-plan-equivalence.json'),
 'new_model_calls':0,'main_generation':142,'main_unchanged':True,'quality_certified':False,'oracle_genos_live_tested':False,
 'frozen_product_revision':'rev-001 unchanged after tests','original_failures_preserved':True}
put(RUN/'result.json',summary);put(OUT/'기술검증요약.json',summary)
notes=[
 '온톨로지 생성 계약과 원문 확보 판정을 수정하여 작업 코드에 반영했다. 제품3+pin31=34파일, 후보/작업528 SHA동일. 선택 MAIN142는 그대로다.',
 '생성: 작업별 필드와 ASCII 지역 참조 규칙을 모델 schema에 직접 제공한다. ADD_STATEMENT의 재사용 문장과 ENTRY/VIEW의 탐색 역할을 구분한다. 모델이 선택한 제시 원문ID·인용문·발생 순서로 기존 canonical 원문 anchor와 문자 위치를 정확히 조립한다. 원문에 없는 인용·미제시 원기록·중복/잘못된 참조는 거부한다. 기존 수동/저장 canonical 계약은 유지한다.',
 '활용: 실제1345 365 ON 저널에서 현재 선택은3항만 남고, 같은 branch의 material_history에는 전체4구간이 보존된 것을 원문DB와 대조했다. source_goal_control은 현재 선택과 정확히 결속된 확보 이력을 함께 검사한다. 계획·문서·조문좌표·범위와 전체 원문 검증을 통과해야 ACQUIRED이며 EXCLUDED 판단을 임의 복구하거나 법률상 충분성을 자동 생성하지 않는다.',
 '검증·복구: 기존 최종 원문/권한/주장/채택 검증, 한 번 보완, UNKNOWN 재송신 금지, 중복 보호를 유지한다. 새 실험 기록기는 각 응답과 사용량의 immutable 압축 버전을 보존하고 작은 최신 포인터만 교체한다. 이전1343 응답과 실패는 변경하지 않는다.',
 f"신규23통과, 관련 고유{matrix['passed']}통과/수정 전 동일2실패. 실제 모의 API5개와 작업 재확인3개 통과; 재확인3개는 고유 수에 더하지 않았다. 기존2실패는 test_need_continuity의 store.check_unchanged 대역 누락으로 수정 전에도 동일 재현됐다.",
 '첫 검사 신규9실패는 propose의 컨텍스트가 commit 이후 바뀌는데 이전 컨텍스트의 재사용을 기대한 fixture 오류다. propose 재조회는 commit 전, apply 재조회는 commit 후로 바로잡아23개 통과했으며 첫 fixture와 결과를 보존했다. 통합 사전검사의 변경 수35 예상은 실제34와 달라 쓰기 전 중단했다. Oracle metadata 변경0임을 확인하고 정확한 수로 정정했다. 제품 rev001은 두 경우 모두 동일하다.',
 'Oracle native639 실행 SQL/계획과 metadata는 변경 없고 engine30/500 통과. 통합 직전 작업528 SHA를 기준과 비교한 뒤34파일만 반영했다. artifacts/working-before에 이전 바이트, integration-preflight에 전후 SHA를 보관했다. 검사 runtime은 전파일 SHA 대조 후 무손실 압축 보관했다.',
 '이번 ADR은 기술 검증과 작업 반영이다. 실제 Qwen 구축과 ON 활용은 별도 사전 동결 후속에서 확인한다. 법률 정답률·속도 개선·Oracle/GENOS 현장 효과를 이번 검사로 인증하지 않는다. MAIN/원문DB/운영게시/현장/메일 변경0.'
]
(OUT/'수정과_기술검증결과.txt').write_text('\n\n'.join(notes)+'\n')
p=OUT/'수정_체크리스트.txt';t=p.read_text().replace('진행 중, ADR1347','기술 수정 완료, 실제 Qwen 확인 중 — ADR1347')
t=t.replace('[ ] ','[x] ').replace('[x] 실제 Qwen 후속:','[진행] 실제 Qwen 후속:')
t+='\n기술 결과: 신규23/고유121 통과, 수정 전 동일 fixture2 실패. 실제 모의 API5 및 작업3 재확인. 제품3+pin31=34파일, 후보/작업528동일. native639/engine30·500.\n'
p.write_text(t)
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'prior_fixture_failures':2},'repaired':summary},comparisons=[],judge_disagreements=0,usage={'physical_live_calls':0},latency={'not_measured':'Technical contracts only'},error_taxonomy=[])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[notes[0],notes[1]+'\n'+notes[2],json.dumps(read(DES/'criteria.json'),ensure_ascii=False),notes[3],notes[6],json.dumps(summary,ensure_ascii=False),notes[4]+'\n'+notes[5],'모델0. 회수 변경/속도 측정 없음.',notes[2],notes[7],notes[6],'setup → candidate edit → freeze → check → integrate → working API → recorded_audit → archive_contracts → finish → adr_structure hash/status/validate --final/graph']
front=(ADR/'README.md').read_text().split('---',2)[1]
(ADR/'README.md').write_text('---'+front+'---\n\n# 온톨로지 생성 계약과 검토 대상 연결 수정\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 case=next(c for c in read(DES/'cases.json') if c['id']==q['case_id'])
 values=['run-001/repaired/rev001',json.dumps(case,ensure_ascii=False),'기술 계약 검사, 법률 기준답변 주입 없음.','### 회수·탈락 단계 원장 — run·arm별\n\nRetrieval not_applicable. Source acquisition receipts only. Actual failed1345 journal read-only audit preserved.','새모델0. scripted API의 원시 요청·응답은 runtime archive에 보존.','제품과 같은 실제 API/engine pin. 생성 모의응답·한번보완·UNKNOWN·중복 검증.', 'accepted-test-matrix.json 및 parent-control 원본. 최초 fixture 실패 보존.',json.dumps(summary,ensure_ascii=False)]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qh,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 체크리스트 검사\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]+list(Path(__file__).parent.glob('*.py'))+[p for p in OUT.glob('*') if p.is_file() and p.name!='수정_체크리스트.txt']
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1347','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen repair, original failures, exact integration and lossless runtime evidence','contains_raw_prompts_and_outputs':p.name.endswith('.tar.gz')} for p in sorted(paths)]})
print(json.dumps(summary,ensure_ascii=False))
