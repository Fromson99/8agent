from types import SimpleNamespace
from semantic_runtime.legal_agent import structure_query as sq
from test_structure_first_search import matcher


def misleading_titles():
 m=matcher();m.structures=SimpleNamespace(match=lambda q:[{'key':'다른제목','start':0,'end':4,'values':[{'kind':'TITLE','document_id':'decree','unit_id':'제6조'}]}]);return m


def test_explicit_document_directory_survives_unrelated_title_hits():
 out=sq.catalogue(misleading_titles(),['law','decree'],queries=['자본시장법'])
 assert out['items']==[{'kind':'document','document_id':'law','document_name':'자본시장과 금융투자업에 관한 법률','content_read':False}]
 assert not out['citation_eligible']


def test_unmatched_title_does_not_fabricate_document_hit():
 out=sq.catalogue(misleading_titles(),['law'],queries=['전혀없는표제'])
 assert out['items']==[] and out['total']==0
