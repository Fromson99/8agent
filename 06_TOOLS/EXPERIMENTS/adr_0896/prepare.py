from pathlib import Path
import json,hashlib,shutil,datetime,sqlite3
R=Path(__file__).resolve().parents[3];T=Path(__file__).parent;A=R/'04_EXPERIMENTS/ADR/ADR-0896-cm-read-continuity-qualification';P=R/'04_EXPERIMENTS/ADR/ADR-0895-committed-answer-consistency';D=A/'artifacts/design';D.mkdir(exist_ok=True)
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
assert not (D/'criteria.json').exists();f=read(P/'artifacts/design/freeze.json');assert read(P/'실험/manifest.json')['reservation']['status']=='completed'
for n in ('baseline.json','working-before.json','data-binding.json','verification-binding.json','release-rebase.json','integration.json','execution-plan.json','cases.json','offline-reference.json'):shutil.copy2(P/'artifacts/design'/n,D/n)
criteria={'hypothesis':'The immutable0895 candidate preserves exact delivered originals, bounded reference recovery and committed/public answer consistency under independent finite boundaries while retaining MAIN86 contracts.',
 'required':['All20 independently frozen Unicode/identity/version/deadline boundary cases pass','44 retained source/API recovery regressions pass and605 same-code regressions remain valid','Candidate, integrated working and selected active actual service each pass10 checks','No source/ACL/hash/state/resource regression; all8 actual CM response audits retain exact originals','Only45 reviewed deltas integrated and711 candidate hashes preserved; selected370 serving hashes match'],
 'promotion_rule':'Accept finite technical qualification only. Detailed legal judgment misses includingCM003 do not automatically block under explicit user policy. This is not unseen legal accuracy validation.',
 'limits':{'workers':1,'rss_gib':8,'address_space_gib':9,'resident_data':'off','allocator':'MALLOC_ARENA_MAX=1 MALLOC_TRIM_THRESHOLD_=65536 MALLOC_MMAP_THRESHOLD_=131072'},
 'no_product_change':True,'legal_holdout':False,'known_case_evidence':'Completed0895: sameCM5 plusCM011/022/038,152actualcalls; externalQwen3.8ParasailFP8reasoningnone/no fallback. No new model calls in qualification.'}
put(D/'criteria.json',criteria)
tests=['06_TOOLS/EXPERIMENTS/adr_0896/test_boundaries.py','06_TOOLS/EXPERIMENTS/adr_0876/test_context.py','06_TOOLS/EXPERIMENTS/adr_0877/test_boundaries.py','05_TESTS/CONTRACTS/test_output_contract_recovery.py']
put(D/'qualification-tests.json',{'tests':tests,'hashes':{n:sha(R/n) for n in tests},'new_finite_cases':20,'retained_additional_cases':44,'prior605_log':str((P/'artifacts/candidate-api.log').relative_to(R)),'prior_deselections':140,'deselection_disposition':'0893 reference-preflight-disposition and0895 frozen selection; legacy41failures reproduced identically on0892; no claim of all repository tests passing.'})
# Registry gold retains historical IDs; record selected source identity separately, never rewrite gold.
db=sqlite3.connect('file:'+str(R/read(D/'baseline.json')['release']['data_path']/'store.sqlite')+'?mode=ro');notes=[]
for cid,old,did in [('cm-022','279d511501174f3f','0798989e52ca0254'),('cm-038','8e6b9251fdfba8f4','92089b5873b2ccc0')]:
 row=db.execute('select source_artifact_sha256,json from document where document_id=?',(did,)).fetchone();meta=json.loads(row[1])['document_metadata']
 notes.append({'case':cid,'frozen_gold_document_id':old,'gold_id_present_in_selected_generation':bool(db.execute('select 1 from document where document_id=?',(old,)).fetchone()),'selected_document_id':did,'source_artifact_sha256':row[0],'title':meta['document_title'],'source_metadata':meta['source_metadata'],'interpretation':'Frozen retrieval ledger keeps historical coordinate mismatch. Manual core review uses actual selected original and version; this is not a rewritten gold hit.'})
db.close();put(D/'gold-coordinate-disposition.json',notes)
m=read(A/'실험/manifest.json');m.update(in_sample=False,decision_eligible=True);m['lineage']['hypothesis_delta']=criteria['hypothesis'];m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Independent finite technical census, separate knownCM8semantic review',success_criteria=criteria['required'],failure_criteria=['Source/ACL/hash/state/consumer/resource failure','Product changes after frozen actualCM8verification'],criteria_frozen_before_run=True)
m['design']['arms']=[{'id':'qualified','role':'candidate','derived_from':['ADR-0895-experiment-v1/consistent'],'changes':'No product changes; independent finite technical qualification','controls':'Exact immutable0895snapshot andMAIN86 data/profile; no model or legal gold in finite tests'}]
m['design']['code_isolation'].update(mode='not_applicable',reason='No implementation change. Reuse immutable completed0895snapshot with all711files hash bound; avoid duplicate storage.',candidates=[])
m['design']['release_rebase']=read(D/'integration.json')['rebase_receipt']
m['runs'][0].update(arm_ids=['qualified'],selection_rule='20new finite technical boundaries +44retained checks; knownCM8results separate, not legal holdout.',artifact_path=str((A/'artifacts/run-001/result.json').relative_to(R)))
m['dataset'].update(name='finite-read-continuity-boundaries',version='20261019-r1',frozen_source=str((D/'qualification-tests.json').relative_to(R)),sha256=sha(D/'qualification-tests.json'))
m['llm_policy']['llm_calls']=[]
why='Finite software contracts without retrieval quality/model comparison. Completed0895knownCM8ledger remains unchanged, including historical gold coordinate mismatches.';m['retrieval_accounting']['not_applicable_reason']=why;m['retrieval_accounting']['stage_ledger']['not_applicable_reason']=why
put(A/'실험/manifest.json',m)
files={str(p.relative_to(R)):sha(p) for p in [*D.glob('*.json'),*T.glob('*.py'),R/'06_TOOLS/EXPERIMENTS/adr_0895/run_tests.py']};files.update({n:h for n,h in f['files'].items() if n.startswith(f['code_root']+'/')})
put(D/'freeze.json',{**f,'files':files,'frozen_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'legal_holdout':False})
print('Frozen20new +44retained; reuse711files; no new model calls')
