from common import *
import re
f=read(DES/'freeze-rev-001.json');base=read(DES/'baseline.json')
first=read(ART/'check-rev-001.json');corrected=read(ART/'fixture-correction-rev-001.json')
assert first['passed']==63 and first['failed']==12
assert corrected['passed']==12 and corrected['failed']==0 and not corrected['import_leaks']
assert {r['test'] for r in first['rows'] if r['status']=='failed'}=={r['test'] for r in corrected['rows']}
assert not first['import_leaks']
C=ROOT/f['code_root']
assert all(sha(C/n)==h for n,h in f['files'].items())
assert all((sha(ROOT/n) if (ROOT/n).is_file() else None)==h for n,h in base['working_files'].items())
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']
changed=[n for n,h in f['files'].items() if base['manifest']['files'][n]!=h]
assert len(changed)==33
out=ROOT/'09_ARTIFACTS/AUDITS/20261029-final-answer-scope-prompt'
result={'status':'complete','technical_success':True,'legal_quality_evaluated':False,
 'candidate_revision':f['candidate_revision'],'frozen_files':len(f['files']),'changed_files':changed,
 'prompt_constants_changed':2,'dependent_pins_changed':31,'unique_contracts_passed':75,
 'initial_passed':63,'initial_fixture_binding_errors':12,'corrected_same_tests_passed':12,
 'source_or_schema_change':False,'additional_model_stage':False,'external_model_calls':0,
 'input_reconstructions':2,'input_reconstructions_sent':False,'model_response_replay':False,
 'api_cases':['supported','limited_source','limited_fact','repair_once','repair_twice_rejected'],
 'working_code_changed':False,'main_generation':115,'main_changed':False,'genos_deployed':False,
 'semantic_quality_certified':False,'performance_certified':False,
 'known_remaining':'Generic stop_reason limitation footer remains a separate server defect',
 'evidence':{p.name:bind(p) for p in [ART/'check-rev-001.json',ART/'fixture-correction-rev-001.json',DES/'fixture-correction.json',ART/'input-integrity-011.json',ART/'input-integrity-012.json',out/'최종_시스템_프롬프트.txt']}}
put(RUN/'result.json',result)
m=read(ADR/'실험/manifest.json')
m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'),success_criteria_met=True)
m['results'].update(status='complete',by_arm={'scoped':{'status':'complete','technical_success':True,
 'legal_quality_evaluated':False,'decision_eligible':False}},comparisons=[],judge_disagreements=[],
 usage={'external_model_calls':0,'external_tokens':0},
 latency={'performance_claim':False,'reason':'Prompt delivery contracts only; no live generation'},
 error_taxonomy=[{'type':'test_fixture_binding','count':12,'resolution':'Same frozen code, correct test ROOT, unchanged assertions passed12'}],
 main_wiring='unchanged',quality_certified=False)
