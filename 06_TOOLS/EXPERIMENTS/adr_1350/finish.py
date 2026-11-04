from common import *
OUT=ROOT/'09_ARTIFACTS/AUDITS/20261104-ontology-repair'
f=read(DES/'candidate-repaired.json');baseline=read(DES/'baseline.json')
assert all(sha(ROOT/n)==h for n,h in f['selected_files'].items())
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==baseline['pointer']
assert all(sha(selected()/n)==h for n,h in baseline['release']['files'].items())
matrix=read(ART/'accepted-test-matrix.json');integration=read(ART/'working-integration.json')
build=read(ART/'build-live/result.json');review=read(ART/'build-review.json')
summary={'status':'WORKING_RECORD_VIEW_FIXED_BUILD_NOT_PASSED','new_tests_passed':4,'related_passed':matrix['passed'],
 'unchanged_baseline_fixture_failures':matrix['failed'],'product_files':2,'pin_files':31,'changed_files':33,
 'candidate_working_same_files':528,'main_generation':142,'main_unchanged':True,
 'engine_preflight':integration['engine_preflight'],'sql':read(DES/'native-plan-equivalence.json'),
 'build':build,'build_review':review,'quality_certified':False,'oracle_genos_live_tested':False}
put(RUN/'result.json',summary);put(OUT/'생성입력_수정검증요약.json',summary)
notes=[
 '생성 모델에 전체 저장행·중복 인덱스 대신 원 payload를 한 번 제공하도록 정리했다. 저장 revision/work_hash는 별도 binding으로 유지하고 생성 전후 변경을 검사한다. 제품2+pin31=33파일 작업 반영, 완료1347/1349 수정 보존·후보/작업528 SHA동일. 선택 MAIN142 유지.',
 '1349 정상 응답은64문장 중56개가 저장 envelope/인덱스/관리필드 설명이었다. 원기록 payload와 관리용 저장 구조가 함께 중복 노출됐다. 현재 projection은 원기록 안의 어떤 필드도 해석·삭제하지 않고 저장 외피와 중복 인덱스만 입력에서 분리한다.',
 'payload 내부에 status·acl_ref·work_hash·index·raw 등 같은 이름의 업무 필드가 있어도 정확히 보존한다. 원기록 저장 바이트/원본 ID와출처 연결은 유지하며 생성 중 원기록 revision이 바뀌면 보완/반영 없이 중단한다. typed schema·원문·권한·중복·UNKNOWN·기존32개 컴파일 선택 한도를 유지한다.',
 '신규4통과, 관련 고유59통과/실패0: 이번36개와 기존1347 신규23개를 같은 최종 후보에서 확인했다. 작업4개는 중복 재확인이다. 앞선1347의 기존fixture2 및1349의25실패 이력은 별도로 보존되며 이번59개 통과로 없어졌다고 해석하지 않는다.',
 'Qwen 실제 생성: '+review['conclusion_ko'],
 '후보 원본 payload/출처 binding 검증은 통과했지만 관리정보 과생성 감소라는 실모델 가설은 미통과다. 현재 수정은 입력 정합·검증 유지이며 자동 구축 성공으로 승격하지 않는다.1348의 OFF/ON 수치는 이전 완료1347 후보에서 측정했으므로 이번 입력 수정의 성능 효과가 아니다.',
 'native639 실행 SQL/계획·metadata 불변, engine30/500. 통합전528 SHA 확인 후33파일만 반영하고 전후 SHA와 원복 바이트 보존. MAIN/원문DB/운영게시/현장/메일 변경0; Oracle/GENOS 실모델 미인증.'
]
(OUT/'생성입력_수정과_실제검증결과.txt').write_text('\n\n'.join(notes)+'\n')
m=read(ADR/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(RUN/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'reference_only':True,'prior1349_statement_count':64,'prior1349_administrative_statements':56},'repaired':summary},comparisons=[],judge_disagreements=0,usage={k:build[k] for k in ('physical_calls','unknown','reported_cost_usd','reported_tokens')},latency={'build_seconds':build['seconds'],'not_comparable':'Different failure stage, not a speed improvement'},error_taxonomy=review.get('errors',[]))
put(ADR/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
vals=[notes[0],notes[1],json.dumps(read(DES/'criteria.json'),ensure_ascii=False),notes[2],'완료1349+이번2제품/pin; Qwen3.8 FP8 reasoning none; 동일 보존 원기록과 공개 원문; 새로 동결한 생성1회, 최대9물리/단계별1보완.',json.dumps(summary,ensure_ascii=False),notes[3]+'\n'+notes[4],json.dumps(build,ensure_ascii=False),notes[4],notes[6],notes[5],'setup → isolated edit → freeze → check/parent control → build preflight/freeze → build once → source review → integrate after1348 complete → archive → finish → hash/status/validate --final/graph']
front=(ADR/'README.md').read_text().split('---',2)[1]
(ADR/'README.md').write_text('---'+front+'---\n\n# 온톨로지 생성 입력 정리\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(heads,vals),1))+'\n')
qh=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 values=['run-001/repaired/rev001',q['case_id'],'Stored exact public originals; no answer-key injection. Archived judgment is an explicit authoring input, not a hidden grading key.','### 회수·탈락 단계 원장 — run·arm별\n\nRetrieval not_applicable: unchanged fixed archived input and originals. design/records.json and originals-origin.json.','build-live/raw/call-*/request.json.gz and response.json.gz; all errors preserved.','build-live/canonical/*.json.gz; immutable observer versions retain cumulative usage and original outputs.','build-review.json; Codex source inspection, no judge model. Parent fixture failures retained.',json.dumps(summary,ensure_ascii=False)]
 (ADR/'실험'/q['file']).write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{v}' for i,(h,v) in enumerate(zip(qh,values),1))+'\n')
(ADR/'실험/README.md').write_text('# 생성 입력 검증\n\n'+'\n'.join(f'- [{q["case_id"]}]({q["file"]})' for q in m['questions'])+'\n')
paths=[p for p in ART.rglob('*') if p.is_file() and p!=ART/'manifest.json' and '.observer-versions' not in p.parts]+list(Path(__file__).parent.glob('*.py'))
put(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1350','files':[{'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact input projection repair, prior failure controls, fixed real build and integration','contains_raw_prompts_and_outputs':p.name.endswith('.tar.gz') or 'canonical' in p.parts} for p in sorted(paths)]})
print(summary['status'],build['status'],build['physical_calls'])
