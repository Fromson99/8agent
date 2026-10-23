"""Reserve-first preparation; no model calls or MAIN edits."""
from pathlib import Path
import json,hashlib,sys,shutil,sqlite3
ROOT=Path(__file__).resolve().parents[3]; D=Path(__file__).parent
old=ROOT/'06_TOOLS/EXPERIMENTS/adr_0993'
(D/'common.py').write_text((old/'common.py').read_text().replace('ADR-0993-knowledge-original-delivery','ADR-0996-knowledge-use-first-prompt'))
sys.path.insert(0,str(D));from common import *
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
parent=ROOT/'04_EXPERIMENTS/ADR/ADR-0993-knowledge-original-delivery/artifacts'
for name in ['curated-source-values.json','method-templates.json','selected.json']:
 put(DES/name,read(parent/'design'/name))
put(ART/'agent_layer/corrected-experiences.json',read(parent/'agent_layer/corrected-experiences.json'))
cases=read(parent/'design/cases.json')
for c in cases:c['reuse_mode']='CLOSED_EVIDENCE' if c['cohort']=='seed' else 'EXTEND'
cases.append({'id':'cm-new-lockup','cohort':'new_composed_public_question','reuse_mode':'EXTEND',
 'question':'코스닥 국내 일반기업의 상장주선인 의무인수 주식 보유기간이 3개월에서 6개월로 연장되는 조건을 설명하고, 그 조건에 해당하는 혁신기술기업 IPO에서 일반청약자의 환매청구권 행사가능기간과 인수회사의 매수가격 기준도 설명해줘.'})
put(DES/'cases.json',cases)
offline=read(parent/'offline/criteria.json')
offline['cm-new-lockup']={'required':offline['cm-008']['required']+['인수규정10조의3제5항에 따른 환매청구권 부여와 상장일부터6개월','공모가격90% 이상','직전거래일 지수가 상장직전 대비10% 초과 하락 시 조정가격 및 산식'],
 'source_ids':['listing','listing_detail','put_option'], 'forbidden':['의무보유기간과 일반청약자의 환매청구권을 동일한 권리로 취급','저장된 의무보유 규정만으로 환매청구권 기간·가격을 추정']}
