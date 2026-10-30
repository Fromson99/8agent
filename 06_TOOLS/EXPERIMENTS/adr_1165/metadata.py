from common import *
for name in ('ADR-1164-genos-vector-initial-build','ADR-1165-vector-navigation-connected'):
 a=ROOT/'04_EXPERIMENTS/ADR'/name;m=read(a/'실험/manifest.json');m['lineage']['hypothesis_delta']='Oracle vector initial retrieval and Dataiku publication; preserve current MAIN contracts'
 m['design']['criteria_frozen_before_run']=True;m['design']['criteria_freeze_evidence']={'path':str((a/'artifacts/design/criteria.json').relative_to(ROOT)),'sha256':sha(a/'artifacts/design/criteria.json'),'note':'Created by setup.py before freeze and first test; missing scaffold boolean corrected during final metadata validation'}
 for arm in m['design']['arms']:
  arm['changes']='Exact MAIN111 baseline' if arm['id']=='baseline' else 'Vector API, publication, navigation and physical source mapping'
  arm['controls']='Same source/model/budgets; synthetic fixtures; no live model'
 put(a/'실험/manifest.json',m)
 artifact=read(a/'artifacts/manifest.json');artifact['files']=[]
 for p in sorted((a/'artifacts').rglob('*')):
  if not p.is_file() or p.name=='manifest.json' or any(x in ('staged-code','__pycache__') for x in p.parts):continue
  artifact['files'].append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'bytes':p.stat().st_size,'description':'Bound criteria, isolated code inventory, technical result or preserved failure','contains_raw_prompts_and_outputs':False})
 put(a/'artifacts/manifest.json',artifact)
