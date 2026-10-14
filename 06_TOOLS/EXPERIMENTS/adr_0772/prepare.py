from pathlib import Path
import json,hashlib,subprocess,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0772-source-provider-display';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
criteria={'scope':'MAIN57 presentation only: Korean source groups and numbered law titles, contiguous candidate/read batching, identical private-event filtering in editor handoff. No model calls; preserve work-tree transport changes outside this scope.', 'required':['Known external source paths display glossary Korean provider names with numbered titles and no technical path','All 0/1/9/37 titles survive same-result chunks and read groups','Unknown providers and internal sources do not acquire a false institution name','Rejected decisions, errors and tracebacks are absent from public cards and flow inputs; accepted judgments and diagnostics storage remain intact','Mode, request/run/journal boundary, answer stream and scope contracts hold','Every non-workflow serving file equals MAIN57; scoped working workflow equals qualified selected code'], 'matrix':{'counts':[0,1,9,37],'boundaries':['candidate','decision','answer'],'modes':['socketio','final-cards']},'failure':'Any new display, source authorization, streaming or integrity failure blocks promotion; no semantic quality claim.', 'evaluation':'Prospective exhaustive synthetic display matrix, baseline and candidate, 24 combinations each; independent regression contracts.','model_calls':0,'rollback':'MAIN57 and guarded scoped workflow backup'}
assert not (D/'criteria.json').exists();put(D/'criteria.json',criteria)
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';a=read(p);assert a['generation']==57;release=read(R/a['manifest_path']);put(D/'baseline.json',{'pointer':a,'pointer_sha256':sha(p),'manifest':release})
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['scope'];m['design'].update(hypothesis=criteria['scope'],primary_metric='All titles grouped by Korean provider; zero private error leakage; answer bytes unchanged',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['dataset'].update(name='Synthetic source provider display boundaries',version='source-provider-display-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[];m['runs'][0].update(selection_rule='All 24 frozen combinations once after code/runner freeze',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['retrieval_accounting'].update(changed=False,not_applicable_reason='Presentation only');m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason='No retrieval changes or legal evaluation')
for arm in m['design']['arms']:arm.update(changes='Selected MAIN57' if arm['id']=='baseline' else criteria['scope'],controls='Same complete non-display code, model input, answer and data; no LLM calls')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[]);put(A/'실험/manifest.json',m)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','provider-display','--experiment-id',m['experiment_id'],'--arm-id','provider-display','--run-id','run-001']
for n in sorted(release['files']):cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
S=R/'02_BACKEND/lawrag/research/candidates/adr_0772/provider-display/snapshot';delta=[]
for n,h in release['files'].items():
 p=R/n
 if sha(p)!=h:delta.append({'path':n,'working_sha256':sha(p),'selected_sha256':h})
 (S/n).write_bytes((R/release['code_root']/n).read_bytes())
put(D/'preserved-worktree-differences.json',delta)
dictionary=R/'01_DATA/LEXICON/glossary-v1/boundary-20260914-v3/dictionary.sqlite';db=sqlite3.connect(f'file:{dictionary}?mode=ro',uri=True);db.row_factory=sqlite3.Row
entries=[dict(db.execute('select id,source,label,english from entry where id=?',(ident,)).fetchone()) for ident in ['moleg:everyday_terms:25845','moleg:everyday_terms:73745','econedu:public-20260912:row:2887','moleg:everyday_terms:47385']]
put(D/'provider-label-evidence.json',{'dictionary_path':str(dictionary.relative_to(R)),'dictionary_sha256':sha(dictionary),'entries':entries,'mapping':{'krx':'한국거래소','kofia':'한국금융투자협회','law':'법제처','moleg':'법제처'},'law_basis':'User-specified source heading 법제처; MOLEG source registry and glossary collection source. No exact 법제처 glossary headword exists; source heading, not law enactment authority.','scope':'Presentation snapshot only; no new semantic synonym or glossary approval; no runtime SQLite dependency in GENOS editor.'})
print('Frozen criteria; snapshot selected MAIN57; preserved',len(delta),'unrelated working differences')
