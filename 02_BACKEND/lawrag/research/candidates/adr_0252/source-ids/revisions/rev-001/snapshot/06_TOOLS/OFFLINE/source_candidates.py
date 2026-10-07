"""Surface candidates only. Exact source spans are code-owned; legal meaning is unreviewed."""
import hashlib,json,re,importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('definition_patterns',Path(__file__).with_name('definition_patterns.py'))
patterns=importlib.util.module_from_spec(spec);spec.loader.exec_module(patterns)

def catalogue(source):
    spans={};candidates=[];blocks=[]
    def add(block,start,end,kind):
        lo=block['source_start'];quote=block['text'][start:end]
        bid=str(block['idx']);units=[u for u in source['structural_units'] if u['span'][0]<=int(bid)<u['span'][1]]
        if not units:raise ValueError('No structural unit for source block '+bid)
        unit=next((u for u in units if str(u['id'])==str(block.get('node'))),min(units,key=lambda u:u['span'][1]-u['span'][0]))
        key=json.dumps([source['document_version_id'],source['source_artifact_sha256'],bid,lo+start,lo+end],ensure_ascii=False)
        sid='span:'+hashlib.sha256(key.encode()).hexdigest()[:24]
        spans[sid]={'source_span_id':sid,'document_version_id':source['document_version_id'],'structural_unit_id':str(unit['id']),
                    'block_id':bid,'start':lo+start,'end':lo+end,'quote':quote}
        return sid
    for b in source['blocks']:
        text=b['text'];whole=add(b,0,len(text),'BLOCK');blocks.append(whole)
        for pattern,kind in [(patterns.RE_QUOTED,'QUOTED_DEFINITION'),(patterns.RE_BARE,'BARE_DEFINITION'),(patterns.RE_YIHA,'DECLARED_ALIAS')]:
            for match in pattern.finditer(text):
                group=3 if kind=='DECLARED_ALIAS' else 1
                term=match.group(group)
                if kind=='DECLARED_ALIAS' and term.startswith(patterns._DEICTIC):continue
                sid=add(b,*match.span(group),'TERM')
                candidates.append({'kind':kind,'term':term,'term_span_id':sid,'context_span_id':whole,
                                   'status':'UNREVIEWED','scope':'UNRESOLVED',
                                   'canonical_surface':(match.group(1) or match.group(2)) if kind=='DECLARED_ALIAS' else None})
        for kind,pattern in [('SCOPE_MARKER',r'이\s*(?:법|규정|편|장|절|조|항)에서'),('PROVISO_MARKER',r'다만[,，]?'),
                             ('REFERENCE_MARKER',r'제\s*\d+조(?:의\d+)?(?:제\d+항)?(?:제\d+호)?'),
                             ('QUANTITY_MARKER',r'(?:100분의\s*)?\d+(?:\.\d+)?\s*(?:퍼센트|%|일|개월|년|원|이상|이하)')]:
            for match in re.finditer(pattern,text):
                candidates.append({'kind':kind,'surface':match.group(),'source_span_id':add(b,*match.span(),kind),
                                   'context_span_id':whole,'status':'UNREVIEWED'})
    return {'status':'SURFACE_CANDIDATES_ONLY','spans':list(spans.values()),'coverage_span_ids':blocks,'candidates':candidates}

def bind(source,result):
    """Expand selected IDs to exact spans; no fuzzy matching and no model coordinates."""
    import copy
    result=copy.deepcopy(result);cat=catalogue(source);spans={s['source_span_id']:s for s in cat['spans']}
    def get(sid):
        if sid not in spans:raise ValueError('Unknown source_span_id: '+str(sid))
        return spans[sid]
    for e in result['graph']['evidence']:
        if set(e)!={'id','source_span_id'}:raise ValueError('Evidence must select a code-owned source_span_id only')
        selected=get(e.pop('source_span_id'));e.update({k:v for k,v in selected.items() if k!='source_span_id'})
    for entry in result['coverage']:
        sid=entry.pop('source_span_id')
        if sid not in cat['coverage_span_ids']:raise ValueError('Coverage must select a full block slice')
        entry.update({k:get(sid)[k] for k in ('block_id','start','end')})
    return result
