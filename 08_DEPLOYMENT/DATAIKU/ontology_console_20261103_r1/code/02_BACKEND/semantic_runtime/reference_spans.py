"""Shared half-open Unicode source scopes for traversal, reading and loss review."""
import hashlib

def canonical(source, spans=None, blocks=None):
    texts={str(b['block_id']):b['text'] for b in source['blocks']}
    if spans is None:
        spans=[{'block_id':b,'start_cp':0,'end_cp':len(texts[b])} for b in (list(texts) if blocks is None else map(str,blocks))]
    out=[]
    for p in spans:
        bid=str(p['block_id']);text=texts.get(bid);a=p.get('start_cp');z=p.get('end_cp')
        if text is None or type(a) is not int or type(z) is not int or not 0<=a<z<=len(text):raise ValueError('invalid source character extent')
        h=hashlib.sha256(text.encode()).hexdigest()
        if p.get('block_hash') and p['block_hash']!=h:raise ValueError('scope block hash mismatch')
        sh=hashlib.sha256(text[a:z].encode()).hexdigest()
        if p.get('span_hash') and p['span_hash']!=sh:raise ValueError('scope span hash mismatch')
        out.append({'block_id':bid,'start_cp':a,'end_cp':z,'block_hash':h})
    merged=[]
    for p in sorted(out,key=lambda x:(x['block_id'],x['start_cp'],x['end_cp'])):
        if merged and merged[-1]['block_id']==p['block_id'] and p['start_cp']<=merged[-1]['end_cp']:merged[-1]['end_cp']=max(merged[-1]['end_cp'],p['end_cp'])
        else:merged.append(p)
    return merged

def contains(outer,inner):
    return all(any(a['block_id']==b['block_id'] and a['start_cp']<=b['start_cp'] and b['end_cp']<=a['end_cp'] for a in outer) for b in inner)

def overlaps(a,b):
    return any(x['block_id']==y['block_id'] and x['start_cp']<y['end_cp'] and y['start_cp']<x['end_cp'] for x in a for y in b)
