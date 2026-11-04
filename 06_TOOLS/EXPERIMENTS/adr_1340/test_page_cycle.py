"""Control regression: real journal, immutable menus, no network/model service."""
from copy import deepcopy
from types import SimpleNamespace as S
from pathlib import Path
import gzip
import json
import sqlite3
import pytest
from jsonschema import validate, ValidationError
from semantic_runtime.contracts import digest
from semantic_runtime.legal_agent import read_candidate_pages as pages, request_repair as rr
from semantic_runtime.legal_agent.answer_progress import ProgressHandoff
from semantic_runtime.legal_agent.errors import ContractError, BudgetExhausted, TransportError
from test_compact_model_input import fixture
from test_output_contract_recovery import Journal


def setup(tmp_path, monkeypatch, choices, count=27):
    data, schema = fixture(count)
    repo = Journal(tmp_path/'journal.sqlite')
    budget = {'model_limit':40, 'model_reserved':5, 'finalization_reserve':3}
    repo.budget = lambda: budget
    inv = S(p={'binding':repo.binding, 'originals':['kept'], 'needs':['OPEN']},
            s=S(repo=repo, profile={}), policy={'minimal_input':True, 'read_candidate_page_size':20}, left=lambda:100)
    saved = {}; calls = []
    def save():
        saved.clear(); saved.update(deepcopy(inv.p))
    inv.save = save
    monkeypatch.setattr(rr, 'gap_review_capacity', lambda inv:None)
    def invoke(view, attempt, wire, suffix):
        calls.append(deepcopy(view)); budget['model_reserved'] += 1
        value = choices[len(calls)-1]
        if isinstance(value, BaseException): raise value
        return deepcopy(value if isinstance(value,dict) else {'choice':value})
    def run(key='k'):
        return pages.choose(inv,data,schema,invoke,lambda v:validate(v,schema),key=key)
    return inv,data,schema,calls,saved,run


def test_saved_main142_alternation_yields_before_budget(tmp_path, monkeypatch):
    root=Path(__file__).resolve().parents[3]
    path=root/'04_EXPERIMENTS/ADR/ADR-1338-main142-charter-resolution-live/artifacts/navigation-trace.json.gz'
    with gzip.open(path,'rt') as f: trace=json.load(f)
    choices=[r['output'] for r in trace['frames'] if 6<=r['number']<=37]
    assert len(choices)==32
    inv,data,schema,calls,saved,run=setup(tmp_path,monkeypatch,choices)
    before=deepcopy(data)
    with pytest.raises(ProgressHandoff,match=pages.NO_PROGRESS):run()
    assert len(calls)==4 and inv.s.repo.budget()['model_reserved']==9
    assert inv.p['read_candidate_pager']['sequence']==3
    assert inv.p['originals']==['kept'] and inv.p['needs']==['OPEN'] and data==before
    inv.p=json.loads(json.dumps(saved))
    with pytest.raises(ProgressHandoff,match=pages.NO_PROGRESS):run()
    assert len(calls)==4
    events=[json.loads(r[0]) for r in inv.s.repo.db.execute("SELECT payload_json FROM event WHERE kind='READ_CANDIDATE_PAGE_HANDOFF'")]
    assert len(events)==1 and not events[0]['legal_sufficiency_approved']
    assert events[0]['final_assessment_required']


@pytest.mark.parametrize('choices,count,target',[
    ([pages.NEXT,pages.PREVIOUS],27,'T0'),
    ([pages.NEXT,pages.PREVIOUS,pages.NEXT,pages.NEXT],61,'T40'),
    ([pages.NEXT,pages.NEXT,pages.PREVIOUS,pages.PREVIOUS,pages.NEXT,pages.NEXT,pages.NEXT],61,'T60'),
])
def test_backtracking_and_reaching_new_pages_remain_possible(tmp_path,monkeypatch,choices,count,target):
    expected={'choice':'READ','selections':[{'target':target}]}
    inv,data,schema,calls,saved,run=setup(tmp_path,monkeypatch,[*choices,expected],count)
    assert run()==expected and run()==expected
    assert len(calls)==len(choices)+1
    assert inv.p['read_candidate_page_progress']['halt'] is None


