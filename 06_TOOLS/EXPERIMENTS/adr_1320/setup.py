from pathlib import Path
import hashlib,json,sys,subprocess
ROOT=Path('/home/jin/8-AGENT')
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1320-genos-embed-env-main'
ART=ADR/'artifacts'; DES=ART/'design'; DES.mkdir(exist_ok=True)
def read(p): return json.loads(Path(p).read_text())
def put(p,v): Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'); release=read(ROOT/active['manifest_path'])
files=release['files']; assert active['generation']==138
assert all(sha(ROOT/n)==h for n,h in files.items())
put(DES/'baseline.json',{'pointer':active,'release':release,'working_files':files})
criteria={'scope':'Only GENOS embedding environment compatibility and optional profile hash; no query/ACL/publication SQL changes',
 'required':['GENOS_EMBED_ID/TOKEN and GENOS_URL aliases resolve gateway without profile/model env',
 'Legacy SERVING_ID/KEY still work; new ID/TOKEN take precedence when both names present',
 'Optional nonempty profile hash must still match; Oracle publication integrity/dimension/normalization preserved',
 'Direct non-gateway endpoint still requires explicit model; LLM environment behavior unchanged',
 'Environment binding changes for all new aliases; no retry, redirects, model discovery or local encoder',
 'Development G19 mapping uses bundled 17-table contract, no external Gold mapping file',
 'One-command installer resolves symlink, validates exact bytes, preserves data/env, rolls back'],
 'real_model_calls':0,'Oracle_mutations':0,'field_deployment':False,'performance_claims':False,
 'upstream_commit':subprocess.check_output(['git','rev-parse','infocz/fde/seungho/integration'],cwd=ROOT,text=True).strip()}
put(DES/'criteria.json',criteria)
for name in ('config','embedder'):
 raw=subprocess.check_output(['git','show',criteria['upstream_commit']+':02-els-qa/core/storage/vdb/'+name+'.py'],cwd=ROOT)
 (DES/('seungho-'+name+'.py')).write_bytes(raw)
m=read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta']='Remove redundant profile env and match user-confirmed GENOS gateway env names'
m['design'].update(hypothesis='ID and token identify the same ingestion encoder; Oracle metadata supplies validation profile without manual hash',primary_metric='All frozen environment/transport/publication and installer contracts pass',success_criteria=criteria['required'],failure_criteria='Wrong endpoint/auth, lost publication/ACL/dimension validation, changed unrelated serving files, or failed replacement/rollback',criteria_frozen_before_run=True)
for arm in m['design']['arms']:
 arm['changes']='Current MAIN138 reference only' if arm['id']=='baseline' else 'Embedding env aliases; optional profile pin; gateway default model genos'
 arm['controls']='Same MAIN138 source/query/vector/ACL/SQL and data generation; no actual model or DB calls'
m['llm_policy']['llm_calls']=[]
m['dataset'].update(name='Synthetic environment and publication contracts',version='20261104-r1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(arm_ids=['integrated'],selection_rule='All frozen technical contracts; no legal question sampling',artifact_path=str((ART/'result.json').relative_to(ROOT)))
reason='Environment configuration audit with synthetic vectors only; retrieval query/ranking/ACL unchanged, no corpus or legal answer quality evaluation'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'integrated',list(files),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'])
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':list(files)})
print(can)
