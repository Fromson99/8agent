"""Verify final consumer contract; it does not judge source interpretation."""
from common import *
import sqlite3
cid=sys.argv[1];P=ART/'live'/cid;f=read(DES/'freeze-live.json');sys.path.insert(0,str(ROOT/f['code_root']/'02_BACKEND'))
from semantic_runtime.legal_agent import completion_contracts as cc,narrative_answer as n
from semantic_runtime.legal_agent.journal_storage import connect as journal_connect
response=read(P/'response.json')['body'] if (P/'response.json').exists() else {};refs=response.get('assembly',{}).get('term_agent',{}).get('case',{}).get('judgment_refs',{})
checks={'final_assessment_and_compose_exist':all(k in refs for k in ('ASSESS','COMPOSE')),'no_compose_model_request':not any(str(x.get('stage')).startswith('memory-compose') for x in read(P/'calls.json'))}
if checks['final_assessment_and_compose_exist']:
 with journal_connect((ROOT/read(P/'result.json')['journals'][0]).as_uri()+'?mode=ro',uri=True) as db:
  def stage(key):
   ref=refs[key];return json.loads(db.execute('select payload_json from entity_version where kind=? and entity_id=? and version=?',(ref['kind'],ref['entity_id'],ref['version'])).fetchone()[0])
  a=stage('ASSESS');c=stage('COMPOSE');cc.verify_composition(a,c)
  events=[json.loads(r[0]) for r in db.execute("select payload_json from event where kind='COMPOSITION_RENDERED'")]
 checks.update(presentation_is_preserved=c['composition_plan'].get('presentation')==n.PRESERVED_VERSION,all_accepted_texts_in_final=all(x['text'] in c['text'] for x in a['claims']),visible_answer_equals_verified_text=response['answer']['text']==c['text'],server_event_has_no_model=bool(events) and events[-1]['model_call'] is False,claims_unchanged=c['claims']==a['claims'])
put(P/'composition-audit.json',{'case_id':cid,'passed':all(checks.values()),'checks':checks,'new_model_calls':0,'meaning_certified':False})
print(checks)
