from pathlib import Path
import json,shutil
R=Path.cwd();D=R/'04_EXPERIMENTS/ADR/ADR-0456-persistent-navigation-work-state';A=D/'artifacts';P=R/'04_EXPERIMENTS/ADR/ADR-0455-routing-validation-repair';T=R/'06_TOOLS/EXPERIMENTS/adr_0456'
def read(p):return json.loads(p.read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
if (A/'design-before-snapshot.json').exists():raise ValueError('already designed')
for f in ['dataset','grading']:shutil.copytree(P/'artifacts'/f,A/f)
for f in ['authorization.json','source-inventory.json']:shutil.copyfile(P/'artifacts'/f,A/f)
m=read(D/'실험/manifest.json');old=read(P/'artifacts/pre-call-manifest.json')
for k in ['design','dataset','llm_policy','retrieval_accounting']:m[k]=old[k]
h='Persistent bounded cross-tool work state and requirement/reference review tasks preserve broad retrieval through grounded multi-source synthesis, improving both content cases without metadata regressions under the same total14call/180s budget.'
m['lineage']['hypothesis_delta']=h;m['design'].update(hypothesis=h,primary_metric='Exact task success18/18; content required sources4/4 each plus blinded semantic correctness, metadata16/16',success_criteria='stateful18/18; no baseline-only regressions; no scope escapes/invalid quotes/provider errors; each turn<=14calls and180s controller budget',failure_criteria='Any declared criterion missed; no reinterpretation of partial answers as success',implementation_scope='common work-state envelope, persistent candidate/reference board, atomic requirements, batched read/review, scoped alias search, bounded recovery, source-grounded synthesis and product verification',protocol_notes='known18synthetic questions once per arm; no adaptive code edits/reruns; separate2offline judges',controls='Same frozen corpus including sparse synthetic occurrence table, queries, metadata routing and mapping approvals, Gemini model/settings and14call budget; parent content loop is baseline')
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-0455-experiment-v1/repaired'],'changes':'Frozen ADR0455 unchanged','controls':'Same corpus/model/totalcall budget'},{'id':'stateful','role':'candidate','derived_from':['ADR-0455-experiment-v1/repaired'],'changes':m['design']['implementation_scope'],'controls':'Same source/authorization/coordinate/mapping contracts'}];m['design']['code_isolation']['candidates']=[]
st=m['design']['retrieval_stage_plan']['stages_by_arm'];st['stateful']=st.pop('repaired')
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['baseline','stateful'],'selection_rule':'all18once, alternate arms, fixed mapping approval/followup','status':'planned','artifact_path':str((A/'results.json').relative_to(R)),'sha256':'PENDING'}]
m['llm_policy']['llm_calls']=[{'role':r,'class':'product','model':'gemini-3.1-flash-lite','repetitions':1,'shared_max_calls_per_turn':14} for r in ['structured_navigation','navigation_requirements','navigation_review','navigation_synthesis','navigation_verify']]+[{'role':'content_judge','class':'offline_evaluator','model':'gemini-3.1-flash-lite','repetitions':1,'case_count':2}]
m['dataset'].update(version='work-state456-v1',frozen_source=str((A/'dataset/product-cases.json').relative_to(R)));m['retrieval_accounting']['stage_ledger']['artifact_path']=str((A/'retrieval-ledger.json').relative_to(R))
write(D/'실험/manifest.json',m);write(A/'design-before-snapshot.json',m)
for f in ['fixtures.py','run_probe.py','score.py','finalize.py','test_routing.py']:
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0455'/f).read_text().replace('adr_0455','adr_0456').replace('ADR-0455','ADR-0456').replace('ADR455','ADR456').replace('routing-validation-repair','persistent-navigation-work-state').replace("'repaired'","'stateful'")
 if f=='run_probe.py':s=s.replace('451,454]', '451,454,455]')
 if f=='score.py':
  a=s.index(" ok=summary[");b=s.index('\n drift=',a)
  s=s[:a]+" ok=summary['stateful']['pass']==18 and not comparison['baseline_only_regressions'] and all(not x['invalid_quotes'] and not x['scope_escapes'] and not x['failure'] for x in metrics['stateful'].values())"+s[b:]
 (T/f).write_text(s)
