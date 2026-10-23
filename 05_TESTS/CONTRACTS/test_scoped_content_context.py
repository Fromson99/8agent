"""Stored parent context survives read projection; no legal judgments inferred."""
from copy import deepcopy
from types import SimpleNamespace as S
import pytest
from semantic_runtime.legal_agent import decision_projection as dp
from semantic_runtime.legal_agent.errors import ContractError
from lawrag.core.legal_coordinate import find_coordinates

def matcher():
 units={};coords={};sources={}
 for i,title in ((1,'공개회사'),(2,'비공개회사')):
  parent=str(i);child=f'{i}-1'
  for uid,p,surface,heading in ((parent,None,f'제{i}장',title),(child,parent,f'제{i}조','의결 기준')):
   units[('d',uid)]={'parent':p,'surface':surface,'title':heading,'coordinate_scope':'body','family':'kr_article' if p else 'kr_chapter'}
   coords[('d',uid)]=find_coordinates(surface)[0].coordinate
  sources['s'+str(i)]={'document_id':'d','unit_id':child}
 return S(units=units,stored_coordinates=coords,sources=sources)

def test_identical_headings_keep_different_stored_parents_without_inventing_body():
 m=matcher();actions={f'T{i}':{'identity':{'document_id':'d','source_id':f's{i}'},'label':'의결 기준'} for i in (1,2)}
 data={'laws':[{'document_id':'d','articles':[{'read_action':f'T{i}','heading':'의결 기준'} for i in (1,2)]}]};before=deepcopy(data)
 rows=dp.read_candidate_rows(data,actions,m)
 assert [r['path'][0]['title'] for r in rows]==['공개회사','비공개회사']
 assert all('text' not in r and len(r['path'])==2 for r in rows)
 assert data==before

def test_wrong_source_document_is_rejected_before_model_context():
 with pytest.raises(ContractError,match='source document'):
  dp.read_candidate_rows({}, {'T1':{'identity':{'document_id':'other','source_id':'s1'},'label':'wrong'}},matcher())

def test_broken_parent_does_not_manufacture_a_context():
 m=matcher();m.units[('d','1-1')]['parent']='missing'
 with pytest.raises(ContractError,match='missing/cyclic'):
  dp.read_candidate_rows({}, {'T1':{'identity':{'document_id':'d','source_id':'s1'},'label':'candidate'}},m)
