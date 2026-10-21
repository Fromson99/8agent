from pathlib import Path
import json,hashlib,re,tarfile,gzip
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0830-comparison-main-confirmation';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def timing(name):
 text=(A/'artifacts'/(name+'.time')).read_text();n=re.search(r'Elapsed \(wall clock\) time .*?: (\S+)\n',text)[1];parts=list(map(float,n.split(':')))
 return {'seconds':sum(v*60**i for i,v in enumerate(reversed(parts))),'max_rss_kib':int(re.search(r'Maximum resident set size \(kbytes\): (\d+)',text)[1]),'exit_status':int(re.search(r'Exit status: (\d+)',text)[1])}
f=read(D/'freeze.json');cases=read(D/'cases.json');matrices={s:read(A/'artifacts'/('matrix-'+s+'.json')) for s in ('baseline','connected')}
expected={c['case_id'] for c in cases};assert all({c['case_id'] for c in m['cases']}==expected for m in matrices.values())
reg={};fail={}
for s in ('baseline','connected'):
 text=(A/'artifacts'/('regression-'+s+'.log')).read_text();assert re.search(r'6 failed, 208 passed',text),'regression not complete: '+s
 reg[s]=208;fail[s]=re.findall(r'^FAILED ([^\n]+)',text,re.M)
api=(A/'artifacts/api.log').read_text();assert re.search(r'58 passed',api),'API not completed/pass'
replay=read(A/'artifacts/replay-result.json');assert replay['status']=='PASS' and replay['rendered_citations']==6 and replay['journal_unchanged']
parent=read(R/'04_EXPERIMENTS/ADR/ADR-0828-comparison-source-publication/artifacts/design/verification-binding.json')
assert f['serving_files']==parent['serving_files']
cons={s:read(A/'artifacts'/(s+'-consumer-v2.json')) for s in ('baseline','candidate')};times={n:timing(n) for n in ('api','regression-baseline','regression-connected','consumer-baseline','consumer-candidate')}
checks={'all306_finite_contracts':matrices['connected']['passed']==306,
 'zero_new_regression_failures':fail['baseline']==fail['connected'] and len(fail['connected'])==6,
 'retained58_development_contracts':True,'known_failure_source_replay':True,'candidate13_service_checks':len(cons['candidate']['checks'])==13 and all(cons['candidate']['checks'].values()),
 'baseline12_service_checks':len(cons['baseline']['checks'])==12 and all(cons['baseline']['checks'].values()),
 'matrix_resources':all(m['elapsed_seconds']<=60 and m['max_rss_kib']<=2*1024*1024 for m in matrices.values()),
 'api_regression_service_resources':all(t['seconds']<=(180 if n.startswith('consumer') else 600) and t['max_rss_kib']<=12*1024*1024 for n,t in times.items()),
 'frozen_inputs':all(sha(R/n)==h for n,h in f['files'].items()),'frozen_serving':all(sha(R/f['code_root']/n)==h for n,h in f['serving_files'].items()),
 'active_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==read(D/'baseline.json')['pointer_sha256']}
limits=['유한 기술 계약 검사이며 법률 정확도·검색 적합성 개선률을 인증하지 않는다.','실제 모델0회; 합성 제안과 원문/상태 계약만 검사. 실제 Qwen 진단은 완료 ADR0827. 그 실패 자료는 별도 읽기 전용 재표시 검사로 사용.','기존 native direct_note=True 검사6개는 양쪽 동일 실패이며 이번 작업에서 수정하지 않는다.','검증 중 MAIN76 유지; 통과한 같은 코드만 MAIN 승격하며 GENOS는 별도다.']
result={'status':'complete','strict_success':all(checks.values()),'checks':checks,'finite_matrix':{s:{k:v for k,v in m.items() if k!='cases'} for s,m in matrices.items()},'regression_passed':reg,'known_regression_failures':fail,'development_contracts_passed':58,'api_batches':[58],'known_failure_replay':replay,'parent_code_unchanged_from_828':True,'service_checks':{s:len(v['checks']) for s,v in cons.items()},'resources':times,'real_model_calls':0,'quality_certified':False,'limitations':limits,'compared_metric':'Mechanical checks only; unsupported baseline contracts are explicit failures, not legal errors'}
put(A/'artifacts/run-001/result.json',result)
# Keep exact API native journals without duplicating the shared source generation or indices.
archive=A/'artifacts/api-journals.tar.gz'
if not archive.exists():
 with tarfile.open(archive,'w:gz') as tar:
  for p in Path('/tmp/adr0830-api').rglob('*.sqlite'):
   if 'runtime' in p.parts:tar.add(p,arcname=str(p.relative_to('/tmp/adr0830-api')))
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=read(D/'criteria.json')['hypothesis'];next(a for a in m['design']['arms'] if a['id']=='connected')['changes']='Exact completed ADR0828 rev001,342 serving files,unchanged';m['runs'][0].update(artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)),status='complete',sha256=sha(A/'artifacts/run-001/result.json'));m['results'].update(status='complete',by_arm={s:{'status':'complete','finite_passed':v['passed'],'finite_total':306,'regressions_passed':reg[s],'known_failures':6} for s,v in matrices.items()},comparisons=[{'mechanical_contracts_improved':48,'regressed':0,'legal_accuracy_evaluated':False}],usage={'product_model_calls':0,'offline_evaluator_calls':0},latency=times,error_taxonomy=[{'kind':'other','detail':'Same six existing native direct_note=True regression failures in both arms; no new failure'}]);put(A/'실험/manifest.json',m)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
texts=[('Accepted' if result['strict_success'] else 'Rejected')+'. 유한 기술 계약에 한정한 판정. 작업 코드 통합과 실제 MAIN 선택은 별도다.',
 '후속 실패가 성공 근거를 지우고, 전체 source 확장이 비교항목의 원문을 불필요하게 늘렸다.',
 '306개 전체 조합,58개 개발 계약,214개 양쪽 회귀, 실제 서비스12/13개와 자원 한도를 실행 전에 동결했다.',
 '완료0828 rev001342파일을 수정 없이 검증. fields96, packets16, tasks42, partial40, resume64, publication48 전수. 개발 API는 holdout이 아닌 회귀다.',
 'cases.json, freeze.json 및 verification-binding.json. 두 arm의 원문/profile 동일. 실제 모델 호출0.',json.dumps(result,ensure_ascii=False,indent=2),
 'baseline 1.4.1은 기존258계약을 통과했으나 새 원문 반환 계약48개는 미지원이었다. 공통 direct_note=True 6실패의 정확한 이름은 result.json. 검사 기준 변경이나 실패 제외 없음.',
 '매트릭스는 이미 제공된 원문을 소비하며 검색을 실행하지 않는다. 원문 span과 조문 root를 구분한다. 실제 조회는 회귀·서비스 연결 검사에 기록. 시간/RSS는 resources 참조.',
 '시스템의 근거 보존·상태/범위/출처 계약을 확인했다. LLM의 의미 대응·예외 해석 정확도는 별도다.', '\n'.join(limits),
 '통과 후 변경별 작업 코드 통합·동일 코드 검증·hash고정 MAIN승격·활성 서비스 검증을 수행한다. 다른 작업 변경 보존. GENOS별도. rollback은 릴리스receipt와 working-before의 hash기준.',
 'setup.py → freeze.py → matrix.py baseline/connected → run_tests.py → regressions.py → consumer_check.py baseline/candidate → report.py → stable validate/status/graph → integrate.py → working API checks']
