"""Literal MAIN104 responses; comparisons never rewrite product input/output."""
from contextlib import contextmanager
from copy import deepcopy
import gzip
import hashlib
import json
import re
import socket
import sqlite3

from common import ROOT, read, sha

class ReplayBoundary(BaseException):
    pass

def require(condition, message):
    if not condition:
        raise ReplayBoundary(message)

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def checked(item):
    path = (ROOT / item['path']).resolve()
    require(path.is_relative_to(ROOT) and sha(path) == item['sha256'], 'Frozen input changed')
    return path

def load(item):
    path = checked(item)
    if path.suffix == '.gz':
        with gzip.open(path, 'rt', encoding='utf8') as stream:
            return json.load(stream)
    return read(path)

def comparable(body, *, domain_choice_id=None):
    result = deepcopy(body)
    messages = result.get('messages', [])
    require(len(messages) == 2 and [m['role'] for m in messages] == ['system', 'user'],
            'Unknown messages layout')
    user = json.loads(messages[1]['content'])
    require(isinstance(user, dict) and isinstance(user.get('view'), dict), 'Unknown user layout')
    view = user['view']
    if re.fullmatch(r'V[0-9a-f]{32}', str(view.get('view_id', ''))):
        view.pop('view_id')
    if domain_choice_id is not None:
        require(view.get('source_stage')=='memory-compose' and
                view.get('domain_choice',{}).get('choice_id')==domain_choice_id,
                'Validated domain ID is not the final compose selection')
        view['domain_choice'].pop('choice_id')
    messages[1]['content'] = user
    return result

def compare_request(expected, actual, *, domain_proof=None):
    old_id=domain_proof['expected_id'] if domain_proof else None
    new_id=domain_proof['actual_id'] if domain_proof else None
    return {'whole_request_exact': digest(expected) == digest(actual),
            'protected_request_exact': digest(comparable(expected,domain_choice_id=old_id)) == digest(comparable(actual,domain_choice_id=new_id)),
            'expected_protected_sha256': digest(comparable(expected,domain_choice_id=old_id)),
            'actual_protected_sha256': digest(comparable(actual,domain_choice_id=new_id)),
            'schema_exact': expected.get('response_format') == actual.get('response_format'),
            'system_exact': expected['messages'][0] == actual['messages'][0],
            'expected_phase': json.loads(expected['messages'][1]['content'])['view'].get('source_stage'),
            'actual_phase': json.loads(actual['messages'][1]['content'])['view'].get('source_stage')}

def domain_record(journal, ident):
    db=sqlite3.connect(journal.resolve().as_uri()+'?mode=ro')
    try:
        db.execute('PRAGMA query_only=ON')
        row=db.execute('SELECT stage,offer_json,choice_json,created_seq FROM domain_choice WHERE id=?',(ident,)).fetchone()
        run=db.execute('SELECT run_id FROM run WHERE singleton=1').fetchone()
        require(row is not None and run is not None,'Domain choice missing from native journal')
        return {'id':ident,'run_id':run[0],'stage':row[0],'offer_json':row[1],
                'choice_json':row[2],'created_seq':row[3]}
    finally:db.close()

def validate_domain_records(expected,actual,*,allowed_stage='COMPOSE'):
    require(allowed_stage in ('SELECT','COMPOSE'),'Unapproved generated-domain-ID scope')
    for record in (expected,actual):
        ident='D'+digest([record['run_id'],record['stage'],record['created_seq'],json.loads(record['choice_json'])])[:28]
        require(record['id']==ident and record['stage']==allowed_stage,'Domain choice ID is not bound to this run/stage/sequence/selection')
    require(all(expected[k]==actual[k] for k in ('stage','offer_json','choice_json','created_seq')),
            'Domain choice semantics or event order changed')
    return {'expected_id':expected['id'],'actual_id':actual['id'],
            'expected_run':expected['run_id'],'actual_run':actual['run_id'],
            'stage':allowed_stage,'created_seq':actual['created_seq'],
            'offer_sha256':digest(json.loads(actual['offer_json'])),
            'choice_sha256':digest(json.loads(actual['choice_json'])),'journal_bound':True}

