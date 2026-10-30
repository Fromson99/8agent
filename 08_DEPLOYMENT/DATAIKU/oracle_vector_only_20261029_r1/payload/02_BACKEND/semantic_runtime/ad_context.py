"""Lossless, turn-scoped references for oversized AD model context.

The complete data remains on the server. Each inference sees one bounded
segment, never an accumulating transcript of all previously read segments.
"""
import json
from .ad_store import ident


class ContextReader:
    STRING_CHARS=160
    LIST_ITEMS=8
    CHUNK_CHARS=2000
    PAGE_ROWS=8
    PREVIEW_NODES=384

    def __init__(self,store,sid):
        self.store,self.sid=store,sid
        self.cursors={}

    def reference(self,value,start=0):
        key=ident('C');self.cursors[key]=(value,start)
        return key

    def pack(self,value):
        return self._pack(value,[self.PREVIEW_NODES])

    def _pack(self,value,budget):
        budget[0]-=1
        if isinstance(value,(dict,list)) and budget[0]<0:
            items=[{'field':k,'value':v} for k,v in value.items()] if isinstance(value,dict) else value
            return {'cursor':self.reference(items),'total_items':len(items),'complete':False}
        if isinstance(value,str) and len(value)>self.STRING_CHARS:
            return {'preview':value[:self.STRING_CHARS],'total_chars':len(value),
                    'cursor':self.reference(value),'complete':False}
        if isinstance(value,list) and len(value)>self.LIST_ITEMS:
            return {'items':[self._pack(v,budget) for v in value[:self.LIST_ITEMS]],
                    'total_items':len(value),'cursor':self.reference(value,self.LIST_ITEMS),'complete':False}
        if isinstance(value,dict):
            # Even a record with thousands of columns must be paged.
            if len(value)>32 or any(len(str(k))>self.STRING_CHARS for k in value):
                items=[{'field':k,'value':v} for k,v in value.items()]
                return {'columns':self._pack(items,budget),'total_columns':len(items),'complete':False}
            return {k:self._pack(v,budget) for k,v in value.items()}
        if isinstance(value,list):return [self._pack(v,budget) for v in value]
        return value

    def read(self,cursor):
        if cursor not in self.cursors:raise ValueError('AD_SCOPE: unknown context cursor for this turn')
        value,start=self.cursors[cursor]
        size=self.CHUNK_CHARS if isinstance(value,str) else self.LIST_ITEMS
        end=min(len(value),start+size)
        return {'cursor':cursor,'offset':start,'end':end,'total':len(value),
                'data':value[start:end] if isinstance(value,str) else self.pack(value[start:end]),'complete':end==len(value),
                'next_cursor':self.reference(value,end) if end<len(value) else None}

    def table(self,source,key,offset):
        db=self.store.db
        if source=='view':
            view=db.execute('SELECT * FROM ad_view WHERE id=? AND session=?',(key,self.sid)).fetchone()
            if not view:raise ValueError('AD_SCOPE: table belongs to another conversation or is missing')
            total=view['total']
            rows=[dict(r) for r in db.execute('SELECT * FROM ad_view_row WHERE view=? AND ordinal>? ORDER BY ordinal LIMIT ?',
                                            (key,offset,self.PAGE_ROWS))]
        else:
            detail=db.execute('SELECT content FROM ad_detail WHERE id=? AND session=?',(key,self.sid)).fetchone()
            if not detail:raise ValueError('AD_SCOPE: detail belongs to another conversation or is missing')
            parsed=json.loads(detail[0])
            if not isinstance(parsed,dict) or parsed.get('display_schema')!='ad-detail-table-v1':
                raise ValueError('AD_CONTEXT: legacy detail; use the display continue action')
            total=len(parsed['rows']);rows=parsed['rows'][offset:offset+self.PAGE_ROWS]
        if offset>total:raise ValueError('AD_CONTEXT: offset exceeds table size')
        end=offset+len(rows)
        return {'source':source,'id':key,'offset':offset,'end':end,'total':total,
                'rows':self.pack(rows),'complete':end==total,
                'next_offset':end if end<total else None}
