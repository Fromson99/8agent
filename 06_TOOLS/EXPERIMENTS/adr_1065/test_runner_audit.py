"""Synthetic native-journal/audit integration; root runs sequentially, no model."""
import json
import sqlite3
import unittest
from copy import deepcopy
from common import canonical_digest as digest
from delivery_spans import text_hash
from wire_audit import journal_records, reconstruct
from run_case import require_continuation_gate, IntegrityFailure


class NativeDeliveryIntegration(unittest.TestCase):
    def setUp(self):
        self.span={'block_id':'11','start_cp':0,'end_cp':3,'text':'가나다',
                   'evidence_id':'E','ordinal':0,'span_hash':text_hash('가나다')}
        self.source={'document_id':'doc','source_id':'source','id':'SRC',
                     'text':'가나다','spans':[deepcopy(self.span)]}
        self.view={'sources':[self.source],'input_mode':'REVIEW','source_stage':'law-navigation-read-choice'}
        self.request={'messages':[{'role':'user','content':json.dumps({'view':self.view},ensure_ascii=False)}]}
        self.codecs={'expand':lambda v:v}
        self.checks=[{'evidence_id':'E','span_count':1,'exact_original_match':True}]
        self.acquired=[{**self.span,'document_id':'doc','source_id':'source','source_artifact_sha256':'a'*64}]
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row
        self.db.executescript('''
          CREATE TABLE evidence_unit(evidence_id,document_id,source_id,source_artifact_hash,generation_id,text_hash,created_seq);
          CREATE TABLE evidence_span(evidence_id,ordinal,block_id,start_cp,end_cp,text,span_hash);
          CREATE TABLE event(kind,payload_json,payload_hash);
          CREATE TABLE model_view(view_id,body_json,body_hash);
          CREATE TABLE model_attempt(attempt_id,status,request_json,request_hash,created_seq,view_id);
        ''')
        self.db.execute('INSERT INTO evidence_unit VALUES(?,?,?,?,?,?,?)',('E','doc','source','a'*64,'g',text_hash('가나다'),1))
        self.db.execute('INSERT INTO evidence_span VALUES(?,?,?,?,?,?,?)',('E',0,'11',0,3,'가나다',text_hash('가나다')))
        self.add_attempt(self.view,self.request)
    def add_attempt(self,view,request):
        self.db.execute('DELETE FROM model_attempt');self.db.execute('DELETE FROM model_view')
        self.db.execute('INSERT INTO model_view VALUES(?,?,?)',('V',json.dumps(view,ensure_ascii=False),digest(view)))
        self.db.execute('INSERT INTO model_attempt VALUES(?,?,?,?,?,?)',('M','SUCCEEDED',json.dumps(request,ensure_ascii=False),digest(request),2,'V'))
    def tearDown(self):self.db.close()
    def collect(self):
        return journal_records(self.db,self.codecs,'runtime/journal.sqlite',checks=self.checks,
            acquired=self.acquired,allowed={'doc'},generation='g')
    def test_actual_journal_binds_original_hash_and_card_reference(self):
        records,failures=self.collect();self.assertEqual(failures,[])
        row=next(iter(records.values()))[0]
        self.assertEqual(row['native_request_sha256'],digest(self.request))
        self.assertEqual(row['missing_text_spans'],0)
        self.assertEqual(row['spans'][0]['source_ref'],'SRC')
        self.assertEqual(row['spans'][0]['text_sha256'],text_hash('가나다'))
    def test_future_acquisition_is_unknown_not_delivery(self):
        self.db.execute('UPDATE evidence_unit SET created_seq=3')
        records,failures=self.collect();self.assertEqual(failures,[])
        row=next(iter(records.values()))[0]
        self.assertEqual(row['status'],'UNKNOWN_NATIVE_SOURCE_BINDING')
        self.assertEqual(row['spans'],[])
    def test_native_request_hash_tamper_rejected(self):
        self.db.execute("UPDATE model_attempt SET request_hash='wrong'")
        records,failures=self.collect();self.assertEqual(records,{})
        self.assertEqual(failures[0]['reason'],'NATIVE_REQUEST_HASH_MISMATCH')
    def test_assessment_option_uses_own_native_coordinate_and_id(self):
        option={'id':'S1','document_id':'doc','source_id':'source','evidence_id':'E',
                'block_id':'11','start_cp':1,'end_cp':3,'text':'나다','text_hash':digest('나다')}
        view={'sources':[{'document_id':'doc','source_id':'source','evidence_refs':['S1']}],
              'evidence_options':[option],'source_stage':'completion-assess'}
        request={'messages':[{'role':'user','content':json.dumps({'view':view},ensure_ascii=False)}]}
        self.add_attempt(view,request);records,failures=self.collect();self.assertEqual(failures,[])
        row=next(iter(records.values()))[0]
        self.assertEqual(row['status'],'VERIFIED_EXACT_RECONSTRUCTION')
        self.assertEqual((row['spans'][0]['start_cp'],row['spans'][0]['source_ref']),(1,'S1'))
    def test_compose_source_uses_explicit_parent_evidence_receipt(self):
        span={k:self.span[k] for k in ('block_id','start_cp','end_cp','text')}
        source={'document_id':'doc','source_id':'source','evidence_id':'E',
                'evidence_ref':'S1','text':'가나다','spans':[span]}
        view={'sources':[source],'source_stage':'memory-compose'}
        request={'messages':[{'role':'user','content':json.dumps({'view':view},ensure_ascii=False)}]}
        self.add_attempt(view,request);records,failures=self.collect();self.assertEqual(failures,[])
        row=next(iter(records.values()))[0]
        self.assertEqual(row['status'],'VERIFIED_EXACT_RECONSTRUCTION')
        self.assertEqual(row['spans'][0]['evidence_id'],'E')
        self.assertEqual(row['spans'][0]['source_ref'],'E')
    def test_unapproved_source_receipt_cannot_pass(self):
        self.checks[0]['exact_original_match']=False
        with self.assertRaisesRegex(ValueError,'ORIGINAL_SOURCE_CHECK_UNKNOWN'):self.collect()
    def test_ordinal_ten_cannot_resume_even_with_any_gate_receipt(self):
        with self.assertRaisesRegex(IntegrityFailure,'exactly nine'):require_continuation_gate({})

if __name__=='__main__':unittest.main()
