"""Research-only expansion decision and bounded READ contracts."""
import importlib.util
import sys
from pathlib import Path

import pytest

from test_unit_access import Store


ROOT = Path(__file__).resolve().parents[3]
SNAP = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0581/unit-expansion/snapshot/02_BACKEND/semantic_runtime/legal_agent'
sys.path.insert(0, str(ROOT/'02_BACKEND'))
import semantic_runtime.legal_agent as package
package.__path__.insert(0, str(SNAP))
from semantic_runtime.legal_agent import unit_expansion, source_selection
from semantic_runtime.legal_agent.repository import text_hash


def test_decision_rejects_unselected_local_target():
    sources = {'article:1': {'read_extent':'exact'}}
    labels = {'C001':'article:1'}
    assert source_selection.checked_expansion(
        {'scope':'SUFFICIENT','source':None,'reason':'현재 원문으로 충분함','query':None},
        ['C001'], sources, labels)['scope'] == 'SUFFICIENT'
    with pytest.raises(ValueError, match='selected source'):
        source_selection.checked_expansion(
            {'scope':'ARTICLE','source':'C999','reason':'예외 항목 확인 필요','query':None},
            ['C001'], sources, labels)
    with pytest.raises(ValueError, match='substantive query'):
        source_selection.checked_expansion(
            {'scope':'SEARCH','source':None,'reason':'다른 규정 확인 필요','query':' '},
            ['C001'], sources, labels)


class Repo:
    def __init__(self):
        self.rows = {}
    def evidence(self, ident=None):
        return self.rows[ident] if ident is not None else list(self.rows.values())


class FakeSources:
    def __init__(self, store):
        self.store = store
        self.matcher = type('Matcher', (), {'units':store.units})()
        self.tools = type('Tools', (), {'sources':{'article:1':{
            'document_id':'D','unit_id':'A','blocks':[
                {'block_id':str(i), 'text':t} for i,t in enumerate(
                    ['외국인 인수 신고 대상','적용 예외 규정','제출 서류'], 1)]}}})()
        self.repo = Repo()
        self.source = type('Verifier', (), {'verify':lambda self, e: None})()
        self.handles = {}
    def handle(self, kind, identity):
        label = kind+str(len(self.handles)+1)
        self.handles[label] = identity
        return label
    def resolve(self, handle, kinds):
        assert handle[0] in kinds
        return self.handles[handle]
    def execute(self, action, action_id):
        assert action['tool'] == 'read'
        node = self.handles[action['args']['target']]
        uid = node['unit_id']
        if action['args']['extent'] == 'article':
            blocks = [1,2,3]
        elif action['args']['extent'] == 'subtree':
            lo, hi = self.store.units[('D',uid)]['span']
            blocks = list(range(lo,hi))
        else:
            blocks = [self.store.units[('D',uid)]['span'][0]]
        ids = []
        for i in blocks:
            text = self.store.db.execute('SELECT text FROM source_block WHERE block_id=?',(str(i),)).fetchone()[0]
            eid = 'E'+str(i)
            self.repo.rows[eid] = {'evidence_id':eid,'source_id':'article:1','document_id':'D',
                'unit_id':'A','generation_id':'G','source_artifact_hash':'H',
                'text_hash':text_hash(text),'metadata':{'document_name':'규정','heading':'제1조'},
                'spans':[{'block_id':str(i),'start_cp':0,'end_cp':len(text),'text':text}]}
            ids.append(eid)
        return {'status':'OK','evidence_ids':ids,'coverage':{'complete':True},'next_cursor':None}


