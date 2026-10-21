from pathlib import Path
import json,hashlib,subprocess,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0912-answer-first-user-followup';D=A/'artifacts/design';T=Path(__file__).parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();put=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
before=json.loads((D/'working-before.json').read_text());drift=[n for n,h in before.items() if sha(R/n)!=h]
assert drift==['06_TOOLS/pipeline.py'],drift
shutil.copy2(D/'working-before.json',D/'working-before-setup.json');put(D/'working-before.json',{n:sha(R/n) for n in before})
put(D/'preflight-rebase.json',{'reason':'Concurrent unrelated pipeline CLI edit made upstream freeze fail; no model calls or software tests had executed. Preserve failed candidate snapshots/partial revision and failed test-launch receipt. Both replacement arms use the same current CLI.','drift':drift,'prior_hashes':{n:before[n] for n in drift},'new_hashes':{n:sha(R/n) for n in drift},'replacements':['baseline-r1','answer-first-r1']})
for arm in ('baseline','answer-first'):
 cmd=[sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id',arm+'-r1','--experiment-id','ADR-0912-experiment-v1','--arm-id',arm,'--run-id','run-001']
 for n in before:cmd+=['--source',n]
 subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
 if arm=='answer-first':
  root=R/'02_BACKEND/lawrag/research/candidates/adr_0912'
  for n in ['00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json']+['02_BACKEND/semantic_runtime/legal_agent/'+x+'.py' for x in ('law_candidates','law_navigation','evidence_inventory','completion_execution')]:
   shutil.copy2(root/'answer-first/snapshot'/n,root/'answer-first-r1/snapshot'/n)
p=T/'seal.py';s=p.read_text().replace("/arm;S=C/'snapshot'","/(arm+'-r1');S=C/'snapshot'").replace("'candidate_id':arm,","'candidate_id':arm+'-r1',");p.write_text(s)
