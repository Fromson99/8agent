"""Bound investigation locations, separate from acquired/citable originals."""
from copy import deepcopy
import json
from ..contracts import digest
from .errors import ContractError

VERSION = 'investigation-leads-v1'
MAX_LEADS = 128
VIEW_LEADS = 24
VIEW_CHARS = 10000


def target(session, identity, scope):
    did, sid = identity['document_id'], identity['source_id']
    if did not in scope:
        raise ContractError('investigation lead outside request scope')
    source = session.tools.sources[sid]
    uid = str(identity['unit_id'])
    if source['document_id'] != did or sid not in session.matcher._unit_sources(did, uid):
        raise ContractError('investigation lead source/unit mismatch')
    return {'document_id':did, 'source_id':sid, 'unit_id':uid,
            'document_name':source['document_name'], 'heading':source.get('heading',''),
            'source_artifact_sha256':source['source_artifact_sha256']}


def capture(inv, data):
    binding = digest([VERSION, inv.p['binding'], sorted(inv.s.scope),
                      inv.s.context.query['generation_id'], inv.idx.manifest['index_sha256']])
    saved = inv.p.setdefault('investigation_leads', {'version':VERSION, 'binding':binding,
                            'items':{}, 'omitted_keys':[], 'catalogues':[]})
    if saved['version'] != VERSION or saved['binding'] != binding:
        raise ContractError('investigation lead binding changed')

    def add(identity, origin, preview):
        t = target(inv.s, identity, inv.s.scope)
        key = 'L'+digest([binding, t])[:24]
        if key not in saved['items']:
            if len(saved['items']) >= MAX_LEADS:
                # Count distinct omitted identities without retaining bodies.
                if key not in saved['omitted_keys'] and len(saved['omitted_keys']) < MAX_LEADS:
                    saved['omitted_keys'].append(key)
                return
            saved['items'][key] = {'lead_id':key, 'target':t, 'origins':[],
                'preview':preview[:240], 'citation_eligible':False}
        row = saved['items'][key]
        if origin not in row['origins']:
            row['origins'].append(origin)

    for card in data.get('references',{}).get('dependency_cards',[]):
        if not card.get('read_action') and not card.get('already_read'):
            continue
        for witness in [card,*card.get('additional_reference_witnesses',[])]:
            original=witness.get('reference_witness')
            # Previously persisted cards use anchor_excerpt for either origin.
            # Retain that text as history, without inventing its source metadata.
            text=original['text'] if original else witness.get('anchor_excerpt','')
            add(card['target'], {'kind':card['direction']+'_REFERENCE',
                'reference_id':original['reference_id'] if original else witness['reference_id'],
                'anchor_ids':[card['anchor']['source_id']] if card.get('anchor') else sorted(data['references'].get('current_anchor_ids',[])),
                'witness_hash':digest(text)},text)
    terms = data.get('document_term_candidates') or {}
    for doc in terms.get('documents',[]):
        catalog = {'document_id':doc['document_id'], 'terms':doc['terms'],
            'query_terms':doc['query_terms'], 'status':doc['status'], 'total':doc.get('total'),
            'reason':doc.get('reason')}
        if catalog not in saved['catalogues']:
            saved['catalogues'].append(catalog)
        entry = inv.p.get('document_term_exploration',{}).get('documents',{}).get(doc['document_id'],{})
        for item in doc['items']:
            # Only exact rows returned by the scoped index may become leads.
            raw = next((r for r in entry.get('items',[]) if r['source_id']==item['source_id']), None)
            if raw is None or any(raw[k]!=item[k] for k in raw):
                raise ContractError('term lead differs from completed query receipt')
            add(item, {'kind':'DOCUMENT_TERM', 'query_terms':doc['query_terms'],
                'query_binding':entry['binding'], 'cursor':deepcopy(entry.get('cursor')),
                'index_sha256':inv.idx.manifest['index_sha256']}, item.get('preview',''))
    inv.save()
    return export(inv)


