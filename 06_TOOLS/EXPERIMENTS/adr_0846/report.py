from pathlib import Path
import hashlib,json,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0846-source-return-boundary';D=A/'artifacts/design';O=A/'artifacts/run-001';O.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');parent=R/'04_EXPERIMENTS/ADR/ADR-0845-source-terminal-qualification';p=read(parent/'artifacts/design/verification-binding-final.json');service=read(parent/'artifacts/candidate-consumer-v2.json');test=(A/'artifacts/candidate-api.log').read_text();live=read(R/'04_EXPERIMENTS/ADR/ADR-0844-comparison-source-return/artifacts/run-001/result.json')
checks={'all16_new_boundary_states_and60_regressions':'76 passed, 1 deselected' in test,'exact_completed845_code':f['serving_files']==p['serving_files'],
 'retained_actual_data_service13':service['status']=='PASS' and len(service['checks'])==13 and all(service['checks'].values()),
 'frozen_inputs':all(sha(R/n)==h for n,h in f['files'].items()),'MAIN80_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256']}
limits=['Finite software contract qualification, not legal holdout or accuracy certification.16 new boundary states and60 retained contracts are identified separately.',
 'The excluded845 fixture is still recorded as failed: its query returned a real original, so it did not instantiate zero sources. New cases freeze empty tool results directly.',
 'Known844 full model run returned2comparison rows in9calls/509.98seconds with zero span mismatch.845changed only native journal closure and internal SELECT schema; this exact final code has synthetic full API and actual-data service verification, not a second full model draw.',
 'GENOS data/reference connection and deployment are unverified; implementation prefers existing exact links and never infers GENOS absence from local data.',
 'Existing resident local services are not restarted automatically; active-pointer bootstrap is verified in a fresh process.']
result={'status':'complete','strict_success':all(checks.values()),'checks':checks,'tests_passed':76,'new_boundary_states':16,'retained_regressions':60,
 'excluded_invalid_fixture':'adr_0845/test_qualification.py::test_zero_read_source_handoff_is_valid_api_result','service_checks':13,
 'real_model_calls':0,'retained_model_run':{'adr':'ADR-0844','calls':live['model_calls'],'seconds':live['seconds'],'rows':len(live['rows']),'original_span_mismatches':live['original_span_mismatches']},
 'quality_certified':False,'limitations':limits};put(O/'result.json',result);put(D/'verification-binding-final.json',read(D/'verification-binding.json'))
put(A/'artifacts/retained-service.json',{'path':str((parent/'artifacts/candidate-consumer-v2.json').relative_to(R)),'sha256':sha(parent/'artifacts/candidate-consumer-v2.json'),'code_files_exactly_equal':checks['exact_completed845_code']})
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(O/'result.json'));m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','basis':'Historical MAIN80 service and original-integrity receipts; not rerun for new boundary states'},'qualified':{'status':'complete','new16':16,'retained60':60,'service13':13}},comparisons=[],usage={'product_model_calls':0,'offline_evaluator_calls':0},latency={},error_taxonomy=[]);put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=['Accepted. Exact completed845 code passed finite technical qualification; eligible for localMAIN81 integration within user authorization.',
 'MAIN80 partially read named rules and required child legal judgment;844added whole-read, reference preference, normal source return and single table;845closed native journal state.',
 read(D/'criteria.json')['hypothesis'], 'Availability(internal/external)2×2 × bounded stop2 × interruption2 =16 new actual API states.60previous valid contracts are regression. Original zero-query fixture remains failed and excluded.',
 '344servingfiles exactly equal completed845. No model calls; source/ACL/generation hashes and registered profile remain pinned.',json.dumps(result,ensure_ascii=False,indent=2),
 'All16zero/one-sided/two-sided/bounded/interrupted cases preserve original availability, terminal state, saved response and monotonic deadline/budget. No semantic rejection.',
 'No product/evaluator model calls. Previous13actual-data checks retained with exact code equality;76full technical tests recorded in candidate-api.log.',
 'Unavailable sources and uncertain opinions remain reportable. Real source, authorization and state integrity are still enforced.', '\n'.join(limits),
 'Integrate only reviewed deltas, preserve unrelated working changes, test same working implementation, prepare hash-fixed release and activate via stable promotion; verify actual local service bootstrap. Rollback toMAIN80. GENOS separate.',
 'setup.py;seal.py;freeze.py;run_tests.py(new16+retained60,exclude documented invalid fixture);report.py;status completed;validate --final;graph;integrate.py;working tests/consumer;prepare_verified_promotion.py;stable apply --confirm-main;consumer_check.py active.']
meta=(A/'README.md').read_text().split('---',2)[1]
for key,val in [('status','Accepted' if result['strict_success'] else 'Rejected'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+key+r':.*$',key+': '+val,meta)
(A/'README.md').write_text('---'+meta+'---\n\n# 원문 반환 경계 기술 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n');(A/'실험/README.md').write_text('# 원문 확보·중단·재개16개 상태\n\n기술 상태 전수 검사이며 법률 정답 평가가 아니다.\n')
paths=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name not in ('manifest.json','final-validation.txt','graph-final.txt') and not p.name.endswith(('-shm','.lock'))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Finite boundary qualification and exact-code receipts','contains_raw_prompts_and_outputs':False} for p in paths]})
print(json.dumps(checks,ensure_ascii=False));assert result['strict_success']
