from pathlib import Path
import json,hashlib,re
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0874-bounded-followup-continuation';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
m=read(A/'실험/manifest.json');assert m['reservation']['status']=='in_progress'
f=read(D/'freeze.json');C=R/f['code_root'];base=read(D/'baseline.json');before=read(D/'working-before.json');cm=read(R/f['candidate']['manifest_path'])
log=(A/'artifacts/candidate-api.log').read_text();match=re.search(r'(\d+) passed',log);consumer=read(A/'artifacts/candidate-consumer.json')
changes=[n for n,h in before.items() if sha(C/n)!=h]
product=['02_BACKEND/workflow/risk_team_compare_workflow/task_board.py','02_BACKEND/semantic_runtime/app.py','08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py']
allowed=lambda n:n in product or n=='00_SYSTEM/PIPELINE.json' or n.startswith('02_BACKEND/ENGINES/') and n.endswith('.json') or n in ('02_BACKEND/workflow/risk_team_compare_workflow/manifest.json','02_BACKEND/workflow/internal_basis_discovery_workflow/manifest.json')
checks={'candidate_tests_pass':bool(match) and not re.search(r'\b\d+ failed|ERROR collecting',log),
 'candidate_api_consumer10':consumer['status']=='PASS' and len(consumer['checks'])==10 and all(consumer['checks'].values()),
 'frozen_candidate_and_runner':all(sha(R/n)==h for n,h in f['files'].items()),
 'latest_MAIN83_working_preserved':all(sha(R/n)==h for n,h in before.items()),
 'selected_pointer_unchanged':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer_sha256'],
 'only_reviewed_product_and_pins_changed':all(allowed(n) for n in changes) and all(n in changes for n in product),
 'unchanged_host_compression':all(sha(C/n)==before[n] for n in ('02_BACKEND/semantic_runtime/legal_agent/minimal_output.py','02_BACKEND/semantic_runtime/legal_agent/decision_projection.py','02_BACKEND/semantic_runtime/legal_agent/wire_schema.py')),
 'resource_limits_respected':all(read(A/'artifacts'/n)['returncode']==0 and read(A/'artifacts'/n)['stop_reason'] is None for n in ('resource-candidate-tests-001.json','resource-candidate-consumer-001.json')),
 'no_model_calls_in_qualification':consumer['model_calls']==0,
 'workflow_versions':read(C/'02_BACKEND/workflow/risk_team_compare_workflow/manifest.json')['version']=='1.9.1' and read(C/'02_BACKEND/workflow/internal_basis_discovery_workflow/manifest.json')['version']=='1.0.0'}
assert all(checks.values()),checks
result={'status':'complete','strict_success':True,'checks':checks,'passed':int(match[1]),'failed':0,'candidate':f['candidate'],'changes':changes,'model_calls':0,'quality_certified':False,'limits':read(D/'criteria.json')['limits'],'notes':{'limitations':['Finite software contracts only; no legal holdout/accuracy certification.','Real model candidate workflow planned in separate ADR before MAIN promotion.','Unresolved originals remain partial and acquisition cap2 remains unchanged.','GENOS inaccessible; no field deployment claim.']}}
put(A/'artifacts/run-001/result.json',result)
m['runs'][0].update(status='complete',sha256=sha(A/'artifacts/run-001/result.json'));m['results'].update(status='complete',by_arm={'baseline':{'status':'complete','basis':'Completed0873 actual observation, no rerun'},'qualified':{'status':'complete','strict_success':True,'checks':checks}},usage={'product_model_calls':0,'offline_evaluator_calls':0},error_taxonomy=[])
heads=['실행 메타','사용자 질문 원문','기준답변 — 채점 전용, 제품 입력 비공개','제품 입력을 구성한 원값','제품 모델 호출 — run·arm별 실제 원문','중간 LLM 호출 — router/compiler/verifier/repair','채점 호출과 반복 판정','사례 최종 판정']
for q in m['questions']:
 p=A/'실험'/q['file'];parts=['run-001 / qualified finite technical census; completed0873 is diagnostic parent.','위원회 대사 중 첫 추가 검색이 비면 다른 독립 과제가 남아도 종료되는 실제0873 경계.', 'Approved legal gold absent; test software contracts only.','design/criteria.json, freeze.json, execution-plan.json, release-rebase.json.\n\n### 회수·탈락 단계 원장 — run·arm별\n\nNot applicable: finite software state tests, no retrieval/model-effect experiment.', '0calls; test doubles are explicitly synthetic.','0calls; existing recovery owners/caps retained.','0judgecalls; assertions verify state, evidence hashes, budgets, duplicate/resume and API consumers.', 'All technical checks passed; real model behavior is a separately frozen follow-up, not certified here.']
 p.write_text('# '+q['case_id']+'\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,parts),1))+'\n');q['sha256']=sha(p)
put(A/'실험/manifest.json',m)
meta=(A/'README.md').read_text().split('---',2)[1]
for k,v in [('status','Accepted'),('main_wiring','promotion-candidate'),('in_sample','false'),('decision_eligible','true')]:meta=re.sub(r'(?m)^'+k+r':.*$',k+': '+v,meta)
heads=['결정 요약','문제와 변경 전 구조','가설과 사전 판정 기준','실험 설계','데이터·모델·재현성','결과','사례별 오류 분석','비용·지연·회수 규모','해석','한계와 일반화 가능 범위','운영 결정·롤백 조건','재현 명령']
parts=['Accepted technical promotion candidate; actual live follow-up required before apply.','0873: completed lookup returned NOT_FOUND/PARTIAL; parent mislabeled completion and stopped remaining independent tasks after one non-progress result.',json.dumps(read(D/'criteria.json'),ensure_ascii=False),'One guarded worker per test; immutable711-file code, shared current data. Exact acquisitions coalesced across fields; original two-attempt cap retained.','Frozen design, code revision, manifest and test hashes. Model0; software census is not legal holdout.',json.dumps(result,ensure_ascii=False),'Empty, successful, failed, wrong receipt, duplicate, resume, budget, authority/hash, output consumers checked. Old evidence never erased or promoted to new acquired evidence.','No data copy. Resource receipts retain peaks; unit suite2GiB cap, actual selected data consumer8GiB cap.','Acquisition execution and original availability are distinct; legal sufficiency remains model/user judgment.', '\n'.join(result['notes']['limitations']),'User authorized latest MAIN preserved; candidate isolated until live validation and stable hash-bound prepare/apply. Rollback previous selected release; no automatic old-state rebinding.','setup.py; pins.py; seal.py; preview.py; resource_guard run_validation.py candidate; resource_guard consumer.py candidate; report.py; validate; status completed; validate --final; graph.']
(A/'README.md').write_text('---'+meta+'---\n\n# 대사 후속 조사 상태·실행 계약\n\n'+'\n\n'.join(f'## {i}. {h}\n\n{x}' for i,(h,x) in enumerate(zip(heads,parts),1))+'\n')
(A/'실험/README.md').write_text('# 기술 검사\n\n'+'\n'.join('- ['+q['case_id']+']('+q['file']+')' for q in m['questions'])+'\n')
out=A/'artifacts/manifest.json';files=[p for p in (A/'artifacts').rglob('*') if p.is_file() and p!=out and not p.name.endswith(('-wal','-shm'))]
put(out,{'schema_version':'adr-artifacts-v1','adr_id':m['adr_id'],'files':[{'path':str(p.relative_to(R)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Exact candidate technical validation','contains_raw_prompts_and_outputs':False} for p in files]})
print('PASS',result['passed'],'tests;10consumerchecks;'+str(len(changes))+'reviewedworkingdeltas')
