"""Small, synthetic failure contracts; no corpus loading or model calls."""
from common import *
import sys, sqlite3, unittest
from copy import deepcopy
from types import SimpleNamespace
from jsonschema import validate, ValidationError
meta=read(DES/'candidate.json')
C=ROOT/meta['path']/'snapshot'/meta['selected_code_relative']
sys.path.insert(0,str(C/'02_BACKEND'))
from semantic_runtime.legal_agent import required_items as r, completion_contracts as cc
from semantic_runtime.legal_agent.errors import ContractError, ProposalError
from semantic_runtime.contracts import digest

class Journal:
    def __init__(self):
        self.db=sqlite3.connect(':memory:')
        self.db.execute('CREATE TABLE event(seq INTEGER PRIMARY KEY,kind,payload_json,payload_hash)')
    def event(self,kind,value):
        self.db.execute('INSERT INTO event(kind,payload_json,payload_hash) VALUES(?,?,?)',(kind,json.dumps(value),digest(value)))

def context():
    item={'item_id':'R1','method_ref':{'id':'method','revision':1},'step_id':'A','title':'모의 규정 제1조',
          'note':'A와 B를 함께 확인한다.','source_refs':[{'document_id':'d','version':'d','locator':'1','content_hash':r.text_hash('모의 원문')}],
          'source_ids':['s'],'original_status':'PREPARED','original_reason':None}
    return {'schema_version':r.VERSION,'context_key':'key','binding':{'generation':'g','store_sha256':'h'},'items':[item],'previous':None}

def claim():return {'claim_id':'C1','source_id':'s','text':'A와 B가 함께 필요하다는 해석이다.','quote':'모의 원문','evidence':[]}
def decision(action='EXPLAIN',ids=None,reason='원문 조건에 연결한 설명'):
    return {'R1':{'action':action,'claim_ids':['C1'] if ids is None else ids,'reason':reason}}

