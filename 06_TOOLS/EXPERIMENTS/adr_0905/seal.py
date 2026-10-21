from pathlib import Path
import hashlib,json,subprocess,sys
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0905-closed-reference-continuity';D=A/'artifacts/design';C=R/'02_BACKEND/lawrag/research/candidates/adr_0905/retained';S=C/'snapshot'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists()
products={'02_BACKEND/semantic_runtime/legal_agent/'+n+'.py' for n in ['law_navigation','unit_relations']};changed=set(products)
for n in products:compile((S/n).read_text(),n,'exec')
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p);used=products&v.get('files',{}).keys()
 if used:
  for n in used:v['files'][n]=sha(S/n)
  put(p,v);changed.add(str(p.relative_to(S)))
p=S/'00_SYSTEM/PIPELINE.json';v=read(p)
for e in v['engines'].values():
 if e['manifest'] in changed:e['sha256']=sha(S/e['manifest'])
put(p,v);changed.add('00_SYSTEM/PIPELINE.json')
before=read(D/'working-before.json');assert {n for n,h in before.items() if sha(S/n)!=h}==changed
put(D/'changes.json',[{'path':n,'before':before[n],'after':sha(S/n)} for n in sorted(changed)])
# This historical test intentionally asserted re-judgment after SKIP. Freeze
# its replacement expectation, preserving all other chain contracts.
text=(R/'05_TESTS/CONTRACTS/test_investigation_chain_adr0671.py').read_text()
a=text.index('def test_real_reference_return_reoffers_identical_menu_after_skip(');b=text.index('\ndef test_repeated_same_choice',a)
text=text[:a]+text[a:b].replace('test_real_reference_return_reoffers_identical_menu_after_skip','test_real_reference_return_reuses_closed_skip').split('    assert len(menus)==2')[0]+'''    assert len(menus)==1
    assert chain.frame(inv.p,fid)['data']['groups']==original
    assert any(step['action']=='RETURN_TO' for step in chain.context(inv.p)['steps'])
    assert any(step['reference_decisions'] for step in chain.context(inv.p)['steps'])
'''+text[b:]
(T/'test_chain.py').write_text(text)
tests=[str((T/'test_continuity.py').relative_to(R)),str((T/'test_chain.py').relative_to(R)),'05_TESTS/CONTRACTS/test_read_choice_input_preservation.py','05_TESTS/CONTRACTS/test_output_contract_recovery.py','06_TOOLS/EXPERIMENTS/adr_0887/test_focus.py','05_TESTS/CONTRACTS/test_batch_reference_navigation.py::test_forged_reference_witness_is_rejected','05_TESTS/CONTRACTS/test_batch_reference_navigation.py::test_reference_choices_cannot_escape_closed_group_contract','05_TESTS/CONTRACTS/test_batch_reference_navigation.py::test_no_verified_links_does_not_create_a_model_turn']
# Old chain API fixture uses an obsolete team selector. The current API is
# exercised by test_read_choice_input_preservation against the same code/pins.
plan={'tests':tests,'pytest_args':['--deselect='+str((T/'test_chain.py').relative_to(R))+'::test_native_api_exposes_chain_and_preserves_it_for_answer'],'model_calls':0,'purpose':read(D/'criteria.json')['evaluation']};put(D/'execution-plan.json',plan)
runner=(R/'06_TOOLS/EXPERIMENTS/adr_0903/run_tests.py').read_text().replace('ADR-0903-read-input-connected-contract','ADR-0905-closed-reference-continuity');(T/'run_tests.py').write_text(runner)
subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','refresh',str(C)],check=True,stdout=subprocess.DEVNULL);subprocess.run([sys.executable,'06_TOOLS/run_tool.py','adr_candidate.py','freeze',str(C)],check=True,stdout=subprocess.DEVNULL)
cm=read(C/'candidate.json');rev=cm['revisions'][-1];code=C/'revisions'/rev['revision_id']/'snapshot';binding={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256']}
files={str((code/n).relative_to(R)):sha(code/n) for n in before}
for folder in [T,D]:
 for p in folder.glob('*'):
  if p.is_file():files[str(p.relative_to(R))]=sha(p)
# Freeze the complete small contract fixture set, rather than duplicate it.
for p in (R/'05_TESTS/CONTRACTS').glob('*.py'):files[str(p.relative_to(R))]=sha(p)
for n in ['06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py','06_TOOLS/EXPERIMENTS/adr_0885/test_focus.py','06_TOOLS/EXPERIMENTS/adr_0892/test_focus.py','06_TOOLS/EXPERIMENTS/adr_0832/test_delivery.py','05_TESTS/conftest.py','06_TOOLS/EXPERIMENTS/resource_guard.py','06_TOOLS/EXPERIMENTS/adr_0887/test_focus.py']:files[n]=sha(R/n)
put(D/'freeze.json',{'code_root':str(code.relative_to(R)),'files':files,'candidate':binding,'serving_files':{n:sha(code/n) for n in read(D/'baseline.json')['release']['files']},'legal_holdout':False})
m=read(A/'실험/manifest.json');m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[{**binding,'candidate_id':'retained','arm_id':'retained','experiment_id':m['experiment_id'],'run_ids':['run-001'],'runner_path':str((T/'run_tests.py').relative_to(R)),'runner_sha256':sha(T/'run_tests.py')}]);put(A/'실험/manifest.json',m)
print('Sealed',len(changed),'code/pin changes and finite contract suite.')
