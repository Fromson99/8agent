"""Map legacy read table references onto the approved SIDDS physical projection."""
from .physical_mapping import CONTRACT_COLUMNS
import re
LEGACY={'SIDDA.LEGAL_SRC_DOCUMENT_A':'document','SIDDA.LEGAL_SRC_SOURCE_UNIT_A':'source_unit','SIDDA.LEGAL_SRC_BLOCK_PAYLOAD_A':'block_payload','SIDDA.LEGAL_RAG_QUERY_ROW_A':'query_row','SIDDA.LEGAL_RAG_QUERY_RELEASE_A':'query_release','SIDDA.LEGAL_RAG_QUERY_ACTIVE_A':'query_active','SIDDA.LEGAL_RAG_RELEASE_A':'source_release'}
def rewrite(text,mapping):
 if mapping is None:return text
 # Physical SQL already names SIDDS columns. Parsing it is unnecessary and can
 # reject native Oracle VECTOR/JSON syntax unsupported by sqlglot. This is only
 # a legacy-name mapper, not the read-only or authorization gate (SQL keeps those).
 code=re.sub(r"'(?:''|[^'])*'|--[^\n]*(?:\n|$)|/\*[\s\S]*?\*/",' ',text).upper()
 identifiers=set(re.findall(r'[A-Z_][A-Z0-9_$#]*',code))
 if not any(name.split('.')[1] in identifiers for name in LEGACY):return text
 import sqlglot
 from sqlglot import exp
 tree=sqlglot.parse_one(text,read='oracle')
 for t in list(tree.find_all(exp.Table)):
  name=((t.db+'.') if t.db else '')+t.name;key=LEGACY.get(name.upper())
  if key is None:continue
  n=mapping.names(key);projection='SELECT '+n.select(*CONTRACT_COLUMNS[key].split())+' FROM '+n.table
  alias=t.alias or t.name
  sub=sqlglot.parse_one(projection,read='oracle').subquery(alias)
  t.replace(sub)
 return tree.sql(dialect='oracle')
