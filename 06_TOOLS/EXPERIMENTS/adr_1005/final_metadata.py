from common import *
import sys,shutil
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.runtime.retrieval_stage_ledger import StageLedgerRecorder,identity_canonicalizer,grade_capture,build_run_artifact,build_experiment_artifact
m=read(ADR/'실험/manifest.json');o=read(ART/'observations.json')
shutil.copyfile(ART/'retrieval-ledger.json',ART/'retrieval-ledger-before-case-label-correction.json')
rec=StageLedgerRecorder('known-query','candidate',identity_canonicalizer)
rec.record_stage('original_read','source',o['read_coordinates'])
rec.record_stage('final_cited','present',o['final_coordinates'],parent_stage_ids=['original_read'],discard_reasons=[{'identity':x,'reason':'Read evidence or preview not selected for final citation; no irrelevance or source-absence finding.'} for x in o['read_coordinates'] if x not in o['final_coordinates']])
ledger=build_experiment_artifact('ADR-1005','ADR-1005-experiment-v1',[build_run_artifact('run-001',[grade_capture(rec.capture(),[])],{'candidate':['original_read','final_cited']})]);save(ART/'retrieval-ledger.json',ledger)
save(ART/'metadata-correction.json',{'reason':'Analyzer inherited an old case label and scalar aggregate shape. Identical source coordinates/claims and results, no regrade, zero calls. Historical baseline has no run in this ADR.','old_case_id':'capital-gains-expenses','case_id':'known-query','run_arm_ids_before':m['runs'][0]['arm_ids'],'run_arm_ids_after':['candidate'],'old_ledger_sha256':sha(ART/'retrieval-ledger-before-case-label-correction.json')})
m['runs'][0]['arm_ids']=['candidate']
for k in ('presented_total','presented_mean','presented_p50','presented_p95','selectivity'):m['retrieval_accounting'][k]={'candidate':m['retrieval_accounting'][k]}
m['retrieval_accounting']['stage_ledger']['sha256']=sha(ART/'retrieval-ledger.json');save(ADR/'실험/manifest.json',m)
files=[p for p in ART.rglob('*') if p.is_file() and p.name!='manifest.json']
files += [ROOT/read(ART/'stage.json')['candidate_dir']/'candidate.json']
files += list(Path(__file__).parent.glob('*.py'))
save(ART/'manifest.json',{'schema_version':'adr-artifacts-v1','adr_id':'ADR-1005','files':[{'path':str(p.relative_to(ROOT)),'bytes':p.stat().st_size,'sha256':sha(p),'description':'Frozen inputs, provider requests/responses, source audit, failures and metadata correction'} for p in files]})
