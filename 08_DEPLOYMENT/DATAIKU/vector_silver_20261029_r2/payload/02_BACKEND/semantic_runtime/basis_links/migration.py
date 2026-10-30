"""Conservative version mapping: identity moves retain review; meaning never inferred."""
from collections import defaultdict
from difflib import SequenceMatcher
import re
from .contracts import require,digest,now

POLICY='basis-structure-diff-v1'
# Only a display heading at the start; body numbers, references and negation remain.
HEADING=re.compile(r'^(제\s*\d+(?:의\d+)?\s*[조장절관편](?:의\d+)?)\s*')


def comparison(end):
    texts=[p['text'] for p in end['spans']]
    # Number removal is permitted only when the block begins with the stored
    # unit heading. A body starting with a statutory reference is not a heading.
    if texts and end['title'] and texts[0].startswith(end['title']) and HEADING.match(end['title']):
        texts[0]=HEADING.sub('',texts[0],count=1)
    context=[HEADING.sub('',c['title'],count=1) for c in end['context'][:-1]]
    return {'text':texts,'context':context,'structure':end.get('structure',[])}


def units(port,did,who,side):
    return port.unit_endpoints(did,who,side)


def map_endpoint(old,old_port,new_port,new_did,who,official=None):
    side=old['side'];candidates=units(new_port,new_did,who,side)
    if old['scope']=='document':candidates=[new_port.endpoint({'document_id':new_did,'scope':'document'},who,side)]
    # Full scope equality proves automatic movement; partial approved ranges do
    # not become full new articles without review.
    old_full=old_port.endpoint({'document_id':old['document_id'],'unit_id':old['unit_id'],'scope':old['scope']},who,side)
    identity=[v for v in candidates if comparison(v)==comparison(old_full)]
    if len(identity)==1 and old['spans']!=old_full['spans']:
        candidate=identity[0];mapped=[]
        for selected in old['spans']:
            positions=[i for i,p in enumerate(old_full['spans']) if p['block_id']==selected['block_id']]
            if len(positions)!=1:break
            raw=candidate['spans'][positions[0]];text=selected['text']
            offset=raw['text'].find(text)
            if offset<0 or raw['text'].find(text,offset+1)>=0:break
            mapped.append({'block_id':raw['block_id'],'start_cp':raw['start_cp']+offset,'end_cp':raw['start_cp']+offset+len(text)})
        if len(mapped)==len(old['spans']):
            exact=new_port.endpoint({**candidate,'spans':mapped},who,side)
            return {'status':'current','method':'UNIQUE_FULL_CONTEXT_SELECTED_SPANS','old':old,'new':[exact],'reason':'전체 원문·문맥 동일, 승인한 선택 범위만 위치 갱신'}

    if len(identity)==1 and old['spans']==old_full['spans']:
        return {'status':'current','method':'UNIQUE_CONTENT_CONTEXT','old':old,'new':identity,'reason':'본문·구조 문맥 동일, 위치 갱신'}
    if len(identity)>1:
        return {'status':'unresolved','method':'AMBIGUOUS_IDENTICAL','old':old,'new':[],
                'candidates':identity,'reason':'동일한 원문이 여러 위치에 있어 단일 위치를 확정하지 않음'}
    if official:
        selected=[v for v in candidates if v['unit_id'] in official['new_units']]
        require(len(selected)==len(set(official['new_units'])),'BASIS_MAPPING_SOURCE','공식 대응 후보 위치가 신판 원문에 없습니다.',409)
        if selected:return {'status':'review_needed','method':'VERSION_BOUND_MAPPING','old':old,'new':selected,'reason':'분할·통합 또는 내용·문맥 변경 후보','mapping_evidence':official}
    same=[v for v in candidates if v['unit_id']==old['unit_id']]
    # Same number is a candidate only. Never preserve its approval silently.
    proposed=same or [v for v in candidates if SequenceMatcher(None,'\n'.join(comparison(old)['text']), '\n'.join(comparison(v)['text']),autojunk=False).ratio()>=0.65]
    if len(proposed)==1:
        return {'status':'review_needed','method':'CHANGED_LOCATION_CANDIDATE','old':old,'new':proposed,'reason':'신판 위치 후보: 원문·문맥 변경 검토 필요'}
    return {'status':'unresolved','method':'UNRESOLVED','old':old,'new':[], 'candidates':proposed,
            'reason':'대응 위치 미확정. 검색 미적중만으로 삭제를 확정하지 않음'}


