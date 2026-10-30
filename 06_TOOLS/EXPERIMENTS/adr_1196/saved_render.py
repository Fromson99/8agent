"""Saved failed-case diagnostic; no product model call or regrade of old run."""
from common import *
import gzip,sqlite3
f=read(sorted(DES.glob('freeze-*.json'))[-1]);sys.path.insert(0,str(ROOT/f['code_root']/'02_BACKEND'))
from semantic_runtime.legal_agent import completion_contracts as cc,narrative_answer as n
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1195-main116-live-cm007/artifacts/live/cm-007'
def raw(p):
 v=json.loads(gzip.decompress(p.read_bytes())) if p.suffix=='.gz' else read(p)
 return raw(ROOT/v['raw_json']['path']) if isinstance(v,dict) and set(v)=={'raw_json'} else v
response=raw(P/'response.json')['body'];refs=response['assembly']['term_agent']['case']['judgment_refs']
journal=ROOT/read(P/'result.json')['journals'][0];before=sha(journal)
with sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True) as db:
 def payload(stage):
  ref=refs[stage]
  return json.loads(db.execute('select payload_json from entity_version where kind=? and entity_id=? and version=?',(ref['kind'],ref['entity_id'],ref['version'])).fetchone()[0])
 a=payload('ASSESS');old=payload('COMPOSE');selection=payload('SELECT')
cc.verify_composition(a,old)
value=cc.compose(a,n.preserved_plan(a,issues=selection.get('issues')));cc.verify_composition(a,value)
assert value['claims']==a['claims'] and value['limitations']==old['limitations'] and value['stop_reason']==old['stop_reason']
assert all(c['text'] in value['text'] for c in a['claims'])
checks={'legacy_saved_composition_still_verifies':True,'every_accepted_claim_text_in_final':True,
 'domestic_classification':'국내소재외국지주회사 제외' in value['text'],
 'foreign_classification':'국내소재외국지주회사 포함' in value['text'],
 'initial_acquisition_denominator':value['text'].count('최초에 취득한 주식의 100분의 5') == 3,
 'domestic_postapplication_scope':'국내에서 모집' in value['text'],
 'all_claims_originals_gaps_and_stop_preserved':True,'old_journal_unchanged':sha(journal)==before}
assert all(checks.values()),checks
(ART/'saved-cm007-preserved-answer.txt').write_text(value['text']+'\n')
put(ART/'saved-render-diagnostic.json',{'in_sample':True,'decision_eligible':False,'new_model_calls':0,'source':bind(P/'response.json.gz'),'checks':checks,'old_chars':len(old['text']),'new_chars':len(value['text']),'claims':len(a['claims']),'cm007_live_pass_claimed':False,'cm009_eligible':False,'quality_certified':False})
print('Saved final render preserves all',len(a['claims']),'claims;',len(old['text']),'to',len(value['text']),'chars; new model calls0')
