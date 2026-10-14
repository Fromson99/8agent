from pathlib import Path
import subprocess
R=Path(__file__).resolve().parents[3];C=R/'02_BACKEND/lawrag/research/candidates/adr_0773/successful-publication';S=C/'snapshot';T=S/'05_TESTS/CONTRACTS'
s=(R/'06_TOOLS/EXPERIMENTS/adr_0683/test_core_routes.py').read_text()
s=s.replace("if stage=='READ':", "if stage=='COMPOSE':payload={'text':'모의 최종 답변','claims':[{'text':'모의 판단'}]}\n            if stage=='READ':")
s=s.replace("return {'goal_id': goal, 'revision': revision, 'route_id': route, 'status': 'READY'}", "result={'goal_id': goal, 'revision': revision, 'route_id': route, 'status': 'READY','intake_id':intake['id']}\n        if ready:publish(cases,result,p)\n        return result")
pos=s.index('@pytest.fixture')
s=s[:pos]+'''def publish(cases,result,p,status='PUBLISHED'):
    import sqlite3
    from semantic_runtime.legal_agent.successful_answer import record
    cases.db.execute("UPDATE sw_intake SET status='COMPLETED' WHERE id=?",(result['intake_id'],))
    envelope={'run_id':'synthetic-'+str(result['route_id']),'answer':{'text':'모의 최종 답변','claims':[{'text':'모의 판단'}]}}
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE publication(singleton INTEGER,status TEXT,result_hash TEXT)')
    db.execute('INSERT INTO publication VALUES(1,?,?)',(status,digest(envelope)))
    work=SimpleNamespace(db=db,run=lambda:{'status':'COMPLETED'})
    try:
        with cases.transaction():record(cases,result,p,envelope,work)
    finally:db.close()


'''+s[pos:]
(T/'test_successful_core_routes.py').write_text(s)
p=T/'test_bounded_wiki_recall.py';s=(R/'05_TESTS/CONTRACTS/test_bounded_wiki_recall.py').read_text();start=s.index('ROOT=');end=s.index('\ndef seed',start);s=s[:start]+'from test_successful_core_routes import routes\n'+s[end:];p.write_text(s)
for name in ('test_successful_core_routes.py','test_bounded_wiki_recall.py','test_successful_shortcut.py'):
 target='05_TESTS/CONTRACTS/'+name
 if name=='test_successful_shortcut.py':continue
 cmd=[str(R/'.venv/bin/python'),'06_TOOLS/run_tool.py','adr_candidate.py','register',str(C),'--target',target]
 if (R/target).exists():cmd+=['--source',target]
 else:cmd+=['--upstream-state','absent']
 subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
# Validate membership against only the actual offered successful records.
p=S/'02_BACKEND/lawrag/pipeline/legal_wiki_compiler.py';s=p.read_text().replace('admit(proposal,snapshots,catalogue)','admit(proposal,admitted,catalogue)');p.write_text(s)
