from copy import deepcopy
from jsonschema import Draft202012Validator
from semantic_runtime.legal_agent import completion_contracts as cc
from test_completion_v4 import claim


def test_wire_binds_nonempty_exceptions_to_source_status():
 validator=Draft202012Validator(cc.rule_schema(['S1','S2'],[]));r=claim()['rule']
 assert not list(validator.iter_errors(r))
 r['exception_status']='NOT_ESTABLISHED';assert list(validator.iter_errors(r))


def test_empty_exceptions_stay_uncertain_and_cannot_claim_source_exceptions():
 validator=Draft202012Validator(cc.rule_schema(['S1','S2'],[]));r=claim()['rule'];r['exceptions']=[]
 assert list(validator.iter_errors(r))
 r['exception_status']='NOT_ESTABLISHED';assert not list(validator.iter_errors(r))
 assert '예외 적용 여부는 확인되지' in cc.render_rule(r)


def test_null_rule_and_strict_schema_remain_compatible():
 schema=cc.rule_schema(['S1'],[]);Draft202012Validator.check_schema(schema);assert not list(Draft202012Validator(schema).iter_errors(None))
 for rule in schema['anyOf'][1:]:assert set(rule['required'])==set(rule['properties']) and rule['additionalProperties'] is False
