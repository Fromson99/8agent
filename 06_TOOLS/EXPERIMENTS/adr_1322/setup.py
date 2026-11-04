from pathlib import Path
import sys,json,shutil
ROOT=Path('/home/jin/8-AGENT');T=Path(__file__).parent
for n in ('common.py','resource_guard.py','check.py','integrate.py'):
 s=(T.with_name('adr_1321')/n).read_text().replace('ADR-1321-multiturn-followup-review-build-integration','ADR-1322-multiturn-enum-diagnostics-working').replace('adr1321','adr1322')
 (T/n).write_text(s)
sys.path.insert(0,str(T));from common import *
DES.mkdir(exist_ok=False)
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1321-multiturn-followup-review-build-integration/artifacts';parent=read(P/'design/candidate-integrated.json');PC=ROOT/parent['code_root'];base=read(P/'design/baseline.json')
assert read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==base['pointer']
put(DES/'baseline.json',base);put(DES/'working-before.json',{n:sha(ROOT/n) for n in parent['selected_files']})
criteria={'hypothesis':'Choose a diagnostic branch only when the received discriminator belongs to exactly one const or enum alternative. Canonical JSON-schema acceptance remains unchanged. This exposes the exact empty claim_refs from actual1319 output and completes1321 diagnostics without model inference.',
 'success':['Actual1319 read-review USE/emptyclaims failures point to all8claim_refs, no generic anyOf hiding those errors.','All124 parent contracts and51 source mode/actualAPI mock contracts pass; ambiguous enum/const alternatives stay generic.','Native639 executableSQL/list/AST unchanged; enginepreflight30/497; working525files match candidate and MAIN139pointer stays same.'],
 'failure':['No new model calls after1319UNKNOWN; no quality or full60pass claim.','Preserve123/1 parentresult; do not overwrite frozenparent','Do not infer legal status or change validator acceptance, source/ACL/retry checks'],
 'limits':{'models':0,'heavy_workers':1,'rss_GiB':5},'authorization':'진행해봐; multi-turn repair and internal testing',
 'parent_result':str((P/'contracts-final/result.json').relative_to(ROOT)),'parent_result_sha256':sha(P/'contracts-final/result.json')}
put(DES/'criteria.json',criteria);put(DES/'cases.json',[{'id':'enum-diagnostic','input':'Actual1319 assessment14; diagnostic child of1321failure'},{'id':'scope-switch','input':'Existing51GENOSapplied-mode contracts; synthetic internal/external/all scope and duplicate actualAPI'},{'id':'working-binding','input':'Same525frozenfiles and latestMAIN139preservation'}])
m=read(ADR/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact diagnostic paths, unchanged rejection, mode/duplicate API contracts and native/working hash closure',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')});m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design']['arms'][0].update(changes='Completed1321 integrated525 baseline;123pass/1fail preserved',controls='No new baseline model/retrieval; final source/working base remains139')
m['design']['arms'][1].update(changes=criteria['hypothesis'],controls='No schema acceptance change; source/hashes/rights/budgets unchanged')
m['runs'][0].update(arm_ids=['integrated'],selection_rule='Parent124 contracts plus all51mode checks; then workingAPI recheck if pass',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['dataset'].update(name='Recorded enum error and existing mode integration contracts',version='20261104-r1',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'));m['llm_policy']['llm_calls']=[]
m['retrieval_accounting']=read(P.parent/'실험/manifest.json')['retrieval_accounting'];put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
can=ac.snapshot(ADR,'integrated',list(parent['selected_files']),experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);C=can/'snapshot'
for n in parent['selected_files']:shutil.copyfile(PC/n,C/n)
x=read(P/'design/candidate-path.json');put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':list(parent['selected_files']),'product_files':x['product_files'],'base_generation':139,'parent':parent['pin']})
p=C/'02_BACKEND/semantic_runtime/legal_agent/output_contract.py';s=p.read_text();old="branch.get('properties',{}).get(key,{}).get('const',object()) == error.instance[key]]";new="(branch.get('properties',{}).get(key,{}).get('const',object()) == error.instance[key] or\n                         error.instance[key] in branch.get('properties',{}).get(key,{}).get('enum',[]))]";assert old in s;s=s.replace(old,new);p.write_text(s)
print('Isolated parent525; diagnostic const-or-enum unique selection only')
