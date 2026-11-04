"""Literal reference groups activated by an existing, explicit source goal.

No legal relevance inference: the originating original and model-selected member
are retained; every member has its own exact goal/coverage receipt.
"""
from copy import deepcopy
import re
from lawrag.core.legal_coordinate import find_coordinates
from ..contracts import digest
from .errors import ContractError

VERSION = 'reference-bundle-purpose-v1'
JOIN = re.compile(r'\s*(?:및|또는|과|와|[ㆍ·,、])\s*')
RANGE = re.compile(r'\s*(?:부터|내지|[~～∼])\s*')


def groups(text):
    """Closed adjacent citation lists; unrelated sentences never share a group."""
    mentions=find_coordinates(text);out=[];current=[];connectors=[]
    for m in mentions:
        between=text[current[-1].end:m.start] if current else ''
        if current and not (JOIN.fullmatch(between) or RANGE.fullmatch(between)):
            out.append((current,connectors));current=[];connectors=[]
        if current:connectors.append(between.strip())
        current.append(m)
    if current:out.append((current,connectors))
    return out


def members(rows, connectors, matcher, did):
    """Enumerate stored range members; never generate nonexistent coordinates."""
    result=[m.coordinate.canonical_surface() for m in rows]
    for left,right,join in zip(rows,rows[1:],connectors):
        if not RANGE.fullmatch(join):continue
        a,b=left.coordinate,right.coordinate
        if (a.unit,a.n,a.sub,a.dash,a.chain[:-1],a.chain_subs)!=(b.unit,b.n,b.sub,b.dash,b.chain[:-1],b.chain_subs) or not a.chain or not b.chain or a.chain[-1][0]!=b.chain[-1][0]:
            return None
        if not a.chain[-1][1]<=b.chain[-1][1]:return None
        coords=matcher.stored_coordinates
        entries=coords.for_document(did) if hasattr(coords,'for_document') else coords.items()
        middle=[]
        for (doc,_),c in entries:
            if doc==did and c and (c.unit,c.n,c.sub,c.dash,c.chain[:-1],c.chain_subs)==(a.unit,a.n,a.sub,a.dash,a.chain[:-1],a.chain_subs) and c.chain and c.chain[-1][0]==a.chain[-1][0] and a.chain[-1][1]<=c.chain[-1][1]<=b.chain[-1][1]:middle.append(c)
        if len(middle)>16:return None
        result.extend(c.canonical_surface() for c in middle)
    return list(dict.fromkeys(result))


