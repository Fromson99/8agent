"""Model selects offered immutable segments; code alone computes source spans."""
import re
from semantic_runtime.legal_agent.corrected_memory import MemoryError


def obj(properties):return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}
def arr(items,maximum=128):return {'type':'array','items':items,'maxItems':maximum}
S={'type':'string'};BOOL={'type':'boolean'}
VALUE={'anyOf':[{'type':'string'},{'type':'number'},{'type':'boolean'},{'type':'null'},{'type':'array','items':{'type':'string'}}]}
ATOM=obj({'op':{'enum':['eq','in','before','duration_lt']},'field':S,
          'value':VALUE,'unit':{'enum':['day','month','year',None]}})
# A bounded root and leaf array avoids provider grammar recursion. Arbitrarily
# nested conditions remain unresolved rather than being silently simplified.
COND=obj({'op':{'enum':['eq','in','before','duration_lt','all','any']},'field':{'type':['string','null']},
          'value':VALUE,'unit':{'enum':['day','month','year',None]},'args':arr(ATOM,8)})



def offered(snapshots):
    segments={};sources={};records=[]
    for snapshot in snapshots:
        for group in ('events','sources','facts','traces'):
            for record in snapshot[group]:
                ref=record['id'];payload=record.get('payload',record if group=='facts' else {})
                if isinstance(payload,str):
                    import json
                    payload=json.loads(payload)
                text=payload.get('text','')
                ranges=[]
                if text:
                    start=0
                    # Fragments are only offered references. The model defines semantic units.
                    ends=[m.end() for m in re.finditer(r'(?<=[.?!。？！])\s+|\n+',text)] if group=='events' else []
                    for end in [*ends,len(text)]:
                        if end>start:ranges.append((start,end))
                        start=end
                else:ranges=[(None,None)]
                for start,stop in ranges:
                    ident='segment-'+str(len(segments)+1)
                    segments[ident]={'ref':ref,'start':start,'stop':stop,'group':group,'record':record}
                    records.append({'segment_id':ident,'kind':group,'text':text[start:stop] if text else payload,
                                    'source_id':ref if group=='sources' else None,
                                    'source_metadata':{k:payload[k] for k in ('document_id','document_name','generation','coordinate','version')} if group=='sources' else None})
                if group=='sources':sources[ref]=record
    return segments,sources,records


def schema(segments,sources,prior=None):
    UNIT={'type':'string','enum':['u'+str(i) for i in range(1,17)]}
    SEG={'type':'string','enum':list(segments)}
    SRC={'type':'string','enum':list(sources)} if sources else {'type':'string','enum':['NO_SOURCE_AVAILABLE']}
    unit=obj({'id':UNIT,'topic':S,'question':S,'completeness':{'enum':['OPEN','BOUNDED','CLOSED_CANDIDATE']},'unresolved':arr(S,24),'jurisdiction':S,'applicable_time':S})
    member=obj({'unit':UNIT,'segment_id':SEG,'role':{'enum':['CONTEXT','SOURCE','CONDITION','RATIONALE','COUNTEREXAMPLE']},'reason':S})
    claim=obj({'unit':UNIT,'id':S,'statement':S,'condition':{'$ref':'#/$defs/condition'},'exceptions_checked':BOOL,
               'evidence_refs':arr(SRC,16),'rationale':S,'unresolved':arr(S,24),'document_name':S,'quote':S})
    # First reusable catalogue has one read-only durable-coordinate adapter.
    step=obj({'id':S,'tool':{'enum':['read_durable_unit']},'document_id':S,'unit_id':S,'after':arr(S,16),'purpose':S,'result_check':{'enum':['complete_source']}})
    procedure=obj({'unit':UNIT,'id':S,'preconditions':{'$ref':'#/$defs/condition'},'steps':arr(step,24),'stop_rules':arr(S,16),'reentry':{'enum':['PLAN','RECALL']}})
    relation=obj({'source':UNIT,'target':UNIT,'type':{'enum':['DEPENDS_ON','SAME_TOPIC','CONTRADICTS','VARIANT']},'reason':S})
    check=obj({'unit':UNIT,'required_facts':BOOL,'sources':BOOL,'exceptions':BOOL,'corrections':BOOL})
    result=obj({'units':arr(unit,16),'members':arr(member,256),'claims':arr(claim,48),'procedures':arr(procedure,16),'relations':arr(relation,48),
                'unassigned_spans':arr(obj({'segment_id':SEG,'reason':S}),256),'conflicts':arr(obj({'unit':UNIT,'reason':S}),32),'completeness_checks':arr(check,16)})
    if prior:
        result['properties']['prior_links']=arr(obj({'unit':UNIT,'prior_unit':{'enum':list(prior)},'prior_revision':{'type':'integer','minimum':1},'type':{'enum':['SAME_TOPIC','VARIANT','CONTRADICTS','SUPERSEDES_PROPOSED']},'reason':S}),32)
        result['required'].append('prior_links')
    result['$defs']={'condition':COND}
    return result


