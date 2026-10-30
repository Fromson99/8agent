from pathlib import Path
import json,hashlib,sys,shutil
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1135-scenario-sufficiency-live';ART=ADR/'artifacts';D=Path(__file__).parent;OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1134-scenario-sufficiency-search-return';SC=ROOT/'04_EXPERIMENTS/ADR/ADR-1133-scenario-selection-receipt'
read=lambda p:json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
f=read(OLD/'artifacts/freeze.json');source=ROOT/f['code_root'];oldm=read(OLD/'실험/manifest.json')
criteria={'hypothesis':'Unchanged1134 short prompt supports required multi-route selection and native fallback on uncovered business scope.', 'primary':['Same4 saved-original probes: CM023 PATH1+PATH2, refund PATH3, exclusion PATH2, unrelated NO_MATCH+SEARCH','Native uncovered convertible-bond question: scenario route requests SEARCH or RESELECT then SEARCH; native SELECT reentry is observed, ordinary assessment sees source and reaches final answer with matching original citations','No source/hash/scope drift; selected scenario bodies unchanged; no repeated same-scope selector loop','No forced semantic retries: record if model does not choose RESELECT'], 'success':'All fixed route expectations and native fallback/publication checks pass. No general legal-quality certification.', 'failure':'Any route mismatch, missed required fallback, fatal contract/source/scope error, budget exhaustion, missing final answer or body drift.', 'run':'Four saved-source product-selector probes sequentially, then one native HTTP fresh navigation question. No replay prefix, no extra model rerun, no paired baseline;1133 is historical reference only.', 'limits':{'direct_max_calls_per_case':4,'native_max_calls':40,'native_tool_limit':1024,'native_wall_seconds':1800,'max_total_calls':56,'output_cap':None,'heavy_processes':1,'max_rss_gib':4,'min_available_gib':3,'min_disk_gib':20}, 'authoring':'Same source-authored unapproved5-path package from1133, same374-character prompt and product662files from1134. Known failure-informed in-sample design.', 'native_expected':'Current frozen source Article41-3 paragraph8 contains nonconversion-at-settlement treatment and refund if unconverted at maturity; source/answer inspection after selection only. No reference answer in product.'}
put(ART/'criteria.json',criteria)
for name in ['baseline.json','build-input.json','package.json','build-result.json','recipe.json']:shutil.copyfile(SC/'artifacts'/name,ART/name)
cases=read(SC/'artifacts/cases.json')
for c in cases:c['mode']='saved_source_selector'
cases.append({'id':'scenario-uncovered','mode':'native_http_fresh','question':'상속세 및 증여세법 제41조의3에서 전환사채를 받은 뒤 정산기준일까지 주식으로 전환하지 않은 경우, 증여세 정산과 이후 만기까지 미전환 시 환급은 어떻게 처리하나요?'})
put(ART/'cases.json',cases);rubric=read(SC/'artifacts/rubric.json');rubric['cases']['scenario-unknown']['next_action']='SEARCH';rubric['cases']['scenario-uncovered']={'requires_native_search_return':True,'final_answer_required':True};put(ART/'rubric.json',rubric)
put(ART/'parent.json',{'experiment':'ADR-1134-experiment-v1/scenario','freeze_sha256':sha(OLD/'artifacts/freeze.json'),'check_sha256':sha(OLD/'artifacts/check-001.json'),'frozen_files':f['files'],'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
for a in m['design']['arms']:a.update(changes='Historical parent, not executed' if a['id']=='baseline' else 'No product change; real-model exercise of1134',controls='Same1134 product662files,374-character system prompt; same1133 package5paths')
m['runs'][0].update(arm_ids=['scenario'],selection_rule=criteria['run'],artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)));put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (ROOT/n).is_file()];C=ac.snapshot(ADR,'scenario-r1',present,experiment_id=m['experiment_id'],arm_id='scenario',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(source/n)==h,n
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/n,p)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
for name in ['common.py']:
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1134'/name).read_text().replace('ADR-1134-scenario-sufficiency-search-return','ADR-1135-scenario-sufficiency-live').replace('adr_1134','adr_1135');(D/name).write_text(s)
for name in ['live.py','source_audit.py']:
 s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1124'/name).read_text();(D/('native.py' if name=='live.py' else name)).write_text(s)
(D/'direct.py').write_text((ROOT/'06_TOOLS/EXPERIMENTS/adr_1133/live.py').read_text().replace('ADR1133','ADR1135'))
print(S)