meta=(A/'README.md').read_text().split('---',2)[1];meta=re.sub(r'(?m)^status:.*$','status: '+('Accepted' if result['strict_success'] else 'Rejected'),meta);meta=re.sub(r'(?m)^main_wiring:.*$','main_wiring: '+('promotion-candidate' if result['strict_success'] else 'unchanged'),meta);meta=re.sub(r'(?m)^in_sample:.*$','in_sample: false',meta);meta=re.sub(r'(?m)^decision_eligible:.*$','decision_eligible: true',meta)
(A/'README.md').write_text('---'+meta+'---\n\n# 대사 조사 과제와 부분 항목 보존 기술 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{t}' for i,(h,t) in enumerate(zip(heads,texts),1))+'\n')
(A/'실험/README.md').write_text('# 유한 기술 계약306개\n\n법률 질문별 정답 검사가 아닌 고정 계약 전수 검사이므로 questions는 비어 있다. cases.json 각 ID의 실제 결과는 matrix-baseline.json/matrix-connected.json에 기록했다. 개발 API, 공통 회귀, 실제 service 소비자를 별도로 집계했다.\n')
files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p.name!='manifest.json' and not p.name.endswith(('-wal','-shm','.lock')) and 'runtime' not in str(p.relative_to(A))]
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'created_at':m['reservation']['created_at'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Frozen inputs, exact technical observations or raw synthetic journals','contains_raw_prompts_and_outputs':p.suffix=='.gz'} for p in files]})
print(json.dumps({'strict_success':result['strict_success'],'checks':checks},ensure_ascii=False))
