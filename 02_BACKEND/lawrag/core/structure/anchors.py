"""Actual source-tree anchors and lossless character scopes (Unicode code points).

Runs on the new publication copy only. Original blocks and pre-existing IDs are
immutable. Explicit sequential submarkers add children, never fabricated targets.
"""
import hashlib
import json
import re
from collections import defaultdict
from lawrag.core.legal_coordinate import MOK_LETTERS

LETTERS = MOK_LETTERS
FAMILY_ROLES = {'circled':'항', 'kr_항':'항', 'dot_number:1':'호', 'kr_호':'호',
                'hangul_dot':'목', 'kr_목':'목', 'detail_number':'세목',
                'detail_paren':'세세목', 'detail_hangul_paren':'세세세목'}


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def span(block, start=0, end=None):
    text=block['text'];end=len(text) if end is None else end
    return {'block_id':str(block['block_id']),'start_cp':start,'end_cp':end,
            'block_hash':hashlib.sha256(text.encode()).hexdigest(),
            'span_hash':hashlib.sha256(text[start:end].encode()).hexdigest()}


def normalize(spans):
    out=[]
    for p in sorted(spans,key=lambda p:(str(p['block_id']),p['start_cp'],p['end_cp'])):
        if out and out[-1]['block_id']==p['block_id'] and p['start_cp']<=out[-1]['end_cp']:
            out[-1]['end_cp']=max(out[-1]['end_cp'],p['end_cp']);out[-1].pop('span_hash',None)
        else:out.append(dict(p))
    return out


def refine_document(units, blocks, document):
    """Return tree with explicit roles/own/subtree spans; preserve all original IDs."""
    byid={str(u['id']):dict(u) for u in units}; owned=defaultdict(list)
    blockmap={str(b['block_id']):b for b in blocks}
    for b in blocks:
        if b.get('unit_id') is not None:owned[str(b['unit_id'])].append(span(b))
    for uid,u in byid.items():
        u['id']=uid;u['parent']=str(u['parent']) if u.get('parent') is not None else None
        u['role']=u.get('role') or FAMILY_ROLES.get(u.get('family'))
        if u.get('ordinal') is None:
            label=(u.get('surface') or '').strip()
            pattern=(r'(['+LETTERS+r'])\.' if u['role']=='목' else
                     r'\((['+LETTERS+r'])\)' if u['role']=='세세세목' else None)
            match=re.fullmatch(pattern,label) if pattern else None
            if match:u['ordinal']=[LETTERS.index(match[1])+1]
        u['own_spans']=u.get('own_spans',owned[uid]);u['scope_contract']='structure-scope-v2'
    patterns=[('목','hangul_dot',re.compile(r'(?<!\S)(['+LETTERS+r'])\.\s+')),
              ('세목','detail_number',re.compile(r'(?<!\S)(\d+)\)\s*')),
              ('세세목','detail_paren',re.compile(r'(?<!\S)\((\d+)\)\s*')),
              ('세세세목','detail_hangul_paren',re.compile(r'(?<!\S)\((['+LETTERS+r'])\)\s*'))]
    child_ids=defaultdict(list)
    for uid,u in byid.items():child_ids[u.get('parent')].append(uid)
    order=['항','호','목','세목','세세목','세세세목']
    def split(uid):
        u=byid[uid];role=u.get('role')
        if role not in order or role=='항':return
        children=[byid[x] for x in child_ids[uid]]
        for child_role,family,pattern in patterns:
            if order.index(child_role)<=order.index(role):continue
            if any(x.get('role')==child_role for x in children):continue
            hits=[]
            for pos,p in enumerate(u['own_spans']):
                text=blockmap[p['block_id']]['text']
                for m in pattern.finditer(text,p['start_cp'],p['end_cp']):
                    n=LETTERS.index(m[1])+1 if m[1] in LETTERS else int(m[1])
                    hits.append((pos,m.start(),m.end(),n,m[0].strip()))
            # A solitary inline number can be a citation. Require an ordered list,
            # or one line-start marker, and never repair conflicting sequences.
            if not hits or [h[3] for h in hits]!=list(range(1,len(hits)+1)):continue
            if len(hits)<2:continue
            old=list(u['own_spans']);prefix=[]
            first=hits[0]
            for i,p in enumerate(old):
                if i<first[0]:prefix.append(p)
                elif i==first[0] and p['start_cp']<first[1]:prefix.append(span(blockmap[p['block_id']],p['start_cp'],first[1]))
            for index,h in enumerate(hits):
                nxt=hits[index+1] if index+1<len(hits) else (len(old),0,0,0,'')
                scopes=[]
                for i in range(h[0],min(nxt[0]+1,len(old))):
                    p=old[i];start=h[1] if i==h[0] else p['start_cp'];end=nxt[1] if i==nxt[0] else p['end_cp']
                    if start<end:scopes.append(span(blockmap[p['block_id']],start,end))
                child='scope:'+digest([uid,family,h[3],scopes])[:24]
                child_ids[uid].append(child)
                byid[child]={'id':child,'parent':uid,'level':u.get('level',0)+1,'family':family,
                    'role':child_role,'ordinal':[h[3]],'surface':h[4],'title':'','block':scopes[0]['block_id'],
                    'span':u.get('span'),'page':u.get('page'),'own_spans':scopes,
                    'scope_contract':'structure-scope-v2','reason':'verified sequential original-text submarkers',
                    'coordinate_scope':u.get('coordinate_scope','body'),'scope_origin':{'parent':uid,'marker':h[4]}}
            u['own_spans']=prefix
            for child in child_ids[uid]:split(child)
            break
    for uid in list(byid):split(uid)
    children=defaultdict(list)
    for uid,u in byid.items():children[u.get('parent')].append(uid)
    visiting=set();done=set()
    def finish(uid):
        if uid in visiting:raise ValueError('structure anchor cycle')
        if uid in done:return byid[uid]['subtree_spans']
        visiting.add(uid);u=byid[uid];allsp=list(u['own_spans'])
        for child in children[uid]:allsp.extend(finish(child))
        u['subtree_spans']=normalize(allsp);u['n_children']=len(children[uid]);visiting.remove(uid);done.add(uid)
        return u['subtree_spans']
    for uid in byid:finish(uid)
    return list(byid.values())


