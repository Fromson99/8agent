"""Freeze the authorized annex-only change against the currently selected MAIN."""
from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac

DES.mkdir(exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release=read(ROOT/ptr['manifest_path'])
assert ptr['generation']==148
assert sha(ROOT/ptr['manifest_path'])==ptr['release_manifest_sha256']
assert all(sha(ROOT/release['code_root']/n)==h for n,h in release['files'].items())
gold=ROOT/'08_DEPLOYMENT/LOCAL/gold_connection_engine_r12'
put(DES/'baseline.json',{'pointer':ptr,'release':release,'gold_binding':read(gold/'binding.json'),
    'gold_files':{str(p.relative_to(ROOT)):sha(p) for p in gold.iterdir() if p.is_file() and p.suffix in ('.json','.py','.yaml')},
    'working_files':{n:sha(ROOT/n) for n in release['files']}})
criteria={'authorization':'그러면 일단은 1. 별표 번호 처리 누락부분만 수정하고 메인에 반영해줘',
 'hypothesis':'The shared coordinate grammar preserves dashed annex numbers in occurrence, label, canonical surface and identity; existing consumers distinguish base and sibling annexes without changing source data or semantic choices.',
 'success':['Preserve annex 17-1 completely; distinguish 17,17-1,17-2 and form numbers through source-target validation and stored-structure lookup.',
 'Existing article, paragraph, branch, ACL and malformed-coordinate rejection remain intact; meaningful parser and consumer tests pass.',
 'Only legal_coordinate.py and derived engine pins change from selected MAIN148; SQL and all other product modules identical.',
 'Prepared same-byte release and fresh actual root service/Gold code binding pass; source generation and current148 transition checks preserved.'],
 'failure':['Scope drift, changed upstream or active MAIN, source mutation, wrong annex/sibling lookup, malformed suffix acceptance, failed selected-service check aborts or rolls back.'],
 'limits':['No external model calls; no legal answer quality or search accuracy claim; no source DB rewrite; historical persisted coordinates are not silently repaired.'],
 'known_failure':'ADR1402 source target coordinate annex 17-1 was parsed only through 17; later model call ended by host resources.'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json')
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Lossless coordinate identity and actual selected code/consumer contracts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['llm_policy']['llm_calls']=[]
m['dataset'].update(name='Synthetic annex coordinates and unchanged selected published source metadata',version='annex-dash-r1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'))
m['retrieval_accounting']['changed']=False
m['retrieval_accounting']['not_applicable_reason']='Deterministic coordinate and consumer contract repair; no retrieval quality comparison'
m['retrieval_accounting']['stage_ledger'].update(mode='not_applicable',not_applicable_reason='No retrieval effect comparison or legal-answer evaluation')
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Frozen parser/source-target/structure contracts then same-byte prepared and actual service checks; no live inference',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
for a in m['design']['arms']:a.update(changes='Historical MAIN148 reference' if a['id']=='baseline' else 'Shared dashed annex coordinate grammar only',controls='Same source data, all other product modules, default profile and inference settings')
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'repaired',list(release['files']),experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
for n in release['files']:shutil.copyfile(ROOT/release['code_root']/n,can/'snapshot'/n)
put(DES/'mutable-candidate.json',{'path':str(can.relative_to(ROOT)),'files':list(release['files'])})
print(can/'snapshot')