def export(inv):
    saved = inv.p.get('investigation_leads')
    if not saved:
        value = {'schema_version':VERSION, 'binding':inv.p['binding'], 'items':[],
                 'catalogues':[], 'omitted_count':0, 'recording_status':'NOT_RECORDED'}
    else:
        from . import evidence_inventory as inventory
        records = inv.read_records()
        acquired={}
        for evidence in inv.s.repo.evidence():
            inv.s.source.verify(evidence)
            acquired.setdefault(evidence['source_id'],[]).append(evidence)
        rows = []
        for row in saved['items'].values():
            t = row['target']
            if target(inv.s,t,inv.s.scope) != t:
                raise ContractError('lead target source binding changed')
            scopes = []
            for gid, r in records.items():
                if r['source_id']!=t['source_id'] or gid not in inv.p['groups']:
                    continue
                receipt = inventory.receipt(inv.s,inv.p['groups'][gid],r,list(inv.p['basis_history'].values()))
                scopes.append({k:deepcopy(receipt[k]) for k in ('scope_id','scope','acquired_complete','delivered_complete','delivered_pages_count','pages_total')})
            # Header/prefetch/preferred reads also live in the exact evidence
            # journal. They must never be labelled unread or full subtree reads.
            actual=acquired.get(t['source_id'],[])
            complete=False
            if actual:
                from .unit_reading import blocks
                wanted=inventory.expected(inv.s,t['document_id'],blocks(inv.s,t['document_id'],t['unit_id'],'subtree'))
                complete=bool(wanted) and inventory.covers(wanted,[p for e in actual for p in e['spans']])
                scopes.append({'scope_id':digest([t,[(e['evidence_id'],e['text_hash']) for e in actual]]),
                    'scope':{'unit_id':t['unit_id'],'extent':'journal_spans'},
                    'evidence_ids':[e['evidence_id'] for e in actual],
                    'acquired_complete':complete,'delivered_complete':None,
                    'delivered_pages_count':None,'pages_total':None})
            rows.append({**deepcopy(row), 'acquisition':'ACQUIRED' if complete else 'PARTIAL' if scopes else 'NOT_READ',
                         'read_scopes':scopes})
        value = {'schema_version':VERSION, 'binding':saved['binding'], 'items':rows,
            'catalogues':deepcopy(saved['catalogues']), 'omitted_count':len(saved['omitted_keys']),
            'recording_status':'BOUNDED' if saved['omitted_keys'] else 'RECORDED'}
    value['catalogue_hash'] = digest(value)
    return value


def validate(value, session=None, scope=None):
    if (not isinstance(value,dict) or value.get('schema_version')!=VERSION
            or digest({k:v for k,v in value.items() if k!='catalogue_hash'})!=value.get('catalogue_hash')
            or not isinstance(value.get('items'),list) or len(value['items'])>MAX_LEADS):
        raise ContractError('investigation lead catalogue changed')
    seen=set()
    for row in value['items']:
        if row.get('citation_eligible') is not False or row['lead_id'] in seen:
            raise ContractError('invalid investigation lead identity/eligibility')
        seen.add(row['lead_id'])
        if session is not None and target(session,row['target'],scope)!=row['target']:
            raise ContractError('investigation lead source hash changed')
    return value


def projection(value):
    validate(value)
    out={'catalogue_hash':value['catalogue_hash'],'items':[], 'omitted_count':value['omitted_count'],
         'meaning':'추가 조사 위치이며 인용 근거가 아니다. 필요한 대상의 원문을 읽고 기존 원문과 함께 판단한다.'}
    rows=sorted(value['items'],key=lambda r:r['acquisition']=='ACQUIRED')
    for row in rows:
        small=brief(row)
        if len(out['items'])>=VIEW_LEADS or len(json.dumps(out,ensure_ascii=False))+len(json.dumps(small,ensure_ascii=False))>VIEW_CHARS:
            out['omitted_count']+=1
            continue
        out['items'].append(small)
    return out


