import unittest
from copy import deepcopy
import json
from native_transport import compare_request, ReplayBoundary, offline_network, answer_content, validate_domain_records, digest

class ReplayComparison(unittest.TestCase):
    def body(self):
        return {'model':'frozen','messages':[{'role':'system','content':'same'},
            {'role':'user','content':json.dumps({'view':{'view_id':'V'+'a'*32,'sources':[{'id':'S1','text':'원문'}],'source_stage':'s'}})}],
            'response_format':{'schema':'same'}}
    def edit_view(self,body,key,value):
        user=json.loads(body['messages'][1]['content']);user['view'][key]=value
        body['messages'][1]['content']=json.dumps(user);return body
    def test_uuid_only_comparison_exemption(self):
        expected=self.body();actual=self.edit_view(deepcopy(expected),'view_id','V'+'b'*32)
        self.assertTrue(compare_request(expected,actual)['protected_request_exact'])
        self.assertFalse(compare_request(expected,actual)['whole_request_exact'])
        self.assertIn('V'+'b'*32,actual['messages'][1]['content'])
    def test_stable_alias_is_protected(self):
        self.assertFalse(compare_request(self.body(),self.edit_view(self.body(),'view_id','V1'))['protected_request_exact'])
    def test_source_action_and_schema_changes_detected(self):
        for field,value in [('sources',[]),('source_stage','other'),('actions',[{'id':'A1'}])]:
            self.assertFalse(compare_request(self.body(),self.edit_view(self.body(),field,value))['protected_request_exact'])
        actual=self.body();actual['response_format']={}
        self.assertFalse(compare_request(self.body(),actual)['schema_exact'])
    def test_network_disabled(self):
        import socket
        with offline_network(),self.assertRaises(ReplayBoundary):socket.getaddrinfo('example.com',443)
    def test_answer_identity_binding(self):
        body={'run_id':'abc','query':{'id':'query:def'},'answer':{'id':'answer:abc','query_id':'query:def','text':'원문'}}
        self.assertEqual(answer_content(body),{'text':'원문'})
        self.assertEqual(body['answer']['id'],'answer:abc')
        body['answer']['id']='answer:wrong'
        with self.assertRaises(ReplayBoundary):answer_content(body)
    def records(self):
        selected={'method_id':'SUPPORTED_PRESENTATION','path':'DISCOVERY','reason':'same','concept_ids':[],'relation_ids':[]}
        rows=[]
        for run in ('original','fresh'):
            rows.append({'run_id':run,'stage':'COMPOSE','created_seq':1595,'offer_json':'{"method":"same"}',
                'choice_json':json.dumps(selected),'id':'D'+digest([run,'COMPOSE',1595,selected])[:28]})
        return rows
    def test_domain_ids_prove_each_native_run(self):
        old,new=self.records();proof=validate_domain_records(old,new)
        expected=self.edit_view(self.body(),'source_stage','memory-compose')
        actual=deepcopy(expected)
        self.edit_view(expected,'domain_choice',{'choice_id':old['id'],'reason':'same'})
        self.edit_view(actual,'domain_choice',{'choice_id':new['id'],'reason':'same'})
        self.assertFalse(compare_request(expected,actual)['protected_request_exact'])
        self.assertTrue(compare_request(expected,actual,domain_proof=proof)['protected_request_exact'])
        self.assertIn(new['id'],actual['messages'][1]['content'])
    def test_domain_corrupt_or_foreign_id_rejected(self):
        for key,value in [('id','Dwrong'),('run_id','another'),('stage','READ'),('created_seq',1596)]:
            old,new=self.records();new[key]=value
            with self.assertRaises(ReplayBoundary):validate_domain_records(old,new)
    def test_recomputed_id_cannot_hide_semantic_change(self):
        for key,value in [('choice_json','{"reason":"changed"}'),('offer_json','{"method":"changed"}')]:
            old,new=self.records();new[key]=value
            new['id']='D'+digest([new['run_id'],new['stage'],new['created_seq'],json.loads(new['choice_json'])])[:28]
            with self.assertRaises(ReplayBoundary):validate_domain_records(old,new)
    def test_domain_id_exemption_cannot_hide_other_input_change(self):
        old,new=self.records();proof=validate_domain_records(old,new)
        expected=self.edit_view(self.body(),'source_stage','memory-compose');actual=deepcopy(expected)
        self.edit_view(expected,'domain_choice',{'choice_id':old['id'],'reason':'same'})
        self.edit_view(actual,'domain_choice',{'choice_id':new['id'],'reason':'changed'})
        self.assertFalse(compare_request(expected,actual,domain_proof=proof)['protected_request_exact'])

if __name__=='__main__':unittest.main()
