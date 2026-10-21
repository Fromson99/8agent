from pathlib import Path
import json,hashlib,sys,subprocess
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0835/connected';S=C/'snapshot';W=S/'02_BACKEND/workflow'
p=W/'risk_team_compare_workflow/task_board.py';s=p.read_text()
a=s.index('                if old:\n',s.index('            for item in item_proposals:'));b=s.index("                row['revisions'].append",a)
s=s[:a]+'''                if old:
                    retain_previous(item,old)
'''+s[b:]
pos=s.index('\ndef review(ctx,state):')
s=s[:pos]+'''
def retain_previous(item,old):
    """Keep prior grounded observations without overriding the new judgment."""
    for side in ('internal','external'):
        prior=old[side];new=item[side]
        alternatives=deepcopy(prior.get('alternatives',[]))
        if prior['citations']:
            alternatives.append({k:deepcopy(prior[k]) for k in ('text','citations','dependencies')})
        current={k:new[k] for k in ('text','citations','dependencies')}
        retained=[]
        for alternative in alternatives:
            if alternative!=current and alternative not in retained:retained.append(alternative)
        if retained:new['alternatives']=retained

'''+s[pos:]
s=s.replace("return (r['text'] or ('항목 검토 미완료 — 확보 원문 참조' if side in available_sides else '미확보'))", "return (r['text'] or ('항목 검토 미완료 — 확보 원문 참조' if side in available_sides else '미확보'))+(' (근거 미선택)' if r['text'] and not r['citations'] else '')")
p.write_text(s)
p=W/'risk_team_compare_workflow/report.py';s=p.read_text().replace("'report':{'basis':basis,'basis_status':'AUDIT_MODEL_PROPOSALS',", "'report':{'basis':basis,'basis_status':'AUDIT_MODEL_PROPOSALS','judgment_authority':'LLM_REVIEW',")
p.write_text(s)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def put(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
p=W/'risk_team_compare_workflow/manifest.json';v=json.loads(p.read_text());v['version']='1.5.0';v['files']={n:sha(W/n) for n in v['files']};put(p,v)
for p in (S/'02_BACKEND/ENGINES').rglob('*.json'):
 v=json.loads(p.read_text())
 if 'files' in v:v['files']={n:sha(S/n) for n in v['files']};put(p,v)
p=S/'00_SYSTEM/PIPELINE.json';v=json.loads(p.read_text())
for e in v['engines'].values():e['sha256']=sha(S/e['manifest'])
for d in v['workflows']['registered']:d['version']='1.5.0';d['sha256']=sha(S/d['manifest'])
put(p,v)
for p in S.rglob('*.py'):compile(p.read_text(),str(p),'exec')
sys.path.insert(0,str(R/'06_TOOLS/GENERATIONS/20260904-code-v19/COMMANDS'));import adr_candidate;adr_candidate.refresh(C)
print('Compiled and repinned workflow1.5.0 candidate')
