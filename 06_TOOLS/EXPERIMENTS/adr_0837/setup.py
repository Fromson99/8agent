from pathlib import Path
import hashlib,json,shutil,subprocess,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0837-comparison-advisory-items';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
P=R/'04_EXPERIMENTS/ADR/ADR-0836-comparison-owned-tools';assert read(P/'실험/manifest.json')['reservation']['status']=='completed'
v=read(P/'artifacts/design/verification-binding-final.json');old=R/v['code_root'];base=read(P/'artifacts/design/baseline.json');put(D/'baseline.json',base);put(D/'data-binding.json',read(P/'artifacts/design/data-binding.json'))
criteria={'hypothesis':'Return LLM field status and explanatory comparison without rejecting citation-presence/status combinations. Keep exact selected citation, side, locator, hash, revision and history integrity.',
'success':['All40 inherited contracts and13 actual service checks pass','All12 status/content combinations preserve model text even without source citation; missing evidence is visible','Partial salvage preserves UNKNOWN explanations','One fresh response for known packet19 reported without adaptive retries'],
'failure':['unknown or altered citation accepted','wrong-side source accepted','unquoted opinion displayed as source quotation','model status/text silently changed','source evidence or failure history lost'],
'limits':{'new_model_calls':1,'repair_calls':0,'test_suite_seconds':600},'in_sample':True,'decision_eligible':False,'quality_certified':False,
'failure_contract':'Model stage retains one bounded repair for malformed or invalid-source proposals. Meaning judgments cause no repair. Source/hash/state failures remain hard, previous originals and failures survive. Render no selected evidence separately.'}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Opinion preservation with source integrity',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='Completed836 observed outputs' if arm['id']=='baseline' else 'Completed836 plus advisory item judgment',controls=['same retrieved sources and model policy','same exact integrity guards'])
m['runs'][0].update(selection_rule='Declared contracts and service checks; known source packet19 once',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='advisory-comparison-items-development',version='20261016-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
m['llm_policy']['llm_calls']=[{'role':'comparison-review','class':'product','model':'qwen/qwen3.8-27b','temperature':0,'repetitions':1}]
reason='Exact source packets already retrieved and fixed; no retrieval/ranking effect measured.';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason;put(A/'실험/manifest.json',m)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0837/connected';cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id',m['experiment_id'],'--arm-id','connected','--run-id','run-001']
for n in v['serving_files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
for n in v['serving_files']:shutil.copy2(old/n,C/'snapshot'/n)
p=C/'snapshot/02_BACKEND/workflow/risk_team_compare_workflow/task_board.py';s=p.read_text()
s=s.replace("            if row['status']=='CONFIRMED' and not row['citations']:raise ValueError('confirmed field requires a read original')\n",'')
s=s.replace("        if item['content_status']!='UNKNOWN' and (not item['difference'].strip() or any(not item[s]['citations'] for s in ('internal','external'))):raise ValueError('content comparison requires both originals')\n",'')
s=s.replace("            # UNKNOWN explanatory prose is not a validated comparative finding.\n            if raw['content_status']!='UNKNOWN':safe=trial", "            safe=trial")
s=s.replace("                'source_complete와 항목 충분성은 다르다. 부분 원문의 필요한 상위 조건·참조가 미확인이면 scope_sufficient=false와 missing에 그 대상을 남긴다. '","                '부분 원문에서 필요한 조건이나 참조가 빠졌다면 missing에 적고, 인용은 실제로 읽은 근거만 선택한다. '")
s=s.replace("lines=['항목별 확인 결과'", "lines=['항목별 LLM 검토 의견'")
s=s.replace("i[s]['status']!='CONFIRMED' or not i[s]['scope_sufficient']", "i[s]['status']!='CONFIRMED' or not i[s]['citations'] or not i[s]['scope_sufficient']")
p.write_text(s)
# Pin the new projection and instructions without changing any native RAG code.
S=C/'snapshot';W=S/'02_BACKEND/workflow';p=W/'risk_team_compare_workflow/manifest.json';x=read(p);x['version']='1.5.2';x['files']={n:sha(W/n) for n in x['files']};put(p,x)
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 x=read(p)
 if 'files' in x:x['files']={n:sha(S/n) for n in x['files']};put(p,x)
p=S/'00_SYSTEM/PIPELINE.json';x=read(p)
for e in x['engines'].values():e['sha256']=sha(S/e['manifest'])
for w in x['workflows']['registered']:w['version']='1.5.2';w['sha256']=sha(S/w['manifest'])
put(p,x)
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'));import adr_candidate;adr_candidate.refresh(C)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
for name in ('run_tests.py','freeze.py','consumer_check.py','live.py','test_judgment.py','test_workflow.py'):
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0836'/name).read_text().replace('adr_0836','adr_0837').replace('ADR-0836-comparison-owned-tools','ADR-0837-comparison-advisory-items').replace('ADR-0836-experiment-v1','ADR-0837-experiment-v1')
 if name=='live.py':s=s.replace('number in (17,19,21)','number in (19,)')
 (R/'06_TOOLS/EXPERIMENTS/adr_0837'/name).write_text(s)
print('837 isolated candidate ready')
