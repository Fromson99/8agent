from common import *
import re
matrix=read(ART/'accepted-test-matrix.json');integration=read(ART/'working-integration.json')
f=read(DES/'candidate-bounded.json');baseline=read(DES/'baseline.json')
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']
selected_root=ROOT/baseline['release']['code_root']
assert all(sha(selected_root/n)==h for n,h in baseline['release']['files'].items())
summary={'status':'WORKING_CODE_FIXED_MAIN142_UNCHANGED','new_tests_passed':19,'new_tests_failed':0,
 'unique_final_tests_passed':matrix['passed'],'existing_failures_reproduced_before_patch':matrix['failed'],
 'initial_fixture_failures_preserved':True,'product_files':1,'pin_files':31,'changed_files':32,
 'candidate_working_equal_files':528,'engine_preflight':integration['engine_preflight'],
 'recorded_page_sequence':{'original_responses':32,'responses_until_handoff':4,'moves_applied':3,'scope':'Saved1338 choices on a bound27candidate synthetic menu; no live latency/answer comparison'},
 'api':{'synthetic_cases':2,'normal_final_answer':'ANSWER/COVERED','repeated_review_failure':'Original-only/INSUFFICIENT','originals_at_handoff':3,'model_attempts_at_handoff':9,'same_request_extra_model_calls':0,'profile_note':'Synthetic API page_size1/max_no_progress5 permit prerequisite connection steps; production profile unchanged'},
 'new_live_model_calls':0,'main_generation':142,'main_pointer_and_528_files_unchanged':True,
 'native_sql_unchanged':True,'oracle_and_genos_runtime_verified':False,'field_deployment':False,'quality_certified':False}
