"""Local source adapter; coordinates are reconstructed from immutable originals."""
import json
from .contracts import require,digest,text_hash


class SourcePort:
    def __init__(self,store,config=None):
        self.store=store
        from types import SimpleNamespace
        from ..folder_navigation import bind_catalogue,load_origin_projection
        projection=load_origin_projection(config[0],config[1],store) if config else None
        self.catalogue=bind_catalogue(SimpleNamespace(),store,projection).document_catalogue

    @property
    def generation(self):return self.store.manifest['generation_id']

    def endpoint(self,selection,who,side):
        require(isinstance(selection,dict),'BASIS_INPUT','원문 선택 객체가 필요합니다.')
        did=selection.get('document_id');uid=selection.get('unit_id')
        require(did in who['document_ids'],'BASIS_SCOPE','허용 문서 범위 밖입니다.',403)
        self.store.check_unchanged()
        row=self.store.db.execute('SELECT name,source_artifact_sha256,json FROM document WHERE document_id=?',(did,)).fetchone()
        require(row is not None,'BASIS_SOURCE_MISSING','선택 원문을 찾을 수 없습니다.',404)
        role=self.catalogue[did]['category']
        require(role==side,'BASIS_SIDE','내규·외규 구분과 선택 원문이 다릅니다.')
        if uid is None:
            require(selection.get('scope')=='document','BASIS_SCOPE','문서 전체 또는 정확한 조문을 선택해야 합니다.')
            blocks=[dict(r) for r in self.store.db.execute('SELECT block_id,text FROM source_block WHERE document_id=? ORDER BY CAST(block_id AS INTEGER)',(did,))]
            title='문서 전체';ancestors=[]
        else:
            value=self.store.section(did,str(uid));blocks=value['blocks'];title=value['title'];ancestors=value['ancestors']
        chosen=selection.get('spans')
        spans=[];available={str(b['block_id']):b for b in blocks}
        if chosen is None:chosen=[{'block_id':str(b['block_id']),'start_cp':0,'end_cp':len(b['text'])} for b in blocks if b['text']]
        require(isinstance(chosen,list) and chosen,'BASIS_EMPTY_SOURCE','실제 원문 범위가 필요합니다.')
        for item in chosen:
            require(isinstance(item,dict),'BASIS_SPAN','원문 범위 객체가 필요합니다.')
            raw=available.get(str(item.get('block_id')));a=item.get('start_cp');z=item.get('end_cp')
            require(raw is not None and type(a) is int and type(z) is int and 0<=a<z<=len(raw['text']), 'BASIS_SPAN','선택 범위가 원문 조문 밖입니다.')
            text=raw['text'][a:z]
            span={'block_id':str(raw['block_id']),'start_cp':a,'end_cp':z,'text':text,'block_hash':text_hash(raw['text']),'span_hash':text_hash(text)}
            for k in ('text','block_hash','span_hash'):
                require(k not in item or item[k]==span[k],'BASIS_SOURCE_HASH','선택한 원문이 현재 원문과 다릅니다.',409)
            spans.append(span)
        spans=sorted({digest(s):s for s in spans}.values(),key=lambda s:(int(s['block_id']),s['start_cp'],s['end_cp']))
        shape=[]
        for span in spans:
            block=self.store.db.execute('SELECT json FROM source_block WHERE document_id=? AND block_id=?',(did,span['block_id'])).fetchone()
            raw=json.loads(block[0]) if block else {}
            shape.append({k:raw[k] for k in ('type','kind','table','cells','rowspan','colspan','structure') if k in raw})
        value={'document_id':did,'document_version':did,'generation_id':self.generation,'unit_id':str(uid) if uid is not None else None,
               'scope':'document' if uid is None else 'unit','side':side,'document_name':row['name'],'title':title,
               'source_artifact_hash':row['source_artifact_sha256'],'spans':spans,'context':ancestors,'structure':shape}
        value['endpoint_hash']=digest(value)
        return value

    def verify(self,end,who):
        require(end['generation_id']==self.generation,'BASIS_GENERATION','현재 세대의 원문이 아닙니다.',409)
        value=self.endpoint(end,who,end['side'])
        require(value==end,'BASIS_SOURCE_HASH','승인 화면의 원문·위치·해시가 변경되었습니다.',409)
        return value

    @property
    def identity(self):return digest(self.store.manifest)

    def document_hash(self,did):
        self.store.check_unchanged()
        row=self.store.db.execute('SELECT source_artifact_sha256 FROM document WHERE document_id=?',(did,)).fetchone()
        return row[0] if row else None

    def unit_endpoints(self,did,who,side):
        from .contracts import BasisError
        values=[]
        for row in self.store.db.execute('SELECT unit_id FROM source_unit WHERE document_id=? ORDER BY CAST(unit_id AS INTEGER)',(did,)):
            try:values.append(self.endpoint({'document_id':did,'unit_id':str(row[0])},who,side))
            except BasisError as exc:
                if exc.code!='BASIS_EMPTY_SOURCE':raise
        return values
