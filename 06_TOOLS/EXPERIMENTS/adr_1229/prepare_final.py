from common import *
import shutil
target=ROOT/'04_EXPERIMENTS/ADR/ADR-1231-source-semantics-state-main';T=ROOT/'06_TOOLS/EXPERIMENTS/adr_1231';T.mkdir(exist_ok=True);d=target/'artifacts/design';d.mkdir(parents=True,exist_ok=True)
b=read(DES/'baseline.json');f=read(DES/'freeze.json');m=read(target/'실험/manifest.json')
criteria=read(DES/'criteria.json');criteria['hypothesis']+='; remove impossible SAME from request relation enum when no base exists, preserving original canonical validation and all LLM legal choices.'
criteria['success']+=['No-base request cannot generate SAME; base-present SAME remains allowed only with exact graph equality','Unmodified actual rejected response remains rejected; any counterfactual diagnostic clearly marked synthetic, never saved as model success','Final frozen489 inventory, working and selected MAIN consumer match; no extra live model calls']
write_summary(d/'criteria.json',criteria);write_summary(d/'baseline.json',b);write_summary(d/'parent-candidate.json',f)
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Technical source/role/state contracts and exact integration; legal quality not certified',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((d/'criteria.json').relative_to(ROOT)),'sha256':sha(d/'criteria.json')},execution=criteria,arms=[{'id':'baseline','role':'baseline','derived_from':['ADR-1227-experiment-v1/source-first'],'changes':'MAIN122 and preserved1227/1229 candidates','controls':'same canonical contracts'},{'id':'source-contract','role':'candidate','derived_from':['baseline'],'changes':criteria['hypothesis'],'controls':'Original validation and legal decisions retained'}]);m['runs'][0].update(arm_ids=['baseline','source-contract'],selection_rule='Synthetic contracts and existing domain regression; archived outputs only diagnostic',artifact_path=str((target/'artifacts/run-001/result.json').relative_to(ROOT)));m['dataset'].update(name='Synthetic source/role/state contracts',version='v1',frozen_source=str((d/'criteria.json').relative_to(ROOT)),sha256=sha(d/'criteria.json'));m['llm_policy']['llm_calls']=[];m['retrieval_accounting']['not_applicable_reason']='Authoring only';m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='No retrieval experiment';(target/'실험/manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
C=ac.snapshot(target,'source-contract',sorted(b['manifest']['files']),experiment_id=m['experiment_id'],arm_id='source-contract',run_ids=['run-001'])
for n in f['files']:
 p=C/'snapshot'/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/f['code_root']/n,p)
 if n not in b['manifest']['files']:ac.register_file(C,n,upstream_state='absent')
p=C/'snapshot/02_BACKEND/semantic_runtime/ontology_work/accumulation.py';s=p.read_text();needle="    comparisons = schema['properties']['comparisons']\n";assert needle in s
s=s.replace(needle,needle+"    if base is None:\n        relations = comparisons['items']['properties']['relation']['enum']\n        comparisons['items']['properties']['relation']['enum'] = [v for v in relations if v != 'SAME']\n");p.write_text(s)
for n in ('common.py','check.py','test_semantics.py','consumer.py','integrate.py','qualify.py','freeze.py'):
 s=(Path(__file__).parent/n).read_text().replace('ADR-1229-source-meaning-evidence','ADR-1231-source-semantics-state-main').replace('adr_1229/meaning-evidence','adr_1231/source-contract').replace('20261030-source-meaning-evidence','20261030-source-semantics-main123').replace('source-meaning-evidence-20261030-r1','source-semantics-20261030-r1').replace("'meaning-evidence'","'source-contract'")
 if n=='freeze.py':s=s.replace("changes={n:sha(S/n) for n in parent['product_changes']}","changes={n:sha(S/n) for n in list(parent['product_changes'])+['02_BACKEND/semantic_runtime/ontology_work/accumulation.py']}")
 if n=='integrate.py':s=s.replace('len(products)==3','len(products)==4').replace("len(d['changes'])==34","len(d['changes'])==35")
 if n=='qualify.py':s=s.replace("c['passed']==82","c['passed']==84").replace("'technical_conditions':82","'technical_conditions':84").replace("'changed_files':34","'changed_files':35").replace('82/','84/').replace('82통과','84통과').replace('82검사','84검사').replace('기술82','기술84').replace('계약82','계약84').replace('신규35+기존47','신규37+기존47').replace('제품3(기존workflow1+신규2)','제품4(기존workflow/accumulation2+신규2)').replace('files489; changes34','files489; changes35')
 (T/n).write_text(s)
s=(T/'test_semantics.py').read_text()+'''
def test_no_base_schema_excludes_same(env):
    o=add_observation(env);p=env.w.selected_profile(env.profile_id,env.profile_work_hash)
    n=env.w.load(o['bundle_id'])['normalized']
    schema=acc.accumulation_schema(p,[n],originals=[env.source])
    assert 'SAME' not in schema['properties']['comparisons']['items']['properties']['relation']['enum']
    value=proposal(env,o,relation='SAME')
    with pytest.raises(ContractError):validate(value,schema)

def test_existing_base_schema_retains_exact_same(env):
    o=add_observation(env);p=env.w.selected_profile(env.profile_id,env.profile_work_hash)
    n=env.w.load(o['bundle_id'])['normalized'];value=proposal(env,o)
    base={'proposal':value,'observation_ledger':{}}
    schema=acc.accumulation_schema(p,[n],base,originals=[env.source])
    assert 'SAME' in schema['properties']['comparisons']['items']['properties']['relation']['enum']
    value['comparisons'][0]['relation']='SAME';validate(value,schema)
    acc.validate_proposal(value,p,[env.source],[n],base)
'''
(T/'test_semantics.py').write_text(s)
(target/'artifacts/schema-sizes.json').write_text((ART/'schema-sizes.json').read_text())
print(C/'snapshot')