def normalize(proposal,segments,catalogue):
    from copy import deepcopy
    out=deepcopy(proposal);members=[];covered=set()
    for row in out['members']:
        ident=row.pop('segment_id');segment=segments.get(ident)
        if not segment:raise MemoryError('unoffered segment')
        covered.add(ident);members.append({**row,'ref':segment['ref'],'start':segment['start'],'stop':segment['stop']})
    out['members']=members;unassigned=[]
    for row in out['unassigned_spans']:
        ident=row['segment_id'];segment=segments.get(ident)
        if not segment:raise MemoryError('unoffered unassigned segment')
        covered.add(ident)
        if segment['group']=='events' and segment['start'] is not None:
            unassigned.append({'ref':segment['ref'],'start':segment['start'],'stop':segment['stop'],'reason':row['reason']})
    # An unselected record remains explicitly unassigned; it is never thrown away.
    for ident,segment in segments.items():
        if ident not in covered and segment['group']=='events' and segment['start'] is not None:
            unassigned.append({'ref':segment['ref'],'start':segment['start'],'stop':segment['stop'],'reason':'MODEL_DID_NOT_ASSIGN'})
    out['unassigned_spans']=unassigned
    for procedure in out['procedures']:
        for step in procedure['steps']:
            step['contract_hash']=__import__('semantic_runtime.legal_agent.corrected_memory',fromlist=['digest']).digest(catalogue[step['tool']]['schema'])
            step['arguments']={'document_id':{'literal':step.pop('document_id')},'unit_id':{'literal':step.pop('unit_id')}}
    # Citations to offered source IDs are already explicit model links. Derive
    # their exact membership mechanically; never infer a new legal authority.
    known_sources={v['ref']:v for v in segments.values() if v['group']=='sources'}
    observations=[];claims=[]
    for claim in out['claims']:
        refs=claim.get('evidence_refs',[]);reason=None
        if not refs:reason='NO_BOUND_SOURCE'
        elif not claim.get('rationale'):reason='NO_RECORDED_RATIONALE'
        elif not claim.get('quote'):reason='NO_EXACT_QUOTE'
        else:
            for ref in refs:
                segment=known_sources.get(ref)
                if not segment:raise MemoryError('unoffered source')
                source=segment['record']['payload']
                if source['document_name']!=claim.get('document_name') or claim['quote'] not in source['text']:
                    reason='SOURCE_NAME_OR_QUOTE_MISMATCH'
                    break
        if reason:
            observations.append({'unit':claim['unit'],'original_claim':claim,'status':'UNVERIFIED','reason':reason})
            continue
        for ref in refs:
            if not any(m['unit']==claim['unit'] and m['ref']==ref for m in out['members']):
                segment=known_sources[ref]
                out['members'].append({'unit':claim['unit'],'ref':ref,'start':segment['start'],'stop':segment['stop'],
                    'role':'SOURCE','reason':'Exact offered source explicitly cited by claim '+claim['id']})
        claims.append(claim)
    out['claims']=claims;out['observations']=observations
    checks={c['unit']:c for c in out['completeness_checks']}
    for unit in out['units']:
        withheld=[o for o in observations if o['unit']==unit['id']]
        if withheld:
            unit['unresolved']=[*unit['unresolved'],*[o['reason']+': '+o['original_claim']['statement'] for o in withheld]]
        check=checks.get(unit['id'],{})
        if withheld or (unit['completeness']=='CLOSED_CANDIDATE' and
                (unit['unresolved'] or not all(check.get(k) is True for k in ('required_facts','sources','exceptions','corrections')))):
            unit['completeness']='OPEN'
            if not unit['unresolved']:unit['unresolved']=['COMPLETENESS_CHECKS_INCOMPLETE']
    return out
