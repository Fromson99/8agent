from pathlib import Path
import hashlib,json,subprocess,shutil
R=Path.cwd();A=R/'04_EXPERIMENTS/ADR/ADR-0810-evidence-completeness-comparison';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(p);manifest=read(R/pointer['manifest_path']);assert sha(R/pointer['manifest_path'])==pointer['release_manifest_sha256']
put(D/'baseline.json',dict(pointer=pointer,pointer_sha256=sha(p),manifest=manifest))
put(D/'working-before.json',{n:sha(R/n) for n in manifest['files']})
put(D/'data-binding.json',dict(path=manifest['data_path'],manifest_sha256=sha(R/manifest['data_path']/'manifest.json')))
criteria={'hypothesis':'General source-coordinate resolution, complete definition acquisition accounting, parent-child issue provenance, intact citation spans and numeric comparison contracts remove reproducible false omissions and unsupported deferred conclusions without question-specific answers or arbitrary slicing.',
 'controls':['MAIN75 source generation and document/ACL selection','Qwen3.8 Parasail FP8 reasoning none no fallback','existing single repair owner and global budgets','exact source/hash/state/restart validation'],
 'success':['All changed contracts pass including missing/ambiguous attachment, >8 definition targets, failed reads/resume, long intact quotes and request provenance','Parent issue identity survives native child export and followup','DIFFERENT numerical criteria can support conflict; UNKNOWN cannot become substantive judgment','System DEFERRED output does not reproduce unverified absence claims','Actual service entry with same frozen source and pins passes; no active changes before qualification'],
 'failure':['invented source/absence/applicability','scope/hash/state integrity regression','silent dropped source text or issue','retries reset budget'],
 'failure_contract':{'classification':['source_location','source_completeness','semantic_field_conflict','provenance'], 'owner':'existing navigation/request repair and workflow model adapters; system deterministic projection only', 'correction':'Only bound IDs, literal source copies and actual incomplete states; no guessed legal meaning', 'budget':'Existing profile/request deadlines/tool/model allowances unchanged; incomplete acquisition must retain pending/failed state', 'final':'Verified current spans and explicit incompleteness; never treat failed or incomplete read as absence', 'tests':'normal, ambiguous/missing/failed recovery, budget, repeat, resume, stale/hash/ACL and actual service consumers'},
 'evaluation':{'type':'known-defect structural probe; no legal accuracy or holdout claim','model':'optional prospectively frozen synthetic comparison cases, exact prompts/results kept separately','gold':'risk_cm remains question_only; no internal data or annotations sent to external model'}}
put(D/'criteria.json',criteria)
m=read(A/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Reproducible boundary failures resolved without source or semantic fabrication',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
for a in m['design']['arms']:a.update(changes='Selected MAIN75 baseline' if a['id']=='baseline' else criteria['hypothesis'],controls=criteria['controls'])
m['runs'][0].update(selection_rule='Prospectively frozen defect contracts and actual API, synthetic public model cases if declared before freeze',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='evidence-completeness-contracts',version='20261016-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
m['llm_policy']['llm_calls']=[]
m['retrieval_accounting']['not_applicable_reason']='No corpus answer-quality comparison; structural resolver and exact acquisition contract fixtures are fully preserved. Any retrieval-effect measurement needs separate frozen stages.'
m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=m['retrieval_accounting']['not_applicable_reason']
put(A/'실험/manifest.json',m)
cmd=['.venv/bin/python','06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','connected','--experiment-id',m['experiment_id'],'--arm-id','connected','--run-id','run-001']
for n in manifest['files']:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
C=R/'02_BACKEND/lawrag/research/candidates/adr_0810/connected/snapshot';base=R/manifest['code_root']
for n,h in manifest['files'].items():assert sha(base/n)==h;shutil.copyfile(base/n,C/n)
T=R/'06_TOOLS/EXPERIMENTS/adr_0810'
for name in ['run_tests.py','consumer_check.py','repin.py','freeze.py']:
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0809'/name).read_text().replace('0809','0810').replace('system-mechanics-qualification','evidence-completeness-comparison').replace('1.1.0','1.2.0').replace('MAIN74','MAIN75')
 (T/name).write_text(s)
print('MAIN75 isolated:',len(manifest['files']),'files; criteria before implementation')
