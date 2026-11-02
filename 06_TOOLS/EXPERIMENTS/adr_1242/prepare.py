from pathlib import Path
import hashlib,json,sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1242-oracle-agent-records-main'
D=ADR/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');release=read(ROOT/active['manifest_path'])
put(D/'baseline.json',{'active':active,'manifest':release,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),
    'working_files':{name:sha(ROOT/name) for name in release['files']},'source':'selected MAIN plus preserved working hashes'})
criteria={'hypothesis':'DP=oracle can persist all active runtime state in the existing compact SIDDA Agent tables without NFS or serving-local record databases, preserving existing legal/SQL contracts and the DP-unset NFS path.',
    'architecture':{'authority':'Oracle Agent rows and immutable bodies, CAS heads and fenced ownership leases',
        'compatibility':'Request-local memory-only SQLite executes existing record SQL/triggers. Hydrate only the requested record namespace; persist changed rows, not a whole SQLite file. No source/index corpus mirror or persistent local cache.',
        'files':'Explicit Oracle logical path adapter for runtime artifacts/publications/diagnostics; never monkeypatch the global pathlib or sqlite modules',
        'atomicity':'Upload immutable bodies first; row/history/head/operation receipt in one maintained Oracle transaction; reconcile ambiguous commits by operation ID; no model retry',
        'scope':'journal-v6, case-v3, shortcut-v4, workflows, budgets, publication, progress/source readers, AD/diagnostics, ontology export',
        'switch':'Existing DP flag; default NFS retained; no separate opt-in required for Oracle records'},
    'success':['All active record consumers route through the Oracle path/connection port under DP=oracle',
        'No NFS mount required and no runtime filesystem read/write or file-backed SQLite in the Oracle service test',
        'Real local Oracle commit/reconnect/row delta/CAS/fence/duplicate/outbox/Unicode/source retrieval tests pass',
        'Existing local/NFS tests retain legal/ACL/hash/UNKNOWN/budget contracts without new relevant failures',
        'NFS history migration reads originals without modifying their bytes and preserves typed values/PK/rowid/NULL/hash',
        'Same qualified working/candidate/selected MAIN inventory and actual service entry verification; Dataiku SQL matches the same three-table schema'],
    'failure':'Any lost original, authorization widening, silent fallback, duplicate model dispatch, stale ownership write, serving-local persistent record, or incompatible MAIN inventory',
    'limits':{'new_real_model_calls':0,'min_available_GiB':3,'min_disk_GiB':80,'max_process_RSS_GiB':5,'max_host_swap_growth_MiB':128},
    'evaluation':'Deterministic technical fixtures and existing contract cases; no legal-quality or performance improvement claim',
    'user_authorization':'지금 DP=oracle로 하면 전체 우리 오라클 디비만 쓰게 해주게 코드를 수정해줘 메인꺼'}
put(D/'criteria.json',criteria)
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
manifest=read(ADR/'실험/manifest.json')
ac.snapshot(ADR,'oracle-records',list(release['files']),experiment_id=manifest['experiment_id'],arm_id='oracle-records',run_ids=['run-001'])
manifest.update(in_sample=False,decision_eligible=True)
manifest['lineage']['hypothesis_delta']=criteria['hypothesis']
manifest['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Storage durability, isolation and no-filesystem service contracts',
    success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,
    criteria_freeze_evidence={'path':str((D/'criteria.json').relative_to(ROOT)),'sha256':sha(D/'criteria.json')})
manifest['design']['arms'][0].update(changes='Current selected MAIN / unchanged NFS record backend',controls='Same model/profile/source/search/ACL contracts')
manifest['design']['arms'][1].update(changes='Oracle record authority and logical runtime paths under existing DP switch',controls='Same legal engine, no actual model calls or source data changes')
manifest['runs'][0].update(selection_rule=criteria['evaluation'],artifact_path=str((ADR/'artifacts/run-001/result.json').relative_to(ROOT)))
manifest['llm_policy']['llm_calls']=[]
manifest['dataset'].update(name='Deterministic storage/consumer contracts',version='20261030-r1',frozen_source=str((D/'criteria.json').relative_to(ROOT)),sha256=sha(D/'criteria.json'))
reason='Storage and persistence technical audit; retrieval candidates/ranking/legal claims unchanged, no legal recall scoring'
manifest['retrieval_accounting']['not_applicable_reason']=reason
manifest['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(ADR/'실험/manifest.json',manifest)
print('Prepared isolated Oracle record candidate; source MAIN',active['generation'])
