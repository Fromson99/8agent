from pathlib import Path
import json,hashlib,sys,shutil
ROOT=Path('/home/jin/8-AGENT');ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1323-genos-oracle-startup-import-main'
ART=ADR/'artifacts';DES=ART/'design';DES.mkdir()
def read(p):return json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
a=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');r=read(ROOT/a['manifest_path']);assert a['generation']==139
working={n:sha(ROOT/n) for n in r['files']}
put(DES/'baseline.json',{'pointer':a,'release':r,'working_files':working,'preexisting_working_changes':[n for n,h in working.items() if h!=r['files'][n]]})
criteria={'change':['08_DEPLOYMENT/GENOS/start_sse.py','08_DEPLOYMENT/GENOS/stream_app.py'],
 'required':['MAIN139 clean subprocess with DP=oracle and no PYTHONPATH reproduces screenshot failure',
 'Corrected exact start command works without PYTHONPATH from root and absolute path from another directory',
 'DP=oracle startup --check and actual HTTP health, SSE_CHECK, JSON PING start without Oracle or model credentials',
 'Direct stream_app import works without a preloaded semantic_runtime',
 'Non-Oracle startup and existing single-worker/port/stream behavior preserved',
 'Only two startup files differ from selected MAIN139; existing multiturn workspace changes preserved',
 'No disabled NFS validation, no new dependencies, no DB/model calls',
 'Same one-command TRANSFER symlink install, repeat, code gate and rollback pass'],
 'image_evidence':'User screenshot: start_sse.py line19 -> genos_diagnostics.py line286 -> ModuleNotFoundError semantic_runtime',
 'field_serving_id':'623 (screenshot only, deployed commit unknown)','new_models':0,'new_Oracle_calls':0}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']='Initialize backend module path before Oracle diagnostics, no environment workaround required'
m['design'].update(hypothesis='Standalone startup omits backend path before Oracle log imports',primary_metric='Clean subprocess startup and actual local HTTP probes pass',success_criteria=criteria['required'],failure_criteria='Import failure, resource eager loading, altered diagnostics validation or unrelated changes',criteria_frozen_before_run=True)
for arm in m['design']['arms']:arm.update(changes='Reference MAIN139' if arm['id']=='baseline' else 'Move backend path registration before log installation in two entrypoints',controls='Same MAIN139 code, environment, Oracle/native SQL/embedding contracts; no real DB/model')
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='Screenshot startup command and synthetic local HTTP probes',version='20261104-r1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(selection_rule='All frozen startup/HTTP/install checks',artifact_path=str((ART/'result.json').relative_to(ROOT)))
reason='Startup import ordering audit; no retrieval policy changes or legal question evaluation'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'integrated',list(r['files']),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001'])
# Restore only the isolated copy to the selected MAIN; keep concurrent working
# changes in the user's workspace intact and out of this startup-only release.
for n,h in r['files'].items():
 assert sha(ROOT/r['code_root']/n)==h
 shutil.copyfile(ROOT/r['code_root']/n,can/'snapshot'/n)
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':list(r['files'])})
print(can,'preexisting workspace differences',sum(working[n]!=h for n,h in r['files'].items()))
