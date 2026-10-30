from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[3];ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-1099-nonmodel-bounded-preparation'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1099/performance-r1';S=C/'snapshot'
p=S/'02_BACKEND/semantic_runtime/legal_agent/law_navigation.py';t=p.read_text()
old='        if read_choice is not None:return read_choice\n        system=SELECTABLE_SYSTEM'
new="        if read_choice is not None:return read_choice\n        if self.policy.get('minimal_input'):\n            candidates={k:a for k,a in actions.items() if a['action']=='READ_ARTICLES'}\n            data=self.prepare_read_details(data,candidates,candidates)\n        system=SELECTABLE_SYSTEM"
assert t.count(old)==1 or new in t
if old in t:p.write_text(t.replace(old,new))
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
new='02_BACKEND/semantic_runtime/legal_agent/schema_preparation.py'
if not any(r.get('target_path')==new for r in json.loads((C/'candidate.json').read_text())['files']):
    ac.register_file(C,new,upstream_state='absent')
# Bind every affected engine to the exact candidate bytes, including the new helper.
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
    d=json.loads(p.read_text());files=d.get('files',{})
    if not files:continue
    if '02_BACKEND/semantic_runtime/legal_agent/read_judgment.py' in files:files[new]=sha(S/new)
    for n in files:
        if (S/n).is_file():files[n]=sha(S/n)
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
if not json.loads((C/'candidate.json').read_text())['revisions']:ac.freeze(C)
m=json.loads((C/'candidate.json').read_text());rev=m['revisions'][-1]
code=C/'revisions'/rev['revision_id']/'snapshot'
binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),
         'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
freeze={'code_root':str(code.relative_to(ROOT)),'binding':binding,
        'files':{str((ROOT/r['frozen_path']).relative_to(code)):r['snapshot_sha256'] for r in rev['files']},
        'scripts':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')}}
put(ADR/'artifacts/design/freeze.json',freeze)
m=json.loads((ADR/'실험/manifest.json').read_text());m['design']['code_isolation']['candidates']=[dict(binding,
    candidate_id=C.name,experiment_id=m['experiment_id'],arm_id='optimized',run_ids=['run-001'],
    runner_path='06_TOOLS/EXPERIMENTS/adr_1099/check.py',runner_sha256=sha(Path(__file__).with_name('check.py')))]
put(ADR/'실험/manifest.json',m)
print(code)
