"""Tiny SQLite contract/plan checks; no corpus or latency benchmark."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace as S

import pytest

SNAPSHOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(SNAPSHOT/'02_BACKEND'))
from semantic_runtime.legal_agent import definition_entry as de
from semantic_runtime.legal_agent.errors import ContractError
from semantic_runtime.legal_agent.repository import text_hash
from semantic_runtime.reference_build import shared_reference_schema

OLD_SQL = ('SELECT l.reference_id,r.json FROM definition_reference l LEFT JOIN reference r '
           'ON r.id=l.reference_id WHERE l.definition_id=? ORDER BY l.reference_id')
LINK_SQL = 'SELECT reference_id FROM definition_reference WHERE definition_id=? ORDER BY reference_id'
POINT_SQL = 'SELECT json FROM reference WHERE id=?'


def fixture(shared=True):
    db=sqlite3.connect(':memory:')
    db.executescript('CREATE TABLE reference(id TEXT PRIMARY KEY,document_id TEXT,json TEXT);'
        'CREATE TABLE definition_reference(definition_id TEXT,reference_id TEXT,PRIMARY KEY(definition_id,reference_id));')
    if shared: shared_reference_schema(db)
    text='용어는 제2조를 따른다.'
    source={'document_id':'DOC','document_name':'원법','source_artifact_sha256':'artifact',
            'unit_id':'U1','heading':'제1조','blocks':[{'block_id':'B1'}]}
    target={'document_id':'TARGET_DOC','document_name':'대상법','source_artifact_sha256':'target-artifact',
            'unit_id':'U2','heading':'제2조','blocks':[{'block_id':'B2'}]}
    definition={'id':'D1','source_id':'S1','unit_id':'U1','document_id':'DOC','block_id':'B1',
        'source_text':text,'source_text_sha256':text_hash(text),'source_artifact_sha256':'artifact',
        'term_start':0,'term_end':2,'label':'용어','key':'용어'}
    references=[]
    for ident in ('RB','RA'):  # Reverse insertion order must not change output order.
        ref={'id':ident,'source_id':'S1','document_id':'DOC','block_id':'B1',
            'source_text':text,'source_text_sha256':text_hash(text),'locator':'제2조',
            'mention_start':4,'mention_end':7,'mention_text':'제2조','resolution':'EXACT_UNIT',
            'targets':[{'source_id':'S2','unit_id':'U2','block_ids':['B2']}]}
        references.append(ref)
        db.execute('INSERT INTO reference VALUES(?,?,?)',(ident,'DOC',json.dumps(ref,ensure_ascii=False)))
        db.execute('INSERT INTO definition_reference VALUES(?,?)',('D1',ident))
    session=S(tools=S(db=db,definitions={'D1':definition},sources={'S1':source,'S2':target}),
        store=S(source=lambda did,bid:{'text':text,'unit_id':'U1'}),scope={'DOC','TARGET_DOC'},
        matcher=S(units={('DOC','U1'):{'surface':'제1조'},('TARGET_DOC','U2'):{'surface':'제2조'}},
                  _unit_sources=lambda did,uid:['S1'] if (did,uid)==('DOC','U1') else ['S2']))
    return session,{'definition_id':'D1','question_span':{'start':0,'end':2,'text':'용어'}},references


def expected(match):
    location={'document_id':'DOC','source_id':'S1','unit_id':'U1','document_name':'원법','heading':'제1조','coordinate':'제1조'}
    target={'document_id':'TARGET_DOC','source_id':'S2','unit_id':'U2','document_name':'대상법','heading':'제2조','coordinate':'제2조'}
    return {**deepcopy(match),'label':'용어','definition':location,'scope_status':'UNRESOLVED','scope_hint':[],
        'verification':'EXACT_ORIGINAL_LOCATION','citation_eligible':False,
        'connections':[{'reference_id':ident,'locator':'제2조','resolution':'EXACT_UNIT','targets':[deepcopy(target)]}
                       for ident in ('RA','RB')]}


@pytest.mark.parametrize('shared',[False,True])
def test_table_and_compact_view_preserve_exact_result_and_order(shared):
    session,match,_=fixture(shared)
    db=session.tools.db
    try:
        old=list(db.execute(OLD_SQL,('D1',)))
        point=[(ident,db.execute(POINT_SQL,(ident,)).fetchone()[0]) for ident, in db.execute(LINK_SQL,('D1',))]
        assert old==point
        statements=[];db.set_trace_callback(statements.append)
        assert de.verified(session,match)==expected(match)
        assert not any('LEFT JOIN' in sql for sql in statements)
        assert len([sql for sql in statements if sql.startswith('SELECT json FROM reference WHERE id=')])==2
    finally:db.close()


@pytest.mark.parametrize('failure,pattern',[
    ('orphan','linked reference missing'),('source_hash','original/hash mismatch'),
    ('source_scope','outside request scope'),('reference_hash','reference witness mismatch')])
def test_existing_failure_contracts_remain(failure,pattern):
    session,match,references=fixture()
    db=session.tools.db
    try:
        if failure=='orphan':db.execute('INSERT INTO definition_reference VALUES(?,?)',('D1','MISSING'))
        elif failure=='source_hash':session.tools.definitions['D1']['source_text_sha256']='bad'
        elif failure=='source_scope':session.scope.remove('DOC')
        elif failure=='reference_hash':
            ref=references[0];ref['source_text_sha256']='wrong'
            # Keep a view row visible, but bind it to an incorrect witness hash.
            db.execute('INSERT INTO reference_body VALUES(?,?)',('wrong',ref['source_text']))
            ref.pop('source_text')
            db.execute('UPDATE reference_payload SET json=? WHERE id=?',(json.dumps(ref),'RB'))
        with pytest.raises(ContractError,match=pattern):de.verified(session,match)
    finally:db.close()


def test_target_outside_acl_is_preserved_as_scope_limited():
    session,match,_=fixture()
    try:
        session.scope.remove('TARGET_DOC')
        result=de.verified(session,match)
        assert [row['reference_id'] for row in result['connections']]==['RA','RB']
        assert all(row['targets']==[] and row['scope_limited'] is True for row in result['connections'])
    finally:session.tools.db.close()


def test_compact_query_plans_use_point_indexes_without_materialization():
    session,_,_=fixture()
    db=session.tools.db
    try:
        prior=[r[3] for r in db.execute('EXPLAIN QUERY PLAN '+OLD_SQL,('D1',))]
        assert any('MATERIALIZE reference' in row for row in prior)
        for sql,key in ((LINK_SQL,'D1'),(POINT_SQL,'RA')):
            plan=[r[3] for r in db.execute('EXPLAIN QUERY PLAN '+sql,(key,))]
            assert plan and all('MATERIALIZE' not in row and 'SCAN ' not in row for row in plan)
            assert all('SEARCH ' in row and 'INDEX' in row for row in plan)
    finally:db.close()
