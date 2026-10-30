from pathlib import Path
import json,hashlib,sys,shutil,subprocess
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-1142-main108-recovery-integration';D=A/'artifacts/design';D.mkdir(parents=True,exist_ok=True)
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
f=read(R/'04_EXPERIMENTS/ADR/ADR-1141-exact-gap-progress/artifacts/design/freeze.json');ff=read(R/'04_EXPERIMENTS/ADR/ADR-1139-ontology-framework-local-http/artifacts/design/freeze.json');old=read(R/'08_DEPLOYMENT/RELEASES/genos-mode-20261027-r1/release.json');active=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');base=read(R/active['manifest_path']);assert active['generation']==108
criteria={'hypothesis':'Combine source preparation reuse, stable IDs/new reviews, body scope resolution and independent final-gap recovery with MAIN108 ontology framework without data publication. Core validity is checked independently even when final review alone has schema errors.','primary':['New integrated native source recovery: nonexistent claims, empty claim_refs, omitted review; no rejected claim/review adoption, additional original and valid final answer, repeated-request reuse','New interaction: approved synthetic ontology ON/OFF/empty/fallback/reselection plus stable IDs and new-review contract, same runtime code','All observed422 recovery/performance/reference contracts and ontology contracts pass; selected framework defaults OFF and no data','Affected old regression outcomes compared by test ID; expected obsolete fixture failures separated, no unexplained protected invariant failure','Official serving inventory equals exactly evaluated candidate; preserve source/model/budgets and latest MAIN108; service live follow-up required'], 'failure':'Any original/ACL/hash/state loss, weakened core validation, duplicate recovery or unexplained contract failure','quality_certified':False,'performance_claim':False,'rollback':'MAIN108 ontology-framework-20261027-r1','known_live_failure':'1141 physical4 model calls3responses1unknown; original reading succeeded, final answer unconfirmed. Not reused as quality success.'};put(D/'criteria.json',criteria)
paths=set(ff['files'])|set(f['files'])|set(base['files']);m=read(A/'실험/manifest.json');m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Protected end-to-end technical contracts',success_criteria=criteria['primary'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True);m['lineage']['hypothesis_delta']=criteria['hypothesis']
for x in m['design']['arms']:x.update(changes='Historical MAIN108 plus completed1141 contracts' if x['id']=='baseline' else 'Exact selective merge and independent final-review shape validation',controls='Same data/model/budgets; ontology default OFF/no data')
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None);m['runs'][0].update(arm_ids=['integrated'],selection_rule='All predeclared new interactions plus observed regressions',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['integration'].update(result_arm='integrated',rationale=criteria['hypothesis'],common_invariants='Source bytes, ACL/version/hash, stable state, model policy and request budgets; no ontology data',no_conflict_reason=None,rollback_ref='ADR-1139-experiment-v1/integrated')
for x in m['integration']['parent_contributions']:
 x.update(adopted='All technical source/recovery changes; interrupted live failure preserved' if '1141' in x['parent_ref'] else 'MAIN108 framework, operator switch, service and default OFF',excluded='No quality/performance success claim; no scenario data')
m['integration']['conflicts']=[{'component':'law_candidates.py defaults and profile flags','resolution':'Union independent stable-reference and ontology flags; preserve MAIN108 framework default OFF'},{'component':'completion_execution.py and law_navigation.py','resolution':'Three-way merge against MAIN107, retain both independent final recovery and ontology execution'},{'component':'engine pins','resolution':'Union dependencies and recompute exact resulting hashes'}]
m['dataset'].update(name='Synthetic new combined runtime interactions and observed source invariants',version='v1',frozen_source=str((D/'criteria.json').relative_to(R)),sha256=sha(D/'criteria.json'))
m['retrieval_accounting']['not_applicable_reason']='Technical synthetic contract qualification, no retrieval quality comparison';m['retrieval_accounting']['stage_ledger']['not_applicable_reason']='No legal evaluation dataset';put(A/'실험/manifest.json',m)
put(D/'baseline.json',{'pointer':active,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':base,'working_files':{n:sha(R/n) if (R/n).is_file() else None for n in paths}})
sys.dont_write_bytecode=True;sys.path.insert(0,str(R/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in paths if (R/n).is_file()];C=ac.snapshot(A,'integrated-r1',present,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);S=C/'snapshot';composition={}
for n in sorted(paths):
 source=R/ff['code_root']/n if n in ff['files'] else R/f['code_root']/n
 if n in base['files']:source=R/base['code_root']/n
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,p);composition[n]={'base':sha(source)}
 if n in f['files'] and f['files'][n]!=old['files'].get(n) and '/ENGINES/' not in n and n!='00_SYSTEM/PIPELINE.json':
  ours=R/f['code_root']/n;theirs=R/base['code_root']/n;ancestor=R/old['code_root']/n
  if n in base['files'] and base['files'][n]!=old['files'].get(n):
   if n.endswith('profile-unified-v6.json'):
    v=read(theirs);o=read(ours);b=read(ancestor)
    for k,x in o['candidate_navigation'].items():
     if x!=b['candidate_navigation'].get(k):v['candidate_navigation'][k]=x
    put(p,v)
   else:
    merge=subprocess.run(['git','merge-file','-p',str(ours),str(ancestor),str(theirs)],capture_output=True,text=True)
    t=merge.stdout
    if merge.returncode:
     assert n.endswith('law_candidates.py') and t.count('<<<<<<<')==1
     start=t.index('<<<<<<<');mid=t.index('=======',start);end=t.index('\n',t.index('>>>>>>>',mid))
     left=t[t.index('\n',start)+1:mid].rstrip();right=t[mid+8:t.index('>>>>>>>',mid)].strip();suffix=right[right.index(", 'ontology_enabled'"):].rstrip().rstrip('}')
     t=t[:start]+left.rstrip('}')+suffix+'}\n'+t[end+1:]
    p.write_text(t)
  else:shutil.copyfile(ours,p)
  composition[n]['recovery_parent']=f['files'][n]
 if n not in present:ac.register_file(C,n,upstream_state='absent')
# Final-review shape failures must not hide an independently valid core source request.
p=S/'02_BACKEND/semantic_runtime/legal_agent/read_judgment_final.py';t=p.read_text().replace("or error.category != 'FINAL_READ_REVIEW_INVALID'","or error.category not in ('FINAL_READ_REVIEW_INVALID','OUTPUT_SHAPE_INVALID')")
t=t.replace('    core_value, core_schema = core(value, schema)\n    try:\n        accepted, proposal',"    core_value, core_schema = core({FIELD:None, **value}, schema)\n    try:\n        if 'disposition' not in core_value:\n            from .completion_execution import assessment_projection\n            _, expand = assessment_projection(core_schema, allowed_targets=allowed_targets)\n            core_value = expand(core_value)\n        accepted, proposal")
p.write_text(t)
# Union pinned dependencies; hashes are recomputed at freeze.
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 n=str(p.relative_to(S));e=read(p)
 if n in f['files']:e.get('files',{}).update(read(R/f['code_root']/n).get('files',{}))
 put(p,e)
put(D/'source-composition.json',composition)
for p in (R/'06_TOOLS/EXPERIMENTS/adr_1141').glob('*.py'):
 if p.name in ('prepare.py','freeze.py','setup.py','live.py'):continue
 (T/p.name).write_text(p.read_text().replace('ADR-1141-exact-gap-progress',A.name).replace('adr_1141','adr_1142'))
for n in ('test_projection.py','test_direct.py','test_semantics.py','test_scenarios.py','test_scenario_native.py','test_sufficiency.py','test_toggle.py','regression.py'):
 (T/n).write_text((R/'06_TOOLS/EXPERIMENTS/adr_1139'/n).read_text().replace('ADR-1139-ontology-framework-local-http',A.name).replace('adr_1139','adr_1142'))
shutil.copyfile(R/'04_EXPERIMENTS/ADR/ADR-1141-exact-gap-progress/artifacts/design/test-support.json',D/'test-support.json')
# New schema-failure variants use the same full native source/answer assertions.
p=T/'test_final_recovery_native.py';t=p.read_text().replace("['final_independent']","['final_independent','final_empty_refs','final_missing_review']")
t=t.replace("                    value['read_judgment_review']=review", "                    value['read_judgment_review']=review\n                    if not value['claims'] and mode=='final_empty_refs':\n                        for row in review['judgments']:row['claim_refs']=[]\n                    if not value['claims'] and mode=='final_missing_review':value.pop('read_judgment_review')")
p.write_text(t)
# Exercise framework with the new reference/review responder, not its old fixture.
p=T/'test_scenario_native.py';t=p.read_text().replace('import test_read_judgment_api as parent','import test_native_integrated as parent').replace('return wire(value)','from api_fixture_integrated import to_wire\n                return wire(to_wire(value))',1)
# Direct scenario choices use presented issue vocabulary as well.
t=t.replace("            return wire(value)\n    t=Transport()","            from api_fixture_integrated import to_wire\n            return wire(to_wire(value))\n    t=Transport()")
p.write_text(t)
print('prepared',len(paths),'files')
