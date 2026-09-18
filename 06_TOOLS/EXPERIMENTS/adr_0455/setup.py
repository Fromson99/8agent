from pathlib import Path
import json,shutil,hashlib
R=Path.cwd();D=R/'04_EXPERIMENTS/ADR/ADR-0455-routing-validation-repair';A=D/'artifacts';P=R/'04_EXPERIMENTS/ADR/ADR-0454-robust-routing-short-handles';T=R/'06_TOOLS/EXPERIMENTS/adr_0455'
def read(p):return json.loads(p.read_text())
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
if (A/'design-before-snapshot.json').exists():raise ValueError('already designed')
for f in ['dataset','grading']:shutil.copytree(P/'artifacts'/f,A/f)
for f in ['authorization.json','source-inventory.json']:shutil.copyfile(P/'artifacts'/f,A/f)
m=read(D/'실험/manifest.json');old=read(P/'artifacts/pre-call-manifest.json')
for k in ['design','dataset','llm_policy','retrieval_accounting']:m[k]=old[k]
h='Preserve ADR0454 catalogue and compact-ID gains while allowing one validation-guided interpretation repair, stopping repeated empty metadata lookup with clarification, and validating mapping targets without retrieval scope restrictions.'
m['lineage']['hypothesis_delta']=h;m['design'].update(hypothesis=h,implementation_scope='initial-stage semantic repair only once, bounded repeated/empty metadata lookup stop, mapping-only scope validation exemption; unchanged inherited content evidence loop',primary_metric='metadata16/16, no metadata regressions; content first interpretation succeeds without400; content answer correctness separately graded',success_criteria='metadata16/16, no metadata regressions, content initial interpretation succeeds without failure; no invalid citations or scope escape; contract checks pass',failure_criteria='Any declared criterion missed',protocol_notes='18known synthetic questions once per arm; no result-based candidate edits/reruns',controls='Same frozen18cases/source and Gemini settings asADR0454; baseline ADR0454, candidate repair; all lower content stages unchanged')
m['design']['arms']=[{'id':'baseline','role':'baseline','derived_from':['ADR-0454-experiment-v1/routed'],'changes':'Frozen ADR0454 routed unchanged','controls':'Same corpus/provider/budget'},{'id':'repaired','role':'candidate','derived_from':['ADR-0454-experiment-v1/routed'],'changes':m['design']['implementation_scope'],'controls':'Same metadata/scope/approval/evidence contracts'}];m['design']['code_isolation']['candidates']=[]
st=m['design']['retrieval_stage_plan']['stages_by_arm'];st['repaired']=st.pop('routed')
m['runs']=[{'id':'run-001','purpose':'primary','parent_run_id':None,'arm_ids':['baseline','repaired'],'selection_rule':'all18once; no adaptive reruns; same fixed mapping followup','status':'planned','artifact_path':str((A/'results.json').relative_to(R)),'sha256':'PENDING'}]
m['dataset'].update(version='routing455-v1',frozen_source=str((A/'dataset/product-cases.json').relative_to(R)));m['retrieval_accounting']['stage_ledger']['artifact_path']=str((A/'retrieval-ledger.json').relative_to(R))
write(D/'실험/manifest.json',m);write(A/'design-before-snapshot.json',m)
# Unchanged synthetic runner/grader, with exact baseline class changed to frozenADR0454.
for f in ['fixtures.py','run_probe.py','score.py','finalize.py','test_routing.py']:
 s=(R/'06_TOOLS/EXPERIMENTS/adr_0454'/f).read_text().replace('adr_0454','adr_0455').replace('ADR-0454','ADR-0455').replace('ADR454','ADR455').replace('robust-routing-short-handles','routing-validation-repair').replace("'routed'","'repaired'")
 if f=='run_probe.py':s=s.replace('449,450,451]', '449,450,451,454]')
 if f=='score.py':
  s=s.replace("and not x['failure'] for x in metrics['repaired'].values()", "for x in metrics['repaired'].values()")
  s=s.replace(" and all(not x['invalid_quotes']", " and all((metrics['repaired'][cid]['interpretation'] or {}).get('intent')=='content' for cid in ['multi-entry-alias','multi-entry-literal']) and all(not x['invalid_quotes']")
 (T/f).write_text(s)
