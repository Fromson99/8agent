"""A complete exact unit remains eligible without pretending article coverage."""
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CANDIDATE = ROOT/'02_BACKEND/lawrag/research/candidates/adr_0581/unit-expansion/snapshot/02_BACKEND/semantic_runtime/legal_agent/source_selection.py'
spec = importlib.util.spec_from_file_location('adr_0581_source_selection', CANDIDATE)
source_selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source_selection)


def test_unit_evidence_flows_to_selection_without_stale_article_spans():
    old = {'evidence_id':'E-old','source_id':'article:1','document_id':'D','unit_id':'A',
           'metadata':{'document_name':'규정','heading':'제1조'},
           'spans':[{'block_id':'1','start_cp':0,'end_cp':4,'text':'기존내용'}]}
    unit = {'evidence_id':'E-unit','source_id':'article:1','document_id':'D','unit_id':'A',
            'metadata':{'document_name':'규정','heading':'제1조'},
            'spans':[{'block_id':'2','start_cp':0,'end_cp':4,'text':'적용규정'}]}
    record = {'evidence':[old, unit], 'read_complete':[], 'unit_complete':['article:1'],
              'selection_complete':['article:1'],
              'selection_evidence_ids':{'article:1':['E-unit']},
              'read_extent_by_source':{'article:1':'exact'},
              'unit_choices':[{'source_id':'article:1','unit_id':'C2'}],
              'selected_for_read':['article:1'],
              'routes':{'article:1':[{'kind':'fulltext','query':'적용규정','rank':1,'branch':'global'}]},
              'query_plan':{'queries':['적용규정']},
              'packets':[{'evidence':[old, unit]}], 'discovery_mode':'fulltext'}
    reconstructed = source_selection.originals(record)
    assert reconstructed['article:1']['text'] == '적용규정'
    assert reconstructed['article:1']['read_extent'] == 'exact'
    assert reconstructed['article:1']['read_unit_id'] == 'C2'
    calls = []
    def invoke(system, data, schema, phase, timeout):
        calls.append((system, data, phase))
        if phase == 'source-omission-review':
            return {'issues':[], 'choices':[], 'expansion':{
                'scope':'SUFFICIENT','source':None,'reason':'현재 원문으로 충분함','query':None}}
        return {'issues':[], 'choices':[{'id':'C001','reason':'적용 규정'}]}
    result = source_selection.select_sources('적용규정', record, invoke, remaining_seconds=30)
    assert result['final_ids'] == ['article:1']
    assert result['actual_selector_excerpts'][0]['cards'][0]['read_extent'] == 'exact'
    assert [e['evidence_id'] for p in result['final_packets'] for e in p['evidence']] == ['E-unit']
    assert '조의 다른 항' in calls[0][0]
    assert [call[2] for call in calls] == ['source-triage','source-omission-review']
    assert result['expansion_request']['scope'] == 'SUFFICIENT'


def test_invalid_expansion_proposal_preserves_selected_original():
    text = '적용 규정'
    evidence = {'evidence_id':'E1','source_id':'article:1','document_id':'D','unit_id':'A',
        'metadata':{'document_name':'규정','heading':'제1조'},
        'spans':[{'block_id':'1','start_cp':0,'end_cp':len(text),'text':text}]}
    record = {'evidence':[evidence],'read_complete':[],'unit_complete':['article:1'],
        'selection_complete':['article:1'],'selection_evidence_ids':{'article:1':['E1']},
        'read_extent_by_source':{'article:1':'exact'},
        'unit_choices':[{'source_id':'article:1','unit_id':'C1'}],
        'selected_for_read':['article:1'],'routes':{'article:1':[]},
        'query_plan':{'queries':[]},'packets':[{'evidence':[evidence]}],
        'discovery_mode':'fulltext'}
    def invoke(system, data, schema, phase, timeout):
        if phase == 'source-triage':
            return {'issues':[],'choices':[{'id':'C001','reason':'적용 규정'}]}
        return {'issues':[],'choices':[], 'expansion':{
            'scope':'ARTICLE','source':'C999','reason':'다른 항의 예외 확인 필요','query':None}}
    result = source_selection.select_sources('적용 규정',record,invoke,remaining_seconds=30)
    assert result['final_ids']==['article:1']
    assert result['expansion_request'] is None
    assert 'selected source' in result['expansion_rejected']
