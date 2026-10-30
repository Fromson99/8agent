"""Single authority for API, AD, discovery, RAG and migration consumers."""
from copy import deepcopy
import uuid
from .contracts import BasisError,require,principal,request_id,digest,now,visible,view_hash


class Service:
    def __init__(self,repository,sources):self.repo=repository;self.sources=sources

    def _receipt_key(self,who,operation,ident):
        return digest([who['team_id'],who['user_id'],operation,request_id(ident)])

    @staticmethod
    def authorized(link,binding,who):
        effective=binding or link
        return visible({**link,'internal':effective['internal'] or link['internal'],'external':effective['external'] or link['external']},who)

    def list(self,who,internal_document_id=None,as_of=None):
        principal(who);out=[]
        links=(self.repo.links_for_document(who['team_id'],internal_document_id)
               if internal_document_id else self.repo.links(who['team_id']))
        for link in links:
            binding=self.repo.binding(link['link_id'],link['revision'],self.sources.generation)
            effective=binding or link
            if not self.authorized(link,binding,who):continue
            ends=binding['internal'] if binding else link['internal']
            if internal_document_id and internal_document_id not in {e['document_id'] for e in ends}:continue
            # A current-version ACL does not authorize disclosure of historic
            # quotes in the original approval or migration's old/candidate data.
            public_link=deepcopy(link);public_binding=deepcopy(binding)
            if not visible(link,who):
                public_link.update(internal=ends,external=effective['external'],provenance={'type':link['provenance']['type'],'history_access':'restricted'})
                public_link['reason']='승인 이력의 설명은 과거 원문 조회 권한이 필요합니다.'
            if public_binding:public_binding.pop('mapping',None)
            from .temporal import applicability
            temporal=applicability(self.repo,effective,as_of)
            out.append({'link':public_link,'binding':public_binding,'view_hash':view_hash(link,binding),
                        'applicability':temporal,'current_status':binding['status'] if binding else 'unresolved'})
        return {'schema_version':'basis-links-v1','generation_id':self.sources.generation,'items':out,'snapshot_hash':digest(out)}

    def propose(self,who,body):
        principal(who)
        require(isinstance(body,dict),'BASIS_INPUT','후보 객체가 필요합니다.')
        require(set(body)<={'request_id','internal','external','kind','reason','provenance','link_id','expected_revision','view_hash','perspective'},'BASIS_INPUT','지원하지 않는 후보 입력입니다.')
        kind=body.get('kind','BASIS');reason=body.get('reason','');perspective=body.get('perspective','CURRENT_BASIS')
        require(kind in ('BASIS','IMPLEMENTS','RELATED') and isinstance(reason,str) and 0<len(reason)<=8000,'BASIS_INPUT','관계 종류와 설명이 필요합니다.')
        require(perspective in ('CURRENT_BASIS','HISTORICAL_ORIGIN'),'BASIS_INPUT','관계 관점이 잘못되었습니다.')
        provenance=body.get('provenance',{'type':'USER_SELECTION'})
        require(isinstance(provenance,dict) and provenance.get('type') in ('USER_SELECTION','MODEL_OBSERVATION','EXPLICIT_REFERENCE','IMPORT'),'BASIS_INPUT','출처 유형이 필요합니다.')
        key=self._receipt_key(who,'propose',body.get('request_id'));ih=digest(body)
        with self.repo.transaction():
            saved=self.repo.receipt(key,ih)
            if saved:
                require(visible(saved['link'],who),'BASIS_SCOPE','저장 원문의 접근권한이 변경되었습니다.',403)
                return saved
            ends={}
            for side in ('internal','external'):
                selections=body.get(side)
                require(isinstance(selections,list) and 0<len(selections)<=256,'BASIS_INPUT','양쪽 원문 선택이 필요합니다.')
                ends[side]=[self.sources.endpoint(e,who,side) for e in selections]
            require(len({e['document_id'] for e in ends['external']})==1,'BASIS_INPUT','외규 문서별로 관계를 생성해야 합니다.')
            previous=None;ident=body.get('link_id') or uuid.uuid4().hex
            if body.get('link_id'):
                principal(who,review=True);old=self.repo.head(ident)
                require(old is not None and old['team_id']==who['team_id'],'BASIS_NOT_FOUND','관계를 찾을 수 없습니다.',404)
                previous=old['revision'];binding=self.repo.binding(ident,previous,self.sources.generation)
                require(self.authorized(old,binding,who),'BASIS_NOT_FOUND','관계를 찾을 수 없습니다.',404)
                require(body.get('expected_revision')==previous and body.get('view_hash')==view_hash(old,binding),'BASIS_STALE_VIEW','관계가 변경되었습니다. 현재 행을 확인해 주세요.',409)
            revision=(previous or 0)+1
            link={'schema_version':'basis-link-v1','link_id':ident,'revision':revision,'team_id':who['team_id'],
                  **ends,'kind':kind,'reason':reason,'perspective':perspective,'provenance':provenance,
                  'status':'PROPOSED','created_at':now(),'created_by':who['user_id'],'previous_revision':previous}
            binding={'schema_version':'basis-binding-v1','binding_id':digest([ident,revision,self.sources.generation]),
                     'link_id':ident,'link_revision':revision,'generation_id':self.sources.generation,**ends,
                     'status':'current','migration_id':None,'previous_binding':None,'reason':'실제 선택 원문'}
            event={'event_id':uuid.uuid4().hex,'link_id':ident,'revision':revision,'action':'revise' if previous else 'propose',
                   'actor':who['user_id'],'team_id':who['team_id'],'at':now(),'request_id':body['request_id'],'binding_hash':digest(binding)}
            self.repo.append(link,event,previous);self.repo.put_binding(binding)
            result={'link':link,'binding':binding,'view_hash':view_hash(link,binding),'receipt':event}
            self.repo.save_receipt(key,ih,result);return result

    def review(self,who,body):
        principal(who,review=True)
        require(isinstance(body,dict),'BASIS_INPUT','승인 객체가 필요합니다.')
        require(set(body)<={'request_id','items','action','reason'},'BASIS_INPUT','지원하지 않는 승인 입력입니다.')
        require(body.get('action') in ('approve','reject','revoke'),'BASIS_INPUT','approve/reject/revoke 중 하나를 선택해야 합니다.')
        items=body.get('items');reason=body.get('reason','')
        require(isinstance(items,list) and 0<len(items)<=256 and isinstance(reason,str) and len(reason)<=8000,'BASIS_INPUT','선택 행과 이유 형식이 잘못되었습니다.')
        require(all(isinstance(i,dict) and isinstance(i.get('link_id'),str) for i in items),'BASIS_INPUT','선택 행 형식이 잘못되었습니다.')
        require(len({i.get('link_id') for i in items})==len(items),'BASIS_INPUT','행을 중복 선택할 수 없습니다.')
        # Each row has its own stable receipt: one stale row never loses earlier commits.
        request_id(body.get('request_id'));results=[]
        # Freeze the entire bulk request before any per-row mutation, including
        # retries after only a subset committed or after response loss.
        key=self._receipt_key(who,'review-envelope',body['request_id']);ih=digest(body)
        with self.repo.transaction():
            if self.repo.receipt(key,ih) is None:self.repo.save_receipt(key,ih,{'input_hash':ih})
        for i,item in enumerate(items):
            try:results.append(self._review_row(who,body,item,i))
            except BasisError as exc:
                if exc.code=='BASIS_REQUEST_CONFLICT':raise
                results.append({'link_id':item.get('link_id'),'status':'not_applied','error_code':exc.code,'message':str(exc)})
        return {'schema_version':'basis-review-v1','status':'completed' if all(r['status']=='applied' for r in results) else 'partial','items':results}

    def _review_row(self,who,body,item,index):
        require(isinstance(item,dict) and set(item)=={'link_id','revision','view_hash'},'BASIS_INPUT','선택 행의 ID·revision·view_hash가 필요합니다.')
        key=self._receipt_key(who,'review:'+str(index),body['request_id']);ih=digest(body)
        with self.repo.transaction():
            saved=self.repo.receipt(key,ih)
            if saved:
                current=self.repo.head(item['link_id'])
                require(current is not None and current['team_id']==who['team_id'],'BASIS_NOT_FOUND','관계를 찾을 수 없습니다.',404)
                binding=self.repo.binding(current['link_id'],current['revision'],self.sources.generation)
                require(self.authorized(current,binding,who),'BASIS_NOT_FOUND','관계를 찾을 수 없습니다.',404)
                return saved
            old=self.repo.head(item['link_id'])
            require(old is not None and old['team_id']==who['team_id'],'BASIS_NOT_FOUND','관계를 찾을 수 없습니다.',404)
            binding=self.repo.binding(old['link_id'],old['revision'],self.sources.generation)
            effective=binding or old
            require(self.authorized(old,binding,who),'BASIS_NOT_FOUND','관계를 찾을 수 없습니다.',404)
            require(item['revision']==old['revision'] and item['view_hash']==view_hash(old,binding),'BASIS_STALE_VIEW','관계가 변경되었습니다. 현재 행을 확인해 주세요.',409)
            if body['action']=='approve':
                require(binding is not None and binding['internal'] and binding['external'],'BASIS_UNRESOLVED','현재 승인할 원문 위치가 없습니다.',409)
                for end in binding['internal']+binding['external']:self.sources.verify(end,who)
            revision=old['revision']+1
            link=deepcopy(old);link.update(revision=revision,previous_revision=old['revision'],status={'approve':'APPROVED','reject':'REJECTED','revoke':'REVOKED'}[body['action']])
            event={'event_id':uuid.uuid4().hex,'link_id':old['link_id'],'revision':revision,'previous_revision':old['revision'],
                   'view_hash':item['view_hash'],'binding_hash':digest(binding),'action':body['action'],'actor':who['user_id'],
                   'team_id':who['team_id'],'at':now(),'request_id':body['request_id'],'reason':body.get('reason','')}
            link['review_event_id']=event['event_id']
            if body['action']=='approve':link.update(internal=binding['internal'],external=binding['external'])
            self.repo.append(link,event,old['revision'])
            # Preserve rollback bindings, but only the reviewed generation becomes current.
            for previous in self.repo.bindings(old['link_id'],old['revision']):
                value={**previous,'link_revision':revision,'binding_id':digest([old['link_id'],revision,previous['generation_id']]),'previous_binding':previous['binding_id']}
                if body['action']=='approve' and previous['generation_id']==self.sources.generation:value['status']='current'
                self.repo.put_binding(value)
            result={'link_id':old['link_id'],'revision':revision,'status':'applied','approval_status':link['status'],'receipt':event}
            self.repo.save_receipt(key,ih,result);return result

    def history(self,who,ident):
        principal(who);link=self.repo.head(ident)
        require(link is not None and visible(link,who),'BASIS_NOT_FOUND','관계를 찾을 수 없습니다.',404)
        value=self.repo.history(ident)
        require(all(visible(row,who) for row in value['revisions']),'BASIS_SCOPE','과거 원문의 조회 권한이 없습니다.',403)
        require(all(visible({**link,'internal':b['internal'],'external':b['external']},who) for b in value['bindings']),'BASIS_SCOPE','판본 이력의 조회 권한이 없습니다.',403)
        return value

    def view(self,who,internal_document_id=None,link_ids=None,as_of=None):
        value=self.list(who,internal_document_id,as_of)
        if link_ids is not None:value['items']=[r for r in value['items'] if r['link']['link_id'] in link_ids]
        value['snapshot_hash']=digest(value['items'])
        rows=[{'link_id':r['link']['link_id'],'revision':r['link']['revision'],'view_hash':r['view_hash']} for r in value['items']]
        payload={'principal':{k:who[k] for k in ('team_id','user_id')},'generation_id':self.sources.generation,'rows':rows}
        ident=digest(payload)
        with self.repo.transaction():
            old=self.repo.receipt('view:'+ident,digest(payload))
            if old is None:self.repo.save_receipt('view:'+ident,digest(payload),payload)
        return {**value,'view_id':ident}

    def review_view(self,who,body):
        import re,json
        principal(who,review=True)
        require(set(body)<={'view_id','rows','text','action','reason','request_id'},'BASIS_INPUT','지원하지 않는 선택 승인 입력입니다.')
        ident=body.get('view_id')
        require(isinstance(ident,str) and re.fullmatch('[a-f0-9]{64}',ident),'BASIS_VIEW','현재 화면의 view_id가 필요합니다.')
        raw=self.repo.db.execute('SELECT * FROM basis_receipt WHERE receipt_id=?',('view:'+ident,)).fetchone()
        view=self.repo.decoded(raw)
        require(view is not None and view['principal']=={k:who[k] for k in ('team_id','user_id')} and view['generation_id']==self.sources.generation,
                'BASIS_VIEW','현재 사용자·세대의 선택 화면이 아닙니다.',409)
        rows=body.get('rows');action=body.get('action');text=body.get('text')
        if text is not None:
            require(rows is None and action is None and isinstance(text,str),'BASIS_INPUT','행 선택과 문장 명령을 함께 보낼 수 없습니다.')
            match=re.fullmatch(r'\s*([0-9]+(?:\s*[,、]\s*[0-9]+)*)\s*번?\s*(승인|반려|취소)\s*',text)
            if match:
                rows=[int(n) for n in re.split(r'\s*[,、]\s*',match[1])]
                action={'승인':'approve','반려':'reject','취소':'revoke'}[match[2]]
            elif len(view['rows'])==1 and text.strip() in ('이 연결 맞아','이 연결 승인'):
                rows=[1];action='approve'
            else:raise BasisError('BASIS_SELECTION_REQUIRED','승인할 행 번호를 명시해 주세요. 예: 2번 승인')
        require(isinstance(rows,list) and rows and all(type(n) is int and 1<=n<=len(view['rows']) for n in rows),'BASIS_SELECTION_REQUIRED','현재 표의 행 번호가 필요합니다.')
        return self.review(who,{'request_id':body.get('request_id'),'action':action,'reason':body.get('reason',''),
                               'items':[view['rows'][n-1] for n in rows]})
