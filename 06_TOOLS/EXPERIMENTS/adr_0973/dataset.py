"""Fresh post-fix holdout; this source never reads previous outcomes or grading."""
from common import *
import sys
sys.path.insert(0,str(ROOT/'06_TOOLS/EXPERIMENTS/adr_0972'))
# Reuse only the deterministic fixture constructor, then build a new independent set.
import importlib.util
spec=importlib.util.spec_from_file_location('prior_fixture',ROOT/'06_TOOLS/EXPERIMENTS/adr_0972/dataset.py');module=importlib.util.module_from_spec(spec)
source=(ROOT/'06_TOOLS/EXPERIMENTS/adr_0972/dataset.py').read_text()
source=source.replace("[('A','설비보전운영규정'),('B','외부작업허가규정')]","[('A','재고점검운영규정'),('B','보관시설관리규정')]")
source=source.replace('[4,8,11,13]','[5,10,12,15]').replace('for p in [2,4]','for p in [1,3]').replace("a=8,p=4","a=10,p=3").replace("question='설비보전운영규정 '","question='재고점검운영규정 '")
start=source.index('    forms=');end=source.index('    assert len(cases)==32',start)
source=source[:start]+'''    forms=[('제10조 제3항 3호~7호',[3,4,5,6,7]),('제10조제3항 제3호에서 제7호까지',[3,4,5,6,7]),
        ('제10조 3항의 3호부터 7호까지',[3,4,5,6,7]),('제10조 제3항의 제3호 내지 제7호',[3,4,5,6,7]),
        ('제10조 제3항의 3, 5, 8호',[3,5,8]),('제10조 제3항의 3~5호 및 9호',[3,4,5,9]),
        ('제10조 제3항은 7호만 빼고 나머지 모든 호',[1,2,3,4,5,6,8,9]),
        ('제10조 제3항에서 3호와 9호를 제외한 각 호',[1,2,4,5,6,7,8]),
        ('제10조 제3항 3호부터 9호 중에서 5~7호는 제외',[3,4,8,9]),
        ('제10조 제3항에서 5호 이상인 호',[5,6,7,8,9]),('제10조 제3항에서 5호 초과인 호',[6,7,8,9]),
        ('제10조 제3항에서 5호 이하인 호',[1,2,3,4,5]),('제10조 제3항에서 5호 미만인 호',[1,2,3,4]),
        ('제10조 제3항 7호와 3호, 그리고 7호',[3,7])]
    for i,(body,ids) in enumerate(forms):add('entry' if i%2==0 else 'compact',body,ids,kind='exclusion' if i in (6,7,8) else 'range_union_boundary')
    for route in ['entry','compact']:
        add(route,'제12조 제1항의 4호부터 7호까지',[4,5,6,7],a=12,p=1)
        add(route,'제10조 제1항의 3호와 제3항의 8~9호',[3],p=1,extra=[('A',10,3,8,'호'),('A',10,3,9,'호')],kind='multiple_parents')
        add(route,'제10조 제3항 제6호에서 가목~다목',[1,2,3],unit='목',kind='letters')
        add(route,'제10조의 1항과 3항',[1,3],unit='항',kind='paragraphs')
        add(route,'제10조 제3항 전체 각 호를 읽되 8호에 해당하지 않는다고 가정',list(range(1,10)),kind='fact_not_read_exclusion')
        add(route,'제10조 제3항 제6호',[6],kind='single_control')
        add(route,'제10조 제3항 80호에서 84호까지',negative=True,kind='missing')
        add(route,'제10조 제3항은 전부 제외하고 아무 호도 읽지 말 것',negative=True,kind='empty')
    add('entry','제10조 제3항의 3~4호와 보관시설관리규정 제12조 제1항 7호',[3,4],extra=[('B',12,1,7,'호')],kind='multiple_documents')
    add('compact','제10조 제3항에서 2~7호 중 4호만 제외',[2,3,5,6,7],kind='exclusion')
'''+source[end:]
exec(compile(source,str(Path(__file__)), 'exec'),module.__dict__)
module.ART=ART
if __name__=='__main__':module.build()
