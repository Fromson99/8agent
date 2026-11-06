from common import *
import shutil
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1371-statement-owned-ontology-build/artifacts'
DES.mkdir(exist_ok=False)
f=read(P/'design/candidate.json')
files=list(f['selected_files'])
before={n:sha(ROOT/n) for n in files}
put(DES/'working-before.json',before)
put(DES/'candidate-parent.json',f)
for n in ('baseline','source-scope','originals','originals-origin','records','provider-policy'):
    put(DES/(n+'.json'),read(P/'design'/(n+'.json')))
shutil.copytree(P/'transport',ART/'transport')
products=['02_BACKEND/semantic_runtime/ontology_work/'+n for n in ('wiki_projection.py','wiki_cli.py','wiki_ui.py')]
assert all(before[n]==f['selected_files'][n] for n in products)
criteria={'hypothesis':'An actual new judgment can be compared with current originals and recorded against the same workspace bundle without replacing its existing graph. A separately activated experimental revision may support another Qwen answer.',
 'success':['Independent actual corroborating judgment retained under the same bundle ID as revision 2, exact old graph/statement provenance, source quotes and new comparison history. Repetition adds no call.',
 'Actual contradictory provisional opinion kept with both bases and explicit conflict in a later draft; prior activated version remains distinct.',
 'Explicit test-copy review and publication, source arrival through DB lookup, actual wire assembly paths, valid committed claim use with exact refs and source-grounded answer. Compare identical question OFF and ON once.'],
 'failure':['No production or parent changes; never count delivery alone as usage, and do not equate one pair with general performance. Stop all new sends on UNKNOWN.'],
 'limits':{'authoring_per_followup':10,'physical_client_ceiling':11,'per_question':40,'heavy_workers':1,'provider':'existing Qwen3.8 FP8 policy, reasoning none'}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json')
m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Reopenable, source-grounded charter bundle accepted by compiler',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((DES/'criteria.json').relative_to(ROOT)),'sha256':sha(DES/'criteria.json')})
m['design']['arms'][0].update(changes='Completed1371/repaired exact stored charter DRAFT and verified source associations',controls='Reference only')
m['design']['arms'][1].update(changes='Version-bound follow-up observation comparison using canonical validation and immutable prior graph',controls='Same public originals, archived judgment, all selected statements, model and provider policy')
m['dataset'].update(name='Actual archived charter judgment and legal source snapshot',version='1354-frozen',frozen_source=str((DES/'records.json').relative_to(ROOT)),sha256=sha(DES/'records.json'),legal_version_checked=True,reference_version_checked=True)
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Fresh build once. Validation may request up to four additional proposals per stage. Stop on unknown.',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
m['llm_policy']['llm_calls']=m['llm_policy']['llm_calls'][:1]
m['runs'][0]['selection_rule']='Corroborate → review & activate isolated revision → same-question ON/OFF → conflicting opinion. Unknown stops all later external calls. On known non-corroboration use reviewed original or mark target explicitly.'
cases=[{'id':'charter-'+short,'arms':[arm],'document_ids':read(DES/'source-scope.json')['public'],'article':434,'steps':[{'number':1,'question':'상법 제433조 제1항과 제434조에 따라 정관을 변경할 때, 출석한 주주의 의결권과 발행주식총수에 각각 어떤 비율을 적용하며 두 기준을 모두 충족해야 하나요?','mode':'외규'}]} for short,arm in [('on','ontology-on'),('off','baseline')]]
put(DES/'live-cases.json',cases)
targets={}
for name,pattern,subpath in [('corroborate','ADR-1369-*/artifacts/public-live/B03-17-parasail/canonical/006-output.json.gz',['claims',0,'explanation']),('conflict','ADR-1341-*/artifacts/public-live/*/canonical/004-output.json.gz',['answer_progress','goals',0,'answer_so_far'])]:
 path=next((ROOT/'04_EXPERIMENTS/ADR').glob(pattern));value=read(path)
 for key in subpath:value=value[key]
 targets[name]={'path':str(path.relative_to(ROOT)),'sha256':sha(path),'pointer':subpath,'payload':value,'run_id':name+'-'+path.parents[1].name}
put(DES/'followups.json',targets)
put(DES/'authorization.json',{'scope':'Isolated copy of public parent1371, independent public archived opinions and comparative Qwen question; copied test publication only','public_ids':cases[0]['document_ids'],'production_writes':False})
m['dataset'].update(name='One existing charter draft, two archived opinions and one identical ON/OFF question',version='1373-r1',frozen_source=str((DES/'followups.json').relative_to(ROOT)),sha256=sha(DES/'followups.json'))
for x in (m['retrieval_accounting'],m['retrieval_accounting']['stage_ledger']):x['not_applicable_reason']='Fixed original authoring input; no answer/retrieval search experiment.'
put(ADR/'실험/manifest.json',m)
can=ac.snapshot(ADR,'repaired',files,experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001'])
for n in files:
    if sha(can/'snapshot'/n)!=f['selected_files'][n]:
        shutil.copyfile(ROOT/f['code_root']/n,can/'snapshot'/n)
assert all(sha(can/'snapshot'/n)==f['selected_files'][n] for n in files)
put(DES/'candidate-path.json',{'candidate':str(can.relative_to(ROOT)),'files':files,'product_files':products})
print(can/'snapshot')
