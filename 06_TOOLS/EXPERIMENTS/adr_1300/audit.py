"""Offline exact-source, outgoing-wire and actual connection-path inspection."""
from common import *
import sqlite3,collections
f=read(DES/'freeze-v2.json');C=ROOT/f['code_root'];sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent import journal_storage
from semantic_runtime.legal_agent.local_gemma import provider_request
base=ART/'live';case=read(DES/'cases-v2.json')[0];allowed=set(case['document_ids'])
data=ROOT/read(DES/'source.json')['data_path']
db=sqlite3.connect((data/'store.sqlite').as_uri()+'?mode=ro',uri=True)
units={};blocks={};versions={};names={}
for did in allowed:
    version,meta=db.execute('SELECT source_artifact_sha256,json FROM document WHERE document_id=?',(did,)).fetchone()
    versions[did]=version;names[did]=json.loads(meta)['document_metadata']['document_title']
    units[did]={str(uid):(str(parent) if parent is not None else None,json.loads(text))
        for uid,parent,text in db.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?',(did,))}
    blocks[did]={str(bid):(str(uid),text,h) for bid,uid,text,h in db.execute(
        'SELECT block_id,unit_id,text,source_artifact_sha256 FROM source_block WHERE document_id=?',(did,))}
def article(did,bid):
    uid=blocks[did][str(bid)][0];seen=set()
    while uid in units[did] and uid not in seen:
        seen.add(uid);parent,value=units[did][uid]
        if value.get('family')=='kr_article':return (did,int(uid))
        uid=parent
    return None
inventory=sorted((did,int(uid)) for did in allowed for uid,(_,u) in units[did].items() if u.get('family')=='kr_article')
acquired=set();presented=set();checked=set();source_errors=[];acl_errors=[];attempts={};wire_errors=[];budgets={};event_counts=collections.Counter();connection_events=[]
calls=read(base/'calls.json');payloads=[read(p) for p in sorted((base/'raw').glob('call-*/request.json.gz'))]
def verify(did,span,where):
    if did not in allowed:acl_errors.append({'where':where,'document_id':did});return
    bid=str(span['block_id']);b=blocks[did].get(bid)
    if not b or b[1][span['start_cp']:span['end_cp']]!=span['text'] or b[2]!=versions[did]:
        source_errors.append({'where':where,'document_id':did,'block_id':bid});return
    checked.add((did,bid,span['start_cp'],span['end_cp']))
    root=article(did,bid)
    if root:(acquired if where=='acquired' else presented).add(root)
for jp in sorted((base/'runtime').rglob('*.sqlite')):
    conn=journal_storage.connect(jp.as_uri()+'?mode=ro',uri=True)
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if {'evidence_unit','evidence_span'}<=tables:
        for row in conn.execute('SELECT u.document_id,s.block_id,s.start_cp,s.end_cp,s.text FROM evidence_unit u JOIN evidence_span s ON s.evidence_id=u.evidence_id'):
            verify(row['document_id'],dict(row),'acquired')
    if 'model_attempt' in tables:
        for row in conn.execute('SELECT * FROM model_attempt ORDER BY created_seq'):
            encoded=provider_request(json.loads(row['request_json']));encoded['usage']={'include':True}
            if encoded not in payloads:wire_errors.append(row['attempt_id'])
            attempts[row['attempt_id']]={'status':row['status'] if 'status' in row.keys() else None}
    if 'event' in tables and {'kind','payload_json'}<={r[1] for r in conn.execute('PRAGMA table_info(event)')}:
        for row in conn.execute('SELECT kind,payload_json FROM event'):
            event_counts[row['kind']]+=1
            if any(token in row['kind'] for token in ('REFERENCE','CONNECTION','DEFINITION','REJECTED','UNRESOLVED')):
                connection_events.append({'kind':row['kind'],'payload':json.loads(row['payload_json'])})
        if 'budget' in tables:
            bs=[dict(r) for r in conn.execute('SELECT * FROM budget')]
            for row in conn.execute("SELECT payload_json FROM event WHERE kind='REQUEST_BUDGET_BOUND'"):
                key=json.loads(row[0])['request_key']
                budgets[key]=max([budgets.get(key,0),*[b.get('model_reserved',0) for b in bs]])
    conn.close()
def strings(v):
    if isinstance(v,str):yield v
    elif isinstance(v,dict):
        for x in v.values():yield from strings(x)
    elif isinstance(v,list):
        for x in v:yield from strings(x)
wire_texts=[]
for payload in payloads:
    for msg in payload.get('messages',[]):
        content=msg.get('content','')
        try:v=json.loads(content)
        except (ValueError,TypeError):v=content
        wire_texts.extend(strings(v))
def walk(v):
    if isinstance(v,dict):
        if v.get('document_id') and isinstance(v.get('spans'),list):
            for span in v['spans']:
                if (isinstance(span,dict) and all(k in span for k in ('block_id','start_cp','end_cp','text'))
                        and span['text'] and any(span['text'] in text for text in wire_texts)):
                    verify(v['document_id'],span,'wire')
        for x in v.values():walk(x)
    elif isinstance(v,list):
        for x in v:walk(x)
for p in sorted((base/'canonical').glob('[0-9][0-9][0-9].json.gz')):walk(read(p)['view'])
states=sorted((base/'states').glob('*.json.gz'))
latest=read(states[-1]) if states else {}
raw(ART/'connection-events.json.gz',connection_events)
raw(ART/'final-navigation-state.json.gz',latest)
def label(pair):
    did,uid=pair;value=units[did][str(uid)][1]
    return {'document_id':did,'article_root':uid,'document':names[did],'coordinate':value.get('coordinate_key',value.get('surface'))}
summary={'source_article_inventory':inventory,'source_artifact_versions':versions,
    'acquired_articles':[label(x) for x in sorted(acquired)],'presented_articles':[label(x) for x in sorted(presented)],
    'unique_verified_spans':len(checked),'source_mismatches':source_errors,'acl_violations':acl_errors,'wire_mismatches':sorted(set(wire_errors)),
    'physical_calls':len(calls),'unknown':sum(c['status']=='unknown' for c in calls),'unique_attempts':len(attempts),
    'reserved_budget':sum(budgets.values()),'budget_matches':sum(budgets.values())==len(calls)==len(attempts),
    'reported_cost_usd':sum((c.get('usage') or {}).get('cost',0) for c in calls),
    'input_tokens':sum((c.get('usage') or {}).get('prompt_tokens',0) for c in calls),
    'output_tokens':sum((c.get('usage') or {}).get('completion_tokens',0) for c in calls),
    'missing_usage_calls':sum(not c.get('usage') for c in calls),'model_seconds':sum(c.get('seconds',0) for c in calls),
    'event_counts':dict(event_counts),'navigation_states':len(states),
    'reference_history_count':len(latest.get('reference_history',[])),
    'connection_scope_count':len(latest.get('connection_scopes',{})),
    'output_cap_fields':[k for p in payloads for k in ('max_tokens','max_output_tokens','max_completion_tokens') if k in p],
    'main_pointer_unchanged':sha(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json')==f['pointer_sha256'],
    'candidate_unchanged':all(sha(C/n)==h for n,h in f['files'].items()),
    'source_only_is_not_semantic_success':True,'genos_field_executed':False}
put(ART/'source-wire-audit.json',summary)
db.close()
print(json.dumps({k:summary[k] for k in ('physical_calls','unknown','unique_verified_spans','budget_matches','acquired_articles','presented_articles','reference_history_count','reported_cost_usd')},ensure_ascii=False,indent=2))
