from common import *
import re
r=read(ART/'contracts/result.json');w={'failed':0,'passed':0,'seconds':0};i=read(ART/'working-integration.json')
assert r['failed']==w['failed']==0
summary={'status':'STRUCTURAL_FIX_IN_WORKING_CODE','unique_contracts_passed':r['passed'],'new_contracts_passed':39,'failed':0,'working_rechecks_passed':w['passed'],'working_rechecks_overlap':True,'product_files_changed':7,'changed_files':i['changed_files'],'same_candidate_working_files':528,'new_model_calls':0,'selected_main':140,'selected_main_unchanged':True,'quality_certified':False,'native_sql':read(DES/'native-plan-equivalence.json'),'engine':i['engine_preflight'],'field_deployment':False,'mail_sent':False}
put(RUN/'result.json',summary)
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-repeat-scope-join';OUT.mkdir(exist_ok=True)
put(OUT/'수정검증요약.json',summary)
notes=[
 '반복 질문 목표·근거 연결·탐색 지침·보완 오류를 수정해 작업 코드에 통합했다. 다른 작업의 화면·Oracle 연결 변경을 보존했다. 선택 MAIN140와 현장 배포는 변경하지 않았다.',
 '범위 scope_reviews의 claim_refs를 중복 작성시키지 않는다. 모델이 선택한 evidence_refs·issue_refs의 정확한 교집합으로 주장 번호를 조립한다. USE/EXCLUDE/OPEN·주장·인용·이유·gap·judgment 채택은 모델이 판단하고, 근거 없는 USE나 배제 충돌은 원래 검증이 계속 거절한다. 과거 canonical/저장영수증 호환 유지.',
 '현재 요청 원문=task=직전 event 원문이고 사실·문서 범위·권한·READY route·원문 binding이 같을 때 같은 목표의 ANSWER_PRESENT/RESEARCH_REENTER/NEED_TARGET을 제시한다. 모델이 재표현/재판단/확인을 선택한다. 변경/pending/binding 불일치는 일반 경로, 과거답 정답 승인0.',
 '일반 질문에 없는 기한·위임을 추측해 조사 목표를 늘리지 말라는 지침을 실제 compact 선택 및 별도 supervisor invoke 양쪽에 연결했다. 동일 법령이라도 다른 주제는 새 목표라는 지침을 추가했다. 테스트 조문·질문·정답 특례0.',
 '최초 출력의 검토자료가 null이거나 목록/행/그룹이 불완전해도 원래 보완 진단을 유지한다. 새 AttributeError가 원래 실패를 가리지 않으며 UNKNOWN 자동 재전송0.',
 f'고유{r["passed"]}검사 모두 통과(신규39+기존67). 실제API 정상·한 번 보완·반복 실패 중단·OPEN, 실제 wire 지침, 동일 질문 목표와 원문 재사용·재조회, 권한/범위/pending, 원래1327 실패의 번호 연결, 불완전 입력8조건을 포함한다. 통합 후528파일 전체SHA와 엔진preflight 일치로 동일 코드 확인, 중복 재실행0.',
 f'작업변경{i["changed_files"]}파일(제품7+native계획1+pin31), 후보/작업528 SHA 동일. 기존화면2·Oracle4수정+2신설+설정1 등 현재 병행 내용은 그대로 보존하고 엔진 결속을 갱신했다. native639 실행SQL/list/AST 동일·engine30/500. 이번SQLite 검사로 병행 Oracle 품질을 인증하지 않는다. 원복 artifacts/working-before·runtime 전체 SHA 보관.',
 '1328/1329 실패 원본,1330/1331의 병행 변경 감지 후 쓰기0 중단,1332 준비 중 Oracle 설정 의존파일 등록 보완을 모두 유지했다. 실제모델0이며 통테60개 통과 인증이 아니다. 실제4턴은 후속1333에서 별도 확인한다.'
]
(OUT/'수정과_검증결과.txt').write_text('\n\n'.join(notes)+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'live_models':0},'integrated':summary},comparisons=[],judge_disagreements=0,usage={'physical_calls':0},latency={'contract_seconds':r['seconds'],'working_recheck_seconds':w['seconds'],'real_model':'not_measured'},error_taxonomy=[])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[notes[0],notes[1]+'\n'+notes[2],json.dumps(read(DES/'criteria.json'),ensure_ascii=False),'완료1331 핵심7수정과 현재 작업의 전체 비충돌 변경을 묶은528파일rev001, 신규39+기존67 검사.',notes[3]+'\n'+notes[4],json.dumps(summary,ensure_ascii=False),notes[2],f'새 모델/비용0. 계약{r["seconds"]:.3f}초, 중복 작업 재검사{w["seconds"]:.3f}초. 실제 corpus 회수 없음.',notes[5],notes[7],notes[6],'setup.py → 후보528파일 동결 → freeze.py → check.py contracts → integrate.py → archive_contracts.py → finish.py → adr_structure hash/status/validate --final/graph. 실제 모델은 후속 ADR에서 새 요청으로 실행.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 반복 목표·근거 연결·보완 오류 수정 작업 통합\n\n'+'\n\n'.join(f'## {n}. {h}\n\n{v}' for n,(h,v) in enumerate(zip(heads,vals),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 case=next(c for c in read(DES/'cases.json') if c['id']==q['case_id'])
 values=['run-001/integrated/rev001; 실제모델0',json.dumps(case,ensure_ascii=False),'합성 규정/주장/미확인 및 원래 실패1325 기록. 법률 정답지 없음, 상태·근거·원문 보존 기준.',
 '### 회수·탈락 단계 원장 — run·arm별\n\n실제 corpus 회수 없음. 합성 계약의 전체 입력은 test_repeat_scope.py, 과거 원본은1327 canonical027/044. 단계 원장 not_applicable.',
 '새 제품모델0. 실제 API 경로의 scripted 응답이며 새 법률정답 생성이 아니다. fixture runtime 전파일은 contract-runtime-archives.json 참조.',
 '새 중간모델0. 원문 보존·보완·중단·재조회 시나리오의 전체 기록을 유지.',
 '채점LLM0. contracts/result.json의106개 node ID와 working-integration.json 전체528 SHA 대조.',json.dumps(summary,ensure_ascii=False)]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {n}. {h}\n\n{v}' for n,(h,v) in enumerate(zip(qh,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 검사 범위\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]+list(Path(__file__).parent.glob('*.py'))+[p for p in OUT.glob('*') if p.is_file()]
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1332','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen code, complete contracts, working integration and lossless fixture runtimes','contains_raw_prompts_and_outputs':p.name.endswith('.tar.gz')} for p in sorted(paths)]})
print(json.dumps(summary,ensure_ascii=False))
