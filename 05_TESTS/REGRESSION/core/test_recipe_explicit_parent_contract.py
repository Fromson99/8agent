"""ADR0357 ordinary negative contracts, fake providers not accuracy evidence."""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
ROOT=Path(__file__).resolve().parents[3]
P=ROOT/'02_BACKEND/lawrag/research/candidates/adr_0357/loop/revisions/rev-001/snapshot/02_BACKEND/lawrag/core/structure/recipe_visual_loop.py'
spec=importlib.util.spec_from_file_location('test_loop_candidate',P)
loop=importlib.util.module_from_spec(spec);spec.loader.exec_module(loop)
CAT={'a':{},'b':{}}
R={'tag':'test','version':1,'levels':[['a'],['b']]}

@pytest.mark.parametrize('recipe',[
 {'tag':'x','version':1,'levels':[['a'],['evil']]},
 {'tag':'x','version':1,'levels':[['a'],['a','b']]},
 {'tag':'x','version':1,'levels':[['a'],[],['b']]},
 {'tag':'x','version':1,'levels':[['a'],['b']],'regex':'.*'},
 {'tag':'../x','version':1,'levels':[['a'],['b']]},
])
def test_invalid_recipe(recipe):
    with pytest.raises(ValueError):loop.validate(recipe,CAT)

def setup_fake(monkeypatch):
    result=SimpleNamespace(ladder=SimpleNamespace(dump=lambda:{}),tree=[],fitness_passed=True,fitness_score=1,warnings=[])
    monkeypatch.setattr(loop,'build',lambda *args:result)
    return [SimpleNamespace(dump=lambda:{'idx':0},idx=0)]

def test_provider_failure_holds(monkeypatch):
    blocks=setup_fake(monkeypatch);saved=[]
    def fail(*args):raise TimeoutError('simulated provider timeout')
    result=loop.correct(None,blocks,R,CAT,[],fail,lambda n,d:saved.append(n))
    assert result['status']=='needs_review' and result['reason']=='failed_step'
    assert any('error' in n for n in saved)

def test_cycle_stops(monkeypatch):
    blocks=setup_fake(monkeypatch);calls=[]
    def call(*args):calls.append(1);return {'verdict':'revise','issues':[{'blocks':[0],'reason':'bad'}],'recipe':R}
    r=loop.correct(None,blocks,R,CAT,[],call,lambda *a:None)
    assert r['reason']=='recipe_cycle' and len(calls)==1

def test_inconsistent_approval_holds(monkeypatch):
    blocks=setup_fake(monkeypatch)
    r=loop.correct(None,blocks,R,CAT,[],lambda *a:{'verdict':'approve','issues':[{'blocks':[0],'reason':'still wrong'}],'recipe':R},lambda *a:None)
    assert r['status']=='needs_review'

def test_budget_stops(monkeypatch):
    blocks=setup_fake(monkeypatch)
    other={**R,'levels':[['b'],['a']]}
    r=loop.correct(None,blocks,R,CAT,[],lambda *a:{'verdict':'revise','issues':[],'recipe':other},lambda *a:None,max_corrections=0)
    assert r['reason']=='correction_budget_exhausted'


def test_explicit_parent_declarations_reach_engine():
    captured={}
    def interpret(blocks,**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(nodes=lambda:[])
    loop.build(SimpleNamespace(interpret=interpret),[],R,CAT,[])
    assert captured['ladder_hint']==[['a'],['b']]
    assert captured['partial_order']==[('a','b')]
    assert captured['llm'] is None