@pytest.mark.parametrize('when',['before','after'])
def test_crash_resume_commits_history_with_page_once(tmp_path,monkeypatch,when):
    inv,data,schema,calls,saved,run=setup(tmp_path,monkeypatch,[pages.NEXT,pages.PREVIOUS,pages.NEXT,pages.PREVIOUS])
    save=inv.save; crashed=False
    def interrupt():
        nonlocal crashed
        if inv.p.get('read_candidate_pager',{}).get('sequence')==2 and not crashed:
            crashed=True
            if when=='after':save()
            raise RuntimeError('checkpoint interruption')
        save()
    inv.save=interrupt
    with pytest.raises(RuntimeError,match='checkpoint interruption'):run()
    inv.p=deepcopy(saved); inv.save=save
    with pytest.raises(ProgressHandoff):run()
    assert len(calls)==4 and inv.p['read_candidate_pager']['sequence']==3
    assert inv.p['read_candidate_page_progress']['checkpoint']==inv.p['read_candidate_pager']


@pytest.mark.parametrize('change',['new_input','new_menu'])
def test_new_bound_presentation_gets_fresh_history(tmp_path,monkeypatch,change):
    inv,data,schema,calls,saved,run=setup(tmp_path,monkeypatch,[pages.NEXT,pages.PREVIOUS,pages.NEXT,pages.PREVIOUS,'FINISH'])
    with pytest.raises(ProgressHandoff):run()
    if change=='new_input':
        data['sources'][0]['text']='새로 확보한 원문';data['presentation_id']='P2'
    else:data['read_candidates'].append({'target':'T27'})
    assert run(key='new-presentation')=={'choice':'FINISH'}
    assert len(calls)==5 and inv.p['read_candidate_page_progress']['visited']==[0]


@pytest.mark.parametrize('field',['edges','checkpoint','input','pager'])
def test_tampered_or_stale_progress_is_not_repaired(tmp_path,monkeypatch,field):
    inv,data,schema,calls,saved,run=setup(tmp_path,monkeypatch,['FINISH'])
    run()
    if field=='input':data['sources'][0]['text']='different original without new binding'
    elif field=='pager':inv.p['read_candidate_pager']['page']=1
    else:inv.p['read_candidate_page_progress'][field]=[[0,1]]
    with pytest.raises(ContractError):run()
    assert len(calls)==1


def test_legacy_cursor_supported_without_fabricating_history(tmp_path,monkeypatch):
    inv,data,schema,calls,saved,run=setup(tmp_path,monkeypatch,['FINISH'])
    inv.p['read_candidate_pager']={'binding':digest([pages.VERSION,'k',data['read_candidates'],schema,20]),'page':1,'sequence':11}
    assert run()=={'choice':'FINISH'}
    assert inv.p['read_candidate_page_progress']['visited']==[1]
    assert inv.p['read_candidate_pager']['sequence']==11


@pytest.mark.parametrize('kind',['budget','time','unknown','hidden'])
def test_existing_failure_boundaries_preserved(tmp_path,monkeypatch,kind):
    choice=TransportError('synthetic timeout',unknown=True) if kind=='unknown' else {'choice':'READ','selections':[{'target':'T26'}]}
    inv,data,schema,calls,saved,run=setup(tmp_path,monkeypatch,[choice,choice])
    reads=[]
    def authorize(action, table, column, database, trigger):
        if action==sqlite3.SQLITE_READ:reads.append(table)
        return sqlite3.SQLITE_OK
    inv.s.repo.db.set_authorizer(authorize)
    if kind=='budget':inv.s.repo.budget()['model_reserved']=37
    if kind=='time':inv.left=lambda:1
    expected=BudgetExhausted if kind in ('budget','time') else TransportError if kind=='unknown' else ValidationError
    with pytest.raises(expected):run()
    assert len(calls)==(0 if kind in ('budget','time') else 1 if kind=='unknown' else 2)
    assert inv.p['read_candidate_pager']['sequence']==0
    assert set(reads)<={'event'}  # Inspect actual tables, not strings inside logged JSON.
    if kind=='unknown':
        with pytest.raises(ContractError,match='unknown'):run()
        assert len(calls)==1