def base_record(sources):
    sources.execute({'tool':'read','args':{'target':sources.handle('U',{
        'document_id':'D','unit_id':'C1'}),'extent':'exact','cursor':None}}, 'initial')
    return {'final_ids':['article:1'],'article_unread_remainder':['article:1'],
        'unit_choices':[{'source_id':'article:1','unit_id':'C1'}],
        'selection_evidence_ids':{'article:1':['E1']},'read_extent_by_source':{'article:1':'exact'},
        'read_complete':[],'unit_complete':['article:1'],'selection_complete':['article:1'],
        'selected_for_read':['article:1'],'read_partial':[], 'routes':{},
        'query_plan':{'queries':[]},'evidence':sources.repo.evidence(),
        'packets':unit_expansion.evidence_packets('질문',sources.repo.evidence())}


@pytest.mark.parametrize('scope,expected',[
    ('NEIGHBORS',{'E1','E2'}),('PARENT',{'E1','E2','E3'}),('ARTICLE',{'E1','E2','E3'})])
def test_local_expansion_reads_only_canonical_article(tmp_path, scope, expected):
    sources = FakeSources(Store(tmp_path/'data.sqlite'))
    record = base_record(sources)
    request = {'scope':scope,'source_id':'article:1','reason':'다른 항의 예외 확인 필요'}
    receipt = unit_expansion.execute_local_expansion(sources,record,request,'질문')
    assert receipt['status'] == 'COMPLETE'
    assert set(record['selection_evidence_ids']['article:1']) == expected
    assert record['read_extent_by_source']['article:1'] == (
        'neighbors' if scope == 'NEIGHBORS' else 'article')
    if scope != 'NEIGHBORS':
        assert not record['article_unread_remainder']
    assert all(e['source_id']=='article:1' for e in record['evidence'])


def test_local_expansion_budget_rejects_before_read(tmp_path):
    sources = FakeSources(Store(tmp_path/'data.sqlite'))
    record = base_record(sources)
    with pytest.raises(ValueError, match='character budget'):
        unit_expansion.execute_local_expansion(sources,record,
            {'scope':'ARTICLE','source_id':'article:1','reason':'전체 예외 확인 필요'},
            '질문',max_chars=1)
    assert record['selection_evidence_ids']['article:1'] == ['E1']


def test_search_expansion_is_scoped_and_single_query(tmp_path):
    sources = FakeSources(Store(tmp_path/'data.sqlite'))
    record = base_record(sources)
    sources.root = sources.handle('R',{'documents':['D']})
    sources.tools.sources['article:2'] = {'document_id':'D','unit_id':'C3',
        'blocks':[{'block_id':'3','text':'제출 서류'}]}
    target = sources.handle('U',{'document_id':'D','unit_id':'C3'})
    ordinary_execute = sources.execute
    searches = []
    def execute(action, action_id):
        if action['tool'] == 'search':
            searches.append(action)
            return {'status':'OK','items':[{'target':target,'article_source_id':'article:2',
                'read_action':{'args':{'extent':'exact'}}}],
                'next_cursor':None,'search_receipt':{'total':1}}
        if action['tool'] == 'read':
            text = '제출 서류'
            sources.repo.rows['E-new'] = {'evidence_id':'E-new','source_id':'article:2',
                'document_id':'D','unit_id':'C3','generation_id':'G',
                'source_artifact_hash':'H','text_hash':text_hash(text),
                'metadata':{'document_name':'규정','heading':'제3조'},
                'spans':[{'block_id':'3','start_cp':0,'end_cp':len(text),'text':text}]}
            return {'status':'OK','evidence_ids':['E-new'],
                    'coverage':{'complete':True},'next_cursor':None}
        return ordinary_execute(action,action_id)
    sources.execute = execute
    receipt = unit_expansion.execute_search_expansion(sources,record,
        {'scope':'SEARCH','source_id':None,'query':'제출 서류','reason':'다른 규정 확인 필요'},
        '질문')
    assert receipt['status']=='COMPLETE'
    assert receipt['new_source_ids']==['article:2']
    assert len(searches)==1
    assert searches[0]['args']['target']==sources.root
    assert record['selection_evidence_ids']['article:2']==['E-new']
