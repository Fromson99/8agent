"""Closed, pre-execution domain choices; discoveries never become approved concepts."""
import json
from pathlib import Path
from jsonschema import validate
from .corrected_memory import MemoryError, STAGES, digest, object_schema, array, choice, encoded

METHODS={
    'INTENT':('PURPOSE_IDENTIFY','조사 목적과 적용 개념을 확인한다'),
    'PLAN':('SOURCE_SCOPE_PLAN','허용 문서 범위에서 원문 조사 경로를 정한다'),
    'RECALL':('ORIGINAL_DISCOVER','구조 좌표와 전문 검색으로 원문 후보를 찾는다'),
    'READ':('EXACT_SOURCE_READ','원문과 명시 참조를 읽고 해시·좌표를 확인한다'),
    'SELECT':('SOURCE_RELEVANCE','읽은 원문 중 질문의 근거를 선별한다'),
    'ASSESS':('CONDITIONAL_APPLICABILITY','현재 사실과 원문의 조건·단서로 적용을 판단한다'),
    'COMPOSE':('SUPPORTED_PRESENTATION','수락한 판단과 근거를 보존해 답변을 작성한다')}


class DomainCatalogue:
    def __init__(self,value):
        if value.get('schema_version')!='legal-agent-domain-catalogue-v1':raise MemoryError('catalogue version required')
        self.value=value;self.hash=digest(value);self.method_hash=digest(METHODS)
        self.concepts={x['id']:x for x in value['concepts']}
        self.relations={x['id']:x for x in value['relations']}
        if len(self.concepts)!=len(value['concepts']) or len(self.relations)!=len(value['relations']):raise MemoryError('duplicate domain ID')
        for x in self.concepts.values():
            if x.get('status') not in ('SYSTEM','REVIEWED') or not x.get('definition'):raise MemoryError('concept requires reviewed definition')
            if x['status']=='REVIEWED':self.reviewed(x)
        for x in self.relations.values():
            if x['source'] not in self.concepts or x['target'] not in self.concepts:raise MemoryError('relation type unknown')
            if x.get('status') not in ('SYSTEM','REVIEWED'):raise MemoryError('unreviewed domain relation')
            if x['status']=='REVIEWED':self.reviewed(x)

    @staticmethod
    def reviewed(item):
        import re
        receipt=item.get('review_receipt')
        if (not isinstance(receipt,dict) or receipt.get('decision')!='ACCEPTED' or
                not receipt.get('reviewer') or not receipt.get('source_generation') or
                not re.fullmatch('[a-f0-9]{64}',str(receipt.get('source_hash',''))) or not receipt.get('evidence_refs')):
            raise MemoryError('reviewed domain item requires source-bound accepted review receipt')

    @classmethod
    def load(cls,root,binding):
        import hashlib
        path=Path(root)/binding['path']
        if not path.resolve().is_relative_to(Path(root).resolve()):raise MemoryError('catalogue path escaped')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=binding['sha256']:raise MemoryError('catalogue binding changed')
        return cls(json.loads(data))

    def offer(self,stage,state):
        if stage not in METHODS:raise MemoryError('unknown domain checkpoint')
        method,purpose=METHODS[stage]
        return {'catalogue_hash':self.hash,'method_policy_hash':self.method_hash,'stage':stage,
            'method_id':method,'purpose':purpose,'concepts':list(self.concepts.values()),
            'relations':list(self.relations.values()),'paths':['REVIEWED','DISCOVERY'],
            'document_ids':state['document_ids'],'facts':state['facts']}

    def select(self,stage,state,session):
        offer=self.offer(stage,state)
        generation=session.work.binding['generation_id']
        offer['concepts']=[c for c in offer['concepts'] if c['status']=='SYSTEM' or c['review_receipt']['source_generation']==generation]
        ids={c['id'] for c in offer['concepts']}
        offer['relations']=[r for r in offer['relations'] if {r['source'],r['target']}<=ids and
            (r['status']=='SYSTEM' or r['review_receipt']['source_generation']==generation)]
        relations=[r['id'] for r in offer['relations']]
        schema=object_schema({'method_id':choice([offer['method_id']]),'path':choice(offer['paths']),
            'concept_ids':array(choice(sorted(ids)) if ids else {'type':'string'}),
            'relation_ids':array(choice(relations) if relations else {'type':'string'}),
            'reason':{'type':'string','minLength':1}})
        for key in ('concept_ids','relation_ids'):schema['properties'][key].update(uniqueItems=True,maxItems=16)
        if not ids:schema['properties']['concept_ids']['maxItems']=0
        if not relations:schema['properties']['relation_ids']['maxItems']=0
        def guard(selected):
            validate(selected,schema)
            for rid in selected['relation_ids']:
                r=self.relations[rid]
                if not {r['source'],r['target']}<=set(selected['concept_ids']):raise MemoryError('relation endpoint concepts not selected')
            if selected['path']=='REVIEWED' and not selected['concept_ids']:raise MemoryError('reviewed path requires offered concepts')
        # The stage already fixes the method. This receipt asserts execution
        # policy only; it never declares a legal concept reviewed.
        selected={'method_id':offer['method_id'],'path':'DISCOVERY',
                  'concept_ids':[],'relation_ids':[],
                  'reason':'Deterministic registered stage method; no legal approval implied.'}
        session.work.event('DOMAIN_METHOD_FIXED',{'stage':stage,'method_id':offer['method_id'],
                                                 'actor':'SYSTEM_POLICY','model_calls':0})
        guard(selected)
        with session.work.transaction():
            ident='D'+digest([session.context.run_id,stage,session.work.run()['next_event_seq'],selected])[:28]
            seq=session.work.event('DOMAIN_CHOICE_ACCEPTED',{'choice_id':ident,'offer':offer,'choice':selected})
            session.work.db.execute('INSERT INTO domain_choice VALUES(?,?,?,?,?)',(ident,stage,encoded(offer),encoded(selected),seq))
        return {'choice_id':ident,**selected,'catalogue_hash':self.hash,'method_policy_hash':self.method_hash}


def compile_catalogue(reviewed,destination):
    """Explicit reviewed input only; no generated labels are silently approved."""
    value=json.loads(Path(reviewed).read_text())
    catalogue=DomainCatalogue(value)
    path=Path(destination)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x',encoding='utf-8') as stream:stream.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    import hashlib
    return {'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'catalogue_hash':catalogue.hash}
