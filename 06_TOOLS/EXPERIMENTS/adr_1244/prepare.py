from common import *
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path']);assert active['generation']==127
put(DES/'baseline.json',{'active':active,'manifest':release,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
 'working_files':{n:sha(ROOT/n) for n in release['files']}})
criteria={'hypothesis':'Preserve ontology/answer/source/decision/ACL/resume authority in Oracle, while raw model requests/responses/SSE/debug and detailed reports are stored only on configured NFS.',
 'success':['Structured case/evidence/claim/correction/gap/answer and workflow recovery remain Oracle with no dependence on diagnostic NFS',
 'Raw model request/response bytes and detailed report/trace files do not enter Oracle bodies or compact blobs',
 'Oracle retains only raw diagnostic location/hash/status references and a minimal canonical structured response for no-redispatch workflow recovery',
 'NFS unavailable cannot create local fallback or duplicate model calls; queued/unavailable detail capture is explicit',
 'Same lexical/nested shared-log roots excluded from Oracle and validated NFS before writing',
 'Explicit import keeps source bytes and structured values, splits raw attempt fields and excludes unreferenced compact log blobs',
 'Default NFS mode and existing source/ACL/budget/hash contracts remain; exact MAIN integration and actual entry check'],
 'failure':'Lost accepted source/decision state, raw prompt/SSE leakage into new Oracle rows, silent local log fallback, or model redispatch from NFS failure',
 'boundary':{'oracle':'Structured original-source evidence, user facts/corrections, proposed/accepted judgments, gaps, canonical answers, provenance, budget/status/CAS/leases',
 'nfs':'Whole transport request including schema/messages, raw response/SSE/reasoning/debug, request reports/trace/log summaries',
 'compatibility':'Existing compact Oracle tables and request-local SQL retained; no new DDL or Gold changes; existing history not deleted'},
 'model_calls':0,'resource_limits':{'min_available_GiB':3,'max_host_swap_growth_MiB':128},'field_nfs_mount':'not certified by local synthetic NFS adapter tests'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True)
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Structured authority preserved and raw diagnostic payload exclusion',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'))
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design']['arms'][1]['id']='oracle-records'
m['design']['arms'][0].update(changes='MAIN127 full Oracle record/log body routing',controls='Same sources/ACL/model/Agent schema')
m['design']['arms'][1].update(changes=criteria['hypothesis'],controls='No legal policy/source/model/DDL change')
m['runs'][0].update(arm_ids=['baseline','oracle-records'],selection_rule='Storage/consumer contracts with real local Oracle and scripted model; synthetic NFS path, no field mount claim',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='Structured Oracle and NFS diagnostics boundary fixtures',version='20261030-r1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
reason='Persistence destinations only; no retrieval/ranking/quality comparison';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
ac.snapshot(ADR,'oracle-records',list(release['files']),experiment_id=m['experiment_id'],arm_id='oracle-records',run_ids=['run-001'])
print('Prepared MAIN127 split-storage follow-up; criteria frozen')
