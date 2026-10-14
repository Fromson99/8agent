from types import SimpleNamespace
import pytest
from semantic_runtime.legal_agent import structure_query as sq
from lawrag.core.legal_coordinate import find_coordinates

@pytest.mark.parametrize('s,expected',[
 ('보고 내용 <개정 2009. 1. 28.>','보고 내용'),
 ('보고 내용[제목개정 2024.3.2]','보고 내용'),
 ('보고 내용 (본조신설 2020년 1월 2일)','보고 내용'),
 ('보호 (법인에 한한다)','보호 (법인에 한한다)'),
 ('신설 사업자의 2020년 보고','신설 사업자의 2020년 보고'),
 ('기간 <개정 절차에 따른다>','기간 <개정 절차에 따른다>'),
 ('기간 <개정 2020.1.1]','기간 <개정 2020.1.1]'),
 ('',''),(None,'')])
def test_only_metadata_annotations_are_removed(s,expected):
 assert sq.matching_heading(s)==expected

def test_matching_drops_annotation_but_keeps_original_and_threshold(monkeypatch):
 from semantic_runtime import fulltext
 monkeypatch.setattr(fulltext,'question_terms',lambda s:s.split())
 title='alpha beta gamma <개정 2009. 1. 28.>'
 m=SimpleNamespace(stored_coordinates={('doc','1'):find_coordinates('제1조')[0].coordinate},
  units={('doc','1'):{'title':title,'coordinate_scope':'body'}})
 assert ('doc','1') in sq.heading_term_candidates(m,['doc'],'alpha beta',{})
 assert not sq.heading_term_candidates(m,['doc'],'alpha unrelated',{})
 assert not sq.heading_term_candidates(m,['doc','other'],'alpha beta',{})
 assert m.units[('doc','1')]['title']==title
 # Removal is insufficient at 4/8: two-thirds matching requirement is retained.
 m.units[('doc','1')]['title']='alpha beta gamma delta eta theta rho tau <개정 2009. 1. 28.>'
 assert not sq.heading_term_candidates(m,['doc'],'alpha beta gamma delta',{})
