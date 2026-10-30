from common import *
f=read(DES/'freeze.json');m=read(ADR/'실험/manifest.json');p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/p['manifest_path'])
assert p['generation']==105
put(DES/'live-baseline.json',{'pointer':p,'release':release})
case=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1082-main105-live-latency/artifacts/design/cases.json')
put(DES/'cases.json',case)
put(DES/'live-criteria.json',{'question_count':1,'known_in_sample':True,'candidate':f['binding'],'limits':{'calls':40,'tools':1024,'seconds':1800,'rss_gib':4,'available_gib':3,'disk_gib':20,'swap_gib':0.5},'provider':'qwen/qwen3.8-27b Parasail FP8 reasoningnone nofallback outputcapnull','success':'Native HTTP completion, preserved source/citation/permission hashes; live usage/timing descriptive only','stop':'Integrity/resource/provider failure ends cell; no whole-case rerun','permission':'User accepted try agent compact-input implementation and SQL care; same public fsc-hard-005 context; no private data or answers.'})
m['runs'].append({'id':'run-002','purpose':'audit','parent_run_id':'run-001','arm_ids':['compact'],'status':'planned','selection_rule':'Exactly frozen public fsc-hard-005 once after contracts; known in-sample; noadaptive rerun','artifact_path':str((RUN/'result.json').relative_to(ROOT)),'sha256':'PENDING'})
m['llm_policy']['llm_calls']=[{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
m['design']['retrieval_stage_plan']['stages_by_arm']={'compact':[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}]}
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-002',artifact_path=str((RUN/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
m['retrieval_accounting']['not_applicable_reason']='Search policy unchanged; observed original/final scope recorded after product run.'
C=ROOT/f['binding']['manifest_path'];cm=read(C);cm['run_ids']=['run-001','run-002'];put(C,cm)
f['binding']['manifest_sha256']=sha(C);put(DES/'freeze.json',f)
m['design']['code_isolation']['candidates'][0].update(f['binding'],run_ids=['run-001','run-002'],runner_path='06_TOOLS/EXPERIMENTS/adr_1086/live.py',runner_sha256=sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1086/live.py'))
put(ADR/'실험/manifest.json',m)
put(DES/'live-freeze.json',{'code_root':f['code_root'],'candidate':f['binding'],'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'serving_files':f['files'],'files':{str(p.relative_to(ROOT)):sha(p) for p in [DES/'cases.json',DES/'live-criteria.json',DES/'live-baseline.json',C]},'scripts':{str((ROOT/'06_TOOLS/EXPERIMENTS/adr_1086'/n).relative_to(ROOT)):sha(ROOT/'06_TOOLS/EXPERIMENTS/adr_1086'/n) for n in ['common.py','live.py']}})
print('Frozen one native public probe; no calls yet')
