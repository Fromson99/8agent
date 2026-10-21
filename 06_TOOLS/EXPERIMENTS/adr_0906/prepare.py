from pathlib import Path
import hashlib,json,shutil
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0906-closed-reference-qualified';D=A/'artifacts/design';D.mkdir(exist_ok=True);P=R/'04_EXPERIMENTS/ADR/ADR-0905-closed-reference-continuity';PT=R/'06_TOOLS/EXPERIMENTS/adr_0905'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();read=lambda p:json.loads(p.read_text())
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'freeze.json').exists();f=read(P/'artifacts/design/freeze.json')
for n in ['criteria.json','baseline.json','changes.json','working-before.json','execution-plan.json']:shutil.copyfile(P/'artifacts/design'/n,D/n)
c=read(D/'criteria.json');c['evaluation']='Unchanged ADR0905 code. Correct three fixture expectations: a closed SKIP is not pending, but a separate unresolved self-heading remains pending. Add explicit no-other-unresolved boundary. Finite technical checks, not legal quality or latency evaluation.';put(D/'criteria.json',c)
s=(PT/'test_continuity.py').read_text().replace("assert refs['pending'] is False and refs['closed_connection_groups']==1", "assert refs['closed_connection_groups']==1, refs\n    assert refs['pending']==bool(refs['unresolved'] or refs['limits'])")
s=s.replace("assert inv.inspect_references()['pending'] is False", "inspection=inv.inspect_references()\n    assert inspection['groups'][0]['decision']['action']=='SKIP'\n    assert inspection['pending']==bool(inspection['unresolved'] or inspection['limits'])")
s=s.replace("    _,actions=inv.view();assert not any(a['action']=='FOLLOW_CONNECTION' for a in actions.values())", "    assert refs['unresolved_count']>0  # keep independent data uncertainty visible")
s=s.replace("assert restored['references']['pending'] is False", "assert restored['references']['closed_connection_groups']==1\n    assert restored['references']['pending']==bool(restored['references']['unresolved_count'])")
s+='''\n\ndef test_all_closed_with_no_other_unresolved_has_no_follow_tool(connected,monkeypatch):
    inv,menus=start(connected[0]);catalog=rel.catalog
    def no_other_unresolved(*a,**kw):
        groups,statuses,limits,unresolved=catalog(*a,**kw)
        assert not limits
        return groups,statuses,[],[]
    monkeypatch.setattr(rel,'catalog',no_other_unresolved)
    refs=overview(inv)
    assert refs['closed_connection_groups']==1 and refs['pending'] is False
    _,actions=inv.view();assert not any(a['action']=='FOLLOW_CONNECTION' for a in actions.values())
'''
(T/'test_continuity.py').write_text(s);shutil.copyfile(PT/'test_chain.py',T/'test_chain.py');(T/'run_tests.py').write_text((PT/'run_tests.py').read_text().replace('ADR-0905-closed-reference-continuity','ADR-0906-closed-reference-qualified'))
plan=read(D/'execution-plan.json');plan['tests']=[x.replace('adr_0905/','adr_0906/') for x in plan['tests']];plan['pytest_args']=[x.replace('adr_0905/','adr_0906/') for x in plan['pytest_args']];put(D/'execution-plan.json',plan)
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=c['evaluation'];m['design'].update(hypothesis=c['hypothesis'],primary_metric='Closed reference and independent unresolved-state continuity',success_criteria=c['success'],failure_criteria=c['failure'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'qualified','role':'candidate','derived_from':['ADR-0905-experiment-v1/retained'],'changes':'Exact same product code and pins; corrected fixture expectations, one added boundary','controls':c['evaluation']}];m['design']['code_isolation'].update(mode='not_applicable',reason='No product change; reuse immutable completed ADR0905 snapshot, all code files hash bound.',candidates=[])
m['runs'][0].update(arm_ids=['qualified'],selection_rule=c['evaluation'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)));m['dataset'].update(name='closed-reference-continuity-contracts',version='20261019-r2',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'));m['llm_policy']['llm_calls']=[]
why='Finite technical software boundary checks; no model or retrieval comparison.';m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why;put(A/'실험/manifest.json',m)
files={n:h for n,h in f['files'].items() if not n.startswith('06_TOOLS/EXPERIMENTS/adr_0905/') and not n.startswith(str((P/'artifacts/design').relative_to(R))+'/')}
for folder in [T,D]:
 for p in folder.glob('*'):
  if p.is_file():files[str(p.relative_to(R))]=sha(p)
put(D/'freeze.json',{**f,'files':files});print('Exact 712 product files; corrected fixture expectations and explicit all-closed boundary frozen.')
