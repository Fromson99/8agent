from pathlib import Path
import hashlib,json,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0836-comparison-owned-tools';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
P=R/'04_EXPERIMENTS/ADR/ADR-0835-comparison-llm-judgment';assert read(P/'실험/manifest.json')['reservation']['status']=='completed'
v=read(P/'artifacts/design/verification-binding-final.json');old=R/v['code_root'];base=read(P/'artifacts/design/baseline.json');put(D/'baseline.json',base);put(D/'data-binding.json',read(P/'artifacts/design/data-binding.json'))
criteria={'hypothesis':'Model selects only a verified location and a research question; host deterministically maps a reference locator to follow_reference, an owning locator to read_node and no locator to search_text.',
'success':['All exact-source/ACL/hash/state guards and835semantic advisory behavior retained','No model operation/anchor field required; no inferred or fabricated locator','43 prior regression expectations migrated only for removed wire operation choices; normal/failure/restart/duplicate remain','All3 fixed known packets receive one fresh model response; report remaining errors without adaptive reruns','Actual data service13checks pass'],
'failure':['unknown location accepted','wrong-side source accepted','model text or semantic verdict rewritten','source evidence or failure history lost'],
'limits':{'new_model_calls':3,'repair_calls':0,'test_suite_seconds':600},'in_sample':True,'decision_eligible':False,'quality_certified':False,
'failure_contract':'Existing model stage owns maximum one structural repair in product; source/ACL/hash/revision failures remain hard. Semantic judgments remain advisory; no new retry owner. Old declarations and results remain immutable.'}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='First-attempt judgment with host-owned research tools',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='Completed835 observed outputs' if arm['id']=='baseline' else 'Completed835 plus host-owned operation from witnessed locator',controls=['same retrieved sources and model policy','same exact integrity guards'])
m['runs'][0].update(selection_rule='Declared contract tests, service checks, known source packets17/19/21 each once',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='host-owned-comparison-tools-development',version='20261016-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
m['llm_policy']['llm_calls']=[{'role':'comparison-review','class':'product','model':'qwen/qwen3.8-27b','temperature':0,'repetitions':1}]
reason='Exact source packets already retrieved and fixed; no retrieval/ranking effect measured.';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason;put(A/'실험/manifest.json',m)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0836/connected';cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id',m['experiment_id'],'--arm-id','connected','--run-id','run-001']
for n in v['serving_files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for n in v['serving_files']:shutil.copy2(old/n,C/'snapshot'/n)
p=C/'snapshot/02_BACKEND/workflow/adapters/projection.py';s=p.read_text();s=s.replace("            props.pop('anchor_ids');result['required'].remove('anchor_ids')", "            for name in ('anchor_ids','operation'):\n                props.pop(name);result['required'].remove(name)")
s=s.replace("                    task['anchor_ids']=[origin] if origin in source_ids else []", "                    task['anchor_ids']=[origin] if origin in source_ids else []\n                    task['operation']=('follow_reference' if locator.get('reference_id') else 'read_node') if locator else 'search_text'")
p.write_text(s)
p=C/'snapshot/02_BACKEND/workflow/risk_team_compare_workflow/task_board.py';s=p.read_text();s=s.replace("                '필요한 부족만 next_tasks에 넣는다. 실제 locator는 직접 read_node/locate_provision/follow_reference, 정의는 lookup_definition, 범위가 명확하면 search_subtree/search_structure, 나머지는 search_text를 선택한다. '","                '정말 필요한 추가 원문만 next_tasks에 넣는다. 제공된 locator에서 읽을 위치를 선택하고 조사할 내용을 query에 적는다. 도구와 근거 연결은 시스템이 정한다. '")
p.write_text(s)
# Pin the new projection and instructions without changing any native RAG code.
S=C/'snapshot';W=S/'02_BACKEND/workflow';p=W/'risk_team_compare_workflow/manifest.json';x=read(p);x['version']='1.5.1';x['files']={n:sha(W/n) for n in x['files']};put(p,x)
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 x=read(p)
 if 'files' in x:x['files']={n:sha(S/n) for n in x['files']};put(p,x)
p=S/'00_SYSTEM/PIPELINE.json';x=read(p)
for e in x['engines'].values():e['sha256']=sha(S/e['manifest'])
for w in x['workflows']['registered']:w['version']='1.5.1';w['sha256']=sha(S/w['manifest'])
put(p,x)
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'));import adr_candidate;adr_candidate.refresh(C)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
for name in ('run_tests.py','freeze.py','consumer_check.py','live.py','test_judgment.py','test_workflow.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0835'/name).read_text().replace('adr_0835','adr_0836').replace('ADR-0835-comparison-llm-judgment','ADR-0836-comparison-owned-tools').replace('ADR-0835-experiment-v1','ADR-0836-experiment-v1')
 if name=='test_judgment.py':s=s.replace("'operation':'read_node',",'')
 if name=='test_workflow.py':
  s=s.replace("'operation':'read_node',",'').replace("'operation':operation,",'')
  s=s.replace("['locate_provision','lookup_definition','follow_reference','search_structure','search_subtree','search_text']", "['read_node','follow_reference','search_text']")
 (R/'06_TOOLS/EXPERIMENTS/adr_0836'/name).write_text(s)
print('836 isolated candidate ready')