def answer_content(body):
    answer = deepcopy(body['answer'])
    require(answer['id'] == 'answer:' + body['run_id'] and answer['query_id'] == body['query']['id'],
            'Answer identity is not bound to native run/query')
    answer.pop('id')
    answer.pop('query_id')
    return answer

class RecordedTransport:
    def __init__(self, inventory):
        self.inventory = inventory
        self.calls = 0
        self.checks = []
        self.current_journal = None
        self.navigation_codec = None
        require(len(inventory['calls']) == 38, 'Expected exactly 38 recorded responses')

    def reply(self, body):
        require(self.calls < 38, 'Unexpected extra model request')
        item = self.inventory['calls'][self.calls]
        expected, response = load(item['wire']), load(item['response'])
        proof=None;alias_proof=None;comparison_expected=expected;comparison_actual=body
        if self.calls==35:
            from handle_proof import prove_aliases
            require(callable(self.current_journal) and self.navigation_codec is not None,'Alias proof binding missing')
            comparison_expected,comparison_actual,alias_proof=prove_aliases(expected,body,response,
                checked(self.inventory['original_journal']),self.current_journal(),self.navigation_codec)
        if self.calls==37:
            require(callable(self.current_journal),'Current journal locator missing')
            old_choice=json.loads(expected['messages'][1]['content'])['view']['domain_choice']
            new_choice=json.loads(body['messages'][1]['content'])['view']['domain_choice']
            proof=validate_domain_records(domain_record(checked(self.inventory['original_journal']),old_choice['choice_id']),
                domain_record(self.current_journal(),new_choice['choice_id']))
        receipt = compare_request(comparison_expected, comparison_actual,domain_proof=proof)
        receipt['comparison_request_exact']=receipt['whole_request_exact']
        receipt['whole_request_exact']=digest(expected)==digest(body)
        receipt['whole_wire_request_exact']=digest(expected)==digest(body)
        receipt['wire_schema_exact']=expected.get('response_format')==body.get('response_format')
        if alias_proof:receipt['alias_proof']=alias_proof
        if proof:receipt['domain_choice_proof']=proof
        receipt['call'] = self.calls + 1
        self.checks.append(receipt)
        require(receipt['schema_exact'] and receipt['system_exact'] and
                receipt['expected_phase'] == receipt['actual_phase'], 'Replay phase/schema mismatch')
        # All protected fields must match before literal evidence is delivered.
        require(receipt['protected_request_exact'], 'Protected request differs from historical input')
        require(response['model'] == 'qwen/qwen3.8-27b' and response['provider'] == 'Parasail'
                and len(response['choices']) == 1 and response['choices'][0]['finish_reason'] == 'stop',
                'Recorded response is not a complete expected-provider response')
        self.calls += 1
        return {'status_code': 200, 'body_json': response, 'acceptance': 'ACCEPTED'}

@contextmanager
def offline_network():
    originals = {n: getattr(socket.socket, n) for n in ('connect', 'connect_ex', 'sendto')}
    resolver = socket.getaddrinfo
    def denied(*args, **kwargs):
        raise ReplayBoundary('Offline replay forbids network resolution')
    def guard(name):
        def call(sock, *args, **kwargs):
            require(sock.family not in (socket.AF_INET, socket.AF_INET6), 'Offline replay forbids network')
            return originals[name](sock, *args, **kwargs)
        return call
    for name in originals:
        setattr(socket.socket, name, guard(name))
    socket.getaddrinfo = denied
    try:
        yield
    finally:
        for name, value in originals.items():
            setattr(socket.socket, name, value)
        socket.getaddrinfo = resolver
