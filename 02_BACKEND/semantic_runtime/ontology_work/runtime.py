"""Load published source bundles on explicit original arrival, once per request.

The request owns immutable publication copies. Later publications are visible to
new requests; a reader never recompiles or replaces an already bound bundle.
"""
from copy import deepcopy
from ..contracts import digest
from ..legal_agent import ontology_compiler as compiler
from ..legal_agent.errors import ContractError
from .configuration import repository
MAX_BUNDLES=8


class PublicationChanged(ContractError):
    """A known authority change requires reassessment, never a transport retry."""


def workspace_references(state):
    # The historical field name remains wire compatible. Domain accumulation
    # publications have the same live SQL authority as workspace publications.
    return [{'bundle_id': bid, 'publication_id': row['publication_id'],
             'package_sha256': digest(row['context'])}
            for bid, row in sorted(state.get('ontology_database', {}).get('contexts', {}).items())]


def recheck(session, state):
    refs=workspace_references(state)
    if not refs:return []
    try:
        provider=getattr(session,'ontology_repository',None) or repository()
        current=provider.current_publications(refs,set(session.scope))
    except Exception as exc:
        current={};reason='PUBLICATION_CHECK_UNAVAILABLE:'+type(exc).__name__
    else:reason='PUBLICATION_WITHDRAWN_OR_ACCESS_CHANGED'
    unavailable=[]
    for ref in refs:
        if current.get(ref['publication_id']) is not True:
            unavailable.append(ref['bundle_id'])
            state.setdefault('workspace_publication_checks',{})[ref['bundle_id']]={'status':'WITHHELD','reason':reason}
            for plan in state.get('ontology_context',{}).get('plans',{}).values():
                if plan['bundle_id']==ref['bundle_id']:
                    plan['status']='NEEDS_REVIEW'
                    plan['workspace_withheld_reason']=reason
    return unavailable


def assessment_references(state, cards):
    used={c.get('payload',{}).get('assembly_catalog',{}).get('bundle_id') for c in cards}
    # Some v1 catalogs expose package hash rather than bundle ID.
    used.update(c.get('payload',{}).get('bundle_id') for c in cards if c.get('payload',{}).get('assembly_catalog'))
    used.update(c.get('bundle_id') for c in cards if c.get('payload',{}).get('assembly_catalog'))
    plans={p['id']:p['bundle_id'] for p in state.get('ontology_context',{}).get('plans',{}).values()}
    used.update(plans.get(c.get('plan_id')) for c in cards if c.get('payload',{}).get('assembly_catalog'))
    return [ref for ref in workspace_references(state) if ref['bundle_id'] in used]


def assert_assessment(assessment, allowed_documents, provider=None):
    refs=assessment.get('assessment_basis',{}).get('workspace_publications',[])
    if not refs:return
    try:
        current=(provider or repository()).current_publications(refs,set(allowed_documents))
    except Exception as exc:
        raise ContractError('WORKSPACE_PUBLICATION_CHECK_UNAVAILABLE: candidate answer not confirmed') from exc
    if any(current.get(ref['publication_id']) is not True for ref in refs):
        raise PublicationChanged('WORKSPACE_PUBLICATION_REVOKED: preserve originals; reassess before publishing')

def config(policy,state,binding):
    from ..legal_agent.ontology_context import configuration
    db=state.get('ontology_database',{})
    contexts=db.get('contexts',{})
    bundles=[];packages={};assemblies={}
    for bid,row in sorted(contexts.items()):
        configuration(row['context'])
        b=row['context']['snapshot']['bundles'][0]
        if b['bundle_id']!=bid:raise ContractError('ontology database checkpoint identity')
        bundles.append(deepcopy(b))
        if 'scenario_package' in row['context']:packages[bid]=deepcopy(row['context']['scenario_package'])
        if 'assembly_package' in row['context']:assemblies[bid]=deepcopy(row['context']['assembly_package'])
    return {'mode':'A1','snapshot':{'schema_version':'ontology-snapshot-v0','bundles':bundles},
        'snapshot_sha256':digest(['ontology-db-request-v1',binding]),'scenario_packages':packages,'assembly_packages':assemblies}

def acquire(inv,primary,primary_records):
    from ..legal_agent import ontology_context as oc
    state=inv.p.setdefault('ontology_database',{'version':'ontology-db-request-v1','contexts':{},'lookups':{}})
    records=inv.p['selected'] if primary_records is None else primary_records
    anchors={}
    for gid in primary:
        record=records.get(gid)
        if not record:continue
        source=inv.s.tools.sources[record['source_id']];did=record['document_id']
        if did not in inv.s.scope:continue
        ids=list(dict.fromkeys(map(str,record['offer']['block_ids'])))
        units=[]
        for offset in range(0,len(ids),100):
            page=ids[offset:offset+100]
            units.extend(inv.s.store.db.execute('SELECT DISTINCT unit_id FROM source_block WHERE document_id=? AND block_id IN ('+','.join('?' for _ in page)+')',(did,*page)).fetchall())
        for (uid,) in units:
            uid=str(uid)
            if (did,uid) not in inv.s.matcher.units:continue
            a={'document_id':did,'version':source['source_artifact_sha256'],'unit_id':uid}
            anchors[compiler.anchor_key(a)]=a
    for key,anchor in sorted(anchors.items()):
        if key in state['lookups']:continue
        state['lookups'][key]={'status':'STARTED','anchor':anchor};inv.save()
        try:
            provider=getattr(inv.s,'ontology_repository',None) or repository()
            rows=provider.lookup(anchor,set(inv.s.scope))
            # Preflight the whole batch; never partially mutate the frozen map.
            staged=deepcopy(state['contexts'])
            for row in rows:
                bid=row['context']['snapshot']['bundles'][0]['bundle_id']
                if bid not in staged:staged[bid]=row
            if len(staged)>MAX_BUNDLES:raise ContractError('ontology request bundle limit')
            compiler._bounded_json(staged)
            state['contexts']=staged;state['lookups'][key]['status']='FOUND' if rows else 'EMPTY'
        except Exception as exc:
            # Read-only optional acceleration. A failed lookup is an explicit,
            # persisted ordinary-search fallback, not proof no ontology exists.
            state['lookups'][key].update(status='UNAVAILABLE',error_type=type(exc).__name__)
            inv.s.repo.event('ONTOLOGY_DATABASE_UNAVAILABLE',{'anchor':anchor,'error_type':type(exc).__name__,'retry':False,'fallback':'ordinary-rag'})
        inv.save()
    recheck(inv.s,inv.p)
    return config(inv.policy,inv.p,inv.p['binding'])
