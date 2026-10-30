from pathlib import Path
import json,hashlib,sys,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1167-supervisor-route-identity';D=A/'artifacts/design';T=Path(__file__).parent;P=R/'04_EXPERIMENTS/ADR/ADR-1166-investigation-supervisor'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(P/'artifacts/design/freeze.json');parent=R/f['code_root'];m=read(A/'실험/manifest.json');m['lineage']['parents'][0]['manifest_sha256']=sha(P/'실험/manifest.json')
criteria={'hypothesis':'Route identity excludes explanation changes; same unrelated target cannot pass REDIRECT; no additional model calls.', 'checks':['Same tool/target plus new reason rejected','Same tool/target plus changed relation/source opinion rejected as no route change','Changed real query/structure/target accepted only through existing validator','Saved007 actual proposal rejected','Shadow/off and native API judgment/source/publication preserved','Resumed supervisor physical limit and independent material gaps preserved'], 'model_calls':0,'scope':'deterministic correction and same-code API validation, not new retrieval or legal quality comparison','parent_metadata_note':'1166 question heading ordering was finalized before candidate freeze; parent result and model artifacts unchanged; bind final validated parent manifest hash'}
put(D/'criteria.json',criteria);put(D/'baseline.json',read(P/'artifacts/design/baseline.json'))
m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Concrete identical route rejection, same-code API and failure contracts',success_criteria=criteria['checks'],failure_criteria='Any contract failure retains unpromoted candidate; no extra model call.',criteria_frozen_before_run=True,arms=[{'id':'repaired','role':'candidate','derived_from':['ADR-1166-experiment-v1/supervised'],'changes':'Exclude explanation fields from actual route identity','controls':'Other459files parent bytes preserved except dependency pins'}],retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{}})
m['runs'][0].update(arm_ids=['repaired'],selection_rule='Saved007 observed output and synthetic action/route/HTTP contracts; no model calls',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[];m['dataset'].update(name='Known saved007 conflicting supervisor action plus synthetic contracts',version='v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=False,reference_version_checked=False)
m['retrieval_accounting'].update(changed=False,not_applicable_reason=criteria['scope'],stage_ledger={'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','artifact_path':None,'sha256':None,'not_applicable_reason':criteria['scope']})
put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (R/n).is_file()];C=ac.snapshot(A,'repaired',present,experiment_id=m['experiment_id'],arm_id='repaired',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(parent/n)==h
 (S/n).parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(parent/n,S/n)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
put(D/'candidate.json',{'root':str(C.relative_to(R)),'snapshot':str(S.relative_to(R))})
p=S/'02_BACKEND/semantic_runtime/legal_agent/investigation_supervisor.py';s=p.read_text();s=s.replace('digest(revised)!=digest(decision)','route_identity(revised)!=route_identity(decision)').replace('digest(revised)==digest(decision)','route_identity(revised)==route_identity(decision)')
s+='''\n\ndef route_identity(decision):
    """Only executable operation/target/query/range define a new direction.

    Reasons, progress opinions and evidence sufficiency do not change an I/O.
    Existing canonical validation still checks authorization and all other fields.
    """
    return digest({'action':decision.get('next_action'),
        'targets':sorted(set(decision.get('targets',[]))),
        'queries':[' '.join(q.split()).casefold() for q in decision.get('queries',[])],
        'structure_filter':decision.get('structure_filter')})
''';p.write_text(s)
O=R/'06_TOOLS/EXPERIMENTS/adr_1166'
for n in ('common.py','freeze.py','check.py','test_supervisor.py','test_native_supervisor.py','api_fixture_integrated.py'):
 text=(O/n).read_text().replace('ADR-1166-investigation-supervisor','ADR-1167-supervisor-route-identity').replace("candidate_id='supervised'","candidate_id='repaired'").replace("arm_id='supervised'","arm_id='repaired'")
 (T/n).write_text(text)
# Test mock canonical actions must carry actual native target arrays.
p=T/'test_supervisor.py';s=p.read_text().replace("return {'next_action':'OPEN_LAW','target':v['target']}","return {'next_action':'OPEN_LAW','target':v['target'],'targets':[v['target']]}")
s+='''\n\ndef test_actual007_reason_change_cannot_redirect():
 from pathlib import Path
 import json
 root=Path(__file__).resolve().parents[3]
 saved=root/'04_EXPERIMENTS/ADR/ADR-1166-investigation-supervisor/artifacts/saved-input-probe/cm-007'
 prior=json.loads((saved/'canonical.json').read_text())['view']['proposed_action']
 after=json.loads((saved/'decision.json').read_text())['action']
 def native(v):return {'next_action':'READ_ARTICLES','targets':[r['target'] for r in v['selections']], 'reason':v['selections'][0]['missing_need']}
 assert native(prior)['reason']!=native(after)['reason']
 assert su.route_identity(native(prior))==su.route_identity(native(after))

@pytest.mark.parametrize('field,value',[('reason','새 이유'),('evidence_sufficient',True),('exploration',[{'source_ref':'new','relation':'DEPENDENCY'}])])
def test_opinion_change_is_not_new_route(field,value):
 a={'next_action':'READ_ARTICLES','targets':['T1']};b={**a,field:value}
 assert su.route_identity(a)==su.route_identity(b)

@pytest.mark.parametrize('field,value',[('targets',['T2']),('queries',['다른 검색']),('structure_filter',{'coordinate':'제2조'})])
def test_real_route_change(field,value):
 a={'next_action':'READ_ARTICLES','targets':['T1']};assert su.route_identity(a)!=su.route_identity({**a,field:value})

def test_same_route_redirect_handoffs_without_tool():
 inv,d,v,p,s,x=fixture();seed(inv,d)
 inv.invoke=lambda *a:{'directive':'REDIRECT','reason':'문구만 바꿈','remaining_scope':'원문 미확인','action':{'choice':'OPEN_LAW','target':'T1'}}
 with pytest.raises(ap.ProgressHandoff):call(inv,d,v,p,s,x)
 with pytest.raises(ContractError):su.before_execute(inv,d,x(v))
 assert su.state_for(inv,d)['calls']==1
''';p.write_text(s)
print('1167 candidate prepared; model0')
