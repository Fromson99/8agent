"""Prospective MAIN103 SQL-equivalence qualification; no corpus load."""
from pathlib import Path
import hashlib,json,subprocess,shutil
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-1073-navigation-sql-main-qualification';D=A/'artifacts/design'
read=lambda p:json.loads(p.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def main():
 D.mkdir(parents=True,exist_ok=True)
 assert not (D/'criteria.json').exists()
 targets=['02_BACKEND/semantic_runtime/legal_agent/definition_entry.py','02_BACKEND/semantic_runtime/search_selection.py']
 faults=['normal','source_text','source_hash','artifact_hash','original_unit','definition_block','term_start_type','term_bounds','term_label','source_acl','source_unit','orphan_reference','null_reference','reference_id','reference_source','reference_document','reference_block','reference_text','reference_hash','reference_span','target_missing','target_acl','target_unit','target_block','unresolved_target']
 criteria={'scope':'Prospective finite deterministic SQL transformation contract census on an exact MAIN103 derivative. Only two SQL hunks and required engine/pipeline hash pins differ.',
 'visibility_matrix':{'layout':['legacy','compact'],'definition':['visible','hidden','missing','null'],'reference':['visible','hidden','missing','null'],'endpoint':['visible','hidden','missing','none'],'duplicates':[1,2],'reverse_order':[False,True]},
 'definition_matrix':{'layout':['legacy','compact'],'fault':faults,'reverse_order':[False,True]},
 'empty_matrix':{'layout':['legacy','compact'],'links':[0,1,2,4],'link_table':[False,True]},
 'required':['Every finite matrix result or typed failure equals unchanged MAIN103 implementation','Expected visibility, duplicate multiplicity and stable ordering hold','Source text, artifact, span, identity, ACL and target guards remain effective','Main database rows and input objects unchanged; query_only and write authorizer retained','All valid compact point-query plans use indexed point lookups without whole reference materialization','Only the two authorized SQL transformations and hash pins change all420 selected serving files','Frozen evaluated release rebase and selected data/profile/search/model/budgets match MAIN103'],
 'failure':'Any primary matrix mismatch, guard relaxation, unexpected exception, database mutation, frozen-code drift or unauthorized changed serving file blocks qualification. Preserve first failure and do not change product code or criteria after seeing results.',
 'evaluation_boundary':'Out-of-sample and decision eligibility refer only to this prospectively fixed finite SQL/permission equivalence census. Prior ADR1066/1072 traces and existing11 tests are supplemental, not new legal holdout. No semantic quality or speed claim.',
 'new_model_calls':0,'heavy_corpus_workers':0,'external_network':False,'max_rss_bytes':1073741824,
 'rollback':'Standard activation rollback to immutable MAIN103 bytes; new activation generation, state and raw data preserved.'}
 put(D/'criteria.json',criteria)
 active=R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json';pointer=read(active);assert pointer['generation']==103
 release=read(R/pointer['manifest_path']);assert len(release['files'])==420
 put(D/'baseline.json',{'pointer':pointer,'pointer_sha256':sha(active),'manifest':release})
 put(D/'working-before.json',{n:sha(R/n) for n in release['files']})
 m=read(A/'실험/manifest.json');m['decision_eligible']=True;m['lineage']['hypothesis_delta']=criteria['scope']
 m['design'].update(hypothesis=criteria['scope'],primary_metric='Zero mismatch and zero guard regression across every prospectively frozen finite SQL/permission case',success_criteria=criteria['required'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
 m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
 for arm in m['design']['arms']:
  arm['changes']='Unmodified MAIN103 SQL functions, loaded by explicit immutable path for mechanical comparisons' if arm['id']=='baseline' else 'MAIN103 plus two SQL lookup transformations; no other product, policy, schema, profile or data change'
  arm['controls']=criteria['evaluation_boundary']
 m['runs'][0].update(selection_rule='Complete Cartesian product declared in criteria.json, plus existing11 supplemental regressions; no sample selection by result',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
 m['dataset'].update(name='Prospective finite SQL visibility and failure contract census',version='sql-main-v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'),legal_version_checked=True,reference_version_checked=True)
 m['llm_policy']['llm_calls']=[]
 reason='Only deterministic SQL implementation equivalence on generated tiny fixtures; no real corpus retrieval, ranking, legal answer or model evaluation.'
 m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason
 put(A/'실험/manifest.json',m)
 names=set(release['files'])|{'05_TESTS/CONTRACTS/test_definition_reference_lookup_adr1071.py','05_TESTS/CONTRACTS/test_definition_selection_exists_adr1072.py'}
 cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','sql-main-r1','--experiment-id',m['experiment_id'],'--arm-id','optimized','--run-id','run-001']
 for n in sorted(names):cmd+=['--source',n]
 subprocess.run(cmd,cwd=R,check=True,stdout=subprocess.DEVNULL)
 C=R/'02_BACKEND/lawrag/research/candidates/adr_1073/sql-main-r1';S=C/'snapshot'
 for n,h in release['files'].items():
  base=R/release['code_root']/n;assert sha(base)==h
  if n not in targets:shutil.copyfile(base,S/n)
 # Repin exactly the two changed modules; no broad working-tree rehash.
 config=read(S/'00_SYSTEM/PIPELINE.json')
 for entry in config['engines'].values():
  p=S/entry['manifest'];engine=read(p);changed=False
  for n in targets:
   if n in engine['files']:engine['files'][n]=sha(S/n);changed=True
  if changed:put(p,engine);entry['sha256']=sha(p)
 put(S/'00_SYSTEM/PIPELINE.json',config)
 put(D/'candidate-preparation.json',{'candidate_path':str(C.relative_to(R)),'source_targets':targets,'main103_files':420,'serving_files':{n:sha(S/n) for n in release['files']},'changed':[n for n,h in release['files'].items() if sha(S/n)!=h]})
 print('Criteria frozen; MAIN103 selective candidate prepared; no matrix executed')
if __name__=='__main__':main()
