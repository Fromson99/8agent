from common import *
import ast,sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
S=CAND/'snapshot'
# Extend the existing native-API fixture to exercise semantic delivery as well.
p=Path(__file__).with_name('test_direct.py');s=p.read_text()
s=s.replace("@pytest.mark.parametrize('need_more',[False,True])", "@pytest.mark.parametrize('with_semantics',[False,True])\n@pytest.mark.parametrize('need_more',[False,True])")
s=s.replace('monkeypatch,need_more):','monkeypatch,need_more,with_semantics):',1)
s=s.replace("            assert view['ontology_bundles'][0]['status']=='COMPLETE'", "            assert view['ontology_bundles'][0]['status']=='COMPLETE'\n            if with_semantics:\n                meaning=view['ontology_bundles'][0]['payload']['semantic_plan']\n                assert meaning['ordered_steps'] and meaning['authority']=='EXPERIMENT_PROPOSAL_NOT_APPROVED'\n                assert all(set(n.get('source_refs',[]))<={o['id'] for o in view['evidence_options']} for n in meaning['ordered_steps'])")
needle="    profile.update(model_binding=t.binding,answer_presentation='structured')"
s=s.replace(needle,"""    if with_semantics:
        from semantic_runtime.legal_agent import ontology_semantics as sem
        from test_semantics import fixture
        bound,_=fixture();original=bound['originals'][0]
        original.update(anchor=bundle_value['provisions'][0]['anchor'],text=provisions[0][1])
        for node in bound['proposal']['nodes']:
            for basis in node['basis']+[b for edge in node['dependencies'] for b in edge['basis']]:basis['quote']=provisions[0][1][:12]
        bound=sem.bind(bound['proposal'],bound['originals'],bound['judgments'])
        profile['candidate_navigation']['ontology_context']['semantic_binding']=bound
"""+needle)
p.write_text(s)
# Static parse before freezing, no candidate effect execution.
for p in list(S.rglob('*.py'))+list(Path(__file__).parent.glob('*.py')):ast.parse(p.read_text())
comp=read(ART/'composition.json');comp['added_product'].append('02_BACKEND/semantic_runtime/legal_agent/ontology_semantics.py');put(ART/'composition.json',comp)
pipeline=read(S/'00_SYSTEM/PIPELINE.json')
for ref in pipeline['engines'].values():
 ep=S/ref['manifest'];engine=read(ep)
 if '02_BACKEND/semantic_runtime/legal_agent/law_navigation.py' not in engine['files']:continue
 for n in comp['added_product']:engine['files'][n]=sha(S/n)
 for n in engine['files']:
  if (S/n).is_file():engine['files'][n]=sha(S/n)
 put(ep,engine);ref['sha256']=sha(ep)
put(S/'00_SYSTEM/PIPELINE.json',pipeline)
ac.freeze(CAND);errors=ac.validate(CAND);assert not errors,errors
cm=read(CAND/'candidate.json');rev=cm['revisions'][-1];code=CAND/'revisions'/rev['revision_id']/'snapshot'
files={str((ROOT/r['frozen_path']).relative_to(code)):r['snapshot_sha256'] for r in rev['files']}
binding={'candidate_id':CAND.name,'experiment_id':'ADR-1121-experiment-v1','arm_id':'semantic','run_ids':['run-001'],'manifest_path':str((CAND/'candidate.json').relative_to(ROOT)),'manifest_sha256':sha(CAND/'candidate.json'),'revision_id':rev['revision_id'],'revision_sha256':rev['revision_sha256'],'runner_path':'06_TOOLS/EXPERIMENTS/adr_1121/live.py','runner_sha256':sha(Path(__file__).with_name('live.py'))}
old=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1105-main106-ontology-cm023/artifacts/freeze.json');m=read(ADR/'실험/manifest.json')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[binding])
m['dataset'].update(name='Authorized known CM023 plus actual saved judgments/originals; reference answer excluded from all product stages',version=read(ART/'baseline.json')['release']['data_manifest_sha256'],frozen_source=str((ART/'cases.json').relative_to(ROOT)),sha256=sha(ART/'cases.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'semantic_proposal','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0},{'role':'service_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1,'temperature':0}]
stages=[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'assess_presented','kind':'present','parent_stage_ids':['original_read']},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['assess_presented']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('baseline','semantic')}
oldm=read(ROOT/'04_EXPERIMENTS/ADR/ADR-1105-main106-ontology-cm023/실험/manifest.json')
m['retrieval_accounting'].update(changed=True,corpus_total=oldm['retrieval_accounting']['corpus_total'],not_applicable_reason=None)
m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path=str((ART/'retrieval-ledger.json').relative_to(ROOT)),sha256='PENDING',not_applicable_reason=None)
put(ADR/'실험/manifest.json',m)
inputs=[ART/n for n in ('criteria.json','baseline.json','composition.json','cases.json','build-input.json','prefix.json')]+[ROOT/old['snapshot_path'],ROOT/'00_SYSTEM/EXPERIMENT_MODEL_POLICY.json',ROOT/'01_DATA/GOLDEN/CM_EXPORT_AUTHORIZATION_20261024.json']
f={'code_root':str(code.relative_to(ROOT)),'files':files,'binding':binding,'pointer_sha256':read(ART/'baseline.json')['pointer_sha256'],'snapshot_path':old['snapshot_path'],'snapshot_digest':old['snapshot_digest'],'inputs':{str(p.relative_to(ROOT)):sha(p) for p in inputs},'scripts':{str(p.relative_to(ROOT)):sha(p) for p in Path(__file__).parent.glob('*.py')},'manifest_sha256_at_freeze':sha(ADR/'실험/manifest.json'),'new_model_calls':0}
put(ART/'freeze.json',f);print('FROZEN',len(files))
