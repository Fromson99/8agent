"""Actual compact wire consumer and ontology synthetic HTTP contracts; models0."""
import ast
from copy import deepcopy
import json,sqlite3
from types import SimpleNamespace as S
import pytest
from conftest import term_glossary
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import ontology_io as io, compact_model_input as minimal
from semantic_runtime.legal_agent.navigation_input import expand_cards

_last_stage=''
_actual=[]
def decode_wire(value):
    # Only fixture routing uses the separately captured stage. All mock choices
    # read the transmitted material and tables, never the hidden canonical view.
    view=expand_cards(value)
    if 'phase' not in view:
        view['phase']='investigate';view['source_stage']=_last_stage
        _actual.append(deepcopy(value))
    if isinstance(view.get('tool_options'),dict):
        view['tool_options']=[dict(row,choice=kind) for kind,rows in view['tool_options'].items() for row in rows]
    view.setdefault('sources',[])
    view.setdefault('references',{}).setdefault('dependency_cards',[])
    ctx=view.get('read_judgments',{})
    for key in ('judgments','needs','conflicts','required','current_originals'):ctx.setdefault(key,[])
    return view


@pytest.mark.parametrize('mode',['A1','A2'])
def test_combined_actual_http_choices_delivery_and_duplicate(tmp_path,term_glossary,monkeypatch,mode):
    import semantic_runtime.app as app_module
    import test_read_judgment_api as fixture_module
    import test_task_local_api_adr1065 as parent
    from test_action_choice_ontology_adr1066 import single_provision_snapshot
    # The retained deterministic transport learns the compact wire syntax,
    # keeping its original decisions and source-bound judgments unchanged.
    tree=ast.parse(open(fixture_module.__file__).read())
    target=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='test_read_judgment_api_retains_decisions_and_reuses_request')
    for n in ast.walk(target):
        if isinstance(n,ast.ImportFrom) and n.module=='semantic_runtime.legal_agent.navigation_input':
            n.module='test_combined';n.names=[ast.alias(name='decode_wire',asname='expand_cards')]
    namespace=dict(vars(fixture_module));exec(compile(ast.fix_missing_locations(ast.Module(body=[target],type_ignores=[])),fixture_module.__file__,'exec'),namespace)
    monkeypatch.setattr(parent,'original_api_case',namespace[target.name])
    old_project=minimal.project;old_create=app_module.create_app;approved={}
    def project(view,schema=None):
        global _last_stage
        _last_stage=view.get('source_stage','')
        return old_project(view,schema)
    monkeypatch.setattr(minimal,'project',project)
    def create(*args,**kwargs):
        snapshot,text=single_provision_snapshot(tmp_path/'raw.sqlite');approved.update(snapshot=snapshot,text=text)
        p=deepcopy(kwargs['legal_agent_profile']);p['candidate_navigation'].update(minimal_input=True,read_candidate_page_size=20,minimal_action_choices=True,
            ontology_context={'mode':mode,'snapshot':snapshot,'snapshot_sha256':digest(snapshot)})
        kwargs['legal_agent_profile']=p
        return old_create(*args,**kwargs)
    monkeypatch.setattr(app_module,'create_app',create)
    _actual.clear()
    result=parent.test_task_local_native_api_screen_review_execute_final_and_duplicate_request(tmp_path,term_glossary,monkeypatch)
    wire=[expand_cards(v) for v in _actual]
    assert wire and all('phase' not in v and 'presentation_id' not in v for v in _actual)
    cards=[c for v in wire for c in v.get('ontology_bundles',[])]
    assert cards and all(c['mode']==mode for c in cards)
    source_texts=[s['text'] for v in wire for s in v.get('sources',[]) if 'text' in s]
    assert approved['text'] in source_texts
    assert any(v.get('read_candidate_page') for v in wire)
    for v in wire:
        assert len(v.get('read_candidates',[]))<=20
        for card in v.get('ontology_bundles',[]):
            assert 'bundle_sha256' not in card['payload']
            for provision in card['payload']['provisions']:
                assert provision['anchor']=={'label':'합성 제1조'}
    with sqlite3.connect(result['journal']) as db:
        kinds=[r[0] for r in db.execute('SELECT kind FROM event')]
        assert 'MINIMAL_INPUT_PROJECTION' in kinds and 'ONTOLOGY_REVIEW_PAGE_DELIVERED' in kinds
        receipts=[json.loads(r[0]) for r in db.execute("SELECT payload_json FROM event WHERE kind='NAVIGATION_REVIEW_TRANSITION'")]
        assert any(r.get('action_status')=='EXECUTED' for r in receipts)
    print('COMBINED_API',mode,result['choices'],'actual_wire',len(wire))


@pytest.mark.parametrize('commit',[False,True])
def test_first_index_ddl_transaction_cannot_poison_ready_flag(commit):
    db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE event(seq INTEGER PRIMARY KEY,kind,payload_json,payload_hash)')
    p={'presentation_id':'p'};db.execute('INSERT INTO event VALUES(1,?,?,?)',('NAVIGATION_INPUT_DELIVERED',json.dumps(p),digest(p)));db.commit()
    repo=S(db=db);db.execute('BEGIN')
    before=list(io.delivery_events(repo,'p'));assert before and repo._ontology_delivery_index_ready is False
    if commit:db.commit()
    else:db.rollback()
    assert bool(db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(io.RECEIPT_INDEX,)).fetchone())==commit
    assert list(io.delivery_events(repo,'p'))==before
    assert repo._ontology_delivery_index_ready is True
    assert db.execute('SELECT 1 FROM sqlite_master WHERE name=?',(io.RECEIPT_INDEX,)).fetchone()
    db.close()
