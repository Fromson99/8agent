"""Compose only ontology acquisition and direct assessment over selected MAIN106."""
from pathlib import Path
import hashlib,json,shutil,sys
R=Path(__file__).resolve().parents[3];sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
A=R/'04_EXPERIMENTS/ADR/ADR-1100-main106-ontology-direct';D=Path(__file__).parent
OLD=R/'02_BACKEND/lawrag/research/candidates/adr_1098/direct-r1/revisions/rev-001/snapshot'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
pointer=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';active=json.loads(pointer.read_text())
release_path=R/'08_DEPLOYMENT/RELEASES/compact-input-20261027-r1/release.json';release=json.loads(release_path.read_text());B=R/release['code_root']
assert active['release_id']==release['release_id']
assert all(sha(B/n)==h for n,h in release['files'].items())
criteria={'hypothesis':'MAIN106 unchanged selection/output contracts plus approved A1 ontology acquisition and direct ASSESS will deliver ontology meaning and verified originals together; ASSESS decides answer and gaps once, with existing MAIN reentry for actual gaps.',
 'sample':'Previously exposed CM023 only; in-sample diagnostic, no generalization or quality certification',
 'arms':['baseline','ontology'],'order':['baseline','ontology'],'repeats':1,
 'primary':['exact MAIN106 baseline binding','A1 ontology present in actual ASSESS wire with current evidence references','first ASSESS immediately after acquisition without another navigation choice','final answer outcome and actual extra investigation decisions'],
 'invariants':['MAIN106 response schemas, existing read_judgment final contract, compact input, SQL, model/provider, corpus and budgets unchanged','original spans/hash/version/ACL preserved','no gold in product','no active pointer change','no fallback or cell retry'],
 'failure_ownership':{'integrity':'existing ContractError stops; no model repair','semantic_uncertainty':'existing ASSESS gaps/reentry/limited answer; no new stop rule','schema':'MAIN106 one repair then existing final state','provider':'MAIN106 transport budget; unknown outcome stops experiment'},
 'limits':{'model_calls_per_arm':40,'tools_per_arm':1024,'wall_seconds_per_arm':1800,'max_output_tokens':None,'heavy_processes':1,'rss_bytes':4294967296,'available_ram_bytes':3221225472,'disk_free_bytes':21474836480},
 'offline_evaluation':'Local exact provenance/flow/retrieval audit and descriptive comparison against frozen evaluator-only CM023 references; no additional judge call, no certified legal accuracy',
 'recovery':'Preserve every failed/partial run. Changed implementation after results requires new ADR. MAIN106 remains selected.'}
put(A/'artifacts/criteria.json',criteria)
put(A/'artifacts/baseline.json',{'pointer':active,'pointer_sha256':sha(pointer),'release':release,'release_manifest_path':str(release_path.relative_to(R)),'release_manifest_sha256':sha(release_path)})
C=ac.snapshot(A,'ontology-r1',list(release['files']),experiment_id='ADR-1100-experiment-v1',arm_id='ontology',run_ids=['run-001']);S=C/'snapshot'
for n in release['files']:shutil.copyfile(B/n,S/n)
prefix='02_BACKEND/semantic_runtime/legal_agent/'
added=[prefix+n+'.py' for n in ('ontology_context','ontology_compiler','ontology_io','ontology_input','ontology_assessment')]+['00_SYSTEM/SCHEMAS/ontology-bundle-v0.schema.json']
for n in added:
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(OLD/n,p);ac.register_file(C,n,upstream_state='absent')
def change(n,old,new):
 p=S/prefix/n;s=p.read_text();assert s.count(old)==1,(n,old[:90],s.count(old));p.write_text(s.replace(old,new))
