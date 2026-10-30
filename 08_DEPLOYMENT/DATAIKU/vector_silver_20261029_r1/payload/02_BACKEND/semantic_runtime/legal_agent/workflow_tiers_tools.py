"""V4 keeps complete relation facts and stable semantic hashes behind bounded menus."""
from ..contracts import digest
from .workflow_relations_tools import RelationsTools
from .repository import encoded

class TiersTools(RelationsTools):
    def materialize(self,value):
        result=super().materialize(value)
        # Candidate read/route state is a projection, never a relation version change.
        result['targets']=[{k:v for k,v in t.items() if k not in ('content_read','assessment','route','read_status','routes','candidate_decision')} for t in result['targets']]
        result['semantic_hash']=digest(value)
        result['notice_hash']=digest({k:v for k,v in result.items() if k!='notice_hash'})
        return result

    def relation_page(self,anchor,family,offset,direction='both'):
        stream=self.cards.references(anchor,direction) if family=='reference' else self.cards.term_relations(anchor) if family=='term' else getattr(self.cards,{'definition':'definitions','occurrence':'occurrences'}.get(family,family))(anchor)
        page=[];size=0
        for i,value in enumerate(stream):
            self.context.remaining()
            if i<offset:continue
            if len(page)>=self.profile['relation_page_size']:
                return page,i,{'scan_status':'PARTIAL','scan_reason':'PAGE_LIMIT'}
            item=self.materialize(value); length=len(encoded(item))
            if page and size+length>self.profile['max_relation_chars']:
                return page,i,{'scan_status':'PARTIAL','scan_reason':'RELATION_CHAR_LIMIT'}
            # Persist the full relation, including an oversized first item. Wire views page it.
            page.append(item);size+=length
            if size>self.profile['max_relation_chars']:
                return page,i+1,{'scan_status':'PARTIAL','scan_reason':'DETAIL_PAGING_REQUIRED'}
        return page,None,{'scan_status':'COMPLETE','scan_reason':'SELECTED_INDEX_ONLY'}
