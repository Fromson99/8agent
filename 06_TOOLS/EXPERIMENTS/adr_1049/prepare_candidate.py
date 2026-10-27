from pathlib import Path
import json,shutil,hashlib,sys,re
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1049-ontology-mvp-provider-failover';ART=ADR/'artifacts'
OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1048-ontology-mvp-r10-restart/artifacts'
def read(p):return json.loads(p.read_text())
def save(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(OLD/'design-freeze.json'); source=ROOT/f['code_root'];old=read(source.parents[2]/'candidate.json')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as c
present=[r['target_path'] for r in old['files'] if r['upstream_state']=='present']
target=c.snapshot(ADR,'provider-failover-r11',present,experiment_id='ADR-1049-experiment-v1',arm_id='A2',run_ids=['run-001'])
for row in old['files']:
 name=row['target_path'];dest=target/'snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/name,dest)
 if row['upstream_state']=='absent':c.register_file(target,name,upstream_state='absent')
c.refresh(target)
for name in ['common.py','run_case.py','run_matrix.py','collect_metrics.py','wire_audit.py','judge.py','evaluate_matrix.py','report_results.py','test_stream_runner.py','test_host_excerpt_metrics.py','test_wire_audit.py']:
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1048'/name).read_text();s=s.replace('ADR-1048-ontology-mvp-r10-restart','ADR-1049-ontology-mvp-provider-failover').replace('ADR-1048','ADR-1049').replace('adr_1048','adr_1049').replace('adr1048','adr1049')
 (Path(__file__).parent/name).write_text(s)
for name in ['cases-product.json','cases-evaluator-r1.json','corpus-selection-r1.json','execution-authorization-20261024-r1.json','evaluation-contract.json','dataset-freeze-r1.json','approved-bundles-20261024-r1.json','corpus-article-root-count-r1.json']:
 shutil.copyfile(OLD/name,ART/name)
save(ART/'provider-authorization.json',{'authorized_by':'user','approved_for_run':True,'user_message':'우리 오류가 생겼을때 제공자를 바꾸면서 실험되게 해볼 수 있나? 더 많은 제공자가 있어도 좋을듯?','scope':'Isolated MVP37x3 product and offline judge, same model Qwen3.8 FP8, provider-only failover on known rejected HTTP429. No MAIN change.','providers':[{'tag':t,'name':n} for t,n in [('parasail/fp8','Parasail'),('reka/fp8','Reka'),('wafer/fp8','Wafer'),('mancer/fp8','Mancer 2'),('coreweave/fp8','CoreWeave')]],'model_fallback':False,'hidden_server_fallback':False,'physical_request_cap_product':40,'physical_request_cap_judge_case':21,'product_wall_seconds':1800,'max_provider_advances_per_cell':4,'gate':'All three arms use identical predeclared policy. Record provider mix as a confound; no clean same-provider causal claim when mixes differ.'})
print(target)
