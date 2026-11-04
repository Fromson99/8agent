"""Map legacy read table references onto the approved SIDDS physical projection."""
from .physical_mapping import CONTRACT_COLUMNS
LEGACY={'SIDDA.LEGAL_SRC_DOCUMENT_A':'document','SIDDA.LEGAL_SRC_SOURCE_UNIT_A':'source_unit','SIDDA.LEGAL_SRC_BLOCK_PAYLOAD_A':'block_payload','SIDDA.LEGAL_RAG_QUERY_ROW_A':'query_row','SIDDA.LEGAL_RAG_QUERY_RELEASE_A':'query_release','SIDDA.LEGAL_RAG_QUERY_ACTIVE_A':'query_active','SIDDA.LEGAL_RAG_RELEASE_A':'source_release'}
def rewrite(text,mapping):
 if mapping is None:return text
 if not any(name in text.upper() for name in LEGACY):return text
 # Tokenize only: the Oracle parser cannot round-trip maintained JSON_TABLE
 # column-level ERROR ON ERROR. Preserve every predicate, bind and error clause.
 from .oracle_sql_tokens import tokens
 scanned=tokens(text);changes=[]
 reserved={'WHERE','JOIN','LEFT','RIGHT','FULL','INNER','CROSS','OUTER','ON','USING','GROUP','ORDER','HAVING','OFFSET','FETCH','UNION','INTERSECT','MINUS','FOR','CONNECT','START','MODEL','PIVOT','UNPIVOT'}
 for i in range(1,len(scanned)-2):
  a,dot,b=scanned[i:i+3]
  previous=scanned[i-1]
  if dot.text!='.' or a.kind not in ('word','identifier') or b.kind not in ('word','identifier'):continue
  if not (previous.kind=='word' and previous.text.upper() in ('FROM','JOIN') or previous.text==','):continue
  key=LEGACY.get((a.text+'.'+b.text).upper())
  if key is None:continue
  n=mapping.names(key);projection='(SELECT '+n.select(*CONTRACT_COLUMNS[key].split())+' FROM '+n.table+')'
  following=scanned[i+3] if i+3<len(scanned) else None
  if following is None or not (following.kind=='identifier' or following.kind=='word' and following.text.upper() not in reserved):projection+=' '+b.text
  changes.append((a.start,b.end,projection))
 for start,end,replacement in reversed(changes):text=text[:start]+replacement+text[end:]
 return text
