from pathlib import Path
import hashlib,json,re,xml.etree.ElementTree as ET
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0926-connected-source-release-qualification';D=A/'artifacts/design';P=R/'04_EXPERIMENTS/ADR/ADR-0925-source-lead-exact-observation';Q=R/'04_EXPERIMENTS/ADR/ADR-0924-source-lead-parent-handoff'
read=lambda p:json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
b=read(D/'binding.json');f=read(D/'freeze.json');base=read(D/'baseline.json');preview=read(A/'artifacts/packager-preview.json');integration=read(D/'integration.json');known=read(P/'artifacts/run-001/result.json');prior=read(Q/'artifacts/checks/test-disposition.json')
staged=dict(base['manifest']['files'])
for x in preview['changes']:
    if x['after'] is None:staged.pop(x['path'],None)
    else:staged[x['path']]=x['after']
suites=list(ET.parse(A/'artifacts/tests.xml').iter('testsuite'))
drift=read(D/'concurrent-working-only.json')['preserved'];names={x['path'] for x in read(D/'working-deltas.json')}
checks={'eight_finite_tests_pass':sum(int(x.get('tests',0)) for x in suites)==8 and all(int(x.get('failures',0))+int(x.get('errors',0))==0 for x in suites),
 'frozen_inputs_exact':all(sha(R/n)==h for n,h in f['files'].items()),'actual_packager_complete_inventory':staged==b['serving_files'],
 'declared_release_deltas_exact':[{k:v for k,v in x.items() if k!='reason'} for x in preview['changes']]==[{k:v for k,v in x.items() if k!='reason'} for x in integration['changes']],
 'parent_154_passes_same_product':prior['passed_unique_contracts']==154 and prior['same_serving_hashes_before_and_after_test_only_repairs'],
 'known_live_originals_and_consumer_integrity':known['all_stored_spans_match'] and all(known['arms']['observed']['consumer_checks'].values()),
 'working_integration_exact_preserving_concurrent_files':all(sha(R/n)==(drift[n]['current'] if n in drift else h) for n,h in staged.items()),
 'candidate_actual_service':all(read(A/'artifacts/candidate-consumer.json')['checks'].values()),'working_actual_service':all(read(A/'artifacts/working-consumer.json')['checks'].values()),
 'resource_bounds':all(read(A/('artifacts/resource-'+x+'.json'))['returncode']==0 and read(A/('artifacts/resource-'+x+'.json'))['stop_reason'] is None for x in ('tests','preview','candidate','working')),
 'pointer_unchanged':read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']}
assert all(checks.values()),checks
remaining=known['limitations']+[f'{len(drift)} concurrent working-only serving files are preserved and excluded from this exact qualified release.','Global ADR graph has pre-existing unrelated errors, separately recorded; this ADR final validation must pass.']
result={'status':'complete','strict_success':True,'checks':checks,'new_finite_tests':8,'retained_tests':154,'technical_tests':162,'inherited_failures':prior['inherited_failures'],'legacy_deselected':prior['legacy_deselected'],'qualification_kind':'Finite software boundaries and actual release closure; no legal holdout','legal_holdout':False,'model_calls':0,'serving_files':len(staged),'working_deltas':len(names),'known_live_observation':{'path':str((P/'artifacts/run-001/result.json').relative_to(R)),'sha256':sha(P/'artifacts/run-001/result.json')},'remaining':remaining,'genos_executed':False};put(A/'artifacts/run-001/result.json',result)
m=read(A/'실험/manifest.json');m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'));m['results'].update(status='complete',by_arm={'qualified':{'status':'complete','strict_success':True,'checks':checks}},usage={'product_model_calls':0,'offline_evaluator_calls':0},error_taxonomy=[{'kind':'retained_limitations','details':remaining}])
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
    p=A/'실험'/q['file'];parts=['run-001 / qualified; immutable completed0925 product.','연결 원문을 함께 선택하고 문서 내 용어 추가 탐색을 구현·실행한다.','Finite software boundaries; no legal gold.','design/binding.json, qualification-tests.json, freeze.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\nNo new retrieval evaluation; known parent ledger preserved.','No new model calls. Known parent925 observation remains in-sample.','No model repair or rerun.','Eight independent boundary cases, retained154 technical passes, actual stable packager census and candidate/working service consumer.',json.dumps(result,ensure_ascii=False)]
    p.write_text('# 연결 원문 경계 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,parts),1))+'\n');q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
meta=(A/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:
    if re.search(r'(?m)^'+k+':',meta):meta=re.sub(r'(?m)^'+k+r':.*$',k+': '+v,meta)
    else:meta+='\n'+k+': '+v+'\n'
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
parts=['Accepted for finite software qualification. Known legal answer is not certified.','Connected term/reference candidates stopped at child return; bound non-citation leads now reach parent for original reading and joint review.',json.dumps(read(D/'criteria.json'),ensure_ascii=False),'Eight independent finite source/side/state/capacity boundaries and actual complete packager inventory; exact completed candidate reused.','Completed0924 bridged rev005; current MAIN88 data/profile/model. No product changes after live observation.',json.dumps(result,ensure_ascii=False),'Known ratio-direction error and internal-source gap remain. One inherited prefetch test expectation fails equally in control; legacy deselection retained.','8 new +154 retained passing checks. No additional model calls. Parent known query15calls/693seconds.','Acquired original, exploration lead and final legal judgment are distinct states.','\n'.join(remaining),'Activate exact qualified local release after final validator and graph check. Preserve MAIN88 rollback; actual selected service verification required. GENOS separate.','prepare; guarded tests; packager preview; integrate; candidate/working consumers; report; finalvalidate/graph; prepare/apply; activeconsumer; completion.']
(A/'README.md').write_text('---'+meta+'---\n\n# 연결 원문 탐색 릴리스 검증\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,parts),1))+'\n')
(A/'실험/README.md').write_text('# 검증 인덱스\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
put(A/'artifacts/manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-0926','files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Finite connected-source software qualification','contains_raw_prompts_and_outputs':False} for p in (A/'artifacts').rglob('*') if p.is_file() and p!=A/'artifacts/manifest.json']})
print('Qualified162 passing checks; inherited failures disclosed; exact serving closure verified')
