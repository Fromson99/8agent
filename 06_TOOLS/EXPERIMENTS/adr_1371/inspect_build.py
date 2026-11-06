"""Audit the persisted workspace and submitted originals without a model call."""
from common import *
import collections
import sqlite3

out=ART/'build-live'
result=read(out/'result.json')
con=sqlite3.connect(f'file:{out}/work.sqlite?mode=ro',uri=True)
latest=con.execute('''SELECT BNDL_ID, REV_NO, WORK_HASH_VAL, ST_CD FROM LGL_ONT_WORK_A w
 WHERE REV_NO=(SELECT max(REV_NO) FROM LGL_ONT_WORK_A WHERE BNDL_ID=w.BNDL_ID)''')
jobs=[]
knowledge=[]
for key,rev,fingerprint,status in latest:
    path=out/'objects/objects'/(fingerprint+'.json')
    assert sha(path)==fingerprint
    obj=read(path)
    if obj.get('kind')=='JOB':
        jobs.append(dict(stage=obj['stage'],phase=obj['phase'],sends=obj['attempt']+1,
                         limit=obj.get('attempt_limit',2),errors=[x['error'] for x in obj['attempts']]))
    elif obj.get('kind')=='KNOWLEDGE':
        knowledge.append(dict(id=key,revision=rev,status=status,work_hash=fingerprint))
calls=read(out/'calls.json') if (out/'calls.json').exists() else []
statements=read(out/'statements.json') if (out/'statements.json').exists() else []
source_texts={x['text'] for x in read(DES/'originals.json')}
judgment_texts={x['payload']['answer_so_far'] for x in read(DES/'records.json')}
literals=[x['content']['text'] for x in statements]
projection=None
if (out/'compiled.json.gz').exists():
    compiled=read(out/'compiled.json.gz')
    doc=compiled['document']
    assert len(knowledge)==1 and knowledge[0]['work_hash']==doc['work_hash']
    assert knowledge[0]['status']=='DRAFT' and doc['bundle_id']==compiled['row']['bundle_id']
    selected={s['bundle_id']:s['content']['text'] for s in doc['workspace_projection']['statements']}
    nodes={n['id']:n for n in doc['proposal']['graph']['nodes']}
    owners={}
    for row in doc['workspace_projection']['coverage']:
        for n in row['node_ids']:
            assert row['decision']=='INCLUDED' and n not in owners and nodes[n]['text']==selected[row['statement_id']]
            owners[n]=row['statement_id']
    assert set(nodes)==set(owners)
    offered=read(DES/'originals.json')
    for src in doc['originals']:
        assert any(x['anchor']==src['anchor'] and x['text']==src['text'] for x in offered)
    by_source={x['id']:x['text'] for x in doc['originals']}
    basis_count=0
    for part in [*nodes.values(),*doc['proposal']['graph']['edges']]:
        for basis in part['basis']:
            assert basis['quote'] and basis['quote'] in by_source[basis['source']]
            basis_count+=1
    paths=compiled['package']['paths']
    for path in paths:
        assert path['body']=='\n\n'.join(nodes[n]['text'] for n in path['node_ids'])

    projection={'paths':[{k:v for k,v in x.items() if k in ('id','title','body','source_ids','purpose')} for x in paths],
                'coverage':doc['workspace_projection']['coverage'],'nodes':list(nodes.values()),'verified_basis':basis_count,
                'unresolved':doc['proposal']['graph']['unresolved'],'ownership_exact':True}
audit={'jobs':jobs,'calls':[{k:r.get(k) for k in ('number','stage','status','seconds','http_status')} for r in calls],
       'logical_stage_counts':dict(collections.Counter(x['stage'] for x in read(out/'generations.json'))),
       'submitted':len(statements),'exact_source_literals':sum(t in source_texts for t in literals),
       'archived_judgment_literals':sum(t in judgment_texts for t in literals),
       'unexpected_literals':[t for t in literals if t not in source_texts|judgment_texts],'knowledge':knowledge,
       'compiled':projection,'publication_count':con.execute('select count(*) from LGL_ONT_PUB_A').fetchone()[0],
       'physical':len(calls),'unknown':result['unknown'],'reported_cost_usd':result['reported_cost_usd'],'seconds':result['seconds']}
assert len(calls)==result['physical_calls'] and all(j['sends']<=j['limit'] for j in jobs)
put(ART/'saved-build-review.json',audit)
print('states',[(r['stage'],r['phase'],r['sends']) for r in jobs], 'knowledge',knowledge)
if projection:
    for p in projection['paths']:print('path',p.get('title'),p.get('body','')[:600])
    print('unresolved',projection['unresolved'])