def refine_store(db):
    """Upgrade only the mutable publication copy; original block text/hash stays intact."""
    stats={'documents':0,'added_units':0,'backfilled_ordinals':0,'version':'structure-scope-v2'}
    for did,raw in db.execute('SELECT document_id,json FROM document').fetchall():
        doc=json.loads(raw);rows=db.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?',(did,)).fetchall()
        units=[dict(json.loads(j),id=uid,parent=parent) for uid,parent,j in rows]
        blocks=[{'block_id':b,'unit_id':u,'text':t} for b,u,t in db.execute('SELECT block_id,unit_id,text FROM source_block WHERE document_id=? ORDER BY CAST(block_id AS INTEGER)',(did,))]
        result=refine_document(units,blocks,doc)
        prior={str(u['id']):u for u in units}
        stats['backfilled_ordinals']+=sum(1 for u in result if u['id'] in prior and
            prior[u['id']].get('ordinal') is None and u.get('ordinal') is not None)
        for u in result:
            db.execute('INSERT OR REPLACE INTO source_unit VALUES (?,?,?,?)',(did,u['id'],u.get('parent'),json.dumps(u,ensure_ascii=False)))
        doc['nodes']=result
        doc['anchor_structure']={'schema_version':'structure-scope-v2','tree_sha256':digest(result),
            'ladder_sha256':digest(doc.get('ladder')),'applied_sha256':digest(doc.get('applied')),
            'added_unit_ids':[u['id'] for u in result if u['id'].startswith('scope:')]}
        # The original rendering tree is retained as provenance; consumers use source_unit.
        db.execute('UPDATE document SET json=? WHERE document_id=?',(json.dumps(doc,ensure_ascii=False),did))
        stats['documents']+=1;stats['added_units']+=len(result)-len(units)
    return stats
