from pathlib import Path
import hashlib, json, re
R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0832-compact-evidence-delivery';D=A/'artifacts/design';O=A/'artifacts/run-001'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert '30 passed, 1 deselected' in (O/'final-delivery-r2.log').read_text()
assert '21 passed' in (O/'wire21.log').read_text()
assert '58 passed' in (O/'api58.log').read_text()
reg=(O/'regression.log').read_text();assert '6 failed, 208 passed' in reg
failures=re.findall(r'^FAILED ([^\n]+)',reg,re.M)
old=(R/'04_EXPERIMENTS/ADR/ADR-0830-comparison-main-confirmation/artifacts/regression-connected.log').read_text()
assert failures==re.findall(r'^FAILED ([^\n]+)',old,re.M)
known=read(O/'known-trace.json');assert known['status']=='PASS'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0832/connected';cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot'
binding={'candidate_id':'connected','arm_id':'connected','experiment_id':'ADR-0832-experiment-v1','run_ids':['run-001'],
 'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),
 'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],
 'runner_path':'06_TOOLS/EXPERIMENTS/adr_0832/run_tests.py','runner_sha256':sha(R/'06_TOOLS/EXPERIMENTS/adr_0832/run_tests.py')}
files={x['target_path']:sha(code/x['target_path']) for x in cm['files']}
put(D/'verification-binding-final.json',{'code_root':str(code.relative_to(R)),'serving_files':files,**binding})
limitations=['Candidate development only, in_sample=true and decision_eligible=false. No fresh model or legal-quality claim.',
 'Original rev001 freeze and all failed development outputs retained. Revisions002-005 correct deterministic receipt/storage/wire contracts.',
 'Initial direct_note=True synthetic API fixture fails before assessment because of its pre-existing invalid quote. Excluded from final51; failure retained.',
 'Valid API fixture checks current assessment receipts, answer publication and duplicate reuse. Legacy strict _ref is separately checked with actual831 read-only journal in an in-memory reconstruction; this is not full workflow recovery.',
 'Same six existing common direct_note=True failures remain. No new failure relative to completed830 common regression.',
 'Working code and active MAIN77 untouched; qualification/promotion and GENOS are separate.']
result={'status':'complete','development_checks_passed':True,'final_revision':rev['revision_id'],
 'delivery_and_wire_tests':51,'retained_workflow_tests':58,'common_passed':208,'common_failures':failures,
 'known_failure':known,'real_model_calls':0,'quality_certified':False,'limitations':limitations}
put(O/'result.json',result)
m=read(A/'실험/manifest.json');m['design']['code_isolation']['candidates']=[binding]
m['runs'][0].update(status='complete',sha256=sha(O/'result.json'))
m['results'].update(status='complete',by_arm={'baseline':{'status':'not_run','basis':'Recorded MAIN77 failure831 and retained830 regression observations'},'connected':{'status':'complete','revision':rev['revision_id'],'tests_passed':317,'existing_failures':6}},usage={'product_model_calls':0,'offline_evaluator_calls':0},comparisons=[],error_taxonomy=[{'kind':'other','detail':'Six existing direct_note fixture failures remain. Development correction history preserved in run-001 logs.'}])
put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Proposed. Compact assessment 실제 원문 전달 기록 수정의 개발 검증 완료. 승격 판정 아님.',
 '실제831 후속 내규 조사에서 evidence_options에 원문이 전달됐으나 metadata sources에는 text가 없어 presentation이 비었다. 엄격한 발행 검사에서 HTTP500 발생.',
 'criteria.json은 수정 전 고정했다. 정확한 source/document/block/offset/text만 허용하고 failed model call은 발행 근거가 될 수 없다.',
 'API/원문 계약과 알려진 실패의 읽기 전용 진단. 개발 fixture 정정과 후보 rev001-005 실패는 모두 보존한다.',
 '최종 verification-binding-final.json. 최초 freeze.json은 변경하지 않았다. 후보342파일 중 runtime2파일과 pin만 수정.',
 json.dumps(result,ensure_ascii=False,indent=2),
 'REUSED observation enum, durable exact_evidence 저장 계약, 공통 wire projection을 차례로 바로잡았다. API fixture가 중복 요청 후 생긴 빈 journal을 고르던 검사 오류도 수정했다. 원본831은 불변이다.',
 '외부 호출0회. 모델 원문 입력에 같은 텍스트를 중복 추가하지 않는다. 상세 실행 시간은 각 로그 마지막 행.',
 '실제 전달된 정확 조각을 현재 child 원장에 기록하면 기존 발행 검사를 통과함을 확인했다. 실제 모델의 검색/의미 판단 개선은 미평가.',
 '\n'.join(limitations),'후속 고정 기술 검증 후 동일 코드만 통합·승격한다. 원문/권한/발행 검사를 완화하지 않는다.',
 'run_tests.py test_delivery.py test_api_delivery.py -k "not without_navigation"; test_wire_delivery.py; known_trace.py; 기존58/214회귀; report.py; stable validate --final/status/graph']
meta=(A/'README.md').read_text().split('---',2)[1]
(A/'README.md').write_text('---'+meta+'---\n\n# Compact assessment 원문 전달 기록 개발\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
(A/'실험/README.md').write_text('# 원문 전달 계약 개발 검사\n\n질문 정답 평가 없음. 알려진831실패의 원문과 hash는 보존하고 복사본으로만 진단했다. 최종317통과와 기존6실패를 분리 기록한다.\n')
artifacts=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json']
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Development snapshots, preserved failures and deterministic validation','contains_raw_prompts_and_outputs':False} for p in artifacts]})
print('Development complete; final revision',rev['revision_id'],'317 passed; same6 failures')
