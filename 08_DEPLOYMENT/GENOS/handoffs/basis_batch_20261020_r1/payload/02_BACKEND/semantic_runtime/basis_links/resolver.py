"""Generation-pinned approval snapshots and exact priority reads, without discovery calls."""
from copy import deepcopy
import json
import sqlite3
from .contracts import BasisUnavailable
from .contracts import BasisError,require,digest,visible


def retrieval_role(link):
    if link.get('perspective','CURRENT_BASIS')!='CURRENT_BASIS':return None
    if link['status']=='APPROVED' and link['kind']!='RELATED':return 'REVIEWED_BASIS'
    provenance=link.get('provenance',{})
    if (link['status']=='PROPOSED' and provenance.get('type')=='MODEL_OBSERVATION'
            and provenance.get('method')=='BATCH_DISCOVERY_V1'
            and provenance.get('retrieval_role')=='UNREVIEWED_CANDIDATE'):
        return 'UNREVIEWED_CANDIDATE'
    return None


def snapshot(service,who,documents,spans=None,as_of=None):
    rows=[];seen=set()
    for item in (r for did in sorted(set(documents)) for r in service.list(who,did,as_of=as_of)['items']):
        link=item['link'];binding=item['binding']
        role=retrieval_role(link)
        if role is None or link['link_id'] in seen:continue
        internal=(binding or link)['internal']
        matches=[end for end in internal if end['document_id'] in documents]
        if not matches:continue
        if spans and not any(end['scope']=='document' or any(
            p['block_id']==q['block_id'] and p['start_cp']<q['end_cp'] and q['start_cp']<p['end_cp']
            for p in end['spans'] for q in spans.get(end['document_id'],[])) for end in matches):continue
        rows.append({**item,'retrieval_role':role});seen.add(link['link_id'])
    value={'schema_version':'basis-snapshot-v1','generation_id':service.sources.generation,'items':rows}
    value['snapshot_hash']=digest(value);return value


def current(service,who,value):
    require(digest({k:v for k,v in value.items() if k!='snapshot_hash'})==value['snapshot_hash'],
            'BASIS_SNAPSHOT_HASH','실행 근거 관계 snapshot이 변경되었습니다.',409)
    out=[]
    for item in value['items']:
        link=service.repo.head(item['link']['link_id'])
        require(link is not None,'BASIS_INTEGRITY','실행 관계 이력이 없습니다.',409)
        binding=item['binding']
        ends=binding or item['link']
        require(visible({**link,'internal':ends['internal'],'external':ends['external']},who),'BASIS_SCOPE','실행 원문의 접근권한이 변경되었습니다.',403)
        out.append({**item,'live_approval':link['status'],'live_revision':link['revision'],
                    'approval_changed':link['revision']!=item['link']['revision']})
    return out


def targets(service,who,value):
    found={}
    for item in current(service,who,value):
        binding=item['binding']
        if item['live_approval'] not in ('APPROVED','PROPOSED') or item['approval_changed'] or not binding:continue
        role=retrieval_role(item['link'])
        if role is None:continue
        if binding['status']!='current' or not item.get('applicability',{}).get('priority_eligible',True):continue
        for end in binding['external']:
            service.sources.verify(end,who)
            found[end['endpoint_hash']]={'endpoint':end,'link_id':item['link']['link_id'],
                'link_revision':item['link']['revision'],'binding_id':binding['binding_id'],'binding_status':binding['status']}
            found[end['endpoint_hash']].update(relation_status=item['link']['status'],retrieval_role=role)
    return list(found.values())