put(ADR/'실험/manifest.json',m)
meta=(ADR/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Proposed'),('main_wiring','unchanged'),('in_sample','true'),('decision_eligible','false')]:
 meta=re.sub(r'(?m)^'+k+':.*$',k+': '+v,meta)
sections=[
 ('결정 요약','최종 ASSESS·보완 호출에 쓰이는 프롬프트 두 곳을 수정한 격리 후보다. 원문 조건의 실제 답변 반영을 지시하며 연결·기존 계약75검사를 통과했다. 모델 효과는 미측정이고 작업 코드·MAIN115는 유지한다.'),
 ('문제와 변경 전 구조','ADR1191은 필요한 원문을 모두 최종 입력으로 전달했으나 모델의 답변에서 산정 대상의 지역·시점 조건이 누락됐다. 최초와 보완 출력에서 같은 누락이 있었고 보완 피드백은 근거 연결 오류만 다뤘다. 서버의 일반 제한 문구 결함은 별도다.'),
 ('가설과 사전 판정 기준','[사전 기준](artifacts/design/criteria.json). 실제 답변 필드의 주체·대상·지역·시점, 수치 기준·단위·상한·기한, 조건·예외를 원문과 대조하는 지시가 누락 감소에 도움이 될 수 있다. 이번 성공 기준은 지시 도달과 기존 계약 보존이며 개선 효과를 성공으로 판정하지 않는다.'),
 ('실험 설계','MAIN115의466파일을 동결한 scoped/rev-001이다. MODERN_ASSESS_PROMPT와 v8.PROMPT만 수정하고 종속pin31개를 갱신했다. AST 대조로 실행 로직 불변을 확인했다. 실제 API에 합성 응답을 주입하며 최초·보완 지시, 같은 근거, 호출 수, 실패·저장·중복 소비자를 확인했다.'),
 ('데이터·모델·재현성','기존 CM007의11·12번째 실제 요청은 시스템 지시문만 재구성했다. user 원문·질문·스키마·모델·공급자는 동일하고 전송하지 않았다. Qwen3.8/Parasail 우선·확정429 NearAI1회·40/1024/1800·개별180초·출력상한 없음·온톨로지 기본OFF를 그대로 보존한다.'),
 ('결과','최종75개 고유 계약 통과: 최초63통과, 기존 검사12개는 작업ROOT와 후보workflow 결속 불일치로 호출 전에 실패했다. 원본 실패를 보존하고 검사ROOT만 동일 frozen code로 맞춘12개가 통과했다. 제품 코드·검사 기대값 변경 없음. [결과](artifacts/run-001/result.json).'),
 ('사례별 오류 분석','실제 API의 정상, 원문 부족, 사실 부족, 보완1회 성공, 보완 반복 실패 검사가 통과했다. 동일 요청 재사용과 저장 답변 검증은 기존 native fixture가 확인한다. 의미 누락은 프롬프트 지시로 다루며 키워드 일치로 법률 정답을 보장하는 검증기를 추가하지 않았다.'),
 ('비용·지연·회수 규모','외부 모델0회·외부 토큰0. CM007의 동일 system 지시문은5762→7250자다. 추가 모델 단계와 출력 필드는 없으며 실제 출력 토큰·지연·품질 영향은 측정하지 않았다. 실제 검색 회수율 평가 없음.'),
 ('해석','새 지시는 조건을 인용 ID·reason·검토 의견에만 남기지 않고 표시되는 claims에 작성하도록 한다. 이미 전달된 원문에서 답변에 빠진 내용은 claims를 고치고, 원문 자체가 부족할 때만 기존 gaps를 쓰도록 구분한다. 보완 응답도 전체 내용 대조를 다시 수행하도록 한다.'),
 ('한계와 일반화 가능 범위','CM007의 알려진 실패에 근거한 인샘플 후보이며 특정 문서명·조문·정답 수치를 넣지 않았다. 단위/API 통과는 모델 지시 준수와 법률 품질 인증이 아니다. 새 실모델·CM007/009·GENOS 검증은 수행하지 않았다. 일반 제한 문구 결함은 여전히 남는다.'),
 ('운영 결정·롤백 조건','Proposed, decision_eligible=false, main_wiring=unchanged. 작업 코드·MAIN115·완료 원본은 미변경이다. 후속 실제 효과 검증과 MAIN 반영은 새 결과로 구분한다. 활성 포인터를 바꾸지 않았으므로 현재 서비스 롤백은 필요 없다.'),
 ('재현 명령','실행기:06_TOOLS/EXPERIMENTS/adr_1192의setup/edit_prompts/freeze/check/recheck_fixture/finish. 완료 산출물을 덮어쓰지 않는다.\n\n`.venv/bin/python 06_TOOLS/run_tool.py adr_structure.py validate --path 04_EXPERIMENTS/ADR/ADR-1192-final-answer-scope-prompt --final`'),
]
(ADR/'README.md').write_text('---'+meta+'---\n\n# 최종 답변 원문 조건 보존 프롬프트\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(sections,1))+'\n')
(ADR/'실험/README.md').write_text('# 질문별 법률 평가 없음\n\n합성 API·기존 계약75검사와 저장된 요청의 입력 동일성만 확인했다. 새 모델 호출·보관 응답 재생·CM007 내용 재채점은 없고 알려진 실패의 품질 통과를 주장하지 않는다. [결과](../artifacts/run-001/result.json).\n')
report='''최종 답변 프롬프트 수정 후보 — ADR1192 / scoped rev-001

수정 내용
- 최종 claims 작성 후 원문의 주체·대상·지역·시점·선행 절차와 역대조한다.
- 수치의 분모·대상 수량·단위·산정 기준·상한 조건·기산점과 예외를 답변 본문에 유지한다.
- 인용 ID나 검토 이유에 조건이 있어도 실제 답변의 누락을 대신하지 못한다고 명시한다.
- 규정은 rule의 subject/scope/norms/conditions/exceptions에 작성하고 단순 요약을 이유로 조건을 제거하지 않는다.
- 보완 호출은 지적된 형식·연결 오류를 고친 뒤 법률 내용도 다시 대조한다.
- 읽은 원문을 답변에 빠뜨린 경우는 답변을 수정하고, 실제 원문이 없을 때만 기존 조사 gap을 남긴다.

확인 결과
동결466파일: 프롬프트2곳과 종속pin31개만 변경. 실행 로직·원문·스키마·모델·공급자·예산 동일.
고유75검사 통과. 최초63통과/검사 경로 오류12개는 원본 보존 후 같은 후보ROOT로 재검사12통과.
정상·제한 답변·보완 성공/실패·동일 요청·저장 소비자 및 최초/보완 실제 API 입력 연결 확인.
저장된007의 실제11·12번째 요청은 시스템 지시문만 재구성: 질문·원문·응답 스키마·라우팅 동일, 미전송.
시스템 지시문5762→7250자. 새 모델 단계·출력 필드·자동 재시도 추가 없음.

적용 범위와 남은 확인
격리 후보에 구현했다. 작업 코드와 활성 MAIN115는 유지했다.
외부 모델0회. 실제 모델의 누락 감소·품질·속도는 아직 미검증이다.
서버가 덧붙인 일반 미확인 문구는 프롬프트 문제가 아닌 별도 코드 결함이며 이번에 수정하지 않았다.
전체 지시문은 같은 폴더의 최종_시스템_프롬프트.txt에 있다.
'''
with (out/'수정과_검증결과.txt').open('x') as p:p.write(report)
put(out/'result.json',result)
a=read(ART/'manifest.json')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and 'test-runtime' not in p.parts]
paths+=list(Path(__file__).parent.glob('*.py'))+[ROOT/f['candidate_revision']['manifest_path'],out/'최종_시스템_프롬프트.txt',out/'수정과_검증결과.txt']
a['files']=[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,
 'description':'Prompt candidate, exact frozen code, contract evidence, or original failure/correction',
 'contains_raw_prompts_and_outputs':p.name=='최종_시스템_프롬프트.txt'} for p in paths]
(ART/'manifest.json').write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n')
print('Prompt candidate complete; contracts75; new model0; MAIN115 unchanged')
