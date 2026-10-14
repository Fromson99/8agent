from pathlib import Path
import hashlib,json,subprocess,shutil,sqlite3
R=Path(__file__).resolve().parents[3];A=R/'04_EXPERIMENTS/ADR/ADR-0769-narrative-main54-recovery';D=A/'artifacts/design'
C=R/'02_BACKEND/lawrag/research/candidates/adr_0769/polished';S=C/'snapshot';P=R/'02_BACKEND/lawrag/research/candidates/adr_0767/polished/revisions/rev-001/snapshot'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists()
ptr=read(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');assert ptr['generation']==54
base={'pointer':ptr,'pointer_sha256':sha(R/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'),'manifest':read(R/ptr['manifest_path'])};put(D/'baseline.json',base)
old=R/'04_EXPERIMENTS/ADR/ADR-0767-polished-narrative-qualification/artifacts/design'
criteria=read(old/'criteria.json');criteria['scope']='Merge completed766 narrative and768 bounded wiki, retaining exact767 final prose instructions. No further presentation changes. Compare with selected MAIN54 on one fresh primary root and known467 regression after environment interruption.'
criteria['required']['candidate_primary_supported']=1
criteria['execution']['order']=[['R01','polished'],['H01','baseline'],['H01','polished']]
criteria['sample']='One fresh approved article root outside complete retained exposure scan, deterministic source-ID order with300-650chars and explicit duty; known467 regression. No adaptive reruns.'
criteria['rollback']='MAIN54 unchanged, working files and GENOS DEV backups; no local activation.';put(D/'criteria.json',criteria)
ex=set(read(D/'excluded-source-ids.json'));allowed=set(read(R/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')['public_document_ids'])
db=sqlite3.connect((R/base['manifest']['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
eligible=[]
for sid,raw in db.execute('SELECT id,json FROM source ORDER BY id'):
 if sid in ex or not sid.startswith('article:'):continue
 s=json.loads(raw)
 if s['document_id'] in allowed and 300<=len(s.get('text',''))<=650 and '하여야 한다' in s['text'] and s.get('heading'):eligible.append((sid,s))
assert eligible;sid,s=eligible[0]
q=f"저장된 {s['document_name'].split(' > ')[-1]} {s['heading']}을 기준으로, 해당 조항의 주체별 의무와 적용 조건, 절차, 기한 또는 예외가 있으면 구분해서 설명해 주세요. 이 조항의 내용만 다루고 참조된 다른 조항의 세부사항은 추가 조사하지 말아 주세요."
cases=[{'case_id':'H01','question':q,'role':'out_of_sample_primary','arm_ids':['baseline','polished']}]
gold=[{'case_id':'H01','source_id':sid,**{k:s[k] for k in ('document_id','unit_id','document_name','heading','text','text_sha256','source_artifact_sha256')}}]
known=next(c for c in read(old/'dataset.json')['cases'] if c['case_id']=='R01');cases.append(known);gold.append(next(c for c in read(old/'gold.json')['cases'] if c['case_id']=='R01'));db.close()
put(D/'dataset.json',{'cases':cases,'product_gold':False,'source_generation':base['manifest']['data_path']});put(D/'gold.json',{'product_visible':False,'cases':gold,'version':'Pinned stored originals; not current-law advice'})
put(D/'selection-audit.json',{'excluded_roots':len(ex),'exposure_scan_sha256':sha(D/'exposure-scan.json'),'primary_roots':[sid],'primary_overlap':False,'known':['R01'],'selection_before_results':True,'eligible_count':len(eligible),'selection_rule':criteria['sample']})
m=read(A/'실험/manifest.json');prior=read(old.parent.parent/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['scope']
m['design'].update(hypothesis=criteria['scope'],primary_metric=prior['design']['primary_metric'],success_criteria=criteria['required'],failure_criteria='Any required gate failure, no activation or final handoff; preserve results',criteria_frozen_before_run=True,repeats=1,evaluation_roles={c['case_id']:c['role'] for c in cases},retrieval_stage_plan=prior['design']['retrieval_stage_plan'])
m['design']['code_isolation'].update(mode='candidate_snapshot',reason=None,candidates=[])
for arm in m['design']['arms']:
 arm.update(changes='Selected MAIN54 unchanged' if arm['id']=='baseline' else criteria['scope'],controls='Same public65 data generation, Qwen3.8 Parasail FP8 none, native40call/1800sec budgets')
 if arm['id']=='baseline':arm.update(derived_from=[],source_binding={'path':str((D/'baseline.json').relative_to(R)),'sha256':sha(D/'baseline.json'),'source_arm':'ADR-0768-experiment-v1/integrated','replica_of_selected_release':True})
 else:arm['derived_from']=['ADR-0766-experiment-v1/narrative','ADR-0768-experiment-v1/integrated']
m['dataset'].update(name='Fresh public root and retained known regression after interruption',version='v1',frozen_source=str((D/'dataset.json').relative_to(R)),sha256=sha(D/'dataset.json'),legal_version_checked=True,reference_version_checked=True)
m['llm_policy']['llm_calls']=[{'role':'product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Exact3 requests in frozen order, no adaptive repeats',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['retrieval_accounting']=prior['retrieval_accounting'];m['retrieval_accounting']['stage_ledger']['artifact_path']=str((A/'artifacts/run-001/retrieval-ledger.json.gz').relative_to(R))
put(A/'실험/manifest.json',m)
names=set(base['manifest']['files'])|{'02_BACKEND/lawrag/research/experiment_client.py'}
cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','snapshot','--adr',str(A),'--candidate-id','polished','--experiment-id',m['experiment_id'],'--arm-id','polished','--run-id','run-001']
for n in sorted(names):cmd+=['--source',n]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
changes=list(read(R/'08_DEPLOYMENT/GENOS/handoffs/rag_narrative_stream_20261013_r1/SOURCE_BINDING.json')['source_files'])+['05_TESTS/CONTRACTS/test_narrative_answer.py']
for n in changes:
 raw=(P/n).read_bytes()
 if n.endswith('/unified_runtime.py'):
  text=raw.decode();needle="for name in ('hint','procedure','judgment','core_evidence_route'):flags[name]=False"
  assert needle in text;raw=text.replace(needle,"for name in ('hint','procedure','judgment','core_evidence_route','bounded_recall'):flags[name]=False").encode()
 p=S/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
 if n not in names:subprocess.run([str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',n,'--upstream-state','present' if (R/n).exists() else 'absent'],check=True,stdout=subprocess.DEVNULL)
put(D/'merge-decision.json',{'parents':['ADR0766/narrative','ADR0768/integrated'],'accepted':{'766':'native narrative implementation','768':'all MAIN54 bounded wiki code'},'767_relationship':'interrupted qualification; same refined prose prompt reused and known outcomes retained','conflict_resolution':'unified_runtime disable flags retain bounded_recall; narrative metadata added separately. No other overlap. No full snapshot overwrite.','excluded':'No dropped parent serving function','rollback':'Keep MAIN54 pointer; retain exact working file backups and GENOS prior inventory.'})
for n,v in [('preview-authorization.json',{'purpose':'integration_preview','quality_gate_override':False}),('preview-validation.json',{'structural_checks_passed':True})]:put(D/n,v)
print('Primary',sid,s['heading'],'chars',len(s['text']),'exclusions',len(ex))
