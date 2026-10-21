"""Third, fresh synthetic set; same frozen task families, new titles/parents/numbers."""
from common import *
import importlib.util
spec=importlib.util.spec_from_file_location('base_fixture',ROOT/'06_TOOLS/EXPERIMENTS/adr_0972/dataset.py');module=importlib.util.module_from_spec(spec)
s=(ROOT/'06_TOOLS/EXPERIMENTS/adr_0972/dataset.py').read_text()
s=s.replace("[('A','설비보전운영규정'),('B','외부작업허가규정')]","[('A','업무기록점검규정'),('B','기자재반출관리규정')]")
s=s.replace('[4,8,11,13]','[12,17,19,23]').replace('for p in [2,4]','for p in [3,6]').replace('a=8,p=4','a=17,p=6').replace("question='설비보전운영규정 '","question='업무기록점검규정 '")
start=s.index('    forms=');end=s.index('    assert len(cases)==32',start)
s=s[:start]+'''    forms=[('제17조 제6항 2호~6호',[2,3,4,5,6]),('제17조제6항 제2호에서 제6호까지',[2,3,4,5,6]),
        ('제17조 6항의 2호부터 6호까지',[2,3,4,5,6]),('제17조 제6항의 제2호 내지 제6호',[2,3,4,5,6]),
        ('제17조 제6항의 3, 7, 9호',[3,7,9]),('제17조 제6항의 2~5호 및 8호',[2,3,4,5,8]),
        ('제17조 제6항은 4호만 빼고 나머지 모든 호',[1,2,3,5,6,7,8,9]),
        ('제17조 제6항에서 1호와 7호를 제외한 각 호',[2,3,4,5,6,8,9]),
        ('제17조 제6항 3호부터 9호 중에서 5~8호는 제외',[3,4,9]),
        ('제17조 제6항에서 3호 이상인 호',[3,4,5,6,7,8,9]),('제17조 제6항에서 3호 초과인 호',[4,5,6,7,8,9]),
        ('제17조 제6항에서 3호 이하인 호',[1,2,3]),('제17조 제6항에서 3호 미만인 호',[1,2]),
        ('제17조 제6항 8호와 4호, 그리고 8호',[4,8])]
    for i,(body,ids) in enumerate(forms):add('entry' if i%2==0 else 'compact',body,ids,kind='exclusion' if i in (6,7,8) else 'range_union_boundary')
    for route in ['entry','compact']:
        add(route,'제19조 제3항의 5호부터 8호까지',[5,6,7,8],a=19,p=3)
        add(route,'제17조 제3항의 4호와 제6항의 1~2호',[4],p=3,extra=[('A',17,6,1,'호'),('A',17,6,2,'호')],kind='multiple_parents')
        add(route,'제17조 제6항 제6호에서 나목~다목',[2,3],unit='목',kind='letters')
        add(route,'제17조의 3항과 6항',[3,6],unit='항',kind='paragraphs')
        add(route,'제17조 제6항 전체 각 호를 읽되 9호에 해당하지 않는다고 가정',list(range(1,10)),kind='fact_not_read_exclusion')
        add(route,'제17조 제6항 제6호',[6],kind='single_control')
        add(route,'제17조 제6항 70호에서 74호까지',negative=True,kind='missing')
        add(route,'제17조 제6항은 전부 제외하고 아무 호도 읽지 말 것',negative=True,kind='empty')
    add('entry','제17조 제6항의 4~5호와 기자재반출관리규정 제19조 제3항 5호',[4,5],extra=[('B',19,3,5,'호')],kind='multiple_documents')
    add('compact','제17조 제6항에서 4~9호 중 6호만 제외',[4,5,7,8,9],kind='exclusion')
'''+s[end:]
exec(compile(s,str(Path(__file__)),'exec'),module.__dict__);module.ART=ART
if __name__=='__main__':module.build()
