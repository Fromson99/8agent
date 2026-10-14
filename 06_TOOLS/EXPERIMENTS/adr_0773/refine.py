from pathlib import Path
import json,hashlib
R=Path(__file__).resolve().parents[3];S=R/'02_BACKEND/lawrag/research/candidates/adr_0773/successful-publication/snapshot'
p=S/'02_BACKEND/semantic_runtime/legal_agent/successful_answer.py';s=p.read_text().replace('from ..ad_store import table_exists','from ..ad_store import table_exists, excluded').replace("if not table_exists(repo.db,'goal'):return []","if not table_exists(repo.db,'goal') or excluded(repo.db,'shortcut',investigation):return []").replace('SELECT payload,hash FROM sw_event WHERE aggregate_id=? AND kind=\'ANSWER_PUBLISHED\' ORDER BY seq DESC','SELECT payload,hash,seq FROM sw_event WHERE aggregate_id=? AND kind=\'ANSWER_PUBLISHED\' ORDER BY seq DESC').replace("AND run=?\",(investigation,p['run_id']))", "AND run=? AND seq>?\",(investigation,p['run_id'],row['seq']))")
s=s.replace("AND run=?\",(case['id'],run)).fetchone()", "AND run=? ORDER BY seq DESC LIMIT 1\",(case['id'],run)).fetchone()")
s=s.replace("    else:repo._event(case['scope']", "    if not existing or not any(p['run_id']==run for p in receipts(repo,case['id'])):repo._event(case['scope']")
p.write_text(s)
