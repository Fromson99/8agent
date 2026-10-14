from copy import deepcopy
import pytest
from jsonschema import Draft202012Validator
from semantic_runtime.legal_agent import completion_contracts as cc


def claim():
 return {'claim_id':'C1','issue_refs':['Q1','Q2'],'evidence_refs':['S1','S2'],'text':'모델의 독립 초안',
  'rule':{'kind':'GENERAL_RULE','subject':'신청자','action':'신청','scope':'모의 규정','conclusion':'승인 대상입니다.',
   'conditions':[{'id':'T1','text':'A 자격','evidence_refs':['S1']},{'id':'T2','text':'B 자격','evidence_refs':['S1']}],
   'groups':[{'id':'G1','mode':'ANY','members':['T1','T2']}],'root':'G1',
   'exceptions':[{'text':'기간 경과 제외','evidence_refs':['S2']}],'exception_status':'SOURCE_EXCEPTIONS','fact_refs':[]}}


def test_versioned_strict_condition_contract_and_deterministic_assembly():
 c=claim();assert cc.CONTRACT.endswith('v4') and not cc.rule_errors(c)
 v={'claims':[c],'disposition':'ANSWER','issue_assessments':[{'issue_id':q,'status':'COVERED','reason':'모의'} for q in ['Q1','Q2']],'gaps':[]}
 options=[{'id':s,'source_id':s,'text':'모의 원문'} for s in ['S1','S2']]
 issues=[{'id':q,'question':q} for q in ['Q1','Q2']]
 schema=cc.assessment_schema(issues,[],options,contract=cc.CONTRACT)
 assert not list(Draft202012Validator(schema).iter_errors(v))
 a=cc.materialize_assessment(v,options,issues);text=cc.compose(a,cc.default_plan(a,None,issues))['text']
 assert '하나 이상' in text and '모두 충족' not in text and '기간 경과 제외' in text
 assert '모델의 독립 초안' not in text and text.count('승인 대상입니다.')==1
 assert '공통 판단에 함께 설명' in text

@pytest.mark.parametrize('change',['cycle','unknown','depth','unreachable','source','exception','fact'])
def test_invalid_condition_provenance_is_rejected(change):
 c=claim();r=c['rule']
 if change=='cycle':r['groups'][0]['members'].append('G1')
 if change=='unknown':r['groups'][0]['members'].append('T9')
 if change=='depth':
  r['root']='G6';r['groups'] += [{'id':'G'+str(i),'mode':'ALL','members':['G'+str(i-1)]} for i in range(2,7)]
 if change=='unreachable':r['conditions'].append({'id':'T9','text':'분리','evidence_refs':['S1']})
 if change=='source':r['conditions'][0]['evidence_refs']=['UNREAD']
 if change=='exception':r['exception_status']='NOT_ESTABLISHED'
 if change=='fact':r['kind']='CASE_APPLICATION'
 assert cc.rule_errors(c)


def test_user_fact_is_bound_to_current_request_separately_from_law():
 c=claim();c['rule'].update(kind='CASE_APPLICATION',fact_refs=[{'id':'U0','quote':'신청일은 1일'}])
 assert not cc.rule_errors(c,[{'id':'U0','text':'신청일은 1일입니다.'}])
 assert cc.rule_errors(c,[{'id':'S1','text':'신청일은 1일'}])
 assert cc.rule_errors(c,[{'id':'U0','text':'신청일은 2일'}])


def test_recovery_notes_never_become_answer_limitations():
 value={'gaps':[],'claims':[]}
 cc.refresh_limitations(value,[], 'MODEL_DECISION_UNRESOLVED',notes=['ASSESSMENT_NORMALIZED','ADOPTION_FALLBACK'])
 assert not any(word in ' '.join(value['limitations']) for word in ['오류','조정','채택','결정'])


def test_late_case_revision_never_publishes_judgment():
 import sqlite3
 from contextlib import contextmanager
 from types import SimpleNamespace
 from semantic_runtime.legal_agent.case_repository import CaseRepository
 from semantic_runtime.legal_agent.corrected_memory import Conflict
 from semantic_runtime.contracts import digest
 db=sqlite3.connect(':memory:');db.executescript('CREATE TABLE node(id,goal,hash,revision);CREATE TABLE goal(id,revision);CREATE TABLE head(node,stage);')
 payload={'claims':[]};db.execute('INSERT INTO node VALUES(1,?, ?, 1)',('g',digest(payload)));db.execute("INSERT INTO goal VALUES('g',2)");db.execute("INSERT INTO head VALUES(1,'ASSESS')");db.commit()
 repo=object.__new__(CaseRepository);repo.db=db
 events=[]
 @contextmanager
 def tx():yield
 work=SimpleNamespace(transaction=tx,event=lambda *a,**k:events.append((a,k)))
 execution=SimpleNamespace(pending_judgment={'stage':'ASSESS'},s=SimpleNamespace(work=work))
 with pytest.raises(Conflict):repo.stage_committed(1,'ASSESS',payload,execution)
 assert not events
 db.execute("UPDATE goal SET revision=1");db.commit()
 repo.stage_committed(1,'ASSESS',payload,execution)
 assert events[0][0][0]=='CASE_JUDGMENT_ACCEPTED'
 assert execution.pending_judgment is None
 repo.stage_committed(1,'ASSESS',payload,execution)
 assert len(events)==1
