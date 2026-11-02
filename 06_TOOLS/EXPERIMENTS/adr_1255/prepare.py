from pathlib import Path
import sys,json,hashlib
R=Path('/home/jin/8-AGENT');A=R/'04_EXPERIMENTS/ADR/ADR-1255-wiki-workspace-oracle-live';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
release=read(R/'08_DEPLOYMENT/RELEASES/oracle-safe-records-20261030-r1/release.json')
names=set(release['files'])
for p in (R/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if isinstance(v.get('files'),dict):names.update(n for n in v['files'] if (R/n).is_file())
names.update(str(p.relative_to(R)) for p in (R/'02_BACKEND/semantic_runtime/ontology_work').glob('wiki_*.py'))
put(D/'baseline.json',{'manifest':release,'active':read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'working_files':{n:sha(R/n) for n in sorted(names)}})
criteria={'scope':'Real external model and actual local Oracle, isolated public workspace; no field deployment or quality certification',
 'gates':['Oracle body persistence and reopen','two immutable actual past records accumulated','real-model workspace proposal and source-only normalization/projection','original compiler accepts source-bound knowledge','explicit delegated review and activation','actual native RAG consumes this workspace publication and returns grounded final answer','withdrawal removes it and old answer fails replay','legacy contracts no new failures'],
 'stop':['unknown external delivery','any unhandled error or incomplete gate','resource or SQL deadline budget','SIDDA allocation above 90% of original 300MiB quota'],
 'model':'qwen/qwen3.8-27b','physical_limit':24,'per_request_seconds':180,'overall_seconds':1800,'authoring_projection_seconds':600,
 'resources':{'min_mem_available_bytes':3*1024**3,'max_rss_bytes':5*1024**3,'max_host_swap_growth_bytes':128*1024**2,'max_process_swap_bytes':256*1024**2},
 'authorization':'User explicitly requested actual model + Oracle record accumulation through compile/review/RAG, fixes, and local MAIN only after passing. Experimental publication is technical delegated review; no assertion of user legal-content approval.',
 'on_failure':'Preserve all evidence and stop; diagnosis/fix in a new child ADR before another actual experiment. No unchanged retries.',
 'promotion':'This probe is not promotion eligible; passing requires separate qualification and official local MAIN procedure.'}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']='Connect free workspace immutable objects and discovery to Oracle; validate actual authoring and runtime consumption.'
m['design'].update(hypothesis=criteria['scope'],primary_metric='All real chain gates and no new regression',success_criteria=criteria['gates'],failure_criteria=criteria['stop'])
m['design']['arms'][0].update(changes='Selected MAIN129 + read-only current work inventory; no repeated model baseline',controls='Original public Oracle corpus and selected release unchanged')
m['design']['arms'][1].update(changes='Current free workspace plus Oracle content store and empty-page cursor repair',controls='Same exact source and immutable model-input/protocol checks')
put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
c=ac.snapshot(A,'connected',sorted(names),experiment_id=m['experiment_id'],arm_id='connected',run_ids=['run-001']);print(c, len(names))
