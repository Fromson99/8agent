"""Map legacy read table references onto the approved SIDDS physical projection."""
from .physical_mapping import CONTRACT_COLUMNS
LEGACY={'SIDDA.LEGAL_SRC_DOCUMENT_A':'document','SIDDA.LEGAL_SRC_SOURCE_UNIT_A':'source_unit','SIDDA.LEGAL_SRC_BLOCK_PAYLOAD_A':'block_payload','SIDDA.LEGAL_RAG_QUERY_ROW_A':'query_row','SIDDA.LEGAL_RAG_QUERY_RELEASE_A':'query_release','SIDDA.LEGAL_RAG_QUERY_ACTIVE_A':'query_active','SIDDA.LEGAL_RAG_RELEASE_A':'source_release'}
def rewrite(text,mapping):
 if mapping is None:return text
 if not any(name in text.upper() for name in LEGACY):return text
 # Tokenize only: the Oracle parser cannot round-trip maintained JSON_TABLE
 # column-level ERROR ON ERROR. Preserve every predicate, bind and error clause.
 from sqlglot import Dialect
 from sqlglot.tokens import TokenType as T
 tokens=Dialect.get_or_raise('oracle').tokenize(text);changes=[]
 for i in range(1,len(tokens)-2):
  a,dot,b=tokens[i:i+3]
  if dot.token_type!=T.DOT or tokens[i-1].token_type not in (T.FROM,T.JOIN,T.COMMA):continue
  key=LEGACY.get((a.text+'.'+b.text).upper())
  if key is None:continue
  n=mapping.names(key);projection='(SELECT '+n.select(*CONTRACT_COLUMNS[key].split())+' FROM '+n.table+')'
  following=tokens[i+3] if i+3<len(tokens) else None
  if following is None or following.token_type not in (T.VAR,T.IDENTIFIER,T.ALIAS):projection+=' '+b.text
  changes.append((a.start,b.end+1,projection))
 for start,end,replacement in reversed(changes):text=text[:start]+replacement+text[end:]
 return text
