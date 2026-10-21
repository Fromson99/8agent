from pathlib import Path
import ast,hashlib,json
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0878-main85-cm-registered-live';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
pointer=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert pointer['generation']==85
release=read(R/pointer['manifest_path']);put(D/'baseline.json',{'pointer':pointer,'release':release})
registry=R/'01_DATA/GOLDEN/registry-v2-risk_cm.json';selected=['cm-001','cm-003','cm-008','cm-033','cm-051'];indexed={c['id']:c for c in read(registry)['cases']}
cases=[{'id':cid,'question':indexed[cid]['question'],'api_type':'RAG_ASK','new_call_limit':40} for cid in selected];put(D/'cases.json',cases)
# This file is offline-only: the product runner never opens it.
put(D/'offline-reference.json',[indexed[cid] for cid in selected])
criteria={'hypothesis':'Current unchanged MAIN85 can retrieve exact originals and answer registered CM questions with compressed schemas without recurring contract/transport failures.', 'success':['All five actual service calls preserve selected MAIN85 code/data and exact source provenance','No schema/ACL/state/hash failure','All five requested issues answered correctly against version-matched registered references; partial/incorrect answers remain explicit'], 'failure':['Any supported question left unanswered or substantively wrong','Unread available candidate misrepresented as missing data','Transport, schema, provenance or state failure'], 'selection':'Purposive known-case probe: two interpretations of KOSDAQ26, one underwriting exception, one reporting-period exception, one holding-ratio calculation. IDs fixed before outputs; not 51-question census or unseen holdout.', 'bounds':{'calls_per_case':40,'wall_seconds_per_case':1800,'concurrency':1,'rss_gib':8,'address_space_gib':9,'repeats':1}, 'gold':'Registered reference is offline only; original version drift reported separately; no external web or judge rewrites product answer.'};put(D/'criteria.json',criteria)
old=(R/'06_TOOLS/EXPERIMENTS/adr_0876/live.py').read_text()
old=old.replace('ADR-0876-original-coverage-scope-probe','ADR-0878-main85-cm-registered-live').replace('adr0876-','adr0878-')
old=old.replace('"""One unchanged MAIN84 service request, audited through the common model client."""','"""Selected MAIN85 actual service ingress, original registered CM question only."""')
old=old.replace("GENOS_RUNTIME_DIR=str(O/'runtime'))","GENOS_RUNTIME_DIR=str(O/'runtime'), GENOS_AUTO_WARMUP='0', WORKFLOW_USER_ID='jin')\nos.environ.pop('DP',None)")
old=old.replace('WSL explicit frozen0876 candidate service.py ASGI dispatch on MAIN84 data; actual active MAIN84 pointer unchanged','WSL actual selected MAIN85 service.py RAG_ASK, no product injection; registered CM51 subset')
old=old.replace("'app_injected': True","'app_injected': False")
start=old.index("    sys.path[:0]=[str(C/'02_BACKEND')")
end=old.index("    put(O/'health.json'",start)
old=old[:start]+"    import service\n    from types import SimpleNamespace\n    actual=importlib.import_module('service.service')\n    app=actual.application()\n    assert actual._BINDING['mode']=='local-release'\n    assert Path(app.state.pipeline.contracts.root).resolve()==C.resolve()\n    actual._ad_control=lambda:SimpleNamespace(intercept=lambda *a:None,start_worker=lambda *a:None)\n"+old[end:]
old=old.replace("'public_question':True,'use_llm':True}}", "'public_question':True,'use_llm':True,'session_id':'adr0878-'+case['id'],'request_id':'adr0878-'+case['id']}}")
old=old.replace("    if value.get('run_id'):","    if case['api_type']=='WORKFLOW_RUN' and value.get('run_id'):")
old=old.replace("    result['active_pointer_unchanged']", "    result['consumer_check_scope']='RAG response and journal saved. WORKFLOW_STATUS does not apply to ordinary RAG.'\n    result['active_pointer_unchanged']")
p=R/'06_TOOLS/EXPERIMENTS/adr_0878/live.py';ast.parse(old);p.write_text(old)
plans=[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Five requested answers, version-matched original provenance, full request completion; not overall CM accuracy',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['retrieval_stage_plan']['stages_by_arm']={'observed':plans}
m['design']['code_isolation']['reason']='No new product implementation or effect comparison. Execute unchanged selected MAIN85 immutable release through actual service entry; exact files/data hashes bound in freeze.json. Read-only shared release avoids duplicate code/data.'
m['design']['arms']=[{'id':'observed','role':'candidate','derived_from':['ADR-0877-experiment-v1/qualified'],'changes':'None; observe selected MAIN85 on registered CM questions','controls':'Exact registered question and public document scope only, no gold input, serial clean runtimes, unchanged profile40calls1800s'}]
m['runs'][0].update(arm_ids=['observed'],selection_rule=criteria['selection'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'max_calls':200}]
m['dataset'].update(name='Registered CM51 purposive five',version='cm-field-core-e2e-v3',frozen_source=str((D/'cases.json').relative_to(R)),sha256=sha(D/'cases.json'))
m['retrieval_accounting']['not_applicable_reason']=None;m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((A/'artifacts/run-001/retrieval-ledger.json').relative_to(R)),not_applicable_reason=None)
put(A/'실험/manifest.json',m)
files=[R/'service.py',R/'service/service.py',R/'02_BACKEND/lawrag/research/experiment_client.py',registry,R/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json',R/pointer['manifest_path'],R/release['data_path']/'manifest.json',D/'baseline.json',D/'cases.json',D/'criteria.json',D/'offline-reference.json',p,Path(__file__)]
freeze={'code_root':release['code_root'],'serving_files':release['files'],'files':{str(p.relative_to(R)):sha(p) for p in files},'design_sha256':hashlib.sha256(json.dumps(m['design'],sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'resources':criteria['bounds']};put(D/'freeze.json',freeze)
print('Frozen five CM questions; selected MAIN85; no product change',selected)
