import pytest
from lawrag.legal_knowledge.ontology import evaluate, validate_expression
from lawrag.legal_knowledge.contracts import KnowledgeError


def literal(value, kind='boolean', unit=''): return {'literal': {'type': kind, 'value': value, 'unit': unit}}
def operation(op, *args): return {'op': op, 'args': list(args)}
def ev(value, facts=None): return evaluate(value, facts or {}, binding={'revision': 1})


@pytest.mark.parametrize('expression,status', [
    (operation('not', {'field':'unknown'}),'UNKNOWN'),
    (operation('all', literal(False), {'field':'unknown'}),'FALSE'),
    (operation('any', literal(True), {'field':'unknown'}),'TRUE'),
    (operation('eq', literal('30000000000','money','KRW'), literal('30000000000','money','USD')),'UNKNOWN'),
    (operation('gt', literal('0.1','decimal'), literal('0.09','decimal')),'TRUE'),
    (operation('divide', literal('1','decimal'), literal('0','decimal')),'UNKNOWN'),
    (operation('divide', literal('1','decimal'), literal('3','decimal')),'UNKNOWN'),
    (operation('multiply', literal('2','money','KRW'), literal('3','money','KRW')),'UNKNOWN')])
def test_typed_three_valued_conditions(expression,status): assert ev(expression)['status']==status


def test_conflict_and_model_proposal_cannot_authorize_skip():
    expression=operation('any',literal(True),{'field':'amount'})
    assert ev(expression,{'amount':{'status':'CONFLICT'}})['status']=='CONFLICT'
    assert ev({'field':'amount'},{'amount':{'status':'MODEL_PROPOSAL','value':literal(True)['literal'],'origin_ref':'model:1'}})['status']=='UNKNOWN'


def test_decimal_uses_strings_and_preserves_origin_and_binding():
    expression=operation('add',{'field':'a'},literal('0.2','decimal'))
    result=ev(expression,{'a':{'status':'ASSERTED','origin_ref':'event:1','value':literal('0.1','decimal')['literal']}})
    assert result['value']['value']=='0.3' and result['binding']=={'revision':1}
    with pytest.raises(KnowledgeError): ev(literal(0.1,'decimal'))


def test_expression_depth_and_arbitrary_code_rejected():
    value=literal(True)
    for _ in range(9):value=operation('not',value)
    with pytest.raises(KnowledgeError):validate_expression(value)
    with pytest.raises(KnowledgeError):validate_expression({'python':'1+1'})