def acquire(inv):
    """Use the native read budget, journal, cursors and exact source receipts."""
    src=inv.s.source;factory=getattr(src,'basis_factory',None)
    who=getattr(src,'basis_principal',None)
    if not factory or not who:return
    from ..legal_agent.workflow_execution import task_context
    task=task_context() or {}
    state=inv.p.setdefault('basis_links',{'reads':{},'snapshot':None,'unresolved':[],'consulted':[]})
    try:
        with factory() as service:
            scoped={**who,'document_ids':list(inv.s.scope)}
            if state['snapshot'] is None:
                if task.get('basis_snapshot'):
                    state['snapshot']=deepcopy(task['basis_snapshot'])
                else:
                    from ..comparison_research_bridge import preferred_documents
                    from ..workflow_bridge import SourcePort
                    docs=preferred_documents(SourcePort(src),inv.question,'internal')
                    read=src.repo.evidence()
                    docs=list(set(docs)|{e['document_id'] for e in read if service.sources.catalogue[e['document_id']]['category']=='internal'})
                    if not docs:return
                    state['consulted']=docs
                    state['snapshot']=snapshot(service,scoped,docs)
                inv.save()
            if not task.get('basis_snapshot'):
                read=src.repo.evidence()
                docs={e['document_id'] for e in read if service.sources.catalogue[e['document_id']]['category']=='internal'}-set(state.get('consulted',[]))
                if docs:
                    extra=snapshot(service,scoped,docs)
                    state['snapshot']['items'].extend(extra['items'])
                    state['snapshot']['snapshot_hash']=digest({k:v for k,v in state['snapshot'].items() if k!='snapshot_hash'})
                    state['consulted']=sorted(set(state.get('consulted',[]))|docs);inv.save()
            # Child external scope cannot see internal originals: parent already
            # verified and compiled only its exact external endpoints.
            if task.get('basis_targets') is not None:
                queue=task['basis_targets']
                for entry in queue:
                    end=entry['endpoint'];service.sources.verify(end,scoped)
                    head=service.repo.head(entry['link_id'])
                    if (head is None or head['revision']!=entry['link_revision']
                            or head['status']!=entry.get('relation_status','APPROVED') or retrieval_role(head) is None):
                        state['unresolved'].append('승인 관계가 변경되어 우선 읽기에서 제외됨: '+entry['link_id'])
                        continue
                    _read(inv,state,entry)
            else:
                for entry in targets(service,scoped,state['snapshot']):_read(inv,state,entry)
    except (sqlite3.OperationalError,OSError,BasisUnavailable) as exc:
        state['unresolved'].append('근거 원장 조회 실패: '+type(exc).__name__)
        inv.s.repo.event('BASIS_LOOKUP_UNAVAILABLE',{'type':type(exc).__name__,'cause':str(exc)})
    inv.save()


def _read(inv,state,entry):
    src=inv.s.source;end=entry['endpoint'];key=end['endpoint_hash']
    require(end['document_id'] in inv.s.scope,'BASIS_SCOPE','승인 근거가 현재 조사 범위 밖입니다.',403)
    saved=state['reads'].setdefault(key,{'cursor':None,'status':'STARTED','evidence_ids':[],'link_id':entry['link_id']})
    if saved['status']=='COMPLETE':
        offer_reads(inv,end,saved['evidence_ids'],entry.get('retrieval_role'));return
    if saved['status']=='FAILED':return
    from ..legal_agent.unit_reading import POLICY
    from ..legal_agent.errors import ToolExecutionError
    inv.add_laws([{'document_id':end['document_id'],'article_count':None,'unit_count':None}])
    while True:
        if inv.p['read_state'].get('count',0)>=POLICY['read_actions'] or inv.p['read_state'].get('chars',0)>=POLICY['initial_chars'] or inv.left()<=inv.s.profile['selection_time_reserve_seconds']:
            saved.update(status='PARTIAL',reason='READ_BUDGET');inv.save();return
        node=src.handle('U',{'document_id':end['document_id'],'unit_id':end['unit_id'],'source_id':None,
                            'read_segments':[{k:s[k] for k in ('block_id','start_cp','end_cp')} for s in end['spans']],
                            'read_label':end['title']})
        inv.save()
        reason=('미승인 배치 연결 후보의 원문 확인; 법적 근거 여부와 질문 적용은 새로 판단'
                if entry.get('retrieval_role')=='UNREVIEWED_CANDIDATE' else '사용자 승인 근거의 현재 원문 우선 읽기')
        try:r=src.execute({'tool':'read_node','args':{'node':node,'cursor':saved['cursor']},'reason':reason})
        except ToolExecutionError as exc:
            saved.update(status='FAILED',error=str(exc));inv.save();return
        evidence=[src.repo.evidence(x['evidence_id']) for x in r.get('items',[]) if x.get('evidence_id')]
        inv.p['read_state']['count']=inv.p['read_state'].get('count',0)+1
        inv.p['read_state']['chars']=inv.p['read_state'].get('chars',0)+sum(len(s['text']) for e in evidence for s in e['spans'])
        checkpoint=getattr(inv.s,'_unit_read_checkpoint',None)
        if checkpoint:checkpoint(evidence,inv.p['read_state'])
        saved['evidence_ids']=sorted(set(saved['evidence_ids'])|{e['evidence_id'] for e in evidence})
        if r['status'] not in ('OK','TRUNCATED'):
            saved.update(status='FAILED',error_code=r.get('error_code'));inv.save();return
        saved['cursor']=r.get('next_cursor');saved['status']='PARTIAL' if saved['cursor'] else 'COMPLETE'
        offer_reads(inv,end,saved['evidence_ids'],entry.get('retrieval_role'))
        inv.save()
        if not saved['cursor']:return