change('ontology_assessment.py',"and policy.get('execution_review') is True","and policy.get('completion_contract') is True")
change('ontology_assessment.py','미검토 원문은 read_judgment_review.pending_sources에서 현재 원문으로 검토한다.','read_judgments에 아직 검토하지 않은 원문이 있으면 현재 원문과 evidence_options로 최종 사용 여부를 판단한다.')
change('law_candidates.py',"'read_candidate_page_size': 20}","'read_candidate_page_size': 20, 'ontology_context': {'mode':'A0'}, 'ontology_direct_assessment': False}")
change('law_candidates.py',"    return result\n\n\ndef enabled", "    from .ontology_context import configuration\n    result['ontology_context']=configuration(result['ontology_context'])\n    if type(result['ontology_direct_assessment']) is not bool:raise ContractError('invalid ontology direct assessment flag')\n    if result['ontology_direct_assessment'] and not (result['completion_contract'] and result['compact_input'] and result['completion_policy_version']=='investigation-completion-v8'):\n        raise ContractError('ontology direct assessment requires modern compact completion')\n    return result\n\n\ndef enabled")
change('unit_relations.py','max_connections=None, preparation=None):','max_connections=None, preparation=None, grant_reads=True):')
change('unit_relations.py',"                grant(s,target,endpoint,witness={\n                    'anchor_source_id':anchor,'reference_id':ref['id'],'direction':direction,\n                    'witness_sha256':expected,'target_unit_id':end.get('unit_id')})", "                if grant_reads:\n                    grant(s,target,endpoint,witness={\n                        'anchor_source_id':anchor,'reference_id':ref['id'],'direction':direction,\n                        'witness_sha256':expected,'target_unit_id':end.get('unit_id')})")
change('law_navigation.py','def register_read(self, group, material, *, reason):','def register_read(self, group, material, *, reason, acquire_context=True):')
change('law_navigation.py','        prepare_delivery()\n        context_records', '        prepare_delivery()\n        if not acquire_context:return\n        context_records')
change('law_navigation.py',"                plan['completed'][target]=gid;plan['status']='STARTED';self.save()", "                if self.policy.get('ontology_context',{}).get('mode','A0')!='A0':\n                    plan.setdefault('primary_records',{})[gid]=deepcopy(self.p['selected'][gid])\n                plan['completed'][target]=gid;plan['status']='STARTED';self.save()")
change('law_navigation.py','            if model_selected:ids.extend(acquire_definition_context(self,list(ids)))',"            if model_selected:\n                primary=list(ids)\n                from .ontology_context import acquire as acquire_ontology\n                ids.extend(acquire_ontology(self,primary,primary_records=plan.get('primary_records')))\n                ids.extend(acquire_definition_context(self,primary))")
change('law_navigation.py',"                    'expanded': True, 'read_required': True})\n            read =", "                    'expanded': True, 'read_required': True})\n                if model_selected:\n                    from .ontology_context import acquire as acquire_ontology\n                    added=acquire_ontology(self,[group['id']])\n                    self.p['window_groups']=list(dict.fromkeys(self.p['window_groups']+added))\n            read =")
p=S/prefix/'law_navigation.py';s=p.read_text();old=(OLD/prefix/'law_navigation.py').read_text();start='    def assessment_handoff(self):';end='    def acquired_handoff_result('
s=s[:s.index(start)]+old[old.index(start):old.index(end)]+s[s.index(end):]
s=s.replace("'connection_scope_history','read_judgments'):","'connection_scope_history','read_judgments','ontology_context','ontology_assessment_prepared'):")
p.write_text(s)
change('completion_execution.py',"        basis = {'locator_options_hash':", "        from . import ontology_assessment\n        ontology_payload=ontology_assessment.project(self.s.sources,investigation,sources,options)\n        basis = {'locator_options_hash':")
change('completion_execution.py',"        signature = digest(basis)","        if ontology_payload:basis['ontology_context_hash']=digest(ontology_payload)\n        signature = digest(basis)")
change('completion_execution.py',"        if judgment_context is not None:answer_policy", "        if ontology_payload:answer_policy += '\\n'+ontology_assessment.PROMPT\n        if judgment_context is not None:answer_policy")
change('completion_execution.py',"                    'current_request': utterance,", "                    **({'ontology_bundles':ontology_payload['ontology_bundles']} if ontology_payload else {}),\n                    'current_request': utterance,")
# Neither the old investigation menus nor its alternate response contracts enter this snapshot.
changed=[n for n,h in release['files'].items() if sha(S/n)!=h]
assert set(changed)=={prefix+n for n in ('law_candidates.py','law_navigation.py','unit_relations.py','completion_execution.py')},changed
put(A/'artifacts/composition.json',{'base':'MAIN106','base_files':len(release['files']),'changed_product':changed,'added_product':added,'unchanged_main_response_contracts':True,'old_candidate_navigation_imported':False,'remaining_connection_catalog':'read-only grant_reads=False; MAIN default remains True','navigation_ontology_cards':'not connected; direct ASSESS only'})
print(S)
