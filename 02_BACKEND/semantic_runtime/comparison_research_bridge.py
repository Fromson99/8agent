"""Server-owned locators and cross-side search hints for native research tasks."""
from copy import deepcopy
import json
from .contracts import digest
from .legal_agent.errors import ContractError
from .legal_agent.repository import text_hash
from .term_references import reference_targets


def locators(port,evidence,leads=None):
    s=port.session;out={}
    def add(did,uid,sid,origin=None,reference=None):
        if did not in port.all_scope:return
        uid=str(uid) if uid is not None else None
        if uid is not None and ((did,uid) not in s.matcher.units or sid not in s.matcher._unit_sources(did,uid)):raise ContractError('research locator source/unit mismatch')
        value={'side':port.categories[did],'document_id':did,'unit_id':uid,'source_id':sid,
               'document_name':s.matcher.documents[did],'coordinate':s.matcher.units.get((did,uid),{}).get('surface',''),
               'origin_evidence_id':origin,'reference_id':reference}
        out['L'+digest(value)[:24]]=value
    for e in evidence:
        s.verify(e)
        # Exact owning units, not every span in the same source/article/annex.
        for span in e['spans']:
            raw=s.store.source(e['document_id'],str(span['block_id']))
            uid=raw.get('unit_id') or e['unit_id']
            add(e['document_id'],uid,e['source_id'],e['evidence_id'])
        for raw, in s.tools.db.execute('SELECT r.json FROM reference r JOIN reference_end x ON x.reference_id=r.id WHERE x.source_id=? ORDER BY r.id',(e['source_id'],)):
            ref=json.loads(raw)
            if ref['source_id']!=e['source_id']:continue
            from .legal_agent.declared_names import upgrade_reference
            # `규정 제32조` after `…상장규정(이하 "규정")` in another article of the same document.
            ref=upgrade_reference(s,ref) or ref
            # A reference must be witnessed inside the actually delivered spans.
            witness=ref.get('source_text')
            if not witness or not any(witness in p['text'] for p in e['spans']):continue
            original=s.store.source(ref['document_id'],str(ref['block_id']))['text']
            if witness not in original or ref.get('source_text_sha256')!=text_hash(witness):raise ContractError('research reference witness changed')
            if not str(ref.get('resolution','')).startswith('EXACT_'):continue
            for target in reference_targets(ref):
                src=s.tools.sources.get(target.get('source_id'))
                if src:add(src['document_id'],target.get('unit_id') or src['unit_id'],target['source_id'],e['evidence_id'],ref['id'])
    from .legal_agent.investigation_leads import lead_locator
    for lead in (leads or {}).get('items',[]):
        value=lead_locator(port,lead)
        out['L'+digest(value)[:24]]=value
    return out


def investigation_leads(port,results):
    from .legal_agent.investigation_leads import parent_catalogue
    return parent_catalogue(port,list(reversed(results)))


def compile_task(port,issue,field,proposal,offered,evidence):
    by={e['evidence_id']:e for e in evidence};anchors=[]
    for ident in proposal['anchor_ids']:
        e=by[ident];port.session.verify(e)
        anchors.append({'origin_side':port.categories[e['document_id']],'evidence_id':ident,
            'generation_id':e['generation_id'],'source_id':e['source_id'],'document_id':e['document_id'],
            'source_artifact_hash':e['source_artifact_hash'],'spans_hash':digest(e['spans']),
            'role':'SEARCH_HINT_ONLY','text':e['text']})
    locator=deepcopy(offered[proposal['locator_id']]) if proposal['locator_id'] else None
    return {'schema_version':'comparison-research-v1','task_id':'unassigned','issue_id':issue,
        'target_side':proposal['side'],'requested_fields':[field],'missing_target':proposal['query'],
        'anchor_refs':anchors,'target_locator':locator,'operation':proposal['operation'],
        'allowed_operations':[proposal['operation']],
        'completion_conditions':['Read target originals and applicable conditions/exceptions','Do not substitute opposite-side content for own-side evidence'],
        'binding_hash':port.session.context.binding_hash}


def validate_parent(port,task,side):
    from .legal_agent.comparison_research import validate_task
    validate_task(task);port.verify_all()
    if task['binding_hash']!=port.session.context.binding_hash or task['target_side']!=side:raise ContractError('research parent binding or side changed')
    known=[]
    for anchor in task['anchor_refs']:
        e=port.session.repo.evidence(anchor['evidence_id'])
        if not e:raise ContractError('unknown research anchor')
        port.session.verify(e)
        if (anchor['origin_side']!=port.categories[e['document_id']] or anchor['spans_hash']!=digest(e['spans']) or
            anchor['source_artifact_hash']!=e['source_artifact_hash'] or anchor['generation_id']!=e['generation_id'] or
            anchor['document_id']!=e['document_id'] or anchor['source_id']!=e['source_id'] or anchor['text']!='\n'.join(p['text'] for p in e['spans'])):
            raise ContractError('research anchor provenance changed')
        known.append(e)
    locator=task['target_locator']
    if locator:
        if task['operation']=='follow_reference' and not locator.get('reference_id'):raise ContractError('reference operation lacks a witnessed reference')
        if locator['side']!=side or locator['document_id'] not in port.all_scope:raise ContractError('research target outside side/ACL')
        origin=locator.get('origin_evidence_id')
        if origin and not any(e['evidence_id']==origin for e in known):
            e=port.session.repo.evidence(origin)
            if e is None:raise ContractError('locator witness missing')
            known.append(e)
        if locator.get('lead_ref'):
            from .legal_agent.investigation_leads import validate_locator
            validate_locator(port,locator)
        elif locator not in locators(port,known).values():raise ContractError('research target is not a current verified locator')


def document_names(session,did):
    """Only names registered in the selected catalogue; no generated aliases."""
    raw=json.loads(session.store.db.execute('SELECT json FROM document WHERE document_id=?',(did,)).fetchone()[0])
    meta=raw.get('document_metadata') or {}
    names=[session.matcher.documents[did],meta.get('document_title'),meta.get('official_abbreviation')]
    names+=meta.get('aliases',[]) if isinstance(meta.get('aliases',[]),list) else []
    return [n for n in names if isinstance(n,str) and n.strip()]


def preferred_documents(port,question,side):
    """Documents of ``side`` whose registered name occurs in the text.

    An occurrence lying inside a longer registered name of another document (a law
    inside its enforcement decree) does not select the shorter one.
    """
    from .folder_navigation import normalized
    q=normalized(question);found=[]
    for d in port.all_scope:
        for n in document_names(port.session,d):
            name=normalized(n)
            if len(name)<2:continue
            start=q.find(name)
            while start>=0:
                found.append((start,start+len(name),d));start=q.find(name,start+1)
    kept={d for a,z,d in found if not any(a2<=a and z<=z2 and z2-a2>z-a and d2!=d for a2,z2,d2 in found)}
    return sorted(d for d in kept if port.categories[d]==side)


def lead_view(value):
    from .legal_agent.investigation_leads import parent_projection
    return parent_projection(value)
