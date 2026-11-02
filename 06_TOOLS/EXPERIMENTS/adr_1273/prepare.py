from pathlib import Path
import json,hashlib,sys
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1273-gold-user-directed-main-binding';D=A/'artifacts'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
criteria={'hypothesis':'An explicit Gold binding to the official user-directed release authorization and structural validation can preserve all exact-byte checks while supporting the user-authorized MAIN cutover.',
 'success':['Qualified existing path retained','User-directed path requires explicit matching authorization/validation hashes and actual user authorization','Missing grant, forged authority, hash drift, failed structural validation or mismatched release rejected','Existing Gold mapping tests remain green'],
 'failure':['Implicit acceptance of arbitrary USER_DIRECTED release','Changed source/connector hash validation or Oracle contents'], 'model_calls':0,'oracle_calls':0}
put(D/'criteria.json',criteria)
m=json.loads((A/'실험/manifest.json').read_text());m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Explicit authority and exact-byte consumer contracts',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,criteria_freeze_evidence={'path':str((D/'criteria.json').relative_to(R)),'sha256':sha(D/'criteria.json')})
m['design']['arms'][0].update(changes='Existing qualified-only guard, historical/read-only evidence',controls='No new baseline model or Oracle call');m['design']['arms'][1].update(changes='Add explicit official user-directed authorization receipt checks',controls='Same release ID, source/engine/connector hashes and physical mappings')
m['runs'][0].update(arm_ids=['compatible'],selection_rule='Predeclared authority rejection matrix and existing Gold mapping contracts',artifact_path=str((D/'result.json').relative_to(R)))
m['llm_policy']['llm_calls']=[];reason='Connector release authority only, no retrieval benchmark';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
put(A/'실험/manifest.json',m)
sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
target='08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/connect.py'
C=ac.snapshot(A,'compatible',[target],experiment_id=m['experiment_id'],arm_id='compatible',run_ids=['run-001']);p=C/'snapshot'/target;s=p.read_text()
helper='''def verify_main_authority(active,binding,manifest_path,manifest):
 """Accept an explicit official cutover grant without claiming quality qualification."""
 basis=active.get('deployment_basis')
 if manifest.get('deployment_basis')!=basis:raise RuntimeError('Gold MAIN deployment basis mismatch')
 if basis=='VALIDATED_ADR_PROMOTION':return
 grant=binding.get('main_authorization')
 expected={'release_id':active['release_id'],'authorization_sha256':manifest.get('authorization_sha256'),
           'validation_sha256':manifest.get('validation_sha256')}
 if basis!='USER_DIRECTED_CUTOVER' or not isinstance(grant,dict) or grant!=expected:
  raise RuntimeError('Gold user-directed MAIN requires an explicit matching authorization binding')
 auth_path=manifest_path.parent/'authorization.json';validation_path=manifest_path.parent/'validation.json'
 if not auth_path.is_file() or not validation_path.is_file() or sha(auth_path)!=grant['authorization_sha256'] or sha(validation_path)!=grant['validation_sha256']:
  raise RuntimeError('Gold MAIN authorization or validation hash changed')
 auth=read(auth_path);validation=read(validation_path)
 if (auth.get('authorized_by')!='user' or not isinstance(auth.get('authorization_text'),str)
     or not auth['authorization_text'].strip() or auth.get('quality_gate_override') is not True
     or validation.get('structural_checks_passed') is not True):
  raise RuntimeError('Gold MAIN lacks explicit user authorization or structural validation')


'''
assert 'def verify_main_authority' not in s;s=s.replace('def engine_binding():',helper+'def engine_binding():')
s=s.replace('Require the independently qualified local MAIN and its exact serving bytes.','Require the exact selected MAIN with qualified or explicitly bound user authority.')
s=s.replace("active.get('deployment_basis')!='VALIDATED_ADR_PROMOTION'", "active.get('deployment_basis') not in ('VALIDATED_ADR_PROMOTION','USER_DIRECTED_CUTOVER')")
s=s.replace('manifest=read(manifest_path)\n', 'manifest=read(manifest_path)\n verify_main_authority(active,binding,manifest_path,manifest)\n')
p.write_text(s);ac.freeze(C);assert not ac.validate(C),ac.validate(C)
v=json.loads((C/'candidate.json').read_text())['revisions'][-1];pin={'manifest_path':str((C/'candidate.json').relative_to(R)),'manifest_sha256':sha(C/'candidate.json'),'revision_id':v['revision_id'],'revision_sha256':v['revision_sha256']}
put(D/'freeze.json',{'code_root':str((C/'revisions'/v['revision_id']/'snapshot').relative_to(R)),'target':target,'before':sha(R/target),'after':sha(p),'candidate_revision':pin})
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[dict(pin,candidate_id='compatible',experiment_id=m['experiment_id'],arm_id='compatible',run_ids=['run-001'],runner_path=str(Path(__file__).relative_to(R)),runner_sha256=sha(Path(__file__)))])
put(A/'실험/manifest.json',m);print('Frozen explicit Gold authority compatibility')
