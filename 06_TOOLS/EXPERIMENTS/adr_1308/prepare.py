from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1308-gold-query-optimization'
DES=ADR/'artifacts/design';DES.mkdir(parents=True,exist_ok=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
active=json.loads((ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json').read_text())
release=json.loads((ROOT/active['manifest_path']).read_text())
sources=set(release['files'])
sources.update(str(p.relative_to(ROOT)) for p in (ROOT/'08_DEPLOYMENT/DATAIKU/gold_fresh_1_jdbc_fast_20261103_r6/package').rglob('*') if p.is_file() and p.suffix in ('.py','.json','.yaml','.txt') and '__pycache__' not in str(p))
sources.update(['05_TESTS/CONTRACTS/test_review_explanation_actions.py','05_TESTS/CONTRACTS/test_user_review_diagnostics.py'])
criteria={'hypothesis':'Exact bounded metadata reuse and scope/key-first SQL eliminate redundant row/body/position processing without changing search semantics.',
 'success':['Address every diagnostic O01..O27 with implemented same-contract optimization or evidence-backed unchanged/conditional disposition',
 'Exact source ownership ACL latest selection row/body hash and numeric order preserved',
 'SQLite/Oracle single token and phrase ranking duplicates ties exact totals and cursor contracts preserved',
 'Request caches bounded, immutable successful results only, invalidated on store/release/ACL drift',
 'Regression contracts and bounded mock/native integration pass; no quality or field speed certification from mock tests',
 'Preserve pending load commit uncertainty and original R6 delivery; provide separate optimized successor if changed',
 'Integrate verified candidate hunks and dependency pins; preserve unrelated user working changes'],
 'failure':['Source/ranking/ACL loss','Silent truncation or cache poisoning','Changed historical artifacts','Implicit new schema/DDL','Unbounded memory or extra external model calls'],
 'authorization':'User: 싹다 고쳐봐. Implementation and necessary verification authorized; no field deployment or database DDL requested.',
 'scope':'Component implementation and deterministic contracts, optionally bounded read-only Oracle verification; no actual model calls, production writes, field deployment, push or mail',
 'resources':{'serial_heavy_processes':True,'max_RSS_GiB':4,'min_available_GiB':3,'max_swap_growth_MiB':128,'min_disk_GiB':20}}
put(DES/'criteria.json',criteria)
put(DES/'baseline.json',{'active':active,'active_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':release,'working_files':{p:sha(ROOT/p) for p in sorted(sources)},'audit_catalog':{'path':'09_ARTIFACTS/AUDITS/20261103-gold-fts-optimization/optimization-catalog.json','sha256':sha(ROOT/'09_ARTIFACTS/AUDITS/20261103-gold-fts-optimization/optimization-catalog.json')}})
m=json.loads((ADR/'실험/manifest.json').read_text());m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact functional contracts and bounded physical reads, no field speed claim',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Selected MAIN135 and preexisting working changes; preserved audit evidence',controls='Same immutable corpus and ranking contracts')
m['design']['arms'][1].update(changes='Query implementation and contract checks',controls=criteria['scope'])
m['runs'][0].update(arm_ids=['optimized'],selection_rule='Predeclared synthetic and existing component regressions; no answer benchmark',artifact_path=str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)))
m['dataset'].update(name='Query contract fixtures, no external legal quality benchmark',version='20261103-v1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['llm_policy']['llm_calls']=[]
reason='SQL implementation contracts; no real legal retrieval benchmark or model answer evaluation'
m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',m)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
c=ac.snapshot(ADR,'optimized',sorted(sources),experiment_id=m['experiment_id'],arm_id='optimized',run_ids=['run-001'])
put(DES/'candidate-path.json',{'candidate':str(c.relative_to(ROOT)),'snapshot':str((c/'snapshot').relative_to(ROOT))})
print('isolated',len(sources),'files',c)
