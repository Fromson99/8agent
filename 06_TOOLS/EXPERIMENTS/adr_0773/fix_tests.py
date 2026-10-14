from pathlib import Path
S=Path(__file__).resolve().parents[3]/'02_BACKEND/lawrag/research/candidates/adr_0773/successful-publication/snapshot'
p=S/'05_TESTS/CONTRACTS/test_successful_shortcut.py';s=p.read_text();pos=s.index('STATES=');s=s[:pos]+'''def simulate_legacy_or_corrupt_ledger(db):
    # Synthetic fault injection only: production immutable triggers are untouched.
    for row in db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='sw_event'").fetchall():
        db.execute('DROP TRIGGER "'+row[0]+'"')

'''+s[pos:];s=s.replace('r=routes;repo=r.cases.shortcut;db=repo.db','r=routes;repo=r.cases.shortcut;db=repo.db\n    simulate_legacy_or_corrupt_ledger(db)').replace("kind,entity,review,trashed,revision) VALUES('shortcut',?,'REJECTED',0,1)","kind,entity,workspace,review,trashed,revision,changed_at) VALUES('shortcut',?,'t','REJECTED',0,1,0)")
s=s.replace('r=routes;r.cases.db.execute', 'r=routes;simulate_legacy_or_corrupt_ledger(r.cases.db);r.cases.db.execute')
s=s.replace('client,send,t,p,runtime=unified','client,send,t,p,runtime=unified\n    p[\'authenticated\']=True')
s=s.replace('        repo.db.execute("DELETE FROM sw_event', '        simulate_legacy_or_corrupt_ledger(repo.db)\n        repo.db.execute("DELETE FROM sw_event');p.write_text(s)
p=S/'02_BACKEND/lawrag/pipeline/legal_wiki_compiler.py';p.write_text(p.read_text().replace('admit(proposal,snapshots,catalogue or {})','admit(proposal,admitted,catalogue or {})'))