class Contracts(unittest.TestCase):
    def test_repeated_acceptance_keeps_revision_and_budget_owner(self):
        j=Journal();c=context()
        e=SimpleNamespace(required_review_context=c,required_review_proposal=decision(),
            verify_claims=lambda claims,sources:None,s=SimpleNamespace(work=j,sources=SimpleNamespace(
                store=SimpleNamespace(source=lambda d,b:{'text':'모의 원문'}),scope=['d'])))
        first=r.accept(e,{'claims':[claim()]},[])['required_review']
        again=r.accept(e,{'claims':[claim()]},[])['required_review']
        self.assertEqual(first,again)
        self.assertEqual(j.db.execute('SELECT COUNT(*) FROM event WHERE kind=?',(r.EVENT,)).fetchone()[0],1)
        e.required_review_proposal=decision('UNKNOWN',[],'재검토로 미확인으로 변경')
        changed=r.accept(e,{'claims':[claim()]},[])['required_review']
        self.assertEqual(changed['rows'][0]['revision'],2)
        j.db.close()
    def test_missing_item_is_visible_unknown_not_explained(self):
        value=r.resolve(context(),{},[])
        self.assertEqual(value['rows'][0]['status'],'UNKNOWN')
        self.assertFalse(value['rows'][0]['model_processed'])
        text=r.render(value)
        self.assertIn('A와 B를 함께 확인한다.',text)
        self.assertIn('미확인',text)
    def test_valid_explanation_bound_to_claim(self):
        value=r.resolve(context(),decision(),[claim()])
        self.assertEqual(value['rows'][0]['claims'],[claim()])
        self.assertIn(claim()['text'],r.render(value))
        self.assertFalse(value['automatic_legal_approval'])
    def test_source_location_alone_cannot_mark_explained_without_claim(self):
        with self.assertRaises(ProposalError):r.resolve(context(),decision(ids=[]),[])
    def test_unknown_item_rejected(self):
        with self.assertRaises(ProposalError):r.resolve(context(),{'bogus':{}},[])
    def test_unknown_claim_rejected(self):
        with self.assertRaises(ProposalError):r.resolve(context(),decision(ids=['C9']),[claim()])
    def test_other_source_claim_rejected(self):
        with self.assertRaises(ProposalError):r.resolve(context(),decision(),[{**claim(),'source_id':'different'}])
    def test_not_applicable_requires_reason_and_no_claim(self):
        value=r.resolve(context(),decision('NOT_APPLICABLE',[],'질문은 기간만 묻고 수량은 묻지 않는다.'),[])
        self.assertEqual(value['rows'][0]['status'],'NOT_APPLICABLE')
        with self.assertRaises(ProposalError):r.resolve(context(),decision('NOT_APPLICABLE',['C1']),[claim()])
        with self.assertRaises(ProposalError):r.resolve(context(),decision('NOT_APPLICABLE',[],'  '),[])
    def test_omission_retains_history_without_current_approval(self):
        c=context();c['previous']=r.resolve(c,decision(),[claim()])
        value=r.resolve(c,{},[]);row=value['rows'][0]
        self.assertEqual(row['status'],'UNKNOWN');self.assertEqual(row['claims'],[])
        self.assertEqual(row['prior_review']['claims'],[claim()])
        self.assertIn('이전 검토 기록',r.render(value))
    def test_explicit_keep_preserves_source_bound_result(self):
        c=context();c['previous']=r.resolve(c,decision(),[claim()])
        value=r.resolve(c,decision('KEEP',[],'원문과 질문 범위가 같아서 유지'),[])
        self.assertEqual(value['rows'][0]['claims'],[claim()])
        self.assertEqual(value['rows'][0]['revision'],2)
    def test_keep_without_prior_is_not_success(self):
        with self.assertRaises(ProposalError):r.resolve(context(),decision('KEEP',[]),[])
    def test_changed_result_preserves_prior_hash_and_reason(self):
        c=context();c['previous']=r.resolve(c,decision(),[claim()]);before=deepcopy(c['previous'])
        value=r.resolve(c,decision('UNKNOWN',[],'새 원문에서 적용 범위가 달라 추가 확인이 필요'),[])
        self.assertEqual(c['previous'],before)
        self.assertEqual(value['rows'][0]['previous_result_hash'],digest(before['rows'][0]))
    def test_undelivered_original_cannot_be_claimed_explained(self):
        c=context();c['items'][0]['original_status']='OMITTED'
        with self.assertRaises(ProposalError):r.resolve(c,decision(),[claim()])
        self.assertIn('완전히 전달하지 못했습니다',r.render(r.resolve(c,{},[])))
    def test_source_acl_version_hash(self):
        items=context()['items'];store=SimpleNamespace(source=lambda d,b:{'text':'모의 원문'})
        r.validate_sources(items,store,['d'])
        with self.assertRaises(ContractError):r.validate_sources(items,store,[])
        changed=deepcopy(items);changed[0]['source_refs'][0]['version']='old'
        with self.assertRaises(ContractError):r.validate_sources(changed,store,['d'])
        store.source=lambda d,b:{'text':'개정 원문'}
        with self.assertRaises(ContractError):r.validate_sources(items,store,['d'])
    def test_journal_resume_and_tamper(self):
        j=Journal();value=r.resolve(context(),decision(),[claim()]);j.event(r.EVENT,value)
        self.assertEqual(r.latest(j,'key'),value);self.assertIsNone(r.latest(j,'other-question'))
        self.assertEqual(r.publication_metadata(j),{r.FIELD:value})
        j.db.execute("UPDATE event SET payload_json='{}'")
        with self.assertRaises(ContractError):r.latest(j,'key')
        j.db.close()
    def test_composition_must_preserve_required_section_and_receipt(self):
        a={'claims':[],'gaps':[],'limitations':[],'limitation_items':[],'completion_contract':cc.V8,
           'required_review':r.resolve(context(),{},[]),'stop_reason':None}
        out=cc.compose(a,cc.default_plan(a));cc.verify_composition(a,out)
        self.assertIn('A와 B를',out['text'])
        changed=deepcopy(out);changed['text']=changed['text'].split('원문별 필수 확인 사항')[0]
        with self.assertRaises(ContractError):cc.verify_composition(a,changed)
        changed=deepcopy(out);changed['required_review']['rows']=[]
        with self.assertRaises(ContractError):cc.verify_composition(a,changed)
    def test_schema_and_capture_dont_touch_other_phases(self):
        e=SimpleNamespace(required_review_context=context());schema={'type':'object','properties':{},'additionalProperties':False}
        view,wire,prompt=r.model_input(e,{},schema,'memory-assess')
        self.assertIn('required_review_items',view);self.assertTrue(prompt);self.assertNotIn(r.FIELD,schema['properties'])
        rows=[{'item_id':k,**v} for k,v in decision().items()]
        validate({r.FIELD:rows},wire);validate({},wire)
        with self.assertRaises(ValidationError):validate({r.FIELD:[{'item_id':'R-other'}]},wire)
        self.assertEqual(r.capture(e,{r.FIELD:rows},'memory-assess'),{})
        self.assertEqual(e.required_review_proposal,decision())
        with self.assertRaises(ProposalError):r.capture(e,{r.FIELD:rows+rows},'memory-assess')
        self.assertEqual(r.model_input(e,{},schema,'memory-compose'),({},schema,''))
    def test_html_in_note_is_not_executable(self):
        c=context();c['items'][0]['note']='<script>alert(1)</script>'
        text=r.render(r.resolve(c,{},[]));self.assertNotIn('<script>',text);self.assertIn('&lt;script&gt;',text)
    def test_count_and_false_certification_rejected(self):
        value=r.resolve(context(),{},[]);value['registered_item_count']=0
        with self.assertRaises(ContractError):r.render(value)
        value=r.resolve(context(),{},[]);value['rows'][0]['semantic_verified']=True
        with self.assertRaises(ContractError):r.render(value)

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Contracts))
    put(ART/'required-item-contracts.json',{'status':'PASS' if result.wasSuccessful() else 'FAIL',
        'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'model_calls':0,'synthetic':True})
    raise SystemExit(0 if result.wasSuccessful() else 1)
