"""Read-only known-case diagnostic, excluded from prospective qualification."""
from common import *
import gzip,sqlite3,copy
f=read(DES/'freeze-rev-001.json');sys.path.insert(0,str(ROOT/f['code_root']/'02_BACKEND'))
from semantic_runtime.legal_agent import completion_contracts as cc
P=ROOT/'04_EXPERIMENTS/ADR/ADR-1193-final-scope-prompt-live-cm007/artifacts/live/cm-007'
def raw(p):
 v=json.loads(gzip.decompress(p.read_bytes())) if p.suffix=='.gz' else read(p)
 return raw(ROOT/v['raw_json']['path']) if isinstance(v,dict) and set(v)=={'raw_json'} else v
response=raw(P/'response.json')['body'];answer=response['answer'];refs=response['assembly']['term_agent']['case']['judgment_refs'];ref=refs['ASSESS'];journal=ROOT/read(P/'result.json')['journals'][0]
with sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True) as db:
 old=json.loads(db.execute('select payload_json from entity_version where kind=? and entity_id=? and version=?',(ref['kind'],ref['entity_id'],ref['version'])).fetchone()[0])
cref=refs['COMPOSE']
with sqlite3.connect(journal.as_uri()+'?mode=ro',uri=True) as db:
 answer=json.loads(db.execute('select payload_json from entity_version where kind=? and entity_id=? and version=?',(cref['kind'],cref['entity_id'],cref['version'])).fetchone()[0])
assert answer['text']==response['answer']['text']
cc.verify_composition(old,answer)
issues=[{'id':s['issue_id'],'question':s['issue_id']} for s in old['issue_assessments']]
new=cc.refresh_limitations(copy.deepcopy(old),issues,old['stop_reason'])
changed=cc.compose(new,answer['composition_plan']);cc.verify_composition(new,changed)
assert new['gaps']==[] and not new['limitations']
assert new['claims']==old['claims'] and new['stop_reason']==old['stop_reason']
assert changed['text']==answer['text'].split('\n\n확인 범위\n\n')[0]
assert '국내에서 모집·매출한' in changed['text']
assert {k:v for k,v in old.items() if k not in ('limitations','limitation_items')}=={k:v for k,v in new.items() if k not in ('limitations','limitation_items')}
(ART/'saved-cm007-without-generic-footer.txt').write_text(changed['text']+'\n')
put(ART/'saved-render-diagnostic.json',{'in_sample':True,'decision_eligible':False,'new_model_calls':0,'source':bind(P/'response.json.gz'),'old_saved_composition_still_verifies':True,'only_generic_footer_removed':True,'claims_evidence_gaps_reviews_stop_reason_preserved':True,'source_original_journal_unchanged':True,'old_chars':len(answer['text']),'new_chars':len(changed['text']),'supervisor_unknown_remains':True,'cm009_eligible':False})
print('Saved CM007 composition: old publication valid; only generic footer removed; failures preserved')
