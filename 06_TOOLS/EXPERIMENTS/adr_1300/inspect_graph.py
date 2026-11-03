"""Post-run, human-guided inspection of existing public reference edges only."""
from common import *
import sqlite3,collections
f=read(DES/'freeze-v2.json');sys.path.insert(0,str(ROOT/f['code_root']/'02_BACKEND'))
from semantic_runtime.storage import Store
from semantic_runtime.team_scope import select_documents
from semantic_runtime.term_references import reference_targets
data=ROOT/read(DES/'source.json')['data_path'];store=Store(data)
allowed=set(read(DES/'cases-v2.json')[0]['document_ids'])
assert allowed<=set(select_documents(store,'financial_team'))
nav=sqlite3.connect((data/'navigation/navigation.sqlite').as_uri()+'?mode=ro',uri=True)
store.selection.bind(nav,navigation=True)
seed='article:88b32b646587c31631bfa149';sources={};references={};depth={seed:0};frontier=[seed];outside=set()
def source(sid):
    if sid not in sources:
        row=nav.execute('SELECT json FROM source WHERE id=?',(sid,)).fetchone()
        if not row:return None
        s=json.loads(row[0])
        if s['document_id'] not in allowed:return None
        unit=json.loads(store.db.execute('SELECT json FROM source_unit WHERE document_id=? AND unit_id=?',
            (s['document_id'],s['article_coordinate']['node'])).fetchone()[0])
        if not unit.get('coordinate_key','').startswith('body:'):return None
        for b in s['blocks']:
            original=store.source(s['document_id'],b['block_id'])
            assert original['text']==b['text'] and original['source_artifact_sha256']==s['source_artifact_sha256']
        sources[sid]=s
    return sources[sid]
while frontier:
    sid=frontier.pop(0);s=source(sid)
    if not s or depth[sid]>=2:continue
    for row in nav.execute('SELECT r.json FROM reference r JOIN reference_end e ON e.reference_id=r.id WHERE e.source_id=?',(sid,)):
        r=json.loads(row[0])
        if r['source_id']!=sid:continue
        text=store.source(s['document_id'],r['block_id'])['text']
        assert r['source_text']==text and hashlib.sha256(text.encode()).hexdigest()==r['source_text_sha256']
        if r.get('mention_text'):assert text[r['mention_start']:r['mention_end']]==r['mention_text']
        retained=[]
        for t in reference_targets(r):
            target=source(t['source_id'])
            if target is None:outside.add(t['source_id']);continue
            bmap={str(b['block_id']):b['text'] for b in target['blocks']}
            for bid in t.get('block_ids',[]):assert str(bid) in bmap
            retained.append(t)
            if target['id'] not in depth:depth[target['id']]=depth[sid]+1;frontier.append(target['id'])
        references[r['id']]={**r,'verified_targets_in_scope':retained}
store.check_unchanged()
edges=[{'reference_id':r['id'],'from':r['source_id'],'to':t['source_id'],'resolution':r['resolution'],
        'source_block_id':r['block_id'],'target_unit_id':t.get('unit_id'),'target_blocks':t.get('block_ids',[])}
       for r in references.values() for t in r['verified_targets_in_scope']]
result={'inspection':'post-run human-guided two-hop outgoing traversal, not model-selected',
    'seed':seed,'max_depth':2,'documents':len({s['document_id'] for s in sources.values()}),
    'nodes':sources,'references':references,'edges':edges,'depths':depth,
    'outside_scope_target_count':len(outside),'source_mismatches':0,'acl_violations':0,
    'semantic_applicability_approved':False,'injected_into_live_model':False}
raw(ART/'stored-public-graph.json.gz',result)
summary={'documents':result['documents'],'articles':len(sources),'references':len(references),'edges':len(edges),
    'cross_document_edges':sum(sources[e['from']]['document_id']!=sources[e['to']]['document_id'] for e in edges),
    'official_delegation_edges':sum(e['resolution']=='OFFICIAL_DELEGATION' for e in edges),
    'unresolved_references':sum(not r['targets'] for r in references.values()),
    'outside_scope_targets':len(outside),'source_mismatches':0,'acl_violations':0,'model_calls':0}
put(ART/'stored-public-graph-summary.json',summary)
print(json.dumps(summary,ensure_ascii=False))
for e in edges:
    if e['from']==seed or e['resolution']=='OFFICIAL_DELEGATION':
        print(sources[e['from']]['document_name'],sources[e['from']]['heading'],'->',sources[e['to']]['document_name'],sources[e['to']]['heading'],e['resolution'])
nav.close();store.close()
