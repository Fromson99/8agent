from common import *
import shutil
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
assert active['generation']==134
parent=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1292-rag-ontology-console-integration/artifacts/design/freeze.json')
criteria={'hypothesis':'Ordinary ASSESS can share exact repeated input strings and claim/evidence relations; fully acquired source-work needs are mechanical projections of explicit scope reviews, not independent legal judgments.',
 'success':['Ordinary and repair lossless text sharing; legacy v1 input and review readers remain compatible',
 'Shared review relations on ordinary modern ASSESS with independent dispositions, reasons, issues, gaps and source partitions intact',
 'Only current v2 fully acquired nonempty source-work targets eligible for host needs; semantic needs, conflicts and incomplete acquisition remain explicit',
 'Reconstruct eligible needs from explicit per-range USE/EXCLUDE/OPEN; all original schema, acquisition, claim, source, gap and scope validators still run',
 'Compare frozen prior12 structural cells on identical canonical views; no text truncation or source loss',
 'Native mock normal/repair/incomplete/requery and scenario regressions; new imports/pins checked',
 'Official prepare/apply local MAIN with Gold same code, current data/mapping/settings/connector and unrelated working changes preserved'],
 'failure':['Source or semantic validation weakened','Lost original or raw proposal','Unknown retried','Unverified or concurrent code overwritten','Declared change reported as actual model quality gain'],
 'authorization':'User: 정리해보고 메인에 반영해. Local MAIN/Gold cutover explicitly authorized; quality_certified=false.',
 'scope':'Implementation and deterministic component/native checks, no new live model, Oracle writes, field deploy, Git push or email',
 'resources':{'minimum_start_available_GiB':5,'minimum_available_GiB':3,'max_RSS_GiB':4,'max_swap_growth_MiB':128,'minimum_disk_GiB':20,'serial_heavy_processes':True},
 'remaining':'Independent semantic needs and repeated scope judgments remain; incremental changed-only review is outside this change; UNKNOWN provider cause and legal quality unconfirmed.'}
put(DES/'criteria.json',criteria)
put(DES/'baseline.json',{'active':active,'active_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':release,'parent':parent,
 'gold_binding':read(GOLD/'binding.json'),'gold_files':{str(p.relative_to(ROOT)):sha(p) for p in GOLD.iterdir() if p.is_file()}})
sources=sorted(parent['files']);before={n:sha(ROOT/n) for n in sources}
put(DES/'working-before.json',before)
put(DES/'concurrent-preserved.json',{'paths':{n:{'working':before[n],'parent':h} for n,h in parent['files'].items() if before[n]!=h}})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Lossless ordinary input and exact host-derived source-work rows with unchanged semantic validators',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence=bind(DES/'criteria.json'))
m['design']['arms'][0].update(changes='MAIN134 verified parent and observed ADR1299 twelve cells',controls='Historical structural baseline, no new model control')
m['design']['arms'][1].update(changes=criteria['scope'],controls='Same source/version/ACL/gap/status and model budgets')
m['runs'][0].update(arm_ids=['verified'],selection_rule='Preregistered contracts/native checks plus same12 component fixtures',artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)))
m['dataset'].update(name='Ordinary input and source-work contracts; identical ADR1299 scaling cells',version='20261103-v1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['llm_policy']['llm_calls']=[]
reason='Contract implementation and structural replay; no retrieval/ranking or real model quality comparison'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(ADR,'verified',sources,experiment_id=m['experiment_id'],arm_id='verified',run_ids=['run-001'])
S=C/'snapshot'
# Isolate concurrent working changes by restoring exact already-frozen parent files in candidate only.
for n,h in parent['files'].items():
 if sha(S/n)!=h:shutil.copy2(ROOT/parent['code_root']/n,S/n)
assert all(sha(S/n)==h for n,h in parent['files'].items())
put(DES/'candidate-path.json',{'candidate':str(C.relative_to(ROOT)),'snapshot':str(S.relative_to(ROOT))})
print('Prepared isolated',len(sources),'files; concurrent differences',len(read(DES/'concurrent-preserved.json')['paths']))
