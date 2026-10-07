"""Reject unread exclusions and retain complete, ACL-bound lexical menus."""
import json
import sqlite3
import pytest
from jsonschema import validate,ValidationError
from semantic_runtime.legal_agent.law_navigation import decision_schema
from semantic_runtime.unit_fulltext import UnitFulltextIndex


@pytest.mark.parametrize('status,valid', [('DEFER',True),('EXCLUDE',False),('KEEP',False)])
def test_candidate_cannot_be_adopted_or_excluded_from_preview(status,valid):
    view={'laws':[],'basis':[],'presentation_id':'P1',
          'branches':[{'id':'unread','allowed_decisions':['DEFER']}]}
    schema=decision_schema(view,{}, {'unread'})
    value={'presentation_id':'P1','law_decisions':[],
           'branch_decisions':[{'branch_id':'unread','status':status,'reason':'preview is unrelated','issue_refs':['Q1'],'basis_refs':[]}],
           'next_action':'PENDING','targets':[],'queries':[],'issue_refs':['Q1'],'basis_refs':[],
           'reason':'continue elsewhere','notes':'','evidence_sufficient':False,'sufficiency_reason':''}
    if valid:validate(value,schema)
    else:
        with pytest.raises(ValidationError):validate(value,schema)


def test_read_branch_can_be_excluded_without_excluding_unread_candidates():
    view={'laws':[],'basis':[{'id':'E1','branch_id':'read'}],'presentation_id':'P1',
          'branches':[{'id':'unread','allowed_decisions':['DEFER']},
                      {'id':'read','allowed_decisions':['KEEP','DEFER','EXCLUDE']}]}
    schema=decision_schema(view,{}, {'unread','read'})
    value={'presentation_id':'P1','law_decisions':[],
           'branch_decisions':[{'branch_id':'read','status':'EXCLUDE','reason':'read rule is unrelated','issue_refs':['Q1'],'basis_refs':['E1']}],
           'next_action':'PENDING','targets':[],'queries':[],'issue_refs':['Q1'],'basis_refs':[],
           'reason':'continue elsewhere','notes':'','evidence_sufficient':False,'sufficiency_reason':''}
    validate(value,schema)
    value['branch_decisions'][0]['branch_id']='unread'
    with pytest.raises(ValidationError):validate(value,schema)


def test_group_menu_orders_relevant_match_first_without_pruning_or_score_exposure():
    db=sqlite3.connect(':memory:')
    db.executescript('CREATE TABLE unit(key TEXT,source_id TEXT,document_id TEXT,json TEXT); CREATE VIRTUAL TABLE unit_fts USING fts5(key UNINDEXED,text);')
    for key,sid,did,text in [('a','a-source','a-law','지정 기타 기타 기타'),
                             ('z','z-source','z-law','내부회계관리자 지정'),
                             ('y','a-second','z-law','지정 기타 기타 기타')]:
        db.execute('INSERT INTO unit VALUES (?,?,?,?)',(key,sid,did,json.dumps({'source_id':sid})))
        db.execute('INSERT INTO unit_fts VALUES (?,?)',(key,text))
    idx=UnitFulltextIndex.__new__(UnitFulltextIndex);idx.manifest={'index_sha256':'f'*64}
    idx.source_ids={'a-source','z-source','a-second'};idx.check_unchanged=lambda:None
    laws=idx.law_groups_page(db,['내부회계관리자','지정'],limit=1)
    assert laws['total']==2 and laws['items'][0]['document_id']=='z-law'
    next_laws=idx.law_groups_page(db,['내부회계관리자','지정'],cursor=laws['next_cursor'],limit=1)
    assert next_laws['items'][0]['document_id']=='a-law'
    articles=idx.article_groups_page(db,['내부회계관리자','지정'],'z-law',limit=1)
    assert articles['total']==2 and articles['items'][0]['source_id']=='z-source'
    restricted=idx.law_groups_page(db,['내부회계관리자','지정'],{'a-source'})
    assert restricted['total']==1 and restricted['items'][0]['document_id']=='a-law'
    assert 'score' not in json.dumps([laws,next_laws,articles,restricted])
