from common import *
import sys,shutil,ast
T=Path(__file__).parent;P=ROOT/'04_EXPERIMENTS/ADR/ADR-1146-source-recovery-main-qualification';Q=ROOT/'04_EXPERIMENTS/ADR/ADR-1150-scenario-complement-candidate-check'
DES.mkdir(parents=True,exist_ok=True)
active=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert active['generation']==109
release=read(ROOT/active['manifest_path']);f=read(P/'artifacts/design/freeze.json');base=ROOT/f['code_root']
assert all(release['files'][n]==f['files'][n] for n in release['files'])
put(DES/'baseline.json',{'pointer':active,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':release,'manifest_sha256':sha(ROOT/active['manifest_path']),'code_root':str(base.relative_to(ROOT)),'working_files':{n:sha(ROOT/n) if (ROOT/n).is_file() else None for n in release['files']}})
module='02_BACKEND/semantic_runtime/legal_agent/ontology_scenarios.py';qf=read(Q/'artifacts/freeze.json');qcode=ROOT/qf['arms']['concise']['code_root']
def parts(p):
 tree=ast.parse(p.read_text());node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(getattr(t,'id',None)=='PROMPT' for t in n.targets));text=ast.literal_eval(node.value);tree.body.remove(node);return text,ast.dump(tree),node
old,rest,_=parts(base/module);new,qrest,_=parts(qcode/module);assert rest==qrest and len(old)==374 and len(new)==365
criteria={'hypothesis':'The exact1150short instruction can be integrated into selected MAIN109 without changing ontology switches, source data, recovery contracts or any other product behavior.',
 'primary':['Exact latest MAIN109440servingfile inventory; only PROMPT literal and31dependent pins differ; AST outside PROMPT identical.','Existing216frameworkcontracts run on integrated code, including current stable-reference/native fixtures, ON/OFF,empty data,reselection,SEARCHreentry and publication.','New finite technical matrix:all8subsets of3synthetic routes preserve exact model choice, actual delivered prompt and same-request reuse;no automatic route injection. Prompt-only AST and profile-preservation checks.','Official release preview exact440files, no data/recipe/package/research files. Same data generation,profile,model,nooutputcap,budgets.','User-authorized formal promotion, same working source hunk and actual selected-service OFF/ON-empty verification; active1151batch must not be silently disrupted.'],
 'success':'All fresh technical and inherited-contract executions pass, code/inventory/permission/state preserved. Separate technical qualification, not new legal-quality holdout or a reinterpretation of1150in-sample observations.',
 'failure':'Any new technical failure,extra product drift,ontology activation/data shipping,source/ACL/hash/state mismatch,or unresolved active-run conflict blocks apply.',
 'boundaries':{'model_calls':0,'legal_quality_certified':False,'in_sample':False,'basis':'Prospectively frozen complete finite technical matrix and latest-code integration contracts, no legal answer scoring','new_tests_planned':10,'existing_tests_to_rerun':216,'primary_arm':'integrated'},
 'resources':{'synthetic_checks_expected_peak_mib':700,'actual_corpus_loads':0,'heavy_service_processes':1,'minimum_available_gib':3,'min_disk_gib':20},
 'concurrency':'ADR1151 active CM51 requires MAIN109 pointer. Prepare and lightweight tests may proceed; no activation or other-worker termination without resolving timing with user. No edits to1151frozen code/design.',
 'rollback':'Official rollback to current109source-recovery release if postactivation binding/source/data/switch verification fails.'}
put(DES/'criteria.json',criteria);put(DES/'prompt.json',{'old':old,'new':new,'old_chars':len(old),'new_chars':len(new),'source':str((qcode/module).relative_to(ROOT)),'source_sha256':sha(qcode/module)})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis'];m.update(in_sample=False,decision_eligible=True)
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric=criteria['primary'],success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['design']['arms'][0].update(changes='Selected MAIN109 and completed1150prompt source, historical references only',controls='Same latest release and data; no semantic regrade')
m['design']['arms'][1].update(changes='PROMPT literal only plus31pins',controls='Same440runtimefiles/profile/data/switch/recovery/budgets outside that literal')
m['integration'].update(result_arm='integrated',rationale='User requests latest MAIN integration of validated selection instruction, switch retention and data exclusion.',common_invariants=['MAIN109recovery/stable references preserved','defaultOFF and ON/OFFenvironment contract','data/model/profile/budgets unchanged','no prototype dataset shipped'],parent_contributions=[{'parent_ref':'ADR-1146-experiment-v1/integrated','adopted':'Entire selected MAIN109440-file release and profile/data binding','excluded':'No exclusions; retain recovery and all prior framework capabilities'},{'parent_ref':'ADR-1150-experiment-v1/concise','adopted':'Exact365-character PROMPT literal only','excluded':'Older MAIN108base, researchdata, all old enginepins, experimental runners and in-sample quality gate'}],conflicts=[],no_conflict_reason='ontology_scenarios AST outside PROMPT matches both parents. All other files come from exact selected109; pins are recalculated from combined bytes.',rollback_ref='ADR-1146-experiment-v1/integrated')
m['runs'][0].update(arm_ids=['integrated'],selection_rule='216currentframeworkcontracts plus10new finite technical integration conditions; no real model',artifact_path=str((ART/'run-001/result.json').relative_to(ROOT)))
m['dataset'].update(name='Prospective finite synthetic technical integration cases, no user ontology data',version='1152-framework-technical-v1',frozen_source=str((DES/'criteria.json').relative_to(ROOT)),sha256=sha(DES/'criteria.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[]
reason='Technical synthetic integration audit only; no real retrieval selection/quality measurement. Prior1150model observations preserved separately.'
m['retrieval_accounting']={'changed':False,**{k:None for k in ('corpus_total','before_filter','after_filter','presented_total','presented_mean','presented_p50','presented_p95','golden_recall','selectivity')},'not_applicable_reason':reason,'stage_ledger':{'mode':'not_applicable','schema_version':'retrieval-stage-ledger-v1','accounting_unit':'case_id + canonical article-root coordinate','summary_run_id':None,'artifact_path':None,'sha256':None,'not_applicable_reason':reason}}
put(ADR/'실험/manifest.json',m)
sys.dont_write_bytecode=True;sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
present=[n for n in f['files'] if (ROOT/n).is_file()];C=ac.snapshot(ADR,'integrated-r1',present,experiment_id=m['experiment_id'],arm_id='integrated',run_ids=['run-001']);S=C/'snapshot'
for n,h in f['files'].items():
 assert sha(base/n)==h;npath=S/n;npath.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(base/n,npath)
 if n not in present:ac.register_file(C,n,upstream_state='absent')
_,_,node=parts(S/module);lines=(S/module).read_text().splitlines(keepends=True);lines[node.lineno-1:node.end_lineno]=['PROMPT='+repr(new)+'\n'];(S/module).write_text(''.join(lines));assert sha(S/module)==sha(qcode/module)
pipe=read(S/'00_SYSTEM/PIPELINE.json')
for ref in pipe['engines'].values():
 p=S/ref['manifest'];e=read(p)
 if module not in e['files']:continue
 e['files'][module]=sha(S/module);put(p,e);ref['sha256']=sha(p)
put(S/'00_SYSTEM/PIPELINE.json',pipe)
for p in (ROOT/'06_TOOLS/EXPERIMENTS/adr_1146').glob('test_*.py'):shutil.copyfile(p,T/p.name)
shutil.copyfile(ROOT/'06_TOOLS/EXPERIMENTS/adr_1146/api_fixture_integrated.py',T/'api_fixture_integrated.py')
shutil.copyfile(P/'artifacts/design/test-support.json',DES/'test-support.json')
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_1146/check_integrated_bootstrap.py').read_text().replace('ADR-1146-source-recovery-main-qualification',ADR.name)
s=s.replace("rc=pytest.main(","\nif mode=='ontology':paths.append(str(Path(__file__).parent/'test_prompt_integration.py'))\nrc=pytest.main(")
(T/'check.py').write_text(s)
print('Prepared latest MAIN109 plus exact365char prompt;665files, only32expectedchanges')
