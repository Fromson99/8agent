from common import *
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-ontology-repair'
f=read(DES/'candidate-repaired.json');baseline=read(DES/'baseline.json')
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']
assert all(sha(selected()/n)==h for n,h in baseline['release']['files'].items())
matrix=read(ART/'accepted-test-matrix.json');integration=read(ART/'working-integration.json')
build=read(ART/'build-live/result.json');review=read(ART/'build-review.json')
summary={'status':'WORKING_WIRE_FIXED','new_tests_passed':2,'related_passed':matrix['passed'],
 'unchanged_baseline_fixture_failures':matrix['failed'],'product_files':1,'pin_files':31,'changed_files':32,
 'candidate_working_same_files':528,'main_generation':142,'main_unchanged':True,
 'engine_preflight':integration['engine_preflight'],'sql':read(DES/'native-plan-equivalence.json'),
 'build':build,'build_review':review,'quality_certified':False,'oracle_genos_live_tested':False}
put(RUN/'result.json',summary);put(OUT/'생성전송_수정검증요약.json',summary)
notes=[
 '온톨로지 생성 요청에도 기존 공통 model_contract.structured_request를 연결했다. 제품1+pin31=32파일 작업 반영, 완료1347의 수정 보존·후보/작업528 SHA동일. 선택 MAIN142는 그대로다.',
 '1348 실제 생성은 Parasail의 uniqueItems 미지원 문법으로 모델 답변 생성 전에 거절됐다. 다른 구조화 호출은 이미 공통 GENOS 문법 변환을 사용했지만 authoring_model은 자체 요청을 만들고 있었다. 같은 공통 변환을 재사용하여 전송 스키마만 호환 형식으로 구성하고 원본 schema hash와 adapter revision을 영수증에 저장한다.',
 '서버 원본 schema와 중복 검증은 유지한다. 실제 authoring_model→Workspace.propose 경로에서 중복 origin_refs 응답을 거부하고 단 한 번 보완한 뒤 정상 반영함을 검사했다. 사용자 데이터에 uniqueItems라는 키/enum이 있어도 그대로 보존한다. 원문/권한/철회/판단·출력상한·UNKNOWN·재송신 정책은 바꾸지 않았다.',
 f"신규2통과·관련{matrix['passed']}통과/기존{matrix['failed']}실패. 기존25실패는 normalize 대역의 옛 coverage 배열·reason/purpose 필드 등 현재 계약과 불일치하며 수정 전 부모에서도 동일25개 실패를 재현했다. 기존 실패는 고치거나 성공으로 집계하지 않았다. 제품 rev001은 검사·실모델 동안 동일하다.",
 'Qwen 생성 재검증: '+review['conclusion_ko'],
 '동시1348 OFF/ON 비교는 그 실험의 동결528을 그대로 사용했다.1348 결과를 확정한 뒤 이번32파일만 작업에 추가했다. 이번 생성 전송 수정은1348 활용 수치의 원인이 아니다. native639 실행 SQL/계획과 metadata 불변, engine30/500. 원복 바이트와 SHA·실패 원응답·호출 사용량을 보존했다.',
 'MAIN/원문DB/운영게시/현장/메일 변경0. 외부 Qwen·공개 SQLite 검사이며 Oracle/GENOS 내부 모델·전체 법률 품질 인증이 아니다.'
]
(OUT/'생성전송_수정과_실제검증결과.txt').write_text('\n\n'.join(notes)+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'fixture_failures':25,'prior_1348_grammar_rejection':True},'repaired':summary},comparisons=[],judge_disagreements=0,usage={k:build[k] for k in ('physical_calls','unknown','reported_cost_usd','reported_tokens')},latency={'build_seconds':build['seconds'],'not_comparable':'Different failure stage, not a speed improvement'},error_taxonomy=review.get('errors',[]))
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[notes[0],notes[1],json.dumps(read(DES/'criteria.json'),ensure_ascii=False),notes[2],'완료1347+이번1제품/pin; Qwen3.8 FP8 reasoning none; 동일 보존 원기록과 공개 원문; 새로 동결한 생성1회, 최대9물리/단계별1보완.',json.dumps(summary,ensure_ascii=False),notes[3]+'\n'+notes[4],json.dumps(build,ensure_ascii=False),notes[4],notes[6],notes[5],'setup → isolated edit → freeze → check/parent control → build preflight/freeze → build once → source review → integrate after1348 complete → archive → finish → hash/status/validate --final/graph']
front=(ADR/'README.md').read_text().split('---',2)[1]
(ADR/'README.md').write_text('---'+front+'---\n\n# 온톨로지 생성 전송 문법 수정\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 values=['run-001/repaired/rev001',q['case_id'],'Stored exact public originals; no answer-key injection. Archived judgment is an explicit authoring input, not a hidden grading key.','### 회수·탈락 단계 원장 — run·arm별\n\nRetrieval not_applicable: unchanged fixed archived input and originals. design/records.json and originals-origin.json.','build-live/raw/call-*/request.json.gz and response.json.gz; all errors preserved.','build-live/canonical/*.json.gz; immutable observer versions retain cumulative usage and original outputs.','build-review.json; Codex source inspection, no judge model. Parent fixture failures retained.',json.dumps(summary,ensure_ascii=False)]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qh,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 생성 전송 검증\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]+list(Path(__file__).parent.glob('*.py'))
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1349','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact wire repair, prior failure controls, fixed real build and integration','contains_raw_prompts_and_outputs':p.name.endswith('.tar.gz') or 'canonical' in p.parts} for p in sorted(paths)]})
print(summary['status'],build['status'],build['physical_calls'])