def expand(inv,data,goals):
    if not inv.policy.get('reference_bundle_review'):return []
    from . import evidence_inventory as inventory
    from .structure_query import coordinate_index
    matcher=inv.s.matcher;index=coordinate_index(matcher);new=[];verified=set()
    for goal in list(goals):
        if goal.get('coordinate_scope')!='body' or goal.get('origin_reference_bundle'):continue
        for page in data.get('sources',[]):
            # Cross-document reference resolution remains with the existing
            # resolver. A bare number must not override an external document.
            if page.get('document_id')!=goal['document_id'] or not page.get('text'):continue
            for span in page.get('spans',[]):
                text=span.get('text','')
                for occurrences,joins in groups(text):
                    surfaces=[x.coordinate.canonical_surface() for x in occurrences]
                    if goal['coordinate'] not in surfaces:continue
                    before=text[:occurrences[0].start]
                    # Conservatively leave qualified/external citations alone.
                    if any(mark in before for mark in ('「','」','《','》','시행령','시행규칙')):continue
                    names=getattr(matcher,'document_names',None)
                    if names and any(set(h['values'])-{page['document_id']} for h in names.match(before)):continue
                    found=members(occurrences,joins,matcher,page['document_id'])
                    range_unresolved=found is None
                    if range_unresolved:found=surfaces
                    if page['id'] not in verified:
                        inventory.check_presented_page(inv.s,inv.p,page);verified.add(page['id'])
                    witness={'version':VERSION,'document_id':page['document_id'],'source_id':page['source_id'],
                        'block_id':str(span['block_id']),'start_cp':span['start_cp'],'end_cp':span['end_cp'],
                        'text_hash':digest(text),'source_quote':text,'reference_quote':text[occurrences[0].start:occurrences[-1].end],
                        'members':found,'connectors':joins,'issue_id':goal['issue_id'],
                        'purpose':'Explain the role of this explicit reference in the originating clause; definition lookup is a separate purpose.'}
                    witness['id']='RP'+digest(witness)[:24]
                    if range_unresolved:
                        ident=digest([goal['identity'],witness['id'],'range'])
                        new.append({'goal_id':'RANGE-'+ident[:12],'identity':ident,'issue_id':goal['issue_id'],'document_id':goal['document_id'],'document_name':goal['document_name'],'coordinate':witness['reference_quote'],'coordinate_scope':'body','reason':'참조 범위의 전체 하위 좌표를 확정하지 못함','status':'BLOCKED','witness':witness,'overflow':True})
                    for coordinate in found:
                        ident=digest([goal['issue_id'],goal['document_id'],coordinate,'body'])
                        target=next((g for g in goals if g['identity']==ident),None)
                        if target is None:
                            if len(goals)>=16:
                                new.append({'goal_id':'OVERFLOW-'+ident[:12],'identity':ident,'issue_id':goal['issue_id'],'document_id':goal['document_id'],'document_name':goal['document_name'],'coordinate':coordinate,'coordinate_scope':'body','reason':'참조 묶음 목표 한도 초과','status':'BLOCKED','witness':witness,'overflow':True});continue
                            target={'goal_id':'SG'+str(len(goals)+1),'identity':ident,'issue_id':goal['issue_id'],
                                'document_id':goal['document_id'],'document_name':goal['document_name'],
                                'coordinate':coordinate,'coordinate_scope':'body','reason':'현재 선택한 참조 묶음의 나머지 원문 확인: '+witness['reference_quote'],
                                'status':'REQUIRED','routes':[],'arrivals':[],'origin_reference_bundle':witness['id']}
                            goals.append(target)
                        purpose=deepcopy(witness)
                        ids=index.get((goal['document_id'],coordinate),[])
                        purpose['target_unit_id']=str(ids[0]) if len(ids)==1 else None
                        purpose['target_source_ids']=list(matcher._unit_sources(goal['document_id'],str(ids[0]))) if len(ids)==1 else []
                        existing=target.setdefault('reference_purposes',[])
                        if target.get('status')=='EXCLUDED' and not existing:
                            target['previous_exclusion']=target.pop('exclusion',None);target['status']='REQUIRED'
                        if not any(p['id']==purpose['id'] for p in existing):existing.append(purpose);new.append({'identity':ident,'coordinate':coordinate,'witness':purpose,'overflow':False})
    return new


def attach_context(heads,investigation,options,issues):
    from .investigation_supervisor import seal
    ids={i['id'] for i in issues}
    for st in investigation.get('investigation_supervisor',{}).values():
        if st.get('state_hash')!=seal(st):raise ContractError('reference purpose state changed')
        for goal in st.get('source_goals',[]):
            if goal['issue_id'] not in ids:continue
            for p in goal.get('reference_purposes',[]):
                for head in heads.values():
                    if head['document_id']!=goal['document_id'] or head['source_id'] not in p['target_source_ids']:continue
                    refs=[o['id'] for o in options if o.get('document_id')==p['document_id'] and o.get('source_id')==p['source_id'] and str(o.get('block_id'))==p['block_id'] and o.get('text')==p['source_quote']]
                    item={**deepcopy(p),'origin_evidence_refs':refs,'goal_id':goal['goal_id'],'target_coordinate':goal['coordinate'],'acquisition_status':goal['status']}
                    expected=goal.get('expected',[])
                    target_options=[o for o in options if o.get('document_id')==goal['document_id'] and o.get('source_id') in p['target_source_ids']]
                    from .evidence_inventory import covers
                    item['target_present']=bool(expected) and covers(expected,target_options)
                    item['target_evidence_refs']=[o['id'] for o in target_options if any(str(o['block_id'])==str(e['block_id']) and o['start_cp']<e['end_cp'] and o['end_cp']>e['start_cp'] for e in expected)]
                    old=head.setdefault('reference_purposes',[])
                    if not any(x['id']==item['id'] and x['target_coordinate']==item['target_coordinate'] for x in old):old.append(item)


def coverage(expected, actual):
    """Same document+block+codepoint ranges and content hashes, not article IDs."""
    from .evidence_inventory import covers
    if not expected:return {'complete':False,'reason':'NO_EXPECTED_SPANS','missing':[]}
    missing=[]
    for span in expected:
        offered=[p for p in actual if p.get('document_id')==span.get('document_id')]
        if not covers([span],offered):missing.append(deepcopy(span));continue
        exact=[p for p in offered if all(p.get(k)==span.get(k) for k in ('block_id','start_cp','end_cp'))]
        if exact and span.get('text_hash') and any(p.get('text_hash')!=span['text_hash'] for p in exact):raise ContractError('source coverage content hash changed')
    return {'complete':not missing,'reason':None if not missing else 'MISSING_REQUIRED_SPANS','missing':missing}