def migrate(service,new_sources,who,changes,*,official=None):
    """Called by build publication and Dataiku recipe, before version selection.

    Changes require registered family identity for both immutable versions.
    Existing approval events and old bindings are never changed.
    """
    require(who.get('basis_migrate') is True,'BASIS_MIGRATION_DENIED','판본 이행 권한이 필요합니다.',403)
    require(isinstance(changes,dict) and changes,'BASIS_MAPPING_INPUT','명시적인 구판→신판 목록이 필요합니다.')
    for old,new in changes.items():
        a=service.repo.lineage(old);b=service.repo.lineage(new)
        require(a and b and a['family_id']==b['family_id'],'BASIS_LINEAGE','동일 문서 계열의 판본 결속이 필요합니다.',409)
        for source,did,lineage in ((service.sources,old,a),(new_sources,new,b)):
            require(source.document_hash(did)==lineage['source_artifact_hash'],'BASIS_LINEAGE_HASH','계열 기록과 실제 원문 해시가 다릅니다.',409)
    official=official or {}
    if official:
        require(official.get('old_manifest')==service.sources.identity and official.get('new_manifest')==new_sources.identity and isinstance(official.get('raw_sha256'),str) and len(official['raw_sha256'])==64,'BASIS_MAPPING_VERSION','보조 자료의 실제 구·신 원문과 수집 해시 결속이 필요합니다.',409)
        require(official.get('old_generation')==service.sources.generation and official.get('new_generation')==new_sources.generation,
                'BASIS_MAPPING_VERSION','보조 대응 자료의 구·신 판본이 다릅니다.',409)
    base={'policy':POLICY,'old_generation':service.sources.generation,'new_generation':new_sources.generation,
          'old_manifest':service.sources.identity,'new_manifest':new_sources.identity,
          'changes':changes,'official_hash':digest(official),'team_id':who['team_id']}
    items=[]
    with service.repo.transaction():
        links=service.repo.links(who['team_id'])
        base['revision_snapshot']=digest([(l['link_id'],l['revision']) for l in links])
        ident=digest(base)
        saved=service.repo.migration(ident)
        if saved:return saved
        for link in links:
            binding=service.repo.binding(link['link_id'],link['revision'],service.sources.generation)
            if not binding:continue
            # Also bind unchanged links to the new generation. Never point a new
            # generation at an old generation's physical unit identifiers.
            existing=service.repo.binding(link['link_id'],link['revision'],new_sources.generation)
            if existing:
                items.append({'link_id':link['link_id'],'revision':link['revision'],'status':existing['status'],'binding_id':existing['binding_id']});continue
            maps=[];ends={}
            for side in ('internal','external'):
                ends[side]=[]
                for end in binding[side]:
                    service.sources.verify(end,who)
                    did=end['document_id'];new_did=changes.get(did,did)
                    if did not in changes and new_sources.document_hash(did) is None:
                        result={'status':'unresolved','method':'DOCUMENT_UNAVAILABLE','old':end,'new':[],'reason':'신판 게시 범위에서 원문 미확보'}
                    elif did not in changes:
                        try:
                            new=new_sources.endpoint(end,who,side)
                            require(new['source_artifact_hash']==end['source_artifact_hash'],'BASIS_SOURCE_HASH','변경 목록 밖의 원문이 달라졌습니다.',409)
                            result={'status':'current','method':'UNCHANGED_DOCUMENT','old':end,'new':[new]}
                        except KeyError:
                            result={'status':'unresolved','method':'DOCUMENT_UNAVAILABLE','old':end,'new':[],'reason':'신판 게시 범위에서 원문 미확보'}
                    else:
                        helper=official.get('mappings',{}).get(did,{}).get(str(end['unit_id']))
                        result=map_endpoint(end,service.sources,new_sources,new_did,who,helper)
                    maps.append(result);ends[side].extend(result['new'])
            state='unresolved' if any(m['status']=='unresolved' for m in maps) else 'review_needed' if any(m['status']=='review_needed' for m in maps) else binding['status']
            # Existing review_needed/unresolved is not cleared by an unrelated move.
            if binding['status']!='current' and state=='current':state=binding['status']
            value={'schema_version':'basis-binding-v1','binding_id':digest([link['link_id'],link['revision'],new_sources.generation]),
                   'link_id':link['link_id'],'link_revision':link['revision'],'generation_id':new_sources.generation,
                   **ends,'status':state,'migration_id':ident,'previous_binding':binding['binding_id'],'reason':'판본 대조','mapping':maps}
            service.repo.put_binding(value)
            items.append({'link_id':link['link_id'],'revision':link['revision'],'status':state,'binding_id':value['binding_id']})
        result={'schema_version':'basis-migration-v1','migration_id':ident,**base,'items':items,'at':now(),
                'status':'prepared','unresolved':sum(x['status']=='unresolved' for x in items),'approval_events_changed':False}
        service.repo.put_migration(result)
    return result
