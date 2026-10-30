from common import *
import sqlite3,sys
f=read(DES/'freeze-preflight-002.json');sys.path.insert(0,str(ROOT/f['code_root']/'02_BACKEND'))
from semantic_runtime.contracts import digest
P=ART/'live'/sys.argv[1];body=read(P/'response.json')['body'] if (P/'response.json').exists() else {}
if not isinstance(body.get('assembly'),dict):
 checks={'stored_request_status':'INCOMPLETE','view_hash_verified':False,'stored_answer_text_equal':False,'stored_assessment_hash_equal':False,'reason':'API did not return a completed answer assembly','new_model_calls':0}
 put(P/'storage-audit.json',checks);print(checks);raise SystemExit(0)
case=body['assembly']['term_agent']['case'];view=body['assembly']['term_agent']['judgment_view'];refs=[]
with sqlite3.connect((ROOT/read(P/'result.json')['journals'][0]).as_uri()+'?mode=ro',uri=True) as j:
 for stage,ref in case['judgment_refs'].items():
  row=j.execute('select payload_json,payload_hash from entity_version where kind=? and entity_id=? and version=?',(ref['kind'],ref['entity_id'],ref['version'])).fetchone()
  assert row and digest(json.loads(row[0]))==row[1]==ref['payload_hash'];refs.append(stage)
checks={'stage_references_verified':refs,'stage_count':len(refs),'case_status':case['status'],'view_hash_verified':digest({k:v for k,v in view.items() if k!='content_sha256'})==view['content_sha256']}
with sqlite3.connect(next((P/'runtime').rglob('cases-v4.sqlite')).as_uri()+'?mode=ro',uri=True) as db:
 records=[(status,json.loads(raw)) for status,raw in db.execute('select status,response from request where response is not null')]
 matched=[(status,value) for status,value in records if value.get('goal_id')==body['question_id']]
 assert len(matched)==1
 status,value=matched[0];checks.update(stored_request_status=status,stored_answer_text_equal=value['answer']['text']==body['answer']['text'],stored_assessment_hash_equal=value['answer']['assessment_hash']==case['judgment_refs']['ASSESS']['payload_hash'],stored_claims=len(value['answer']['claims']))
assert checks['view_hash_verified'] and checks['stored_answer_text_equal'] and checks['stored_assessment_hash_equal']
put(P/'storage-audit.json',checks);print(checks)
