"""Static report/schema checks only; does not execute product tools or model calls."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
schema = json.loads((HERE / 'contracts.schema.json').read_text())
Draft202012Validator.check_schema(schema)


def validator(name):
    return Draft202012Validator({**schema, '$ref': '#/$defs/' + name})


args = {
    'browse': dict(target='E3', relation='document', view='outline', depth=1, cursor=None),
    'search': dict(query='채무 절차', target='R1', mode='fulltext', cursor=None),
    'match_terms': dict(text='빚', target='R1', strategy='bridge', cursor=None),
    'term_occurrences': dict(terms=['T1'], target='R1', match='any', cursor=None),
    'locate': dict(locator='가상 업무규정 제12조', target='R1', branch='body', cursor=None),
    'lookup_definition': dict(query='채무', target='D1', cursor=None),
    'follow_reference': dict(evidence='E1', direction='incoming', cursor=None),
    'read': dict(target='U1', extent='subtree', cursor=None),
    'inspect': dict(section='challenges', cursor=None),
}
actions = {k: {'tool': k, 'args': v, 'reason': '설계 예시'} for k, v in args.items()}
declared = {v['properties']['tool']['const'] for v in schema['$defs']['ToolAction']['oneOf']}
assert declared == set(actions), (declared, set(actions))
positive = []
negative = []
for name, action in actions.items():
    validator('ToolAction').validate(action)
    positive.append('tool:' + name)

turn = dict(actions=[], assessments=[], candidate_decisions=[], route_decisions=[],
            question_updates=[], intent='CONTINUE', reason='다음 탐색 판단')
validator('TurnDecision').validate(turn)
positive.append('empty_assessment_and_no_mandatory_browse')
choice = deepcopy(turn)
choice['actions'] = [actions['search']]
validator('TurnDecision').validate(choice)
positive.append('search_without_browse')
choice = deepcopy(turn)
choice['assessments'] = [dict(evidence='E1', summary='조건 원문', disposition='DEFER',
                              role='CHALLENGE', reason='사실 미확인', question_refs=['Q1'])]
validator('TurnDecision').validate(choice)
positive.append('deferred_challenge')

draft = dict(paragraphs=[dict(text='가상 조건부 설명', evidence=['E1'],
                             question_refs=['Q1'], fact_dependencies=[])], limitations=[])
review = dict(checks=[dict(claim='C1', verdict='UNCERTAIN', evidence=['E1'], issue='사실 미확인',
                          reason='판단 보류', actions=[])],
              question=dict(status='MISSING_FACT', question_refs=['Q1'], reason='회사 유형 필요'))
rebuttal = dict(claim='C1', evidence=['E1'], reason='반대 문구와 대조 필요',
                requested_resolution='REVIEW_AGAIN')
for name, value in [('Draft', draft), ('ReviewDecision', review), ('Rebuttal', rebuttal)]:
    validator(name).validate(value)
    positive.append(name)


def reject(label, name, value):
    assert list(validator(name).iter_errors(value)), label + ' unexpectedly accepted'
    negative.append(label)


for bad_alias in ('P3', 'C1', 'E0', 'E-1', 'E1suffix'):
    bad = deepcopy(choice)
    bad['assessments'][0]['evidence'] = bad_alias
    reject('assessment_alias:' + bad_alias, 'TurnDecision', bad)
bad = deepcopy(actions['read'])
bad['args']['target'] = 'C1'
reject('read_claim_as_node', 'ToolAction', bad)
bad = deepcopy(actions['follow_reference'])
bad['args']['evidence'] = 'P1'
reject('follow_unread_preview', 'ToolAction', bad)
bad = deepcopy(actions['browse'])
bad['args']['depth'] = 0
reject('invalid_tree_depth', 'ToolAction', bad)
bad = deepcopy(actions['search'])
bad['args']['scope_override'] = 'all'
reject('undeclared_scope_override', 'ToolAction', bad)
bad = deepcopy(turn)
bad['actions'] = [{'tool': 'shell', 'args': {'cmd': 'ls'}, 'reason': '임의 셸'}]
reject('unregistered_shell_tool', 'TurnDecision', bad)
bad = deepcopy(draft)
bad['paragraphs'][0]['evidence'] = ['P1']
reject('draft_preview_citation', 'Draft', bad)
bad = deepcopy(turn)
bad['select'] = ['E1']
reject('legacy_untyped_select_field', 'TurnDecision', bad)

docs = ['README.md', 'DESIGN.md', 'CONTRACTS.md', 'ACCEPTANCE.md', 'SELF_REVIEW.md']
texts = {name: (HERE / name).read_text() for name in docs}
ids = re.findall(r'^\| (A\d\d) \|', texts['ACCEPTANCE.md'], re.M)
assert len(ids) == len(set(ids)) == 46
references = set(re.findall(r'\bA\d\d\b', '\n'.join(texts.values())))
assert references <= set(ids), references - set(ids)
links_checked = 0
for text in texts.values():
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', text):
        target = target.split('#', 1)[0]
        if not target or '://' in target:
            continue
        path = Path(target) if target.startswith('/') else HERE / target
        assert path.resolve().exists(), str(path)
        links_checked += 1

sources = json.loads((HERE / 'sources.json').read_text())
for item in sources['files']:
    path = ROOT / item['path']
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    assert actual == item['sha256'], 'Source changed: ' + item['path']

review_binding = HERE / 'review-targets.json'
targets_checked = 0
if review_binding.exists():
    for item in json.loads(review_binding.read_text())['files']:
        actual = hashlib.sha256((HERE / item['path']).read_bytes()).hexdigest()
        assert actual == item['sha256'], 'Reviewed target changed: ' + item['path']
        targets_checked += 1

print(json.dumps(dict(status='PASS', kind='static_design_validation_only',
                      product_or_model_executed=False, schema_positive_cases=len(positive),
                      schema_negative_cases=len(negative), tool_variants=len(declared),
                      acceptance_scenarios_defined=len(ids), acceptance_scenarios_executed=0,
                      local_links_checked=links_checked, source_hashes_checked=len(sources['files']),
                      reviewed_target_hashes_checked=targets_checked), ensure_ascii=False, indent=2))
