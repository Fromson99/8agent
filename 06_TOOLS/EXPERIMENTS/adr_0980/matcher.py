"""Small public metadata reader; no full original/index loading."""
from common import *
import sqlite3
from types import SimpleNamespace as S
def build(code):
 from semantic_runtime.inherited_navigation import _derive_bindings
 from lawrag.core.legal_coordinate import find_coordinates
 stage=read(ART/'stage.json');request=read(ROOT/'90_RUNTIME/manual_queries/special-resolution-20261022/retry/request.json')['json']
 allowed=request['document_ids'].copy();db=sqlite3.connect('file:'+str(ROOT/stage['base_release']['data_path']/'store.sqlite')+'?mode=ro',uri=True)
 docs={};metadata={};aliases={};raw={}
 for did,name,j in db.execute('SELECT document_id,name,json FROM document WHERE document_id IN (SELECT value FROM json_each(?))',(json.dumps(allowed),)):
  data=json.loads(j).get('document_metadata',{});docs[did]=name;metadata[did]=data
  if data.get('official_abbreviation'):aliases[did]=[data['official_abbreviation']]
  if data.get('document_title')=='상법':
   for uid,parent,j in db.execute('SELECT unit_id,parent_id,json FROM source_unit WHERE document_id=?',(did,)):
    n=json.loads(j);raw[(did,str(uid))]={**n,'parent':str(parent) if parent is not None else None,'raw_structure':n}
 db.close()
 for doc in read(ART/'documents.json'):
  did=doc['id'];allowed.append(did);docs[did]=doc['title'];metadata[did]={'document_title':doc['title'],'source_category':'external'}
  for node in doc['nodes']:
   n=dict(node);parts=n['id'].split('-');locator=''.join(f'제{v}{u}' for v,u in zip(parts,('조','항','호')))
   coord=find_coordinates(locator)[0].coordinate
   n.update(legal_coordinate=coord.as_dict(),coordinate_key='body:'+coord.canonical_surface())
   base=(21,24,25,26).index(int(parts[0]))*7
   if len(parts)==1:n['span']=[base,base+7]
   elif len(parts)==2:n['span']=[base+1,base+7]
   raw[(did,n['id'])]={**n,'raw_structure':n}
 units,coordinates=_derive_bindings(raw)
 return S(documents=docs,document_context=metadata,document_aliases=aliases,units=units,stored_coordinates=coordinates),allowed
