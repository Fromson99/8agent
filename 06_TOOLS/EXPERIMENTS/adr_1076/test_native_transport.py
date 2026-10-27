import unittest
from copy import deepcopy
import json
from native_transport import compare_request, ReplayBoundary, offline_network, answer_content

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

if __name__=='__main__':unittest.main()
