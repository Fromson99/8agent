exec((__import__('pathlib').Path(__file__).parent.parent/'adr_1225/common.py').read_text().replace('ADR-1225-cumulative-authoring-main','ADR-1227-source-first-authoring-semantics').replace('20261029-cumulative-authoring-main122','20261029-source-first-authoring').replace('adr_1225/authoring-contract','adr_1227/source-first'))
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1227/source-first';S=C/'snapshot';b=read(DES/'baseline.json')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
added=['02_BACKEND/semantic_runtime/ontology_work/'+n for n in ('recorded_fields.py','authoring_semantics.py')]
for n in added:ac.register_file(C,n,upstream_state='absent')
changed={n:sha(S/n) for n,h in b['manifest']['files'].items() if sha(S/n)!=h and n!='00_SYSTEM/PIPELINE.json' and not n.startswith('02_BACKEND/ENGINES/')}
changed.update({n:sha(S/n) for n in added});assert len(changed)==3
hashes={}
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if '02_BACKEND/semantic_runtime/ontology_work/domain_workflow.py' not in v.get('files',{}):continue
 before=sha(p);v['files'].update(changed);put(p,v);hashes[before]=sha(p)
p=S/'00_SYSTEM/PIPELINE.json';s=p.read_text()
for before,after in hashes.items():s=s.replace(before,after)
p.write_text(s)
put(DES/'fixture-bindings.json',{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')})
ac.freeze(C);assert not ac.validate(C),ac.validate(C)
v=read(C/'candidate.json')['revisions'][-1];code=C/'revisions'/v['revision_id']/'snapshot'
files={str((ROOT/x['frozen_path']).relative_to(code)):x['snapshot_sha256'] for x in v['files']}
binding={'manifest_path':str((C/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
put(DES/'freeze.json',{'code_root':str(code.relative_to(ROOT)),'files':files,'candidate_revision':binding,'product_changes':changed})
m=read(ADR/'실험/manifest.json');m['design']['fixture_bindings']=bind(DES/'fixture-bindings.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(binding,candidate_id='source-first',experiment_id=m['experiment_id'],arm_id='source-first',run_ids=['run-001'],runner_path=str((Path(__file__).parent/'check.py').relative_to(ROOT)),runner_sha256=sha(Path(__file__).parent/'check.py'))]);put(ADR/'실험/manifest.json',m)
print('Frozen',len(files),'files; product',len(changed),'pin',len(hashes)+1)
