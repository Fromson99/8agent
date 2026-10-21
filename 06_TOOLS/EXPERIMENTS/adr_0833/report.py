from pathlib import Path
import hashlib,json,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0833-compact-delivery-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(D/'freeze.json');criteria=read(D/'criteria.json');base=read(D/'baseline.json')
mat={s:read(A/'artifacts'/('matrix-'+s+'.json')) for s in ('baseline','connected')}
cons={s:read(A/'artifacts'/(s+'-consumer-v2.json')) for s in ('baseline','candidate')}
retained=criteria['retained_development'];dev=read(R/retained['result'])
parent=read(R/'04_EXPERIMENTS/ADR/ADR-0832-compact-evidence-delivery/artifacts/design/verification-binding-final.json')
times={}
for s in cons:
 t=(A/'artifacts'/('consumer-'+s+'.time')).read_text();v=re.search(r'Elapsed \(wall clock\) time .*?: (\S+)\n',t)[1]
 parts=list(map(float,v.split(':')))
 times[s]={'seconds':sum(v*60**i for i,v in enumerate(reversed(parts))),'max_rss_kib':int(re.search(r'Maximum resident set size \(kbytes\): (\d+)',t)[1]),'exit':int(re.search(r'Exit status: (\d+)',t)[1])}
expected={c['case_id'] for c in read(D/'cases.json')}
checks={'all160_candidate_cases':mat['connected']['passed']==160 and all({r['case_id'] for r in m['cases']}==expected for m in mat.values()),
 'no_false_positive':all(m['false_positives']==0 for m in mat.values()),'baseline120_explicit':mat['baseline']['passed']==120,
 'same_completed_parent342files':f['serving_files']==parent['serving_files'],
 'retained317_tests_and_six_existing_failures':sha(R/retained['result'])==retained['sha256'] and dev['development_checks_passed'] and len(dev['common_failures'])==6,
 'both13service_checks':all(len(v['checks'])==13 and all(v['checks'].values()) for v in cons.values()),
 'unchanged_publication_guard':f['serving_files']['02_BACKEND/semantic_runtime/legal_agent/unified_publication.py']==base['manifest']['files']['02_BACKEND/semantic_runtime/legal_agent/unified_publication.py'],
 'matrix_resources':all(m['elapsed_seconds']<60 and m['max_rss_kib']<2*1024**2 for m in mat.values()),
 'service_resources':all(t['seconds']<180 and t['max_rss_kib']<12*1024**2 and t['exit']==0 for t in times.values()),
 'frozen_inputs':all(sha(R/n)==h for n,h in f['files'].items()),'frozen_serving':all(sha(R/f['code_root']/n)==h for n,h in f['serving_files'].items()),
 'active_MAIN77_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256']}
limits=['Finite software contract verification only; no retrieval or legal accuracy certification.',
 'Retained317 developmental tests and six known failures are reused only after verifying identical342files; not counted as new holdout.',
 'One matrix fixture preflight failed before any case observation: missing exact text member. Source and freeze preserved; corrected fixture before matrix measurement; product and160criteria unchanged.',
 'Actual831 remains a failed request. In-memory reconstruction proves its receipt cause but does not publish or resume the old request.',
 'External model0calls in this qualification. Fresh full workflow and GENOS are separate.']
result={'status':'complete','strict_success':all(checks.values()),'checks':checks,'finite_matrix':{s:{k:v for k,v in m.items() if k!='cases'} for s,m in mat.items()},
 'retained_development':retained,'service_checks':{s:len(v['checks']) for s,v in cons.items()},'resources':times,'real_model_calls':0,'quality_certified':False,'limitations':limits}
put(A/'artifacts/run-001/result.json',result)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'))
m['results'].update(status='complete',by_arm={s:{'status':'complete','finite_passed':v['passed'],'finite_total':160} for s,v in mat.items()},comparisons=[{'mechanical_contracts_improved':40,'regressed':0,'legal_accuracy_evaluated':False}],usage={'product_model_calls':0,'offline_evaluator_calls':0},latency=times,error_taxonomy=[{'kind':'other','detail':'Existing six developmental direct_note failures unchanged; fixture preflight recorded before matrix observation.'}])
put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[('Accepted' if result['strict_success'] else 'Rejected')+'. 고정 기술 계약에 한정한 판정.',
 'MAIN77 compact ASSESS 원문 옵션 전달은 기록하지 않아 후속 child의 최종 발행이 실패했다.',criteria['hypothesis'],
 '길이5×Unicode2×줄수2×재결속2×출처범위4=160 전수. 실제 데이터의 서비스13항목을 두 arm으로 검사. 완료832의317통과와 기존6실패는 동일 코드 지문으로 연결한다.',
 'freeze.json의342파일, 같은 profile/data. 실제 모델 호출 없음. known831진단은 개발 자료로 명시한다.',json.dumps(result,ensure_ascii=False,indent=2),
 '기준은 새 receipt 기능40조합을 지원하지 않는다. 후보는 정확 원문만 기록하며 foreign/unread120조합에 오수락 없음. 기존 발행 검사를 수정하지 않았다.',
 'artifacts의 시간/RSS, matrix별 전체 조합을 보존했다. 검색/정확도/실제 모델 비용 차이 미측정.',
 '기술 결함 수정의 범위에서 통과. 외규·내규의 의미적 대응 및 모델의 예외 판단 품질을 뜻하지 않는다.',
 '\n'.join(limits),'변경33파일(구현2와pin31)만 작업 코드 통합→동일코드 API→hash고정승격→활성포인터와 서비스 확인. GENOS 별도.',
 'setup.py;freeze.py;matrix.py baseline/connected;consumer_check.py baseline/candidate;report.py;stable validate/status/graph;integrate.py;working checks;prepare_promotion.py;stable apply --confirm-main;consumer_check.py active']
meta=(A/'README.md').read_text().split('---',2)[1]
for key,value in [('status','Accepted' if result['strict_success'] else 'Rejected'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+key+r':.*$',key+': '+value,meta)
(A/'README.md').write_text('---'+meta+'---\n\n# Compact 원문 전달 기록 고정 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
(A/'실험/README.md').write_text('# 기술 계약160조합\n\n법률 질문 정답 검사가 아닌 원문 전달 기술 계약 전수 검사다. matrix별 모든 case ID와 서비스 소비자 결과를 보존한다.\n')
paths=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm','.lock')) and '-runtime/' not in str(p)]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen technical census and service receipts','contains_raw_prompts_and_outputs':False} for p in paths]})
print(json.dumps({'strict_success':result['strict_success'],'checks':checks}))
