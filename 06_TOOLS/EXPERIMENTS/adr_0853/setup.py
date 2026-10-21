from pathlib import Path
import json,hashlib,subprocess,shutil
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0853-basis-wire-integration';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
parents={}
for ident,folder in [('basis','ADR-0852-basis-workflow-ingress-repair'),('wire','ADR-0850-minimal-output-qualification')]:
 p=R/'04_EXPERIMENTS/ADR'/folder;f=read(p/'artifacts/design/freeze.json');m=read(R/f['candidate']['manifest_path']);assert read(p/'실험/manifest.json')['reservation']['status']=='completed';parents[ident]={'adr':folder,'code_root':f['code_root'],'files':{x['target_path']:sha(R/f['code_root']/x['target_path']) for x in m['files']}}
names=sorted(set().union(*(set(v['files']) for v in parents.values())));C=R/'02_BACKEND/lawrag/research/candidates/adr_0853/integrated';editor='08_DEPLOYMENT/GENOS/workflow/genos_rag_chat.py'
p=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert p['generation']==81;m=read(R/p['manifest_path']);put(D/'baseline.json',{'pointer':p,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'release':m});put(D/'data-binding.json',{'path':m['data_path'],'manifest_sha256':m['data_manifest_sha256']});put(D/'working-before.json',{n:sha(R/n) for n in names})
choices=[]
for n in names:
 h=sha(R/n);known={key:v['files'].get(n) for key,v in parents.items()}
 assert h in known.values(),('Unreviewed third-party bytes',n)
 choices.append({'path':n,'parents':known,'selected_parent':'basis' if n==editor else next(k for k,v in known.items() if v==h),'selected_sha256':parents['basis']['files'][n] if n==editor else h})
put(D/'merge-selection.json',{'parents':parents,'choices':choices,'conflicts':'Both parents already share basis code;850rebased workflow_bridge preserves basis functions while adding codec. Select850current bytes and852editor correction; all unchanged basis modules match both. No discarded feature.','rollback':'MAIN81; retain both parent candidate and working backups; data/authority history unchanged.'})
criteria={'scope':'Merge completed basis authority/editor and minimal model output adapter using exact parent bytes', 'success':['Every chosen file equals an identified completed parent','Basis/editor/authorization/source/API contracts and minimal-wire contracts all pass together','Actual selected-data service checks pass','Same integration checked in working code then hash-fixed MAIN selected'], 'failure':['Lost basis factory or codec wiring','Original/ACL/review/budget/state regression','Unexpected third-party bytes','Wrong model/source grant or editor routing'], 'novelty':'Technical integration of two completed branches. All test cases are identified regressions, not new legal holdout. Exact-input consumer contracts are verified, no legal accuracy claim.', 'model_calls':0,'quality_certified':False};put(D/'criteria.json',criteria)
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','integrated','--experiment-id','ADR-0853-experiment-v1','--arm-id','integrated','--run-id','run-001']
for n in names:cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
shutil.copy2(R/parents['basis']['code_root']/editor,C/'snapshot'/editor)
for row in choices:assert sha(C/'snapshot'/row['path'])==row['selected_sha256']
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['scope'];m['design'].update(hypothesis=criteria['scope'],primary_metric='Exact parent merge and full consumer contract integrity',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True)
m['integration']={'parents':[{'experiment_id':'ADR-0852-experiment-v1','arm_id':'qualified'},{'experiment_id':'ADR-0850-experiment-v1','arm_id':'qualified'}],'adopted':'All basis and minimal output behavior; exact per-file choices in merge-selection.json','excluded':'None; only852redundant local import repair replaces850editor bytes','conflict_resolution':'850already rebased over shared basis additions; choose matched completed parent bytes, no wholesale older snapshot overwrite','rollback':'MAIN81; source authority history retained'}
for arm in m['design']['arms']:arm.update(changes='Two completed parents' if arm['role']=='baseline' else criteria['scope'],controls=['same immutable data/model policy','actual sources and trusted identities','zero real model calls'])
m['runs'][0].update(arm_ids=['integrated'],selection_rule=criteria['novelty'],artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
reason='Finite software integration with synthetic proposals; no model accuracy/retrieval effectiveness comparison';m['retrieval_accounting']['not_applicable_reason']=reason;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=reason;put(A/'실험/manifest.json',m)
for name in ('run_tests.py','consumer.py','preview.py','seal.py'):
 t=(T.parent/'adr_0852'/name).read_text().replace('adr_0852/qualified','adr_0853/integrated').replace('adr_0852','adr_0853').replace('ADR-0852-basis-workflow-ingress-repair','ADR-0853-basis-wire-integration').replace("'candidate_id':'qualified'","'candidate_id':'integrated'").replace("'arm_id':'qualified'","'arm_id':'integrated'").replace("arm_ids=['qualified']","arm_ids=['integrated']").replace('basis-lifecycle-qualified-preview','basis-lifecycle-integrated-preview')
 if name=='seal.py':
  t=t.replace("subprocess.run([str(R/'.venv/bin/python'),str(Path(__file__).with_name('pins.py'))],check=True)\n",'')
  t=t.replace('Remove one function-local asyncio import from pinned editor; verify both existing AD and explicit workflow control branches.','Exact parent integration of852basis and850minimal output; no new product source edits.').replace('18 prospective pinned-editor cases plus138 prior contracts. Legacy editor test uses working path so it is replaced for candidate by explicit pinned version and included again after working integration; no legal holdout','Merged finite integration contracts for basis lifecycle and minimal output. Root editor test replaced by candidate-pinned equivalent until integration. No legal holdout or model accuracy claim.')
 (T/name).write_text(t)
shutil.copy2(T.parent/'adr_0850/test_boundaries.py',T/'test_wire_boundaries.py')
print(C,len(names))