put(RUN/'result.json',summary)
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-candidate-page-cycle';OUT.mkdir(exist_ok=True)
put(OUT/'검증요약.json',summary)
notes=[
 '후보 페이지를 무진전으로 왕복하던 중단 제어를 수정하여 작업 코드에 반영했다. 선택 MAIN142·현장 배포는 그대로다. 작업의 기존1332/1337 멀티턴 변경은 보존했다.',
 '원인: read_candidate_pages.choose 내부 while이 NEXT/PREV를 소비하여 상위 조사 진행 검사에 반환하지 않았다. MAIN142 실제1338은 정답 근거 확보 뒤 같은 두 페이지를32회 왕복하고 조사37회 예산 경계로 종료했다. 역방향 연결은 이미 성공했고 특정 조문 연결 기능의 문제가 아니었다.',
 '수정: 현재 메뉴·입력·체크포인트에 결속한 방문 페이지와 이동 이력을 저장한다. 새 페이지를 보면 반복 구간을 초기화한다. 새 페이지 없이 같은 방향 이동을 다시 제안하면 READ_CANDIDATE_PAGE_NO_PROGRESS로 기존 ProgressHandoff → Investigation.run → bounded_result → ASSESS 경로에 넘긴다. 한 번 돌아가 읽거나 되돌아 지나 새 페이지에 도달하는 경로는 유지한다. 반복 이동 요청 자체는 실행하지 않는다.',
 '페이지 커서와 반복 기록은 같은 저장에서 함께 확정한다. 프로세스 재개·중복 응답에도 횟수를 초기화하지 않고, input/체크포인트/hash 불일치는 기존 무결성 오류로 거절한다. 옛3필드 pager는 현 위치부터 새 이력을 시작하며 과거 방문을 추측하지 않는다. 신규 원문·판단의 새 메뉴는 별도로 조사한다.',
 '판단·원문·미해결 필요·권한·기존 예산·기한·최종 검토는 유지한다. FINISH 응답·법률 충분성을 자동 생성하지 않는다. 페이지 이동은 원문 확보나 판단 완료로 기록하지 않는다. 후보를 숨기거나433→434 같은 특례를 넣지 않았다.',
 '검증: 신규19개 모두 통과(페이지/재개/변조/예산/UNKNOWN 등17 + 실제 FastAPI 소비자2). 관련 고유115개 중112통과, 기존3실패는 수정 전 코드에서 동일 재현. SQL 문자열 검사2는 저널 JSON의 문자열까지 검색하는 기존 기대이며 신규 SQL authorizer 검사에서는 실제 참조 테이블event만 확인했다. 과거 FINISH1은 이미1337에서 미열람 구조를 남긴 종료 기대로 판정한 기존 fixture다.',
 '보관1338의32개 페이지 응답을 바인딩한27후보 메뉴에 넣었을 때4번째 선택에서 검토로 반환, 실제 이동3회. 새 실제 모델 호출이나 전체199초의 개선율을 측정한 것은 아니다. 합성 API는 실제 후보/연결·기록·최종 검토를 통과하여3원문 전달·9번째 호출 뒤 탐색 종료, 정상COVERED와 검토2회실패 시 원문전용INSUFFICIENT 모두 확인. 중복 요청 추가호출0. 이 API는 목표 페이지 반복에 도달하도록 시험용page_size1/상위max_no_progress5를 사용하며 제품 설정은 불변이다.',
 '변경32파일=제품read_candidate_pages.py1+엔진pin31. 검증후보/작업528파일SHA 동일·engine30/500. native SQL와 원문DB·선택 MAIN142의528파일/포인터 불변. 후보 전체 덮어쓰기 없이 수정32파일만 사전해시 확인 후 반영. 원복은 artifacts/working-before와 integration-preflight.json을 따라 현재 파일이 이번after해시인지 확인한 뒤 수행한다.',
 '최초 변조검사1은 빈목록을 같은 빈목록으로 대입한 fixture 오류로 원본 보존 후 정정. 최초 API2는 목표 반복 전에 상위no_progress2가 작동한 준비 실패로 보존, 시험용상한5로 조건을 고정한 후 재검사2통과. 제품 후보rev001은 그대로였다. 완료 runtime5는 전파일SHA 검증 무손실압축으로 보존했다. Oracle/GENOS 실제 동작·실모델 품질/지연은 미검증이다.'
]
(OUT/'수정과_검증결과.txt').write_text('\n\n'.join(notes)+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'existing_failures':3,'live_models':0},'bounded':summary},comparisons=[],judge_disagreements=0,usage={'physical_live_calls':0},latency={'real_model':'not_measured','api_contract_seconds':read(ART/'api-contracts-r2/result.json')['seconds']},error_taxonomy=[])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[notes[0],notes[1],json.dumps(read(DES/'criteria.json'),ensure_ascii=False),notes[2]+'\n'+notes[3],notes[4],json.dumps(summary,ensure_ascii=False),notes[8],notes[6],notes[5],notes[8],notes[7],'setup.py → snapshot제품1수정 → freeze.py → check.py pager-contracts/parent-control/api-contracts-r2/final-contracts/parent-finish-control → integrate.py → archive_contracts.py → finish.py → adr_structure hash/status/validate --final/graph. 실제 모델은 호출하지 않는다. tests/fixture 최초 실패와 최종 수정 SHA는 artifacts에 보존.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 후보 페이지 무진전 반복의 조사 종료 검토 연결\n\n'+'\n\n'.join(f'## {n}. {h}\n\n{v}' for n,(h,v) in enumerate(zip(heads,vals),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 case=next(c for c in read(DES/'cases.json') if c['id']==q['case_id'])
 values=['run-001/bounded/rev001; 실제모델0',json.dumps(case,ensure_ascii=False),'법률 정답 비교 없음. 제어·원문·상태·예산 보존 계약.',
 '### 회수·탈락 단계 원장 — run·arm별\n\n후보 집합 변경 없음. 합성 원문/메뉴와 보관된1338 응답. 단계 원장 not_applicable. 전체 입력은 test_page_cycle.py/cycle_api_fixture.py, 실제기록 원본은 ADR1338 navigation-trace.json.gz.',
 '새 실모델0. 실제 API의 scripted transport와 검증된 제품/엔진 경로. contract-runtime-archives.json에 성공·실패 runtime 전체파일SHA 및 복원방법.',
 '새 중간모델0. 원문 확인·보완·제한 답변·재조회는 실제 서버 계약을 통과.',
 '채점LLM0. accepted-test-matrix.json과 각각의 result.json에 전체 node ID/실패/원인. 기존3실패는 parent-control과 parent-finish-control에서 재현.',json.dumps(summary,ensure_ascii=False)]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {n}. {h}\n\n{v}' for n,(h,v) in enumerate(zip(qh,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 검사 범위\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
put(ART/'final-test-source-hashes.json',{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')})
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]+list(Path(__file__).parent.glob('*.py'))+[p for p in OUT.glob('*') if p.is_file()]
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1340','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen code, failures and final contracts, working integration and lossless runtimes','contains_raw_prompts_and_outputs':p.name.endswith('.tar.gz')} for p in sorted(paths)]})
print(json.dumps(summary,ensure_ascii=False))