def offer_reads(inv,end,ids,retrieval_role=None):
    """Expose already-read exact spans in the normal native page/adoption menu."""
    from ..legal_agent import unit_relations as relations,law_candidates as candidates
    from ..legal_agent.repository import text_hash
    offered=inv.p.setdefault('basis_offered',{})
    key=end['endpoint_hash']
    if offered.get(key)==sorted(ids):return
    by={}
    for ident in ids:
        e=inv.s.repo.evidence(ident);inv.s.source.verify(e)
        by.setdefault(e['source_id'],[]).append(e)
    groups=[]
    for sid,evidence in by.items():
        uid=evidence[0]['unit_id'];hit=relations.hit_for(inv.s,sid,uid)
        spans=[p for e in evidence for p in e['spans']]
        offer={'id':'basis:'+digest([end['endpoint_hash'],sid]),'unit_id':uid,'extent':'exact',
               'reader_target':'reviewed_spans','label':end['title'],'block_ids':sorted({str(p['block_id']) for p in spans}),
               'block_count':len({str(p['block_id']) for p in spans}),'chars':sum(len(p['text']) for p in spans),
               'description':'실제 읽은 승인 선택 범위; 조문 전체 확보를 뜻하지 않음','article_complete':False}
        record={'key':hit['key'],'source_id':sid,'document_id':end['document_id'],'unit_id':uid,
                'article_unit_id':hit['article_unit_id'],'offer':offer,'complete':True,
                'text':'\n'.join(p['text'] for p in spans),'evidence_ids':[e['evidence_id'] for e in evidence],
                'evidence':evidence,'actions':[],'document_name':end['document_name'],'heading':end['title'],'hit':hit}
        inv.add_reads([record])
        gid=candidates.token(inv.s,'B',[sid,candidates.parent_offer(inv.s,hit)['id']])
        previous=inv.p['selected'].get(gid)
        if previous:
            records={e['evidence_id']:e for e in previous['evidence']+evidence}
            record['evidence']=list(records.values());record['evidence_ids']=list(records)
            record['text']='\n'.join(p['text'] for e in record['evidence'] for p in e['spans'])
        inv.p['selected'][gid]=record
        group=inv.p['groups'][gid];group['status']='READ';group['delivery_requested']=True
        group['reason']=('미승인 배치 연결 후보의 실제 원문. 관계의 타당성과 질문 적용은 새로 판단해야 합니다.'
                         if retrieval_role=='UNREVIEWED_CANDIDATE'
                         else '사용자 승인 관계의 실제 원문 우선 읽기 — 질문 적용은 모델이 판단')
        group['page_plan']=inv.plan_pages(group,inv.read_records());group['delivery']=0;groups.append(gid)
    offered[key]=sorted(ids)
    inv.p['window']='read';inv.p['window_groups']=list(dict.fromkeys(inv.p.get('window_groups',[])+groups))
    inv.save()
