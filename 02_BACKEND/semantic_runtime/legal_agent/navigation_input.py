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
 'table_columns/table_rows는 같은 순서의 열 이름/행 값이다. 각 행은 원래 객체와 같으며 누락·요약이 아니다. '
 'navigation_segments는 순서대로 이어 붙이는 목록 묶음이다. '
 'navigation_card_ref는 shared_navigation_cards에서 같은 이름의 완전한 위치·선택 정보를 참조한다. '
 '그 참조는 내용 삭제나 요약이 아니며 원래 객체·배열과 동일하다.')
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
    from .repository import encoded
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
                    if len(encoded(candidate))+40<len(encoded(rows)):return candidate
            if len(rows)>=3 and all(isinstance(r,dict) for r in rows):
                segments=[];start=0
                for i in range(1,len(rows)+1):
                    if i==len(rows) or set(rows[i])!=set(rows[start]):
                        batch=rows[start:i];cols=sorted(batch[0])
                        packed={'table_columns':cols,'table_rows':[[r[k] for k in cols] for r in batch]}
                        segments.append(packed if len(encoded(packed))<len(encoded(batch)) else batch)
                        start=i
                candidate={'navigation_segments':segments}
                if len(encoded(candidate))+40<len(encoded(rows)):return candidate
            return rows
        return v
    baseline=table(result)
    # Factor only exactly equal, repeated metadata. Source/evidence bodies stay
    # literal and complete; the journal still holds the unprojected view.
    reserved={'shared_navigation_cards','navigation_card_ref'}
    if any(k in result for k in reserved):return baseline
    from .repository import encoded
    counts=defaultdict(int)
    def count(v,key=None):
        if key in protected:return
        if isinstance(v,(dict,list)):
            raw=encoded(v)
            if len(raw)>=64:counts[raw]+=1
            children=v.items() if isinstance(v,dict) else ((None,x) for x in v)
            for k,x in children:count(x,k)
    for k,v in result.items():count(v,k)
    shared={}
    # Stored views sort object keys; handles must not depend on insertion order.
    names={raw:'N'+str(i+1) for i,raw in enumerate(sorted(raw for raw,count in counts.items()
        if count>1 and (len(raw)-45)*(count-1)>90))}
    def factor(v,key=None):
        if key in protected:return v
        if isinstance(v,(dict,list)):
            raw=encoded(v)
            if raw in names:
                shared.setdefault(names[raw],deepcopy(v))
                return {'navigation_card_ref':names[raw]}
            if isinstance(v,dict):return {k:factor(x,k) for k,x in v.items()}
            return [factor(x) for x in v]
        return v
    factored={k:factor(v,k) for k,v in result.items()}
    if shared:factored['shared_navigation_cards']=shared
    factored=table(factored)
    return factored if len(encoded(factored))<len(encoded(baseline)) else baseline


def expand_cards(view):
    """Deterministic audit expansion; never used to invent source contents."""
    shared=view.get('shared_navigation_cards',{})
    def walk(v,seen=()):
        if isinstance(v,dict):
            if set(v)=={'navigation_card_ref'}:
                name=v['navigation_card_ref']
                if name not in shared or name in seen:raise ValueError('invalid shared navigation card')
                return walk(shared[name],seen+(name,))
            if set(v)=={'navigation_segments'}:
                return [row for segment in v['navigation_segments'] for row in walk(segment,seen)]
            if set(v)=={'table_columns','table_rows'}:
                return [walk(dict(zip(walk(v['table_columns'],seen),row,strict=True)),seen) for row in walk(v['table_rows'],seen)]
            return {k:walk(x,seen) for k,x in v.items()}
        if isinstance(v,list):return [walk(x,seen) for x in v]
        return deepcopy(v)
    result=walk({k:v for k,v in view.items() if k!='shared_navigation_cards'});articles={r['id']:r for r in result.get('articles',[]) if 'id' in r}
    for law in result.get('laws',[]):
        if 'article_refs' in law:law['articles']=[deepcopy(articles[i]) for i in law.pop('article_refs')]
    return result
