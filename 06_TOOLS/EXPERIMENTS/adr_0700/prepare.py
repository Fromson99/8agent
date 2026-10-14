from pathlib import Path
import json,hashlib,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0700-named-document-menu-preservation';P=R/'02_BACKEND/lawrag/research/candidates/adr_0698/focused';C=R/'02_BACKEND/lawrag/research/candidates/adr_0700/preserved'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
criteria={'hypothesis':'Preserve the explicitly named document directory when title hits only belong to other documents or non-readable nodes; never hide the document or fallback to fulltext.','required':['Explicit named document remains visible when unrelated titles match','No named document and unmatched title stays empty','Named doc plus bare coordinate stays within named doc','Named multi-document batches preserve all named candidates','No named document: broad structural candidates retained','Named inaccessible document plus bare coordinate stays empty','Pagination repeats the same query document scope','No new critical regression'],'model_calls':0,'qualification':'Synthetic probe only; independent new qualification required'}
put(A/'artifacts/design/criteria.json',criteria);m=read(A/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact document and coordinate scope integrity',success_criteria=criteria['required'],failure_criteria='Any new critical failure',criteria_frozen_before_run=True);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['dataset'].update(name='Synthetic named menu and scoped title cases',version='named-menu-v1',frozen_source=str((A/'artifacts/design/criteria.json').relative_to(R)),sha256=sha(A/'artifacts/design/criteria.json'),legal_version_checked=True,reference_version_checked=True);m['runs'][0].update(selection_rule='All new and inherited critical synthetic contracts',artifact_path=str((A/'artifacts/contracts/result.json').relative_to(R)));m['retrieval_accounting']['not_applicable_reason']='Synthetic contracts only';m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='Synthetic contracts only'
for a in m['design']['arms']:a.update(changes='Completed0698 parent' if a['id']=='baseline' else criteria['hypothesis'],controls='Same parent code/data policy; no model calls')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[]);put(A/'실험/manifest.json',m)
pcm=read(P/'candidate.json');ps=P/'revisions'/pcm['revisions'][-1]['revision_id']/'snapshot';cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','preserved','--experiment-id',m['experiment_id'],'--arm-id','preserved','--run-id','run-001']
for f in pcm['files']:
 if (R/f['target_path']).is_file():cmd+=['--source',f['target_path']]
subprocess.run(cmd,cwd=R,check=True)
for f in pcm['files']:
 name=f['target_path'];t=C/'snapshot'/name;t.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ps/name,t)
 if not (R/name).exists():subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',name,'--upstream-state','absent'],cwd=R,check=True)
p=C/'snapshot/02_BACKEND/semantic_runtime/legal_agent/structure_query.py';s=p.read_text();assert 'if query and not title_hits:' in s;s=s.replace('if query and not title_hits:', 'if query and not keys:');p.write_text(s)
subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/EXPERIMENTS/adr_0689/pin_engines.py',str(C/'snapshot')],cwd=R,check=True)
print('Isolated generic query-batch document scope fix')
