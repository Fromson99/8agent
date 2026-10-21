"""New synthetic expressions and offline-only expected sets, frozen before calls."""
from common import *
import sys
sys.path.insert(0,str(ROOT/'02_BACKEND'))
from lawrag.core.legal_coordinate import LegalCoordinate

def build():
    docs=[]
    for did,title in [('A','설비보전운영규정'),('B','외부작업허가규정')]:
        texts=[];nodes=[]
        def add(parent,c,text,family):
            uid=str(len(nodes));lo=len(texts);texts.append(c.canonical_surface()+' '+text)
            node={'id':uid,'parent':parent,'family':family,'surface':c.canonical_surface(),
                  'title':'','span':[lo,lo+1],'legal_coordinate':c.as_dict(),
                  'coordinate_scope':'body','coordinate_key':'body:'+c.canonical_surface()}
            nodes.append(node);return node
        for a in [4,8,11,13]:
            ac=LegalCoordinate('조',a);article=add(None,ac,'모의 기록 절차를 따른다.','kr_article')
            for p in [2,4]:
                pc=ac.append_part(LegalCoordinate('항',p));paragraph=add(article['id'],pc,'아래 항목의 점검 기록을 작성한다.','circled')
                for i in range(1,10):
                    ic=pc.append_part(LegalCoordinate('호',i));item=add(paragraph['id'],ic,'식별표 '+did+str(a)+str(p)+str(i)+'를 기록한다.','dot_number:1')
                    if i==6:
                        for k in range(1,5):add(item['id'],ic.append_part(LegalCoordinate('목',k)),'세부 확인 결과를 남긴다.','hangul_dot')
                        item['span'][1]=len(texts)
                paragraph['span'][1]=len(texts)
            article['span'][1]=len(texts)
        docs.append({'id':did,'title':title,'texts':texts,'nodes':nodes})
    cases=[];gold=[]
    def add(route,body,items=None,*,a=8,p=4,unit='호',extra=None,negative=False,kind='range'):
        cid=f'set-{len(cases)+1:02d}';question='설비보전운영규정 '+body+' 원문을 보여 주세요.'
        wanted=[('A',a,p,n,unit) for n in (items or [])]+(extra or [])
        expected=[]
        for did,an,pn,n,level in wanted:
            c=LegalCoordinate('조',an)
            if level!='조':c=c.append_part(LegalCoordinate('항',pn if level!='항' else n))
            if level in ('호','목'):c=c.append_part(LegalCoordinate('호',n if level=='호' else 6))
            if level=='목':c=c.append_part(LegalCoordinate('목',n))
            doc=next(d for d in docs if d['id']==did)
            node=next(row for row in doc['nodes'] if row['coordinate_key']=='body:'+c.canonical_surface())
            expected.extend({'document_id':did,'block_id':str(b)} for b in range(*node['span']))
        cases.append({'id':cid,'route':route,'question':question,'scope':['A','B']})
        gold.append({'case_id':cid,'kind':kind,'expected_blocks':list({(r['document_id'],r['block_id']):r for r in expected}.values()),'negative':negative})
    forms=[('제8조 제4항 4호~7호',[4,5,6,7]),('제8조제4항 제4호에서 제7호까지',[4,5,6,7]),
        ('제8조 4항의 4호부터 7호까지',[4,5,6,7]),('제8조 제4항의 제4호 내지 제7호',[4,5,6,7]),
        ('제8조 제4항의 4, 6, 9호',[4,6,9]),('제8조 제4항의 2~4호 및 8호',[2,3,4,8]),
        ('제8조 제4항은 6호만 빼고 나머지 모든 호',[1,2,3,4,5,7,8,9]),
        ('제8조 제4항에서 2호와 8호를 제외한 각 호',[1,3,4,5,6,7,9]),
        ('제8조 제4항 2호부터 8호 중에서 4~6호는 제외',[2,3,7,8]),
        ('제8조 제4항에서 6호 이상인 호',[6,7,8,9]),('제8조 제4항에서 6호 초과인 호',[7,8,9]),
        ('제8조 제4항에서 4호 이하인 호',[1,2,3,4]),('제8조 제4항에서 4호 미만인 호',[1,2,3]),
        ('제8조 제4항 6호와 2호, 그리고 6호',[2,6])]
    for i,(body,ids) in enumerate(forms):add('entry' if i%2==0 else 'compact',body,ids,kind='exclusion' if i in (6,7,8) else 'range_union_boundary')
    for route in ['entry','compact']:
        add(route,'제11조 제2항의 3호부터 6호까지',[3,4,5,6],a=11,p=2)
        add(route,'제8조 제2항의 2호와 제4항의 7~8호',[2],p=2,extra=[('A',8,4,7,'호'),('A',8,4,8,'호')],kind='multiple_parents')
        add(route,'제8조 제4항 제6호에서 나목~라목',[2,3,4],unit='목',kind='letters')
        add(route,'제8조의 2항과 4항',[2,4],unit='항',kind='paragraphs')
        add(route,'제8조 제4항 전체 각 호를 읽되 7호에 해당하지 않는다고 가정',list(range(1,10)),kind='fact_not_read_exclusion')
        add(route,'제8조 제4항 제6호',[6],kind='single_control')
        add(route,'제8조 제4항 90호에서 94호까지',negative=True,kind='missing')
        add(route,'제8조 제4항은 전부 제외하고 아무 호도 읽지 말 것',negative=True,kind='empty')
    add('entry','제8조 제4항의 2~3호와 외부작업허가규정 제11조 제2항 8호',[2,3],extra=[('B',11,2,8,'호')],kind='multiple_documents')
    add('compact','제8조 제4항에서 3~8호 중 7호만 제외',[3,4,5,6,8],kind='exclusion')
    assert len(cases)==32
    save(ART/'documents.json',docs);save(ART/'cases.json',cases);save(ART/'grading-only.json',gold)
if __name__=='__main__':build()
