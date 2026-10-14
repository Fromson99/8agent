from pathlib import Path
import json,hashlib,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0702-exception-state-wire-contract';P=R/'02_BACKEND/lawrag/research/candidates/adr_0700/preserved';C=R/'02_BACKEND/lawrag/research/candidates/adr_0702/coupled'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
criteria={'hypothesis':'Couple explicit exception list and its status in provider wire alternatives; never auto-edit model semantics. Empty list stays uncertainty, not a no-exception assertion.', 'required':['Nonempty source exceptions require SOURCE_EXCEPTIONS in wire','Empty exception list requires NOT_ESTABLISHED in wire','Null rule remains supported','Condition logic and provenance validators unchanged','No new critical regression'],'model_calls':0,'qualification':'Synthetic only; same-code independent public qualification required'}
put(A/'artifacts/design/criteria.json',criteria);m=read(A/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact document and coordinate scope integrity',success_criteria=criteria['required'],failure_criteria='Any new critical failure',criteria_frozen_before_run=True);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['dataset'].update(name='Synthetic exception list and status wire cases',version='exception-wire-v1',frozen_source=str((A/'artifacts/design/criteria.json').relative_to(R)),sha256=sha(A/'artifacts/design/criteria.json'),legal_version_checked=True,reference_version_checked=True);m['runs'][0].update(selection_rule='All new and inherited critical synthetic contracts',artifact_path=str((A/'artifacts/contracts/result.json').relative_to(R)));m['retrieval_accounting']['not_applicable_reason']='Synthetic contracts only';m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='Synthetic contracts only'
for a in m['design']['arms']:a.update(changes='Completed0700 parent' if a['id']=='baseline' else criteria['hypothesis'],controls='Same parent code/data policy; no model calls')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[]);put(A/'실험/manifest.json',m)
pcm=read(P/'candidate.json');ps=P/'revisions'/pcm['revisions'][-1]['revision_id']/'snapshot';cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','coupled','--experiment-id',m['experiment_id'],'--arm-id','coupled','--run-id','run-001']
for f in pcm['files']:
 if (R/f['target_path']).is_file():cmd+=['--source',f['target_path']]
subprocess.run(cmd,cwd=R,check=True)
for f in pcm['files']:
 name=f['target_path'];t=C/'snapshot'/name;t.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ps/name,t)
 if not (R/name).exists():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',name,'--upstream-state','absent'],cwd=R,check=True)
p=C/'snapshot/02_BACKEND/semantic_runtime/legal_agent/completion_contracts.py';s=p.read_text();start=s.index('def rule_schema(');end=s.index('\n\ndef rule_errors',start);part=s[start:end];part=part.replace("return {'anyOf':[{'type':'null'},obj({", "rule = obj({");assert part.endswith("    })]}\n");part=part[:-len("    })]}\n")]+"""    })
    # Full alternatives bind the redundant state to its evidence list before
    # generation. The model still chooses the exceptions and their sources.
    branches=[]
    for status,bounds in [('SOURCE_EXCEPTIONS',{'minItems':1}),('NOT_ESTABLISHED',{'maxItems':0})]:
        branch=deepcopy(rule)
        branch['properties']['exception_status']={'type':'string','const':status}
        branch['properties']['exceptions'].update(bounds)
        branches.append(branch)
    return {'anyOf':[{'type':'null'},*branches]}
""";s=s[:start]+part+s[end:];s=s.replace('exception status must retain source-backed exceptions or uncertainty','exception_status must be SOURCE_EXCEPTIONS when exceptions is nonempty; an empty list requires NOT_ESTABLISHED, never a no-exception assertion');p.write_text(s)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0689/pin_engines.py',str(C/'snapshot')],cwd=R,check=True)
print('Isolated generic query-batch document scope fix')
