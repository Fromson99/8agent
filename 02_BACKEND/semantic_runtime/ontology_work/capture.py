"""Explicit export of accepted agent judgments and already verified own-body reads.

Called by an operator/export job with the existing investigation object. No model,
new read, approval, S3 access or publication occurs in the serving process.
"""
from copy import deepcopy
from ..contracts import digest
from ..legal_agent import read_judgment,unit_reading,ontology_io,ontology_compiler,ontology_context,evidence_inventory
from ..legal_agent.errors import ContractError
from .schema import VERSION,validate_input

def capture(inv,concept):
    sources={};source_ids={}
    for gid,record in inv.p['selected'].items():
        source=inv.s.tools.sources[record['source_id']];did=record['document_id']
        if did not in inv.s.scope:continue
        ids=set(map(str,record['offer']['block_ids']))
        units=[]
        ordered=sorted(ids)
        for start in range(0,len(ordered),100):
            part=ordered[start:start+100]
            units.extend(inv.s.store.db.execute('SELECT block_id,unit_id FROM source_block WHERE document_id=? AND block_id IN ('+','.join('?' for _ in part)+')',(did,*part)).fetchall())
        for uid in {str(u) for b,u in units if str(b) in ids and u is not None}:
            own=unit_reading.blocks(inv.s,did,uid,'exact')
            if not set(own)<=ids:continue
            evidence=[e for e in record['evidence'] if all(str(p['block_id']) in set(own) for p in e['spans'])]
            if not evidence:continue
            for e in evidence:inv.s.source.verify(e)
            spans=[p for e in evidence for p in e['spans']]
            if not evidence_inventory.covers(evidence_inventory.expected(inv.s,did,own),spans):continue
            text=unit_reading.reassemble(evidence)
            anchor={'document_id':did,'version':source['source_artifact_sha256'],'unit_id':uid,
                'content_sha256':ontology_compiler.content_hash(text),'label':str(inv.s.matcher.units[(did,uid)].get('title') or uid)}
            if ontology_context.resolve(inv.s,anchor)[1]:continue
            key='P'+ontology_compiler.anchor_key(anchor)[:24]
            sources[key]={'id':key,'anchor':anchor,'text':text};source_ids.setdefault(record['source_id'],[]).append(key)
    judgments=[]
    for state in inv.p.get('read_judgments',{}).values():
        read_judgment.checked(state)
        for head in state['heads'].values():
            ids=list(dict.fromkeys(source_ids.get(head['source_id'],[])))
            if ids and head['operation']!='WITHDRAW':
                judgments.append({'id':head['id'],'source_ids':ids,'judgment':deepcopy(head),
                    'origin':{'request_key':state['request_key'],'state_hash':state['state_hash'],'revision':head['version']}})
    return validate_input({'version':VERSION,'concept':concept,'originals':list(sources.values()),'judgments':judgments,
        'origin':{'run_id':inv.p['binding'],'request_key':digest([inv.p['binding'],inv.question])}})


def record_if_enabled(inv):
    import os
    if os.environ.get('GENOS_ONTOLOGY_CAPTURE_ENABLED','off').lower() not in ('on','true','1'):return
    if not any(state.get('heads') for state in inv.p.get('read_judgments',{}).values()):return
    try:
        work=capture(inv,'원문 기반 검토 시나리오')
        if not work['judgments']:return
        key=digest(work)
        emitted=inv.p.setdefault('ontology_work_inputs',[])
        if key in emitted:return
        inv.s.repo.event('ONTOLOGY_WORK_INPUT',{'input_hash':key,'input':work,
            'authority':'CANDIDATE_INPUT_ONLY','automatic_approval':False})
        emitted.append(key);inv.save()
    except Exception as exc:
        inv.s.repo.event('ONTOLOGY_WORK_CAPTURE_UNAVAILABLE',{'error_type':type(exc).__name__,
            'fallback':'existing-agent-judgment-log','retry':False})
