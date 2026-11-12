"""Freeze ADR-1491 before any model call: baseline = MAIN204 release code, candidate = MAIN204 + single answer
write (short planning calls decide the reads, the full answer is written once). Eight financial CM standalone
questions chosen from ADR-1482 before any run of this change: the five with the most answer rewrites whose
required articles were registered (cm-005/016/017/043/048) and three whose required articles were reached by
answer-round reads in earlier runs (cm-018 제78조, cm-029 하위 규정, cm-030 시행령 제170조).
User 2026-11-11: "구현하고 회귀없ㅎ는지 실험해보자 ... 몇몇 질문만 선별해"."""
from common import *
import shutil
P1482=ROOT/'04_EXPERIMENTS/ADR/ADR-1482-main187-r5-fixes-answer-r8-cm50-qwen-run2/artifacts'
AUDIT=ROOT/'09_ARTIFACTS/AUDITS/20261111-guided-answer-single-write'
ORDER=['cm-005','cm-016','cm-017','cm-043','cm-048','cm-018','cm-029','cm-030']
DES.mkdir(parents=True,exist_ok=False)
ptr=read(ROOT/'01_DATA/ACTIVE/local/ACTIVE_RELEASE.json');rel=read(ROOT/'08_DEPLOYMENT/RELEASES/sql-loops-20261111-r1/release.json');assert rel['release_id']=='sql-loops-20261111-r1'
base_root=ROOT/rel['code_root'];assert all(sha(base_root/n)==h for n,h in rel['files'].items())
staged=AUDIT/'staged';files={n:sha(staged/n) for n in rel['files']};changed=sorted(n for n in files if files[n]!=rel['files'][n])
assert {'02_BACKEND/semantic_runtime/legal_agent/guided_answer.py','02_BACKEND/semantic_runtime/legal_agent/completion_execution.py','02_BACKEND/semantic_runtime/legal_agent/law_candidates.py','00_SYSTEM/LEGAL_AGENT/profile-unified-v6.json'}<=set(changed),changed
code=ART/'candidate-code';shutil.copytree(staged,code,symlinks=True)
assert all(sha(code/n)==h for n,h in files.items())
put(DES/'arms.json',{'baseline':{'code_root':rel['code_root'],'files':rel['files'],'label':'sql-loops-20261111-r1 (MAIN204)'},
 'candidate':{'code_root':str(code.relative_to(ROOT)),'files':files,'label':'MAIN204 + single answer write','changed':changed}})
old=read(P1482/'design/baseline.json');put(DES/'baseline.json',{'pointer':ptr,'release':{**old['release'],'code_root':rel['code_root'],'release_id':rel['release_id']},'note':'data_path is the ADR-1482 generation, checked against the Gold dataset hash in live.py'})
cases={c['id']:c for c in read(P1482/'design/live-cases.json')};grades={g['id']:g for g in read(P1482/'design/grading-only.json')}
put(DES/'live-cases.json',[{k:v for k,v in cases[i].items() if k!='provider_profile'} for i in ORDER])
put(DES/'grading-only.json',[grades[i] for i in ORDER])
criteria={'authorization':'User 2026-11-11: "구현하고 회귀없ㅎ는지 실험해보자 ... 몇몇 질문만 선별해"; CM question authorization as ADR-1482',
 'scope':__doc__,
 'required':['Primary, no regression: required articles acquired, candidate >= baseline - 1 over the eight questions (ADR-1481/1482 repeats of identical code differed by 1 to 2 of 90); cited, candidate >= baseline - 2',
  'Mechanism: each candidate question has exactly one full answer write, the others are planning calls',
  'Speed: guided-answer model seconds, candidate at most 60% of baseline',
  'All 16 requests HTTP 200; no more unknown calls than baseline; source/ACL integrity'],
 'limits':{'physical_total':260,'per_request':40,'per_physical_seconds':180,'reported_cost_usd':2.5,'time_box_minutes':90,'workers':1},
 'stop':'UNKNOWN ends that request without retry; three consecutive UNKNOWN, source/ACL/code/resource violation, budget or time box stop the batch. No other heavy work during cells.',
 'quality_certified':False,'in_sample':True,'order':ORDER,
 'note':'One run per arm, baseline before candidate for each question; a difference of one or two articles is within run-to-run variance. Questions were chosen from earlier runs, so this is not an out-of-sample result.'}
put(DES/'criteria.json',criteria)
put(DES/'provider-policy.json',read(base_root/'00_SYSTEM/EXPERIMENT_PROVIDER_ROUTING.json'))
for name in ('authorization.json','oracle-gold.json','embed-validate.json','embed-profile-files.json','deviation.json','question-source.json'):shutil.copyfile(P1482/'design'/name,DES/name)
transport=ART/'transport';shutil.copytree(P1482/'transport',transport)
pins=read(transport/'transport-pins.json');assert all(sha(transport/n)==h for n,h in pins['files'].items())
paths=[*Path(__file__).parent.glob('*.py'),*(DES/x for x in ('criteria.json','live-cases.json','grading-only.json','authorization.json','provider-policy.json','arms.json','oracle-gold.json'))]
put(DES/'freeze-live.json',{'files':{str(p.relative_to(ROOT)):sha(p) for p in paths if p.name!='report.py'},'selected_pointer':ptr,'model_calls_before_freeze':0})
print('Frozen MAIN204 baseline and single-write candidate,',len(changed),'changed files, 8 questions x 2 arms; model 0')
