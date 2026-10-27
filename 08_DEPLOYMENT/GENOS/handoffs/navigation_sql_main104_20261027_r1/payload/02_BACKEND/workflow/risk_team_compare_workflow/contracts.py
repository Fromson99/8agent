"""Schemas for question-scoped observations; these are not global legal rules."""
def text():
    return {'type':'string','minLength':1}


def choice(*values):
    return {'type':'string','enum':list(values)}


def array(item, minimum=0, maximum=24):
    return {'type':'array','items':item,'minItems':minimum,'maxItems':maximum}


def obj(**fields):
    return {'type':'object','properties':fields,'required':list(fields),'additionalProperties':False}


# Exact original spans are bounded by the presented request, not shortened to
# an unrelated quote length. Models select the bound citation ID on the wire.
CITATION = obj(evidence=text(),quote={'type':'string','minLength':1})
ISSUE = obj(id=text(),label=text(),numeric={'type':'boolean'},internal_task=text(),external_task=text())
FACT = obj(name=text(),value={'type':['string','null']},user_quote=text())
INTAKE = obj(issues=array(ISSUE,1,12),internal_queries=array(text(),1,4),
             external_queries=array(text(),1,4),scope_note=text(),facts=array(FACT,0,16),
             missing_user_facts=array(text(),0,8))
ACTION = obj(side=choice('internal','external'),question=text(),reason=text())
ACTION['properties']['context_evidence']=array(text())
ACTION['properties']['context_evidence'].pop('maxItems',None)
GAP = obj(issue_id=text(),kind=choice('PARTIAL_PROVISION','MISSING_REFERENCE','EXTERNAL_SCOPE',
    'INTERNAL_SCOPE','QUERY_SCOPE','NOT_REGISTERED','TOOL_FAILURE','MISSING_NUMERIC','UNKNOWN_VERSION'),
    reason=text(),action={'anyOf':[ACTION,{'type':'null'}]})
PATH = obj(from_evidence=text(),to_evidence=text(),citation=CITATION)
APPLICABILITY = obj(status=choice('MATCH','MISMATCH','UNKNOWN'),reason=text(),
                    citations=array(CITATION),as_of={'type':['string','null']})
PAIR = obj(pair_id=text(),issue_id=text(),internal=array(text(),1),
    external=array(text(),1),applicability=APPLICABILITY,
    basis_relation=choice('DIRECT','INDIRECT','CONTENT_ONLY','UNKNOWN','UNRELATED'),
    basis_path=array(PATH),comparison_eligibility={'type':'boolean'},reason=text(),
    content_difference={'type':'string'},content_citations=array(CITATION))
BASIS = obj(pairs=array(PAIR),gaps=array(GAP),summary=text())
# System-inherited child gaps may exceed one model proposal; none may disappear.
BASIS['properties']['gaps'].pop('maxItems',None)
DIMENSIONS = ('definition','numerator','denominator','scope','unit','period','date','exceptions','direction','value')
DIMENSION = obj(name=choice(*DIMENSIONS),status=choice('MATCH','DIFFERENT','UNKNOWN','NOT_APPLICABLE'),
                citations=array(CITATION),reason=text())
ROW = obj(pair_id=text(),item=text(),verdict=choice('CONFORMS','ADDITIONAL_INTERNAL',
    'CONFLICT','POSSIBLE_GAP','DEFERRED'),difference={'type':'string','minLength':1},reason=text(),
    citations=array(CITATION),numeric={'type':'boolean'},dimensions=array(DIMENSION,0,len(DIMENSIONS)),
    unresolved=array(text()))
COMPARE = obj(rows=array(ROW),answer=text(),unresolved=array(text()))


def evidence_map(evidence):
    return {e['evidence_id']:e for e in evidence}


def check_citations(citations, evidence):
    for c in citations:
        e = evidence.get(c['evidence'])
        if e is None or not c['quote'].strip() or not any(c['quote'] in s['text'] for s in e['spans']):
            raise ValueError('citation must be an exact quote in a read source span')


def check_sides(ids, side, evidence):
    if len(ids) != len(set(ids)) or any(i not in evidence or evidence[i]['side'] != side for i in ids):
        raise ValueError('pair evidence is unknown, duplicated or from the wrong side')

# Optional intake selectors preserve the earlier question contract. The host owns
# each configured field and all durable task/receipt identities.
ISSUE['properties']['work_type']=choice('general','procedure','authority','ratio')
ISSUE['properties']['requested_fields']=array(choice('subject','obligation','procedure','authority','condition','exceptions','date','definition','numerator','denominator','unit','period','direction','value'),0,14)
