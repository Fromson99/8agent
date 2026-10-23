"""Apply only verified modules/tests; never replace a candidate tree or select MAIN."""
from common import *
import shutil,subprocess
s=read(ART/'stage.json');f=read(ART/'design-freeze.json');C=ROOT/s['roots']['candidate']
assert read(ART/'regression-review.json')['deterministic_gates_pass']
assert not (ART/'working-integration.json').exists()
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
files=['02_BACKEND/semantic_runtime/legal_agent/'+n for n in ('unit_relations.py','navigation_input.py')]
files += ['05_TESTS/CONTRACTS/'+n for n in ('test_navigation_input_compaction.py','test_selected_connection_scope_api.py',
 'test_retained_partial_connections.py','test_batch_reference_navigation.py')]
assert all(sha(C/n)==f['files']['candidate'][n] for n in f['files']['candidate'])
for n in files:assert sha(ROOT/n)==s['working_before'][n], 'concurrent working edit: '+n
helper='05_TESTS/CONTRACTS/test_read_choice_input_preservation.py'
assert sha(ROOT/helper)==sha(C/helper)
helper_before=sha(ROOT/helper)
backup=ART/'working-before';backup.mkdir(exist_ok=False)
backup_files=files+[helper,'00_SYSTEM/PIPELINE.json']+[str(p.relative_to(ROOT)) for p in (ROOT/'02_BACKEND/ENGINES').rglob('*.json')]
for n in backup_files:
 dst=backup/n;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dst)
for n in files:shutil.copyfile(C/n,ROOT/n)
p=ROOT/helper;src=p.read_text()
old="return codec.restore(json.loads(request['messages'][1]['content'])['view'])"
new="from semantic_runtime.legal_agent.navigation_input import expand_cards\n    return expand_cards(codec.restore(json.loads(request['messages'][1]['content'])['view']))"
assert src.count(old)==1
p.write_text(src.replace(old,new))
subprocess.run([str(ROOT/'.venv/bin/python'),'-B',str(Path(__file__).with_name('repin.py')),str(ROOT)],check=True,cwd=ROOT)
assert all(sha(ROOT/n)==sha(C/n) for n in files)
assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==s['pointer_sha256']
save(ART/'working-integration.json',{'changed_files':{n:{'before':s['working_before'][n],'after':sha(ROOT/n),'frozen_candidate_match':True} for n in files},
 'fixture_decoder_update':{'file':helper,'before':helper_before,'after':sha(ROOT/helper),'same_logic_verified_by':'wire-fixture.xml','product_source_changed':False},
 'backup_files':{n:sha(backup/n) for n in backup_files},'backup_root':str(backup.relative_to(ROOT)),
 'engine_pins':read(ART/'working-pins.json'),'main_unchanged':True,'genos_changed':False,
 'rollback':'Restore only changed modules/tests and affected manifest pins from working-before after checking for subsequent edits. No release pointer was changed.'})
print('Integrated',len(files),'modules/tests; selected MAIN unchanged')
