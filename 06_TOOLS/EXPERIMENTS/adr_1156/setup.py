from common import *
import sys,shutil
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert active['generation']==110
release=read(ROOT/active['manifest_path']);parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1154-ontology-selection-release-receipt/artifacts/design/freeze.json')
files=list(parent['files'])+['03_FRONTEND/APPS/legal-knowledge-streamlit/app.py','03_FRONTEND/APPS/legal-knowledge-streamlit/site_design_app.py','06_TOOLS/pipeline.py']
put(DES/'baseline.json',{'pointer':active,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':release,'working_files':{n:sha(ROOT/n) if (ROOT/n).is_file() else None for n in files}})
criteria={'hypothesis':'Source-bound reviewed recipes can be compiled offline, published atomically and consumed by the existing RAG through source-anchor lookup without automatic approval, runtime composition or changes to default OFF.',
'primary_metric':'Prospective synthetic lifecycle and failure matrix, actual selected-inventory nonempty-source execution, UI and SQLite/Oracle consumer verification.',
'success_criteria':'All new checks pass; immutable source/revision/approval binding; unapproved/stale/out-of-scope data excluded; idempotent publish; unknown writes reconciled; OFF no ontology I/O; known original path selection and SEARCH/reselection preserved; schema shipped; latest MAIN baseline preserved outside declared changes.',
'failure_criteria':'New regression, automatic approval or source inference, secret exposure, wrong revision/ACL, silent runtime compile or uncontrolled retries blocks qualification.',
'matrix':['source/hash/quote/DAG validation','draft create/revise/reject/approve exact revision','local and Dataiku stream stores immutable records','approval tied to authenticated operator','DB transactional revision/head/anchor publication and receipt','duplicate publish and stale expected head','rollback does not delete history','source anchor point lookup with bounded bundles','ON/OFF empty/nonempty','multiple bundles and path IDs','runtime original/ACL/version verification','native UI generate/preview/approve/publish','actual served schema not only research snapshot','SQLite real DB end-to-end; isolated local Oracle when available','existing ontology regression suite'],
'failure_policy':{'schema_repair':1,'transport_unknown':'persist UNKNOWN; no automatic retry','publication':'atomic transaction; query receipt after uncertain commit, never blind resubmit','runtime_db':'one lookup per arrived anchor; persist unavailable and ordinary-RAG fallback; no retry loop','immutables':['source anchors/text','judgment origins','approved revision/hash','existing active publication until replacement transaction']},
'model_calls':0,'quality_certified':False,'data':'synthetic only; no active MAIN ontology data','field_deployment':False,'resources':{'peak_mib':1600,'heavy_processes':1},'concurrency':'ADR1155 is isolated. Do not copy its changes or overwrite shared working files.'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update({k:criteria[k] for k in ['hypothesis','primary_metric','success_criteria','failure_criteria']},criteria_frozen_before_run=True)
m['design']['arms'][0].update(changes='Selected MAIN110 historical baseline and regression contracts',controls='Exact same data/model/profile/budgets')
m['design']['arms'][1].update(changes='Schema packaging and explicit authoring/review/publication/source DB consumer workflow',controls='Default OFF, no research data publication, existing navigation and source authority unchanged')
m['runs'][0].update(arm_ids=['connected'],selection_rule='Complete prospective technical lifecycle/failure matrix; zero model calls',artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[]
m['dataset'].update(name='Synthetic source-bound workflow contracts',version='1156-v1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
reason='Read/write integration and synthetic failure tests, not legal retrieval evaluation.'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'connected-r1',[n for n in files if (ROOT/n).is_file()],experiment_id=m['experiment_id'],arm_id='connected',run_ids=['run-001'])
for n,h in parent['files'].items():
 src=ROOT/parent['code_root']/n;assert sha(src)==h
 dst=S/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
 if not (ROOT/n).exists():ac.register_file(C,n,upstream_state='absent')
print('Prepared isolated baseline',len(files),'files; criteria fixed before implementation')
