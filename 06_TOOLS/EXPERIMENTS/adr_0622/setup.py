"""Reserve-first design and exact parent snapshot; no production mutation."""
import hashlib,importlib.util,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
ADR=ROOT/'04_EXPERIMENTS/ADR/ADR-0622-batch-reference-navigation'
PARENT=ROOT/'04_EXPERIMENTS/ADR/ADR-0621-unit-read-canonical-boundaries'
def read(p):return json.loads(p.read_text())
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 m=read(ADR/'실험/manifest.json');assert m['results']['status']=='not_run'
 design=ADR/'artifacts/design';design.mkdir(parents=True,exist_ok=True)
 for name in ('inputs.json','gold.json','source-coordinates.json','source-binding.json'):
  shutil.copy2(PARENT/'artifacts/design'/name,design/name)
 m['lineage']['hypothesis_delta']='Expose verified forward/reverse references as grouped selectable routes even for exact structure MATCH; only model-chosen extents are read.'
 stages=[('corpus','source'),('recall','retrieve'),('read','filter'),('initial_selection','select'),('relations','expand'),('selection','select'),('present','present')]
 plans=[{'stage_id':s,'kind':k,'parent_stage_ids':[] if i==0 else [stages[i-1][0]]} for i,(s,k) in enumerate(stages)]
 m['design'].update(hypothesis=m['lineage']['hypothesis_delta'],primary_metric='Verified grouped decisions, exact chosen READ and shared evidence consumers; live required source root selection is a separate metric.',
  success_criteria='All inherited and new relation contracts pass; both public cases complete without scope/hash/READ errors; CM003 selects the existing reverse-linked bylaw source; no per-edge LLM loop.',
  failure_criteria='Unverified or out-of-scope relation executed, unoffered READ accepted, skipped relation read, unlimited frontier, missing shared evidence, or CM003 reverse-link selection failure.',
  criteria_frozen_before_run=True,controls='Same frozen ADR0621 implementation/index/store/model/query/context. Fresh paired selector-only probes; candidate adds at most two batched relation calls. No final legal-answer grading.',
  navigation_limits={'rounds':2,'groups_per_batch':16,'edges_per_anchor':256,'anchors_per_round':16,'witnesses_per_group':8,'witness_chars':600,'relation_context_chars':24000,'follow_groups':8,'scopes_per_group':4,'total_model_calls':4},
  retrieval_stage_plan={'schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','stages_by_arm':{a:plans for a in ('baseline','batch-reference')}},
  index_reuse=read(PARENT/'실험/manifest.json')['design']['index_reuse'],
  product_scope='Original selection and navigation only. Final ASSESS/COMPOSE verified with synthetic contract, no live final answer claims.')
 for a in m['design']['arms']:
  a.update(changes='Byte-identical frozen ADR0621 parent' if a['id']=='baseline' else 'Grouped reference navigation plus unit selector integration, two bounded batch rounds before original review',controls='Fixed 145 public documents, known CM003/CM051, unchanged raw queries, current Qwen3.8 policy, 80000 context chars, same own-unit inventory')
 m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None)
 m['runs'][0].update(selection_rule='Both exact parent questions, fresh paired calls; CM003 baseline then candidate, CM051 candidate then baseline; no outcome-driven reruns',artifact_path='artifacts/run-001/result.json')
 pm=read(PARENT/'실험/manifest.json');m['dataset']=pm['dataset'];m['dataset'].update(name='CM003 CM051 known public source-selection questions',frozen_source=str((design/'inputs.json').relative_to(ROOT)),sha256=sha(design/'inputs.json'))
 m['llm_policy']['llm_calls']=[{'role':'source_unit_selection_and_batch_reference_navigation','class':'product','model':m['llm_policy']['required_model'],'repeats':1,'temperature':'provider_default','max_calls_per_case':{'baseline':2,'batch-reference':4}}]
 m['retrieval_accounting'].update(changed=True,not_applicable_reason=None)
 m['retrieval_accounting']['stage_ledger'].update(mode='measured',summary_run_id='run-001',artifact_path='artifacts/run-001/stage-ledger.json',sha256='PENDING',not_applicable_reason=None)
 m['design']['frozen_inputs']={str(p.relative_to(ROOT)):sha(p) for p in design.glob('*.json')}
 for name in ('00_SYSTEM/EXPERIMENT_MODEL_POLICY.json','08_DEPLOYMENT/CONFIG/legal-source-export.json','01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'):
  m['design']['frozen_inputs'][name]=sha(ROOT/name)
 for key in ('manifest','database'):
  p=ROOT/m['design']['index_reuse'][key];m['design']['frozen_inputs'][str(p.relative_to(ROOT))]=sha(p)
 put(ADR/'실험/manifest.json',m)
 sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
 spec=importlib.util.spec_from_file_location('candidate_tool',ROOT/'06_TOOLS/COMMANDS/adr_candidate.py');tool=importlib.util.module_from_spec(spec);spec.loader.exec_module(tool)
 parent=read(ROOT/'02_BACKEND/lawrag/research/candidates/adr_0621/bounded-unit/candidate.json');files=parent['revisions'][-1]['files']
 targets=[r.get('target_path') or r['frozen_path'].split('/snapshot/',1)[1] for r in files];present=[p for p in targets if (ROOT/p).is_file()]
 path=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0622/batch-reference'
 if not path.exists():tool.snapshot(ADR,'batch-reference',present,experiment_id=m['experiment_id'],arm_id='batch-reference',run_ids=['run-001'])
 snap=path/'snapshot'
 for r,target in zip(files,targets):
  src=ROOT/r['frozen_path'];assert sha(src)==r['snapshot_sha256'];dst=snap/target;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
 for p in targets:
  if p not in present and p not in {row['target_path'] for row in read(path/'candidate.json')['files']}:tool.register_file(path,p,upstream_state='absent')
 tool.refresh(path)
 put(ADR/'artifacts/parent-copy-receipt.json',{'parent_arm':'ADR-0621-experiment-v1/bounded-unit','files':len(files),'all_parent_implementation_bytes_copied':True,'canonical_worktree_preserved':True})
 print(path)
if __name__=='__main__':main()