def parent_catalogue(port, results):
    """Only committed exports; result equality prevents candidate injection."""
    rows=[];seen=set();hashes=[];omitted=0
    active={ident for result in results for ident in result.get('evidence_ids',[])}
    acquired={}
    for ident in active:
        evidence=port.session.repo.evidence(ident)
        if evidence:
            port.session.verify(evidence)
            acquired.setdefault(evidence['source_id'],[]).append(ident)
    for result in results:
        bundle=result.get('bundle') or {}
        leads=(bundle.get('investigation_return') or {}).get('leads')
        if leads is None:continue
        db=port.session.repo.db
        row=db.execute('SELECT bundle_json,bundle_hash FROM workflow_child_export WHERE call_id=?',(result['request_id'],)).fetchone()
        if not row or digest(json.loads(row[0]))!=row[1] or json.loads(row[0])!=bundle:
            raise ContractError('lead return is not a committed child export')
        validate(leads,port.session,port.all_scope)
        if bundle['side']!=result['side']:
            raise ContractError('lead side differs from child export')
        hashes.append(leads['catalogue_hash']);omitted+=leads['omitted_count']
        for lead in leads['items']:
            if port.categories[lead['target']['document_id']]!=result['side']:
                raise ContractError('lead target escaped source side')
            identity=digest(lead['target'])
            if identity in seen:continue
            seen.add(identity)
            rows.append({**deepcopy(lead),'side':result['side'],
                'parent_read_evidence_ids':sorted(acquired.get(lead['target']['source_id'],[])),
                'return_ref':{
                'call_id':result['request_id'],'bundle_hash':bundle['bundle_hash'],
                'catalogue_hash':leads['catalogue_hash'],'lead_id':lead['lead_id']}})
    return {'items':rows,'catalogue_hash':digest(sorted(hashes)),'omitted_count':omitted}


def lead_locator(port, lead):
    t=target(port.session,lead['target'],port.all_scope)
    return {'side':port.categories[t['document_id']], **{k:t[k] for k in ('document_id','unit_id','source_id','document_name')},
            'coordinate':port.session.matcher.units.get((t['document_id'],t['unit_id']),{}).get('surface',''),
            'origin_evidence_id':None, 'reference_id':None, 'lead_ref':deepcopy(lead['return_ref'])}


def validate_locator(port, locator):
    ref=locator.get('lead_ref') or {}
    row=port.session.repo.db.execute('SELECT bundle_json,bundle_hash FROM workflow_child_export WHERE call_id=?',(ref.get('call_id'),)).fetchone()
    if not row or digest(json.loads(row[0]))!=row[1]:
        raise ContractError('research lead export missing/changed')
    bundle=json.loads(row[0]);leads=(bundle.get('investigation_return') or {}).get('leads')
    validate(leads,port.session,port.all_scope)
    if bundle['bundle_hash']!=ref.get('bundle_hash') or leads['catalogue_hash']!=ref.get('catalogue_hash'):
        raise ContractError('research lead return binding changed')
    lead=next((r for r in leads['items'] if r['lead_id']==ref.get('lead_id')),None)
    if not lead or lead_locator(port,{**lead,'return_ref':ref})!=locator:
        raise ContractError('research target differs from verified lead')
    if bundle['side']!=locator['side']:
        raise ContractError('research lead side changed')
    return locator


def brief(row):
    value={k:deepcopy(row[k]) for k in ('lead_id','target','acquisition','citation_eligible')}
    value.update(preview=row['preview'][:160],origins=deepcopy(row['origins'][:2]),
                 omitted_origins=max(0,len(row['origins'])-2))
    for key in ('side','return_ref','parent_read_evidence_ids'):
        if key in row:value[key]=deepcopy(row[key])
    return value


def parent_projection(value):
    out={**value,'items':[]};chars=0
    for row in sorted(value['items'],key=lambda r:r['acquisition']=='ACQUIRED'):
        small=brief(row);size=len(json.dumps(small,ensure_ascii=False))
        if len(out['items'])>=16 or chars+size>6000:
            out['omitted_count']+=1
            continue
        out['items'].append(small);chars+=size
    return out
