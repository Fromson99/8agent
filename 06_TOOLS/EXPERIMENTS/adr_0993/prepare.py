from pathlib import Path
import json,hashlib,sys,shutil
ROOT=Path(__file__).resolve().parents[3]; D=Path(__file__).parent
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'));import adr_candidate as ac
src=ROOT/'06_TOOLS/EXPERIMENTS/adr_0987'
common=(src/'common.py').read_text().replace('ADR-0987-cm-source-ontology-native-e2e','ADR-0993-knowledge-original-delivery')
(D/'common.py').write_text(common)
exec(common.replace('ROOT=Path(__file__).resolve().parents[3]','ROOT=ROOT'))
old=ROOT/'04_EXPERIMENTS/ADR/ADR-0987-cm-source-ontology-native-e2e/artifacts'
for name in ['cases.json','curated-source-values.json','method-templates.json']:
 put(DES/name,read(old/'design'/name))
put(ART/'offline/criteria.json',read(old/'offline/criteria.json'))
put(ART/'agent_layer/corrected-experiences.json',read(old/'agent_layer/corrected-experiences.json'))
p=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');r=read(ROOT/p['manifest_path']);C=ROOT/r['code_root']
assert p['generation']==100 and all(sha(C/n)==h for n,h in r['files'].items())
put(DES/'selected.json',{'pointer':p,'release':r,'pointer_sha256':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')})
criteria={'hypothesis':'Exact original delivery for source-bound knowledge improves required-item coverage while retaining model applicability judgments.',
 'success':['All authorized in-budget knowledge source bundles appear in assessment evidence, or explicit omission reason; original hashes/ACL/consumer verification hold.', 'No additional model stage; no fake navigation adoption; source-bound checks stay review candidates.', 'Report actual eight API outcomes and frozen required/forbidden coverage, candidate improvement without source integrity regression. Speed only evaluated alongside complete answers.'],
 'limits':{'max_requests':8,'max_model_calls_per_request':24,'wall_seconds_per_request':900,'concurrency':1,'rss_gib':6,'minimum_available_gib':3,'supplemental_chars':16000,'supplemental_items':12},
 'order':[[c['id'],a] for i,c in enumerate(read(DES/'cases.json')) for a in (['baseline','candidate'] if i%2==0 else ['candidate','baseline'])],
 'failure':'First provider transport failure or code/source/ACL/state integrity failure stops all later physical calls. No whole-case retry; no fallback provider. Preserve incomplete outcomes.',
 'recovery_owner':'Existing native gateway/decision bounded repair. Exact delivery handles only budget omissions; source integrity errors propagate. Counters/deadline remain in native journal.',
 'scope':'Isolated MAIN100 candidate with ADR0987 public source-curated knowledge; local SQLite research only; no MAIN or GENOS change.',
 'failure_contract':{'missing':'Explicit unresolved/omitted receipt; never infer absence or user fact.','budget':'Skip whole source-method bundle on delivery cap; preserve native tool/read budget and verified partial records.','duplicates':'Reuse existing unit evidence and deterministic receipts; no new budget on resume.','meaning':'Delivery does not imply relevance/adoption/truth; existing assessment determines claims and gaps.','consumers':'SELECT evidence/originals/final_ids -> ASSESS options -> COMPOSE/citation publication; delivery receipts separate prepared/input-returned.'}}
put(DES/'criteria.json',criteria)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(hypothesis=criteria['hypothesis'],primary_metric='Exact assessment original delivery and frozen required item coverage, paired calls/latency',success_criteria=criteria['success'],failure_criteria=criteria['failure'],criteria_frozen_before_run=True,execution=criteria)
for a in m['design']['arms']:
 a.update(changes='MAIN100 + same published knowledge; exact delivery '+('off' if a['id']=='baseline' else 'on'),controls='Same source, ontology, scopes, model, existing stop behavior, limits')
m['integration'].update(result_arm='candidate',reason='Combine MAIN100 native contracts with prior source-bound ontology pilot',common_invariants=['Original evidence ACL/hash/state checks','No cached legal conclusions','Source-primary Gold and Agent logs separate','User explicitly forbids MAIN activation'],conflicts=[],no_conflict_reason='Retain all MAIN100 code; adopt only ADR0987 explicit research export/route bridge and curated data. No MAIN99 engine/stop code copied.',rollback_ref='ADR-0985-experiment-v1/candidate')
for item in m['integration']['parent_contributions']:
 item.update(adopted=['MAIN100 code and native completion'] if '0985' in str(item) else ['Source-primary curated experience, public export grant, knowledge route bridge'],excluded=['Prior selected runtime/code except named bridge','Any performance certification'])
m['design']['retrieval_stage_plan']['stages_by_arm']={a:[{'stage_id':'original_read','kind':'source','parent_stage_ids':[]},{'stage_id':'final_cited','kind':'present','parent_stage_ids':['original_read']}] for a in ['baseline','candidate']}
m['dataset'].update(name='Previously exposed CM051/008 seeds and CM010/007 reuse',version='20261022',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['llm_policy']['llm_calls']=[{'role':'native_rag_product','class':'product','model':'qwen/qwen3.8-27b','repeats':1}]
m['runs'][0].update(selection_rule='Four prior-exposed CM, fixed alternating pairs',artifact_path=str((RUN/'result.json').relative_to(ROOT)))
put(ADR/'실험/manifest.json',m)
P=ac.snapshot(ADR,'candidate',[str((C/n).relative_to(ROOT)) for n in r['files']]+['02_BACKEND/lawrag/research/experiment_client.py','02_BACKEND/lawrag/pipeline/shortcut_package.py','02_BACKEND/lawrag/pipeline/legal_wiki_compiler.py'],experiment_id=m['experiment_id'],arm_id='candidate',run_ids=['run-001']);S=P/'snapshot'/r['code_root']
b=read(old/'design/candidate.json');B=ROOT/b['path']/'revisions/rev-001/snapshot'/b['selected_code_relative']
shutil.copyfile(B/'02_BACKEND/semantic_runtime/legal_agent/knowledge_bridge.py',S/'02_BACKEND/semantic_runtime/legal_agent/knowledge_bridge.py')
config=read(S/'00_SYSTEM/PIPELINE.json');config['legal_knowledge'].update(management_enabled=True,consumer_mode='consume');put(S/'00_SYSTEM/PIPELINE.json',config)
put(DES/'candidate.json',{'path':str(P.relative_to(ROOT)),'selected_code_relative':r['code_root']})
runner=(src/'e2e.py').read_text().replace('ADR0987','ADR0993').replace("'source_main':99","'source_main':100")
runner=runner.replace("['block_ids'][:2]","['block_ids']")
runner=runner.replace("config['consumer_mode']='off' if arm=='baseline' else 'consume'","config['consumer_mode']='consume';app.state.pipeline.term_agent.transport.knowledge_delivery_enabled=(arm=='candidate')")
runner=runner.replace('max_calls=40','max_calls=24')
runner=runner.replace("status==429,unknown=status>=500","False,unknown=False")
runner=runner.replace("except ExperimentProviderError as exc:\n                status=", "except ExperimentProviderError as exc:\n                current['provider_failed']=True\n                status=")
runner=runner.replace("except ExperimentTransportError as exc:raise", "except ExperimentTransportError as exc:\n                current['provider_failed']=True\n                raise")
runner=runner.replace("calls=current['client'];n=", "assert not current.get('provider_failed'), 'Provider failed: no further dispatch'\n        calls=current['client'];n=")
runner=runner.replace("after={str(p) for p in (RUN/'agent_layer/runtime').rglob('journal.sqlite')}","fatal=fatal or current.get('provider_failed',False)\n            after={str(p) for p in (RUN/'agent_layer/runtime').rglob('journal.sqlite')}")
(D/'e2e.py').write_text(runner)
for n in ['audit.py','report_common.py','archive_runtime.py']:
 (D/n).write_text((src/n).read_text().replace('ADR-0987','ADR-0993').replace('ADR0987','ADR0993').replace("'knowledge'","'candidate'"))
print('Prepared isolated MAIN100 with shared source knowledge; model calls0')
