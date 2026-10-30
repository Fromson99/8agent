"""Batch journal reads preserve exact spans, corruption checks and bounded SQL."""
import json
import sqlite3
from types import SimpleNamespace
import pytest
from semantic_runtime.legal_agent.repository import WorkRepository,text_hash
from semantic_runtime.legal_agent.errors import ContractError,ProposalError

@pytest.mark.parametrize('count',[0,1,80])
def test_batch_matches_individual_originals_with_two_selects(count):
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.executescript('CREATE TABLE evidence_unit(evidence_id TEXT PRIMARY KEY,text_hash,metadata_json);CREATE TABLE evidence_span(evidence_id TEXT,ordinal INTEGER,text,PRIMARY KEY(evidence_id,ordinal));')
    for i in range(count):
        parts=[f'원문 {i}\n','  조건·예외 ']
        db.execute('INSERT INTO evidence_unit VALUES(?,?,?)',(str(i),text_hash('\n'.join(parts)),json.dumps({'version':'1'})))
        for j in (1,0):db.execute('INSERT INTO evidence_span VALUES(?,?,?)',(str(i),j,parts[j]))
    statements=[];db.set_trace_callback(statements.append);obj=SimpleNamespace(db=db)
    rows=WorkRepository.evidence(obj)
    assert len(rows)==count and len(statements)==(2 if count else 1)
    for row in rows:
        assert WorkRepository.evidence(obj,row['evidence_id'])==row
        assert [s['ordinal'] for s in row['spans']]==[0,1]
    with pytest.raises(ProposalError):WorkRepository.evidence(obj,'missing')
    if count:
        db.execute('UPDATE evidence_span SET text=? WHERE evidence_id=? AND ordinal=0',('변조','0'))
        with pytest.raises(ContractError):WorkRepository.evidence(obj)
    db.close()
