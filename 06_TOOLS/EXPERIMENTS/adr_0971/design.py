from common import *
import sqlite3
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
assert not (DES/'criteria.json').exists()
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json'); release=read(ROOT/pointer['manifest_path'])
assert pointer['generation']==98
data=ROOT/release['data_path']; db=sqlite3.connect((data/'store.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
scope=[]
for did,name,raw in db.execute("SELECT document_id,name,json_extract(json,'$.document_metadata') FROM document"):
    meta=json.loads(raw or '{}')
    if (meta.get('source_category')=='external' and meta.get('raw_role')=='body') or did in {'527731af0a9a554c','8f93eda174f02974'}:
        scope.append({'document_id':did,'name':name,'metadata':meta})
db.close();assert len(scope)==70
registry=read(ROOT/'01_DATA/GOLDEN/registry-v2-risk_cm.json')
cases=[{'id':c['id'],'question':c['question']} for c in registry['cases'] if c['collection']=='cm'];assert len(cases)==51
put(DES/'cases.json',cases);put(DES/'scope.json',scope)
rebinding=read(ROOT/'09_ARTIFACTS/AUDITS/20261008-native-cm-serving/CM51_PORTABLE_SOURCE_PACKAGE.json')
put(DES/'offline-reference.json',rebinding['cases'])
criteria={
 'hypothesis':'All stored text of the user-selected70 structured standalone external documents can be embedded with exact source coverage and bounded RAM; on this same complete corpus reranking dense top50 may improve CM51 source recall.',
 'primary_metric':'Build:70/70 documents,100% nonempty original block character coverage and0 tokenizer-truncated embedding inputs. Retrieval: exact current rebound required article recall@10, not legal answer accuracy.',
 'success_criteria':['Build source/span/hash checks have zero mismatches; every nonempty character and every nonempty source block covered','All70 documents embedded; all1024-dimensional vectors finite and normalized within0.01','For reranker superiority only: recall@10 increase>=0.05 and all-required cases increase with<=2 newly uncovered cases'],
 'failure_criteria':'Source/model/code hash mismatch stops. Missing source blocks or implicit token truncation stops. Provider failure stops external calls and is not an incorrect legal answer. Build success and rerank success are separate.',
 'scope':[r['document_id'] for r in scope], 'generation_path':release['data_path'],
 'latest_scope':'Exactly current selected retained70 documents; no official latest-version claim. KRX5 lack date metadata and two CM supplements lack document_metadata. Standalone attachments elsewhere and excluded2 PDFs are not included.',
 'chunking':{'max_characters':800,'overlap_characters':100,'max_embedding_tokens':512,'prefix_characters':100,'group':'nearest true article ancestor; otherwise block owner unit, or explicit unassigned block group','coverage':'all original source blocks, including headings/addenda/whitespace, exact UTF-8 text preserved; token-aware subdivision instead of truncation; explicit source block offsets per chunk','prefix':'document name and source coordinate only; bounded prefix is navigation metadata, never a replacement for original text'},
 'retrieval':{'pool':50,'present':10,'article_score':'max cosine across all indexed chunks; stable row tie-break','rerank_input':'query plus best chunk of each selected group; tokenize-aware overlapping windows <=512 tokens, group score=max window score','context':'same top10 source groups, whole original group text,32000 character total budget with explicit oversized exclusions; index coverage is separate from answer context budget'},
 'answer_case_ids':['cm-001','cm-011','cm-021','cm-031','cm-041','cm-051'],
 'answer':{'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','max_calls':12,'max_repairs':0,'retries':0,'circuit':'first provider/quote failure stops all remaining external product calls; preserve unknown attempts'},
 'judge':{'model':'qwen/qwen3.8-27b','max_calls':6,'scope':'completed pairs only, alternating blind A/B, offline reference only; no human calibration'},
 'data':'All CM51 original registered questions, known in-sample. Offline reference uses20261008 exact current coordinate rebinding; all98 source versions/coordinates checked after product selection. Prior0970 raw-coordinate scores are not directly comparable.',
 'resources':{'concurrency':1,'cpu_threads':4,'batch_size':4,'shard_rows':256,'rss_gib':5.5,'as_gib':9,'min_available_gib':3,'min_disk_gib':10,'embedding_deadline_seconds':21600,'model':'cached BGE-M3 exact pinned local bytes; CPU, no model/provider fallback'},
 'failure_contract':{'owner':'single explicit research runner; embedding shard commit is sole resume owner','recovery':'source or frozen input mismatch is terminal; incomplete shard temporary files retained, committed hash-verified shards reused without re-encoding; bounded same deadline and1 explicit resume after interruption/resource recovery; no automatic semantic repairs','states':'prepared/embedding/partial/complete/failed; only committed shards count; durable progress and attempt logs; same run counters/deadline on resume','tests':'full character coverage, long-token split, compound coordinates, empty blocks, partial shard resume, stale source/checkpoint, duplicate execution lock, finite vectors, allowed-scope reader; actual CLI candidate consumer smoke test'},
 'stage_boundary':'source ledger begins with dense50; full searchable group inventory recorded once, gold joined only offline after immutable product selection'}
put(DES/'criteria.json',criteria);put(DES/'baseline.json',{'pointer':pointer,'release':release})
models=read(ROOT/'04_EXPERIMENTS/ADR/ADR-0970-canonical-dense-rerank-cm/artifacts/design/models.json');put(DES/'models.json',models)
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(**{k:criteria[k] for k in ['hypothesis','primary_metric','success_criteria','failure_criteria']},criteria_frozen_before_run=True,execution=criteria)
m['design']['arms']=[{'id':a,'role':'candidate','derived_from':['ADR-0967-experiment-v1/integrated'],'changes':'Complete70-document chunk corpus; '+a,'controls':'Same structured sources, chunk vectors, questions, source reader, generation prompt and budget'} for a in ['dense','dense-rerank']]
stages=[{'stage_id':'vector50','kind':'source','parent_stage_ids':[]},{'stage_id':'rank','kind':'rerank','parent_stage_ids':['vector50']},{'stage_id':'top10','kind':'select','parent_stage_ids':['rank']},{'stage_id':'present','kind':'present','parent_stage_ids':['top10']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ['dense','dense-rerank']}
m['dataset'].update(name='CM51 on complete structured standalone external70',version='MAIN98 source +20261008 CM rebindings',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['runs'][0].update(arm_ids=['dense','dense-rerank'],selection_rule=criteria['data'],artifact_path=str((RUN/'result.json').relative_to(ROOT)))
put(ADR/'실험/manifest.json',m)
for arm in ['dense','dense-rerank']:
 ac.snapshot(ADR,arm,['02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py'],experiment_id=m['experiment_id'],arm_id=arm,run_ids=['run-001'])
print('Design frozen;70 documents;51 queries; local models shared; no model calls.')
