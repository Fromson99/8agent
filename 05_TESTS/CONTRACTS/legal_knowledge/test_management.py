from copy import deepcopy
import json
from pathlib import Path
import pytest
from lawrag.legal_knowledge.contracts import KnowledgeError, validate_definition, DEFINITION, COMMAND, REF, PLAN, canonical
from lawrag.legal_knowledge.application import ref, BINDING as BINDING_SCHEMA
from .conftest import WHO, BINDING, command, publish


def test_atomic_publication_and_edit_does_not_change_active(service, definition):
    draft, build, active = publish(service, definition)
    definition['title'] = '새 초안'
    changed = command(service, 'save_draft', {'object_id': draft['id'], 'expected_revision': 1, 'definition': definition})
    assert changed['revision'] == 2 and service.active(WHO) == active
    assert service.plan(WHO, '승인 기준', BINDING, as_of='2026-10-21')['items'][0]['title'] == draft['definition']['title']
    assert service.repo.read('definition', draft['id'], 1) == draft


def test_duplicate_command_and_changed_input_conflict(service, definition):
    args = {'object_id': None, 'expected_revision': 0, 'definition': definition}
    first = command(service, 'save_draft', args, 'same')
    assert command(service, 'save_draft', args, 'same') == first
    args = deepcopy(args); args['definition']['title'] = 'different'
    with pytest.raises(KnowledgeError, match='다른 입력'): command(service, 'save_draft', args, 'same')
    assert len(service.listing(WHO)['items']) == 1


def test_conflicting_edit_and_publish_keep_old_head(service, definition):
    draft, build, active = publish(service, definition)
    with pytest.raises(KnowledgeError) as e:
        command(service, 'save_draft', {'object_id': draft['id'], 'expected_revision': 0, 'definition': definition})
    assert e.value.status == 409
    with pytest.raises(KnowledgeError):
        command(service, 'publish', {'build_id': build['id'], 'build_hash': build['content_hash'], 'expected_revision': 0})
    assert service.active(WHO) == active


def test_retire_and_explicit_rollback_preserve_history(service, definition):
    draft, build, active = publish(service, definition)
    command(service, 'retire', {'expected_revision': 1, 'reason': '철회'})
    assert service.plan(WHO, '승인', BINDING)['items'] == []
    resumed = command(service, 'rollback', {'build_id': build['id'], 'build_hash': build['content_hash'], 'expected_revision': 2, 'reason': '복원 검토'})
    assert resumed['revision'] == 3 and service.repo.read('channel', active['id'], 1) == active


@pytest.mark.parametrize('change', [{'document_ids': []}, {'team_id': 'other'}, {'tenant_id': 'other'}])
def test_scope_hides_detail_list_operation_and_plan(service, definition, change):
    draft, build, active = publish(service, definition)
    who = {**WHO, **change}
    assert service.listing(who)['items'] == []
    with pytest.raises(KnowledgeError) as e: service.definition(ref(draft), who)
    assert e.value.status == 404
    assert service.plan(who, '승인', BINDING)['items'] == []


def test_dependency_acl_cannot_be_removed_by_draft(service, definition):
    draft, _, _ = publish(service, definition)
    linked = deepcopy(definition); linked['source_refs'] = []; linked['dependencies'] = [ref(draft)]
    saved = command(service, 'save_draft', {'object_id': None, 'expected_revision': 0, 'definition': linked})
    assert saved['document_ids'] == ['d']
    with pytest.raises(KnowledgeError):
        command(service, 'save_draft', {'object_id': None, 'expected_revision': 0, 'definition': linked}, who={**WHO, 'document_ids': []})


def test_source_change_rejects_publish_and_records_failure(service, definition):
    draft, build, active = publish(service, definition)
    service.references.denied = True
    with pytest.raises(KnowledgeError):
        command(service, 'publish', {'build_id': build['id'], 'build_hash': build['content_hash'], 'expected_revision': 1}, 'failure')
    assert service.active(WHO) == active
    assert service.operation('failure', WHO)['status'] == 'FAILED'


def test_tampered_payload_ref_and_lookup_fail_closed(service, definition):
    draft, build, _ = publish(service, definition)
    wrong = {**ref(draft), 'content_hash': '0'*64}
    with pytest.raises(KnowledgeError): service.definition(wrong, WHO)
    service.repo.db.execute('UPDATE lk_record SET payload=? WHERE namespace=? AND object_id=?', ('{}', 'definition', draft['id']))
    with pytest.raises(KnowledgeError): service.plan(WHO, '승인', BINDING)


