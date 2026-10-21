from pathlib import Path
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0893/references/snapshot/02_BACKEND/semantic_runtime/legal_agent';P=R/'02_BACKEND/lawrag/research/candidates/adr_0892/verified/revisions/rev-001/snapshot/02_BACKEND/semantic_runtime/legal_agent'
p=C/'unit_relations.py';s=(P/'unit_relations.py').read_text();s=s.replace('import time\n','import time\nfrom jsonschema import ValidationError\n',1)
marker='def catalog(s, anchors, selected, handled, *, after_by_anchor=None):'
helper='''def delivered_blocks(session, spans_by_source):
    """Exact current-authorized delivery across windows, never model adoption."""
    from .evidence_inventory import covers, expected
    result={};raw_cache={}
    for sid,spans in spans_by_source.items():
        source=session.tools.sources.get(sid)
        if not source or source['document_id'] not in session.scope:
            raise ContractError('delivered reference source outside current scope')
        did=source['document_id'];allowed={str(b['block_id']) for b in source['blocks']};blocks=set()
        for span in spans:
            bid=str(span['block_id'])
            if bid not in allowed:raise ContractError('delivered reference block outside source')
            key=(did,bid)
            if key not in raw_cache:raw_cache[key]=session.store.source(did,bid)['text']
            text=raw_cache[key];lo=span['start_cp'];hi=span['end_cp']
            if (type(lo) is not int or type(hi) is not int or not 0<=lo<=hi<=len(text)
                    or span.get('text')!=text[lo:hi]
                    or 'block_hash' in span and span['block_hash']!=text_hash(text)
                    or 'span_hash' in span and span['span_hash']!=text_hash(text[lo:hi])):
                raise ContractError('delivered reference original span changed')
            blocks.add(bid)
        result[sid]={bid for bid in blocks if covers(expected(session,did,[bid]),spans)}
    return result


def bounded_reference_completion(session):
    from . import completion_contracts as cc
    p=session.profile.get('candidate_navigation',{})
    return bool(p.get('completion_contract') and p.get('completion_policy_version') in (cc.V5,cc.V6,cc.V7,cc.V8))


'''
assert marker in s;s=s.replace(marker,helper+marker,1)
old="""        evidence_blocks = {sid:{bid for bid in blocks if covers(
            expected(s,s.tools.sources[sid]['document_id'],[bid]),evidence_spans.get(sid,[]))}
            for sid,blocks in evidence_blocks.items()}"""
assert old in s;s=s.replace(old,"        evidence_blocks = delivered_blocks(s,evidence_spans)",1)
old="""    def covered(g):
        known=blocks_read().get(g['target']['source_id'],set())"""
new="""    def covered(g):
        known=blocks_read().get(g['target']['source_id'],set())
        if session.profile.get('candidate_navigation',{}).get('investigation_control') and hasattr(session,'investigation_delivered_spans'):
            known=known | delivered_blocks(session,session.investigation_delivered_spans).get(g['target']['source_id'],set())"""
assert old in s;s=s.replace(old,new,1)
old="""        decision=output.bounded_decision(session.repo,'reference-navigation',data,schema(offered),
            invoke_decision,lambda value:validate(value,offered),
            identity={'binding':binding,'menu':{k:v for k,v in data.items() if k!='round'}},
            can_repair=lambda:seconds_left()>1)"""
new="""        menu_key=digest({'binding':binding,'groups':sorted(group_signature(question,g) for g in offered.values())})
        blocked=state.get('unresolved_decision_menus',{}).get(menu_key)
        if blocked:
            payload={k:blocked.get(k) for k in ('failure','groups')}
            if blocked.get('hash')!=digest(payload):raise ContractError('unresolved reference decision changed')
            limits.append({'kind':'reference_decision_unresolved','menu_key':menu_key,'failure':blocked['failure'],'reused':True})
            batches.append({'round':round_number,'phase':phase,'data':data,'decision':None,'model_called':False,'unresolved':True})
            save();break
        try:
            decision=output.bounded_decision(session.repo,'reference-navigation',data,schema(offered),
                invoke_decision,lambda value:validate(value,offered),
                identity={'binding':binding,'menu':{k:v for k,v in data.items() if k!='round'}},
                can_repair=lambda:seconds_left()>1)
        except (ProposalError,ValidationError) as error:
            if not bounded_reference_completion(session):raise
            failure={'failure':output.diagnostics(error),'groups':sorted(group_signature(question,g) for g in offered.values())}
            state.setdefault('unresolved_decision_menus',{})[menu_key]={**failure,'hash':digest(failure)}
            limits.append({'kind':'reference_decision_unresolved','menu_key':menu_key,'failure':failure['failure'],'reused':False})
            batches.append({'round':round_number,'phase':phase,'data':data,'decision':None,'model_called':True,'unresolved':True})
            session.repo.event('REFERENCE_DECISION_UNRESOLVED',{'menu_key':menu_key,**failure,'adopted':False,'counter_reset':False})
            # Keep the exact original queue and reads. The investigation owner
            # may select another route or answer from confirmed originals.
            save();break"""
assert old in s;s=s.replace(old,new,1);p.write_text(s)
print('Cross-window verified delivery and durable bounded unresolved reference handoff')
