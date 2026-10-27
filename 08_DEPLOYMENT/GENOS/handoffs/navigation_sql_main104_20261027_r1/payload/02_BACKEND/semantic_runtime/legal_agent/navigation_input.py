"""Request-local reversible handles and lossless table/card representation.

Original source text, legal coordinates and persisted identities never change.
The repository independently rebuilds this mapping before reserving an attempt.
"""
from copy import deepcopy
from collections import defaultdict
import re
from jsonschema import Draft202012Validator, ValidationError
from ..contracts import digest
from .errors import ProposalError

INSTRUCTIONS = ('선택 ID는 이 화면에만 유효한 짧은 문자열이다. 법률 숫자·원문은 바꾸지 말고 제시된 ID를 그대로 선택한다. '
 '같은 선택·근거 ID는 목록에 한 번만 넣고, 제시된 서로 다른 ID 수를 넘지 않는다. ' 
 'article_refs는 articles의 같은 id 카드다. '
 'table_columns/table_rows는 같은 순서의 열 이름/행 값이다. 각 행은 원래 객체와 같으며 누락·요약이 아니다.')
OPAQUE=re.compile(r'^[A-Z][0-9a-f]{16,64}$')
TEXT_FIELDS={'explanation','text','quote','source_quote','request_quote','question','current_request','request_text',
 'conclusion','reason','sufficiency_reason','notes','description','label','name','document_name','heading','title','surface','missing_need','missing_target'}
# These verify storage/indices, not a model selection. Keep their original journal copy.
AUDIT_FIELDS={'query_fingerprint','index_sha256','source_artifact_sha256','source_artifact_hash',
 'span_hash','block_hash','text_hash','source_hash','decision_hash','request_hash','schema_sha256'}

class NavigationReferences:
    def __init__(self,view):
        identities=set();strings=set()
        def scan(v,key=None):
            if isinstance(v,str):
                strings.add(v)
                if key not in TEXT_FIELDS and OPAQUE.fullmatch(v):identities.add(v)
            elif isinstance(v,list):
                for x in v:scan(x,key)
            elif isinstance(v,dict):
                for k,x in v.items():scan(x,k)
        scan(view);self.forward={};counts=defaultdict(int)
        for ident in sorted(identities):
            prefix=ident[0]
            while True:
                counts[prefix]+=1;short=prefix+str(counts[prefix])
                if short not in strings:break
            self.forward[ident]=short
        self.reverse={v:k for k,v in self.forward.items()}
        self.ids={'navigation':sorted(identities),'claims':[]}
    def _map(self,value,mapping,key=None):
        if isinstance(value,str):return mapping.get(value,value) if key not in TEXT_FIELDS else value
        if isinstance(value,list):return [self._map(v,mapping,key) for v in value]
        if isinstance(value,dict):return {k:self._map(v,mapping,k) for k,v in value.items()}
        return deepcopy(value)
    def view(self,view):return self._map(view,self.forward)
    def schema(self,schema):
        # Only enum/const values are identifiers; object keys and source quotations are data.
        def walk(node,key=None):
            if isinstance(node,list):return [walk(v,key) for v in node]
            if not isinstance(node,dict):return deepcopy(node)
            out={}
            for k,v in node.items():
                if k=='properties':out[k]={name:walk(child,name) for name,child in v.items()}
                elif k=='enum' and key not in TEXT_FIELDS:out[k]=[self.forward.get(x,x) if isinstance(x,str) else deepcopy(x) for x in v]
                elif k=='const' and key not in TEXT_FIELDS and isinstance(v,str):out[k]=self.forward.get(v,v)
                else:out[k]=walk(v,key)
            return out
        return walk(schema)
    def decode(self,value,wire_schema,schema_name=None):
        try:Draft202012Validator(wire_schema).validate(value)
        except ValidationError as exc:raise ProposalError('invalid request-local selection at '+str(list(exc.absolute_path))+': '+exc.message) from exc
        return self._map(value,self.reverse)
    def restore(self,value):return self._map(value,self.reverse)
    def receipt(self,view):return {'schema_version':'navigation-handles-v1','view_hash':digest(view),'mapping':dict(self.forward)}


def compact_cards(view):
    """Remove only duplicated/opaque metadata; keep all original bodies and actions."""
    result=deepcopy(view)
    def strip(v):
        if isinstance(v,dict):return {k:strip(x) for k,x in v.items() if k not in AUDIT_FIELDS}
        if isinstance(v,list):return [strip(x) for x in v]
        return v
    result=strip(result)
    articles={r['id']:r for r in result.get('articles',[]) if isinstance(r,dict) and 'id' in r}
    for law in result.get('laws',[]):
        rows=law.get('articles')
        if isinstance(rows,list) and rows and all(r.get('id') in articles and r==articles[r['id']] for r in rows):
            law['article_refs']=[r['id'] for r in law.pop('articles')]
    # Column representation never touches source/evidence containers or legal text.
    protected={'sources','exact_evidence','evidence_options','answer_content','rejected_assessment'}
    def table(v,key=None):
        if key in protected:return v
        if isinstance(v,dict):return {k:table(x,k) for k,x in v.items()}
        if isinstance(v,list):
            rows=[table(x,key) for x in v]
            if len(rows)>=3 and all(isinstance(r,dict) for r in rows):
                cols=sorted(rows[0])
                if cols and all(set(r)==set(cols) for r in rows):
                    candidate={'table_columns':cols,'table_rows':[[r[k] for k in cols] for r in rows]}
                    from .repository import encoded
                    if len(encoded(candidate))+40<len(encoded(rows)):return candidate
            return rows
        return v
    return table(result)


def expand_cards(view):
    """Deterministic audit expansion; never used to invent source contents."""
    def walk(v):
        if isinstance(v,dict):
            if set(v)=={'table_columns','table_rows'}:
                return [dict(zip(v['table_columns'],[walk(x) for x in row],strict=True)) for row in v['table_rows']]
            return {k:walk(x) for k,x in v.items()}
        if isinstance(v,list):return [walk(x) for x in v]
        return deepcopy(v)
    result=walk(view);articles={r['id']:r for r in result.get('articles',[]) if 'id' in r}
    for law in result.get('laws',[]):
        if 'article_refs' in law:law['articles']=[deepcopy(articles[i]) for i in law.pop('article_refs')]
    return result
