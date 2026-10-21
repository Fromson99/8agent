from common import *
C=ART/'code-candidate';p=C/'02_BACKEND/semantic_runtime/legal_agent/structure_selection.py';t=p.read_text();needle='각 그룹의 포함 집합을 합친 뒤 모든 제외 집합을 뺀다.'
assert needle in t;t=t.replace(needle, '"전부 제외", "아무 항목도 읽지 말라"는 빈 선택 의도다. ALL 포함과 ALL 제외로 보존하거나 읽지 않고 이유를 설명한다. 빈 선택을 문서 전체 읽기로 바꾸지 않는다.\n'+needle);p.write_text(t)
for p in (C/'02_BACKEND/ENGINES').rglob('*.json'):
 v=read(p)
 if 'files' in v:
  for n in v['files']:v['files'][n]=sha(C/n)
  save(p,v)
def pins(v):
 if isinstance(v,dict):
  if v.get('manifest') and 'sha256' in v and (C/v['manifest']).is_file():v['sha256']=sha(C/v['manifest'])
  for x in v.values():pins(x)
 elif isinstance(v,list):
  for x in v:pins(x)
p=C/'00_SYSTEM/PIPELINE.json';v=read(p);pins(v);save(p,v)
s=read(ART/'stage.json');s['files']['candidate']={n:sha(C/n) for n in s['files']['candidate']};save(ART/'stage.json',s)
