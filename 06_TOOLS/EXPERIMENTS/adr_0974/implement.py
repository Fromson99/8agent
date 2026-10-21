"""A new isolated prompt/schema-description candidate after completed ADR0973."""
from common import *
import shutil
P=ROOT/'04_EXPERIMENTS/ADR/ADR-0973-required-structural-selection/artifacts';old=read(P/'stage.json')
assert read(P.parent/'실험/manifest.json')['reservation']['status']=='completed'
C=ART/'code-candidate';shutil.copytree(ROOT/old['roots']['candidate'],C)
p=C/'02_BACKEND/semantic_runtime/legal_agent/structure_selection.py';t=p.read_text()
t=t.replace("'exclude': {'type': 'array', 'items': CLAUSE, 'maxItems': 64}","'exclude': {'type': 'array', 'items': CLAUSE, 'maxItems': 64,\n                    'description': '읽기 대상에서 빼 달라는 요청만. 해당하지 않는다는 가정, 예외 적용 사실, 적용 불가능 판단은 원문 제외가 아니므로 [] 유지.'}")
needle='"5호 제외하고 읽어"는 제외 선택이다. "5호에는 해당하지 않는다고 가정"은 사건 적용 조건이며 원문 읽기 제외로 바꾸지 않는다.'
assert needle in t
t=t.replace(needle,'''원문을 어느 범위까지 읽을지와 읽은 조항을 사건에 적용할지는 별개의 판단 축이다. 먼저 원문 요청(단일/범위/전체)을 selection에 보존하고, 적용·해당 여부의 가정은 facts 또는 조사 쟁점에만 기록한다.
exclude에는 사용자가 원문 열람·답변 범위에서 빼라고 지시한 항목만 넣는다. "해당하지 않는다", "적용되지 않는다고 가정", "예외에 해당한다고 가정"이라는 사건 조건 자체는 읽기 제외 지시가 아니다. 이런 조건 때문에 전체 원문 요청을 좁히지 않는다.
두 요청의 결과를 구분하는 예:
A. "제12조 3항의 모든 호 원문을 읽고, 6호에는 해당하지 않는다고 가정해" → facts=[6호 미해당 가정], 해당 항 아래 unit="호", include=[{kind:"ALL"}], exclude=[]. 6호 원문도 읽고 그 적용 여부를 나중에 판단한다.
B. "제12조 3항 원문에서 6호는 빼고 읽어" → facts에 미해당 사실을 만들지 않음, 해당 항 아래 unit="호", include=[{kind:"ALL"}], exclude=[{kind:"SINGLE",value:{n:6}}].
출력 전에 각 exclude가 실제 원문 제외 요청에 근거하는지 검토한다. 적용 가정만 근거로 넣었다면 exclude에서 빼고 facts/쟁점에만 남긴다. 이 검토도 네 구조화 판단에 포함되며 별도 의미 추정 코드는 없다.''')
p.write_text(t)
p=C/'02_BACKEND/semantic_runtime/legal_agent/request_entry.py';t=p.read_text();oldtext="'facts':{'type':'array','items':fact,'maxItems':16},";assert oldtext in t
t=t.replace(oldtext,"'facts':{'type':'array','items':fact,'maxItems':16,\n            'description':'사용자 사건 조건·가정. 특정 호에 미해당/적용 안 됨이라는 가정은 원문 읽기 제외가 아니며 selection.exclude로 중복 변환하지 않는다.'},");p.write_text(t)
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
files={n:sha(C/n) for n in old['files']['candidate']}
save(ART/'stage.json',{**old,'roots':{**old['roots'],'candidate':str(C.relative_to(ROOT))},'files':{**old['files'],'candidate':files}})
save(ART/'integration-delta.json',{'against_main98':[n for n,h in files.items() if old['files']['baseline'].get(n)!=h], 'followup_changes':[n for n,h in files.items() if old['files']['candidate'].get(n)!=h], 'parent_observation':{'path':str((P/'trials/set-19/candidate/result.json').relative_to(ROOT)),'sha256':sha(P/'trials/set-19/candidate/result.json')},'working_unchanged':True})
print('Isolated fact/read distinction candidate; working and MAIN unchanged')
