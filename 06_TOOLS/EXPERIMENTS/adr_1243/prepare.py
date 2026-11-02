from common import *
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==126
put(DES/'baseline.json',{'active':active,'manifest':release,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'working_files':{n:sha(ROOT/n) for n in release['files']}})
criteria={'hypothesis':'DP=oracle without GENOS_RUNTIME_DIR must use the same Oracle logical runtime for service AD/report/recovery and chat progress as the Oracle Factory. Default NFS must remain unchanged.',
 'success':['Oracle runtime default and NFS default resolution checks','Real Oracle source and record v3/v4 API using only DP and existing Oracle configuration, no GENOS_RUNTIME_DIR','Actual gateway administration runtime matches Factory runtime','Existing row/lease/migration contracts retain the same results','Exact working/frozen/MAIN binding and actual default NFS entry'],
 'failure':'A persistent local/NFS runtime path, split AD/report/query runtime, input/model/ACL drift, or silent fallback',
 'scope':'Three pure runtime resolution consumers; existing legal/DB schema unchanged','models':0,'field_deploy':False}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Runtime destination identity and no filesystem fallback',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'))
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design']['arms'][1]['id']='oracle-records'
m['design']['arms'][0].update(changes='MAIN126 existing Oracle adapter with separate service/chat default runtime expressions',controls='Existing profile, source, ACL, Agent schema and model')
m['design']['arms'][1].update(changes=criteria['hypothesis'],controls='Same parent494 files/DB/schema/model/profile, no new actual models')
m['runs'][0].update(arm_ids=['baseline','oracle-records'],selection_rule='Deterministic runtime port tests and real local Oracle with scripted model',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='Runtime root and actual Oracle source/record contracts',version='20261030-r1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
reason='Pure persistence destination correction; source retrieval/ranking/claims unchanged'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.snapshot(ADR,'oracle-records',list(release['files']),experiment_id=m['experiment_id'],arm_id='oracle-records',run_ids=['run-001'])
print('Prepared MAIN126 follow-up; criteria frozen before editing')