put(ART/'offline/criteria.json',offline)
selected=read(DES/'selected.json');assert sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==selected['pointer_sha256']
db=sqlite3.connect((ROOT/selected['release']['data_path']/'navigation/navigation.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
extra=[]
for row in db.execute("select json from source where document_id='7687ac5d901e9a4a'"):
 s=json.loads(row[0])
 if any(str(b['block_id'])=='233' for b in s['blocks']):extra.append(s)
assert len(extra)==1
s=extra[0];db.close();put(ART/'offline/extra-source.json',{'id':'put_option','document_id':s['document_id'],'node':s['unit_id'],'source_id':s['id'],'heading':s.get('heading')})
criteria={'hypothesis':'With equal source knowledge, evidence delivery and exploration gates, a use-first assessment prompt improves core explanation coverage and reduces repeated missing-source generation.',
 'success':['Candidate required-item total exceeds baseline, no per-case coverage regression and no new forbidden inference.', 'Two CLOSED_EVIDENCE cases have zero assessment-triggered additional research in both arms; missing evidence remains explicit.', 'Novel composed case preserves stored-condition explanation and acquires/cites the non-stored put-option source; no answer copied from an earlier question.', 'No ACL/hash/state/citation regression; candidate total model calls <= baseline and total seconds <= 1.5 times baseline.'],
 'limits':{'max_requests':10,'max_model_calls_per_request':24,'wall_seconds_per_request':900,'concurrency':1,'rss_gib':6,'minimum_available_gib':3},
 'order':[[c['id'],a] for i,c in enumerate(cases) for a in (['baseline','candidate'] if i%2==0 else ['candidate','baseline'])],
 'failure':'First provider transport/binding or source/ACL/state integrity failure stops later physical calls. Native one schema repair only, no case retry, no fallback.',
 'failure_contract':{'owner':'Existing assessment and gateway retain their one repair and cumulative request budget; no extra recovery stage.', 'closed':'After native source selection/delivery, block ASSESS_GAP_REENTRY; retain claims, gaps and LIMITED_ANSWER. Initial discovery/read cost remains and is measured.', 'empty_plan':'Explicit no-match disables delivery; both arms use identical null guard fix.', 'meaning':'Prompt cannot certify legal applicability. Existing claims/gaps schema, exact citation and publication checks remain.', 'resume':'Native journal preserves counters and failures; research runner refuses automatic replay of an existing request.', 'item_tracking':'Prompt-only instruction through existing claims/gaps/reasons. No new enforced per-item output schema in this experiment.'},
 'controls':'Both arms use ADR0993 delivery ON and the same source-first Gold seed, model, version, scopes, limits and CLOSED/EXTEND gate. Candidate changes only assessment system prompt. New question excluded from seed definitions.',
 'scope':'Known four CM plus one newly composed public extension; all in-sample probe. Closed cases are counterfactual manually curated source knowledge, not prior verified successful answers. MAIN unchanged.'}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Paired required-item coverage, repeated-output failures, added research and original-source integrity',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria)
for a in m['design']['arms']:a.update(changes='Shared source delivery and reuse gate; assessment use-first prompt '+('off' if a['id']=='baseline' else 'on'),controls=criteria['controls'])
m['design']['retrieval_stage_plan']['stages_by_arm']={a:[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}] for a in ['baseline','candidate']}
m['dataset'].update(name='CM known4 and novel composed put-option extension',version='20261022',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'native_rag_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Five prospectively fixed cases, alternating baseline/candidate order, one request each',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
put(ADR/'실험/manifest.json',m)
r=selected['release'];C=ROOT/r['code_root']
P=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0996/candidate'
if not P.exists():P=ac.snapshot(ADR,'candidate',[str((C/n).relative_to(ROOT)) for n in r['files']]+['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/pipeline/shortcut_package.py','02_BACKEND/lawrag/pipeline/legal_wiki_compiler.py'],experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001'])
else:assert not read(P/'candidate.json')['revisions'], 'Cannot alter frozen candidate'
pm=read(parent/'design/candidate.json');PP=ROOT/pm['path'];rev=read(PP/'candidate.json')['revisions'][-1]
for f in rev['files']:
 target=str(Path(f['frozen_path']).relative_to(PP.relative_to(ROOT)/'revisions'/rev['revision_id']/'snapshot'));dest=P/'snapshot'/target;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/f['frozen_path'],dest)
 if not (ROOT/target).exists():ac.register_file(P,target,upstream_state='absent')
put(DES/'candidate.json',{'path':str(P.relative_to(ROOT)),'selected_code_relative':r['code_root']})
runner=(old/'e2e.py').read_text().replace('ADR0993','ADR0996')
runner=runner.replace("transport.knowledge_delivery_enabled=(arm=='candidate')", "transport.knowledge_delivery_enabled=True\n        t.knowledge_use_first_prompt=(arm=='candidate');t.knowledge_reuse_mode=case['reuse_mode']")
runner=runner.replace("'complete':len(results)==8", "'complete':len(results)==len(read(DES/'criteria.json')['order'])")
runner=runner.replace("'actual_native_api':True", "'actual_native_api':True,'reuse_mode':case['reuse_mode']")
(D/'e2e.py').write_text(runner)
for name in ['pin.py','contracts.py','audit.py','report_common.py','archive_runtime.py','delivery_audit.py']:
 text=(old/name).read_text().replace('ADR-0993','ADR-0996').replace('ADR0993','ADR0996')
 if name=='audit.py':text=text.replace("important[case['id']]", "important.get(case['id'],[('7687ac5d901e9a4a','233')])")
 (D/name).write_text(text)
print('DESIGN AND SNAPSHOT PREPARED; zero model calls')