def test_partial_unknown_source_binding_and_feedback(service, definition):
    draft, _, _ = publish(service, definition)
    plan = service.plan(WHO, '승인', BINDING)
    assert plan['items'][0]['application_status'] == 'UNRESOLVED'
    assert 'AS_OF_UNSPECIFIED' in plan['items'][0]['missing']
    assert service.plan(WHO, '승인', {**BINDING, 'store_sha256': 'b'*64})['unresolved'] == ['SOURCE_BINDING_CHANGED']
    feedback = command(service, 'feedback', {'target': ref(draft), 'request_ref': 'request:1', 'reason': '예외 확인 추가'})
    assert feedback['status'] == 'PROPOSED' and service.active(WHO)['revision'] == 1


def test_transaction_abort_does_not_leak_draft(service, definition, monkeypatch):
    original = service.repo.append
    def fail(namespace, *args, **kwargs):
        if namespace == 'operation': raise RuntimeError('synthetic crash before receipt')
        return original(namespace, *args, **kwargs)
    monkeypatch.setattr(service.repo, 'append', fail)
    with pytest.raises(RuntimeError): command(service, 'save_draft', {'object_id': None, 'expected_revision': 0, 'definition': definition}, 'resume')
    assert service.listing(WHO)['items'] == []
    monkeypatch.setattr(service.repo, 'append', original)
    assert command(service, 'save_draft', {'object_id': None, 'expected_revision': 0, 'definition': definition}, 'resume')['revision'] == 1


@pytest.mark.parametrize('mutation', ['cycle', 'scope', 'unknown_field', 'code', 'same_step'])
def test_invalid_structural_input(definition, mutation):
    if mutation == 'cycle': definition['content']['steps'][0]['after'] = ['read']
    if mutation == 'scope': definition['scope']['business']['values'] = ['risk']
    if mutation == 'unknown_field': definition['visibility'] = 'public'
    if mutation == 'code': definition['content']['steps'][0]['capability'] = 'exec'
    if mutation == 'same_step': definition['content']['steps'] *= 2
    with pytest.raises(KnowledgeError): validate_definition(definition)


def test_schema_exports_match_runtime():
    root = Path(__file__).resolve().parents[3]
    for name, schema in [('definition-v1', DEFINITION), ('command-v1', COMMAND), ('reference-v1', REF), ('source-binding-v1', BINDING_SCHEMA), ('plan-v1', PLAN)]:
        value = json.loads((root/'00_SYSTEM/SCHEMAS/legal-knowledge'/f'{name}.schema.json').read_text())
        value.pop('$schema'); value.pop('$id')
        assert value == schema


def test_private_case_link_does_not_expand_visibility(service,definition):
    definition['dependencies']=[{'kind':'SHORTCUT','id':'inv:private','revision':1,'content_hash':'b'*64}]
    draft,build,channel=publish(service,definition)
    other={**WHO,'user_id':'colleague'}
    assert draft['private_owner']==WHO['user_id']
    assert service.listing(other)['items']==[]
    assert service.listing(other,namespace='release')['items']==[]
    assert service.plan(other,'승인',BINDING)['items']==[]
    # A linked common method cannot bypass that private dependency boundary.
    child=deepcopy(definition);child['dependencies']=[ref(draft)]
    saved=command(service,'save_draft',{'object_id':None,'expected_revision':0,'definition':child})
    assert saved['private_owner']==WHO['user_id']


def test_lost_commit_ack_is_reconciled_by_same_operation(service,definition,monkeypatch):
    from contextlib import contextmanager
    original=service.repo.db.transaction
    @contextmanager
    def lost_ack():
        with original():yield
        raise KnowledgeError('KNOWLEDGE_UNAVAILABLE','synthetic lost commit acknowledgement',503)
    monkeypatch.setattr(service.repo.db,'transaction',lost_ack)
    args={'object_id':None,'expected_revision':0,'definition':definition}
    with pytest.raises(KnowledgeError):command(service,'save_draft',args,'lost-ack')
    monkeypatch.setattr(service.repo.db,'transaction',original)
    receipt=service.operation('lost-ack',WHO)
    assert receipt['status']=='COMPLETE'
    assert command(service,'save_draft',args,'lost-ack')==receipt['result']
    assert len(service.listing(WHO)['items'])==1


def test_prepare_keeps_unmodified_published_objects(service,definition):
    first,_,_=publish(service,definition)
    other=deepcopy(definition);other['title']='다른 업무 검토'
    second,build,_=publish(service,other)
    assert {r['id'] for r in build['refs']}=={first['id'],second['id']}


def test_pipeline_cli_validates_same_contract(tmp_path,definition):
    import subprocess,sys
    root=Path(__file__).resolve().parents[3]
    path=tmp_path/'draft.json';path.write_text(json.dumps(definition))
    result=subprocess.run([sys.executable,str(root/'06_TOOLS/pipeline.py'),'legal-knowledge','validate','--file',str(path)],capture_output=True,text=True)
    assert result.returncode==0 and json.loads(result.stdout)['published'] is False
