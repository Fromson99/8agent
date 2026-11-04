from common import *
import re
r=read(ART/'contracts/result.json');w=read(ART/'working-api/result.json');i=read(ART/'working-integration.json')
assert r['failed']==w['failed']==0
summary={'status':'STRUCTURAL_FIX_IN_WORKING_CODE','unique_contracts_passed':r['passed'],'new_contracts_passed':24,'failed':0,'working_rechecks_passed':w['passed'],'working_rechecks_overlap':True,'product_files_changed':6,'changed_files':i['changed_files'],'same_candidate_working_files':525,'new_model_calls':0,'selected_main':140,'selected_main_unchanged':True,'quality_certified':False,'native_sql':read(DES/'native-plan-equivalence.json'),'engine':i['engine_preflight'],'field_deployment':False,'mail_sent':False}
put(RUN/'result.json',summary)
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-scope-review-recovery';OUT.mkdir(exist_ok=True)
put(OUT/'수정검증요약.json',summary)
notes=[
 '1325 실제 실패를 근거로 원문 구간별 검토와 같은 요청 재개를 수정해 작업 코드에 통합했다. 실제 답변 통과 여부는 후속 실모델 실험에서 별도 판정한다. 선택 MAIN140와 현장 배포는 변경하지 않았다.',
 '최종 생성 scope_reviews는 대상별 현재 원문 ID만 허용하고 구간마다 한 행을 요구한다. 원문 전체를 한 USE 묶음으로 처리할 수 없다. 사용·제외·미확인, 실제 주장·근거·이유는 모델이 정한다. 기존 canonical 그룹 검증/저장 reader는 그대로라 옛 묶음 기록도 읽는다.',
 'SCOPE_USE_UNSUPPORTED_RANGE 보완 입력에는 해당 대상·사용하지 않은 원문ID·실제 연결된 주장별 근거와 가능한 수정 선택을 제공한다. 최초 실제1325 초안은 계속 거절되며 원문이나 주장을 보정해 통과시키지 않는다.',
 '대화의 previous_response에 정확한 검토 실패 category/issues 및 review_recovery를 추가한다. 원문전용·INCOMPLETE·알려진 보완 가능한 검토 실패일 때만 ASSESS 재개를 제시한다. 같은 요청을 다시 받은 경우 기존 RESEARCH_REENTER/ASSESS로 원문을 재사용하도록 resolver와 검증자에 같은 지침을 전달한다. 새 목적/자료 요청은 모델이 별도 판단하고 UNKNOWN·시간초과는 이 복구 대상이 아니다. 자동재전송은 없다.',
 '탐색 진행 지침은 일반 규칙 질문에 요청하지 않은 날짜·기간·회사 사정을 새 완료 조건으로 추가하지 않고, 실제 위임 문구 없이 다른 문서를 가정하지 않도록 보강했다. 특정 법률·조문·질문·정답을 코드나 프롬프트에 넣지 않았다.',
 f'검증: 신규24 포함 고유{r["passed"]} 통과/실패0. 실제 제공자 직전 번호참조·고정값 축약, 구간 누락/중복/외부범위, 과거 canonical 호환, 실제1325 실패 보완 진단, UNKNOWN 제외, 메모리 원문 재사용·같은 목표·동일요청 재조회, API 정상/한 번 보완/반복 실패/OPEN을 포함한다. 작업 재검사{w["passed"]}는 중복이며 합산하지 않는다.',
 f'제품6+native계획1+pin31={i["changed_files"]}파일. 후보/작업525 SHA 동일, native639 실행SQL/list/AST 동일, engine30/497 통과. 기존1322·1324·1323 기동 수정 보존. 원복 바이트는 artifacts/working-before. 활성MAIN·기존 기록DB·현장·메일 변경0.',
 '이 단계는 모의/구조 검사다. 모델의 의미 판단·행 사이 관계 충돌·공급자 공백 응답이 사라졌다고 주장하지 않는다. 새 실모델0, 통테60개 통과0. 테스트 runtime은 전파일 해시를 확인한 무손실 보관본으로 보존한다.'
]
(OUT/'수정과_검증결과.txt').write_text('\n\n'.join(notes)+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'live_models':0},'integrated':summary},comparisons=[],judge_disagreements=0,usage={'physical_calls':0},latency={'contract_seconds':r['seconds'],'working_recheck_seconds':w['seconds'],'real_model':'not_measured'},error_taxonomy=[])
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[notes[0],notes[1]+'\n'+notes[2],json.dumps(read(DES/'criteria.json'),ensure_ascii=False),'완료1325 exact525 기반 격리 rev001. 사전 선언 신규24와 관련 기존 검사, 작업 API 재검사.',notes[3]+'\n'+notes[4],json.dumps(summary,ensure_ascii=False),notes[2],f'새 모델/비용0. 계약{r["seconds"]:.3f}초, 중복 작업 재검사{w["seconds"]:.3f}초. 실제 corpus 회수 없음.',notes[5],notes[7],notes[6],'setup.py → 후보6파일 수정 → freeze.py → check.py contracts → integrate.py → check.py working-api → archive_contracts.py → finish.py → adr_structure hash/status/validate --final/graph. 실제 모델은 후속 ADR에서 새 요청으로 실행.']
front=(ADR/'README.md').read_text().split('---',2)[1];front=re.sub(r'(?m)^status:.*$','status: Proposed',front)
(ADR/'README.md').write_text('---'+front+'---\n\n# 원문 구간 검토와 같은 요청 재개 수정\n\n'+'\n\n'.join(f'## {n}. {h}\n\n{v}' for n,(h,v) in enumerate(zip(heads,vals),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 case=next(c for c in read(DES/'cases.json') if c['id']==q['case_id'])
 values=['run-001/integrated/rev001; 실제모델0',json.dumps(case,ensure_ascii=False),'합성 규정/주장/미확인 및 원래 실패1325 기록. 법률 정답지 없음, 상태·근거·원문 보존 기준.',
 '### 회수·탈락 단계 원장 — run·arm별\n\n실제 corpus 회수 없음. 합성 계약의 전체 입력은 test_scope_recovery.py, 과거 원본은1325 canonical006/007. 단계 원장 not_applicable.',
 '새 제품모델0. 실제 API 경로의 scripted 응답이며 새 법률정답 생성이 아니다. fixture runtime 전파일은 contract-runtime-archives.json 참조.',
 '새 중간모델0. 원문 보존·보완·중단·재조회 시나리오의 전체 기록을 유지.',
 '채점LLM0. contracts/result.json 및 working-api/result.json의 각 node ID 결과.',json.dumps(summary,ensure_ascii=False)]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {n}. {h}\n\n{v}' for n,(h,v) in enumerate(zip(qh,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 검사 범위\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]+list(Path(__file__).parent.glob('*.py'))+[p for p in OUT.glob('*') if p.is_file()]
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1326','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen code, complete contracts, working integration and lossless fixture runtimes','contains_raw_prompts_and_outputs':p.name.endswith('.tar.gz')} for p in sorted(paths)]})
print(json.dumps(summary,ensure_ascii=False))
