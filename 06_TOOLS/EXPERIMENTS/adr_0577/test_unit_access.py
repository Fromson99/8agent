"""Synthetic contract checks for the isolated unit-first candidate."""
import importlib.util
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT / '02_BACKEND/lawrag/research/candidates/adr_0577/unit-first/snapshot/02_BACKEND/semantic_runtime/legal_agent/unit_access.py'
spec = importlib.util.spec_from_file_location('adr_0577_unit_access', CANDIDATE)
unit_access = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = unit_access
spec.loader.exec_module(unit_access)


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          CREATE TABLE source_unit(document_id TEXT,unit_id TEXT,parent_id TEXT,json TEXT);
          CREATE TABLE source_block(document_id TEXT,block_id TEXT,unit_id TEXT,text TEXT,source_artifact_sha256 TEXT);
        ''')
        self.db.executemany('INSERT INTO source_unit VALUES(?,?,?,?)', [
            ('D','A',None,'{"span":[1,4]}'),
            ('D','C1','A','{"span":[1,2]}'),
            ('D','C2','A','{"span":[2,3]}'),
            ('D','C3','A','{"span":[3,4]}')])
        self.db.executemany('INSERT INTO source_block VALUES(?,?,?,?,?)', [
            ('D','1','C1','외국인 인수 신고 대상','artifact-1'),
            ('D','2','C2','적용 예외 규정','artifact-1'),
            ('D','3','C3','제출 서류','artifact-1')])
        self.units = {('D','A'):{'span':[1,4],'parent':None,'title':'제1조','family':'조'},
                      ('D','C1'):{'span':[1,2],'parent':'A','title':'①','family':'항'},
                      ('D','C2'):{'span':[2,3],'parent':'A','title':'②','family':'항'},
                      ('D','C3'):{'span':[3,4],'parent':'A','title':'③','family':'항'}}


def test_localize_and_bounded_context(tmp_path):
    store = Store(tmp_path/'source.sqlite')
    uid, basis = unit_access.choose_unit(store, store.units, 'D', 'A', '외국인 인수 신고')
    assert uid == 'C1' and basis['basis'] == 'lexical_block_overlap'
    card = unit_access.neighborhood(store, store.units, 'D', uid)
    assert card['focus']['preview'] == '외국인 인수 신고 대상'
    assert [item['unit_id'] for item in card['after']] == ['C2']
    assert card['expansion']['parent_unit_id'] == 'A'
    assert all(not item['citation_eligible'] for item in card['after'])
    assert unit_access.choose_unit(store, store.units, 'D', 'A', '전혀 다른 문장')[0] == 'A'


def test_origin_anchor_survives_unit_rename(tmp_path):
    store = Store(tmp_path/'source.sqlite')
    anchor = unit_access.origin_anchors(store, 'D', 'C1')
    store.db.execute("UPDATE source_unit SET unit_id='RENAMED' WHERE unit_id='C1'")
    store.db.execute("UPDATE source_block SET unit_id='RENAMED' WHERE unit_id='C1'")
    assert unit_access.origin_anchors(store, 'D', 'RENAMED') == anchor


def test_memory_needs_independent_positive_traces_and_never_hard_excludes(tmp_path):
    store = Store(tmp_path/'source.sqlite')
    anchors = unit_access.origin_anchors(store, 'D', 'C1')
    memory = unit_access.UnitPathMemory(tmp_path/'memory.sqlite')
    base = dict(purpose_id='find_applicable_rule', anchors=anchors, action='READ',
                decision='FOLLOW', outcome='useful', reason='적용 규정 원문 확인',
                generation_id='g1')
    memory.record(question_hash='q1', **base)
    memory.record(question_hash='q1', **base)
    assert memory.guide(purpose_id='find_applicable_rule', anchors=anchors)[0]['status'] == 'OBSERVED'
    memory.record(question_hash='q2', **base)
    guide = memory.guide(purpose_id='find_applicable_rule', anchors=anchors)[0]
    assert guide['status'] == 'SUGGEST' and guide['supporting_questions'] == 2
    assert guide['hard_exclusion'] is False
    assert not memory.guide(purpose_id='different_purpose', anchors=anchors)
    memory.record(question_hash='q3', **{**base, 'outcome':'not_useful'})
    assert memory.guide(purpose_id='find_applicable_rule', anchors=anchors)[0]['status'] == 'OBSERVED'
    memory.close()
