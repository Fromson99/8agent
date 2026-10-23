"""Compact host observations; exact original/provider bytes stay in native logs."""
import json, functools, time

def install(out):
    from semantic_runtime.legal_agent import connection_scope as cs, unit_relations as rel
    path=out/'scope-trace.jsonl'; sequence=0
    def write(kind, value):
        nonlocal sequence
        sequence+=1
        with path.open('a') as stream:
            stream.write(json.dumps({'seq':sequence,'time':time.time(),'kind':kind,'data':value},ensure_ascii=False)+'\n')
    def members(scope):
        return [{'source_id':m['source_id'],'document_id':m.get('document_id'),'parent_body_block_ids':m.get('parent_body_block_ids',[]),'missing_parent_body_block_ids':m.get('missing_parent_body_block_ids',[]),
            'spans':[{k:p[k] for k in ('block_id','start_cp','end_cp','span_hash') if k in p} for p in m['spans']]}
            for m in scope.get('members',[])]
    original_accept=cs.accept
    @functools.wraps(original_accept)
    def accept(inv, scope, data, reason, **kw):
        result=original_accept(inv,scope,data,reason,**kw)
        write('scope_selected',{'id':scope['id'],'label':scope['label'],'structural_selection':scope['structural_selection'],
            'members':members(scope),'reason':reason,'replay':kw.get('replay',False)})
        return result
    cs.accept=accept
    original_catalog=rel.catalog
    @functools.wraps(original_catalog)
    def catalog(session, anchors, *args, **kw):
        result=original_catalog(session,anchors,*args,**kw)
        scoped=getattr(session,'connection_scope_spans',None)
        write('catalog',{'anchors':anchors,'scope':members({'members':[{'source_id':sid,'spans':spans} for sid,spans in scoped.items()]}) if scoped is not None else None,
            'groups':[{'anchor':g['anchor'],'target':g['target'],'direction':g['direction'],
                'connections':[{k:c.get(k) for k in ('reference_id','witness_document_id','witness_block_id','witness_sha256','endpoint_block_ids','anchor_head_block_ids','already_read')} for c in g['connections']]}
                for g in result[0]],'statuses':result[1],'limits':result[2]})
        return result
    rel.catalog=catalog
