"""Pre-result specification; no models or retrieval are executed here."""
from common import *
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/COMMANDS'))
import adr_candidate as ac
assert not (DES/'criteria.json').exists()
pointer=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')
release=read(ROOT/pointer['manifest_path']);assert pointer['generation']==98
grant=read(ROOT/release['code_root']/'00_SYSTEM/LEGAL_AGENT/local-gemma-public.json')
rows=[x for x in read(ROOT/'01_DATA/GOLDEN/registry-v2-risk_cm.json')['cases'] if x['collection']=='cm']
assert len(rows)==51
put(DES/'cases.json',[{'id':x['id'],'question':x['question']} for x in rows])
put(DES/'offline-reference.json',[{'id':x['id'],'reference_answer':x['reference_answer'],'as_of':x['as_of'],'targets':x['targets']} for x in rows])
criteria={
 'hypothesis':'On the same raw CM51 questions and source versions, cross encoding the dense top50 article roots improves required-source recall at10 versus dense-only top10, and can improve answers generated with the same Qwen prompt.',
 'primary_metric':'Required canonical article-root recall at10. Secondary all-required-covered cases and paired answer pass among evaluable generated pairs. Source retrieval is not legal accuracy.',
 'success_criteria':['Rerank recall@10 exceeds dense by at least 0.05 absolute','All-required-covered count increases with at most2 newly uncovered cases','No source/hash/permission drift; only approved public documents'],
 'failure_criteria':'Any mismatch stops execution. Provider failure is not wrong answer. No superiority claim without paired completed answers. Recall criteria failure retains Proposed.',
 'data':'All51 registered collection=cm questions, raw wording including original business context; no target-aware scope or query rewriting. Known in-sample, not a holdout.',
 'scope':grant['public_document_ids'],
 'generation_path':release['data_path'],
 'retrieval':{'vector':'existing BGE-M3 section vectors; admit only exact legacy800-character input hashes against selected MAIN98 originals','pool':50,'present':10,'article_score':'maximum cosine of its descendant sections; stable doc/node ties','reranker':'cross-encoder/mmarco-mMiniLMv2-L12-H384-v1 @1427fd652930e4ba29e8149678df786c240d8825','rerank_input':'raw question + best vector passage per article, same50 article pool; max_length512, batch4','context':'same10 whole article spans per arm; stable ordered prefix under32000 characters, skip oversized article explicitly; source text never summarized','corpus_exclusion':'unmatched cache rows and out-of-scope documents excluded; no backfill or lexical expansion'},
 'embedding_identity':'Legacy cache lacks a model identity receipt. Pin current local model bytes; recompute16 deterministic distributed cached passages and require cosine>=0.995 before query encoding. Empirical compatibility, not a full historical provenance certificate.',
 'answer':{'model':'qwen/qwen3.8-27b','provider':'Parasail FP8','reasoning':'none','max_output_tokens':4000,'order':'even numbered case rerank first, odd dense first','max_calls':102,'transport_retries':0,'schema_repairs':0,'circuit_breaker':'After first HTTP429/402/401 or transport unknown, stop remaining external calls; retain full offline retrieval and all attempted responses. No alternate provider/model.'},
 'judge':{'model':'qwen/qwen3.8-27b','max_calls':51,'blind_labels':'A/B alternate per case; same judge sees both same-question answers and reference only offline','human_calibration':'not performed; provisional same-model judgment, not certified accuracy'},
 'baseline_main':'ADR0968 is a separate observational MAIN98 run. Reuse only completed artifacts after hash pinning; no direct accuracy comparison if provider failures. It is not a lineage parent or a paired same-final-prompt arm.',
 'resources':{'concurrency':1,'rss_gib':5.5,'as_gib':9,'min_available_gib':3,'min_disk_gib':10,'max_local_seconds':1800,'cpu_threads':4,'encoder_and_reranker':'separate serial processes; no concurrent weight loads'},
 'failure_contract':{'owner':'one experiment runner','recovery':'No semantic rewriting or automatic retry; keep partial results and exact error. Resume skips completed stages, rejects partially started model stages. Hash/permission mismatch stops all dependent work.','state':'immutable input locks; per-case retrieval, raw provider I/O and usage; restart never resets budget','consumer':'local experiment result and per-question report; no MAIN or GENOS change'},
 'stage_boundary':'source stage is the admitted dense top50 article candidates; full searchable article corpus manifest stored once. Ledger accounts rerank/selection/context losses. Gold joined only after all product selection; misses before top50 remain misses.'}
put(DES/'criteria.json',criteria)
put(DES/'baseline.json',{'pointer':pointer,'release':release,'grant':grant})
m=read(ADR/'실험/manifest.json');m['lineage']['hypothesis_delta']=criteria['hypothesis']
m['design'].update(**{k:criteria[k] for k in ('hypothesis','primary_metric','success_criteria','failure_criteria')},criteria_frozen_before_run=True,execution=criteria)
m['design']['arms']=[{'id':a,'role':'candidate','derived_from':['ADR-0967-experiment-v1/integrated'],'changes':'Plain dense top10' if a=='dense' else 'Same dense top50 reordered by local cross encoder, top10','controls':'Same question, exact public source rows, vector cache/model, complete article reader, Qwen generation prompt and context budget'} for a in ('dense','dense-rerank')]
stages=[{'stage_id':'vector50','kind':'source','parent_stage_ids':[]},{'stage_id':'rank','kind':'rerank','parent_stage_ids':['vector50']},{'stage_id':'top10','kind':'select','parent_stage_ids':['rank']},{'stage_id':'present','kind':'present','parent_stage_ids':['top10']}]
m['design']['retrieval_stage_plan']['stages_by_arm']={a:stages for a in ('dense','dense-rerank')}
m['dataset'].update(name='CM51 registered on MAIN98 public65 exact legacy-vector subset',version='registry-v2-risk_cm 20261021 cm collection',frozen_source=str((DES/'cases.json').relative_to(ROOT)),sha256=sha(DES/'cases.json'),legal_version_checked=False,reference_version_checked=False)
m['runs'][0].update(arm_ids=['dense','dense-rerank'],selection_rule=criteria['data'],artifact_path=str((RUN/'result.json').relative_to(ROOT)))
put(ADR/'실험/manifest.json',m)
for a in ('dense','dense-rerank'):
    ac.snapshot(ADR,a,['02_BACKEND/lawrag/runtime/retrieval_stage_ledger.py'],experiment_id=m['experiment_id'],arm_id=a,run_ids=['run-001'])
print('Frozen CM51 specification; candidates created; model calls0')
