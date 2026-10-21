"""Offline parent input/need-transition accounting; never a product dependency."""
from pathlib import Path
import gzip
import hashlib
import json
import sqlite3

R=Path(__file__).resolve().parents[3]
A=R/'04_EXPERIMENTS/ADR/ADR-0948-research-decision-live-repeat'
out={}
for p in sorted((A/'artifacts/run-001').glob('*/*/calls.json')):
    case=p.parent;reviews=[]
    for row in json.loads(p.read_text()):
        if row['phase']!='workflow-items':continue
        with gzip.open(case/'wire'/f'{row["call"]:03d}.json.gz','rt') as f:wire=json.load(f)
        view=json.loads(wire['messages'][1]['content'])['view']
        reviews.append({'call':row['call'],'mode':view.get('review_mode'),
            'new_originals':len(view.get('new_evidence_ids',[])),
            'budget':view.get('investigation_budget'),
            'attempt_statuses':[r['status'] for r in view.get('research_task_history',[])],
            'attempts_with_no_new_originals':sum(not r.get('new_evidence_ids') for r in view.get('research_task_history',[])),
            'need_statuses':[r['status'] for r in view.get('unresolved_research',[])]})
    states=[]
    for dbp in (case/'runtime').rglob('journal.sqlite'):
        with sqlite3.connect('file:'+str(dbp)+'?mode=ro',uri=True) as db:
            tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'workflow_state' not in tables:continue
            raw=db.execute('SELECT checkpoint_json FROM workflow_state').fetchone()
            if not raw:continue
            state=json.loads(raw[0]);board=state.get('task_board',{})
            states.append({'journal':str(dbp.relative_to(case)), 'stage':state['stage'],
                'used_followups':board.get('round'),
                'reviewed_input_count':len(board.get('reviewed_inputs',[])),
                'need_states':[{'need_id':n['need_id'],'field':n['field'],'side':n['side'],
                    'status':n['status'],'history_statuses':[r['status'] for r in n.get('history',[])],
                    'explicit_resolution_receipt':bool(n.get('resolution',{}).get('need_id')),
                    'missing_preserved':bool(n.get('missing'))}
                    for n in board.get('research_needs',{}).values()],
                'attempt_statuses':[r['status'] for r in board.get('tasks',{}).values()]})
    out[str(case.relative_to(A/'artifacts/run-001'))]={'reviews':reviews,'final_states':states,
        'empty_original_updates':sum(r['mode']=='UPDATE' and r['new_originals']==0 for r in reviews),
        'interpretation':'A zero-new-original review observes lead/attempt changes. Physical completion and legal sufficiency remain separate.'}
(A/'artifacts/transition-audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v['empty_original_updates'] for k,v in out.items()}))
