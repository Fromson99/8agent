from pathlib import Path
import json,hashlib,sys,shutil
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1106-preparation-without-wire-change';ART=ADR/'artifacts';OLD=ROOT/'04_EXPERIMENTS/ADR/ADR-1102-candidate-page-serialization'
def read(p):return json.loads(p.read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
criteria=read(OLD/'artifacts/design/criteria.json');criteria.update(frozen_at=datetime.now(timezone.utc).isoformat(),hypothesis='A-C preparation reuse preserves all protected tape requests; D lazy preview is deferred to input version with durable identifiers.',scope=['document-only PLAN and schema preparation','bounded source batches and exact metadata costs','exact query/scope/ACL projection reuse'],failure='Stop on any protected request/source/answer mismatch. No model calls or MAIN change.')
put(ART/'design/criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Protected tape equality and actual SQL counts',success_criteria=criteria['primary'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True);m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None);m['dataset'].update(name='Frozen nine-response trace with A-C contracts',version='v1',frozen_source=str((ART/'design/criteria.json').relative_to(ROOT)),sha256=sha(ART/'design/criteria.json'));m['llm_policy']['llm_calls']=[]
for a in m['design']['arms']:a.update(changes='Completed1102failure' if a['id']=='baseline' else criteria['scope'],controls='Exact same source/model tape/ACL/budgets and presentation contract')
put(ADR/'실험/manifest.json',m)
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
f=read(OLD/'artifacts/design/freeze.json');parent=ROOT/f['code_root'];new='02_BACKEND/semantic_runtime/legal_agent/schema_preparation.py'
C=ac.snapshot(ADR,'preparation-r1',[n for n in f['files'] if n!=new],experiment_id=m['experiment_id'],arm_id='optimized',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(parent/n)==h;shutil.copyfile(parent/n,S/n)
ac.register_file(C,new,upstream_state='absent')
# Exact prior MAIN106 menu and schema construction, retaining only A's validator reuse.
release=read(ROOT/'08_DEPLOYMENT/RELEASES/compact-input-20261027-r1/release.json');base=ROOT/'08_DEPLOYMENT/RELEASES/compact-input-20261027-r1/code';AG='02_BACKEND/semantic_runtime/legal_agent/'
for name in ['law_navigation.py','decision_projection.py','read_candidate_pages.py']:
 assert sha(base/AG/name)==release['files'][AG+name];shutil.copyfile(base/AG/name,S/AG/name)
p=S/AG/'read_candidate_pages.py';t=p.read_text().replace('from jsonschema import validate','from .schema_preparation import validate').replace('validate(value, wire)','validate(value, wire, owner=inv.s)');p.write_text(t)
p=S/AG/'decision_projection.py';t=p.read_text().replace('from jsonschema import validate','from jsonschema import validate\nfrom .schema_preparation import validate as prepared_validate, OrderedSchemaValidators').replace('    def expand(raw):\n        validate(raw,wire)','    validators = OrderedSchemaValidators()\n    def expand(raw):\n        validators.validate(raw,wire)').replace('        validate(value,schema)\n        return value','        validators.validate(value,schema)\n        return value').replace('        validate(value,schema)','        prepared_validate(value,schema,owner=inv.s)').replace('judgment.validate_review(value,judgment_context,current,issues)','judgment.validate_review(value,judgment_context,current,issues,owner=inv.s)');p.write_text(t)
for name in ['check.py','replay.py','test_preparation.py']:
 t=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1102'/name).read_text().replace('ADR-1102-candidate-page-serialization',ADR.name).replace('adr_1102','adr_1106')
 if name=='test_preparation.py':t=t[:t.index('def test_only_visible_details_prepared_and_resume_reuses')]
 (Path(__file__).parent/name).write_text(t)
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 d=read(p)
 for n in d.get('files',{}):d['files'][n]=sha(S/n)
 if d.get('files'):put(p,d)
p=S/'00_SYSTEM/PIPELINE.json';d=read(p)
for e in d['engines'].values():e['sha256']=sha(S/e['manifest'])
put(p,d)
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
ac.freeze(C);v=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot';binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
put(ART/'design/freeze.json',{'code_root':str(code.relative_to(ROOT)),'binding':binding,'files':{str((ROOT/r['frozen_path']).relative_to(code)):r['snapshot_sha256'] for r in v['files']},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')}})
plan=read(OLD/'artifacts/design/replay.json');plan['runner_sha256']=sha(Path(__file__).with_name('replay.py'));put(ART/'design/replay.json',plan)
m['design']['code_isolation']['candidates']=[dict(binding,candidate_id=C.name,experiment_id=m['experiment_id'],arm_id='optimized',run_ids=['run-001'],runner_path='06_TOOLS/EXPERIMENTS/adr_1106/replay.py',runner_sha256=plan['runner_sha256'])];put(ADR/'실험/manifest.json',m);print(code)
