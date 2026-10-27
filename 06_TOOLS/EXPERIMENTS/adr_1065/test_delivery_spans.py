"""Small synthetic JSON contracts; no corpus, native service or model imports."""
from copy import deepcopy
import unittest
from delivery_spans import (AuditError,Unknown,audit_view,digest,text_hash,evidence_index,union)


class DeliverySpans(unittest.TestCase):
    def setUp(self):
        self.version='a'*64;self.allowed={'doc'}
        self.spans=[{'block_id':'11','start_cp':0,'end_cp':3,'text':'가나다','evidence_id':'E',
                     'ordinal':0,'span_hash':text_hash('가나다')},
                    {'block_id':'12','start_cp':0,'end_cp':4,'text':'조건 예','evidence_id':'E',
                     'ordinal':1,'span_hash':text_hash('조건 예')}]
        record={'evidence_id':'E','document_id':'doc','source_id':'source','source_artifact_hash':self.version,
                'generation_id':'g','text_hash':text_hash('가나다\n조건 예'),'spans':deepcopy(self.spans)}
        self.records=[record];self.checks=[{'evidence_id':'E','span_count':2,'exact_original_match':True}]
        self.acquired=[{'evidence_id':'E','document_id':'doc','source_id':'source',
            'source_artifact_sha256':self.version,**{k:s[k] for k in ('block_id','start_cp','end_cp')},
            'text_sha256':text_hash(s['text'])} for s in self.spans]
        self.index=evidence_index(self.records,self.checks,self.acquired,self.allowed,'g')
        source={'document_id':'doc','source_id':'source','id':'group','text':'가나다\n조건 예',
                'spans':deepcopy(self.spans)}
        exact={'evidence':'E','text':source['text'],'spans':deepcopy(self.spans)}
        self.stored={'sources':[source],'exact_evidence':[exact]}
        self.wire=deepcopy(self.stored)
        self.wire['sources'][0]['text_id']='TEXT1'
        self.wire['exact_evidence'][0].pop('text')
        self.wire['exact_evidence'][0]['text_ref']={'id':'TEXT1','start':0,'end':8}
        for s in self.wire['exact_evidence'][0]['spans']:s.pop('text')

    def result(self):return audit_view(self.wire,self.stored,self.index,self.allowed)

    def test_parent_ref_exact_children_and_duplicate_union(self):
        result=self.result()
        self.assertEqual(result['status'],'VERIFIED')
        self.assertEqual(result['parent_children_resolved'],2)
        self.assertEqual(result['occurrence_count'],4)
        self.assertEqual(result['unique_range_count'],2)
        self.assertEqual(result['unique_codepoints'],7)

    def test_every_source_span_ref_is_checked_independently(self):
        row=self.wire['sources'][0]['spans'][0];row.pop('text')
        row['text_ref']={'id':'TEXT1','start':0,'end':3}
        self.assertEqual(self.result()['status'],'VERIFIED')
        row['text_ref']['start']=1
        with self.assertRaises(AuditError):self.result()

    def test_wrong_parent_owner_with_identical_text_rejected(self):
        self.wire['sources'][0]['document_id']='other'
        with self.assertRaises(AuditError):self.result()

    def test_parent_ref_out_of_range_rejected(self):
        self.wire['exact_evidence'][0]['text_ref']['end']=9
        with self.assertRaisesRegex(AuditError,'PARENT_TEXT_REF_OUT_OF_RANGE'):self.result()

    def test_parent_wrong_offset_rejected(self):
        self.wire['exact_evidence'][0]['text_ref']['start']=1
        with self.assertRaisesRegex(AuditError,'PARENT_BODY_DIFFERS_FROM_NATIVE'):self.result()

    def test_parent_unknown_is_not_verified(self):
        self.wire['exact_evidence'][0]['text_ref']['id']='missing'
        result=self.result();self.assertEqual(result['status'],'UNKNOWN')
        self.assertEqual(result['unknown'][0]['code'],'PARENT_TEXT_REF_UNAVAILABLE')

    def test_coordinate_change_rejected(self):
        self.wire['exact_evidence'][0]['spans'][1]['start_cp']=1
        with self.assertRaisesRegex(AuditError,'WIRE_NATIVE_COORDINATE_MISMATCH'):self.result()

    def test_native_span_hash_change_rejected(self):
        self.stored['exact_evidence'][0]['spans'][0]['span_hash']='b'*64
        with self.assertRaisesRegex(AuditError,'NATIVE_SPAN_HASH_MISMATCH'):self.result()

    def test_duplicate_conflicting_occurrence_not_discarded(self):
        self.wire['exact_evidence'][0]['spans'][0]['text']='거짓말'
        with self.assertRaisesRegex(AuditError,'DELIVERED_TEXT_DIFFERS_FROM_NATIVE'):self.result()

    def test_union_rejects_conflicting_overlap(self):
        rows=self.result()['occurrences'];bad=deepcopy(rows[0]);bad['text']='거짓말'
        with self.assertRaisesRegex(AuditError,'CONFLICTING_OVERLAP_TEXT'):union(rows+[bad])

    def assessment(self):
        identity={'source_id':'source','document_id':'doc','block_id':'11','start_cp':1,'end_cp':3,
                  'evidence_id':'E','text_hash':digest('나다')}
        option={'id':'S1',**identity,'text':'나다'}
        self.stored={'sources':[{'document_id':'doc','source_id':'source','evidence_refs':['S1']}],
                     'evidence_options':[option]}
        self.wire={'sources':[{'source_id':'source','evidence_refs':['S1']}],
                   'evidence_options':[{'id':'S1','text':'나다'}]}

    def test_assessment_option_uses_native_id_and_exact_acquired_subrange(self):
        self.assessment();result=self.result()
        self.assertEqual(result['status'],'VERIFIED')
        self.assertEqual(result['unique_codepoints'],2)
        self.assertEqual(result['occurrences'][0]['start_cp'],1)

    def test_missing_evidence_ref_rejected(self):
        self.assessment();self.wire['sources'][0]['evidence_refs']=['absent']
        with self.assertRaises(AuditError):self.result()

    def test_evidence_ref_silently_removed_rejected(self):
        self.assessment();self.wire['sources'][0]['evidence_refs']=[]
        with self.assertRaises(AuditError):self.result()

    def test_unknown_option_id_is_not_text_matched(self):
        self.assessment();self.wire['evidence_options'][0]['id']='other'
        with self.assertRaisesRegex(AuditError,'DELIVERED_OPTION_ID_NOT_IN_NATIVE_VIEW'):self.result()

    def test_assessment_option_text_hash_rejected(self):
        self.assessment();self.stored['evidence_options'][0]['text_hash']='c'*64
        with self.assertRaisesRegex(AuditError,'NATIVE_OPTION_TEXT_HASH_MISMATCH'):self.result()

    def test_assessment_unacquired_evidence_is_unknown(self):
        self.assessment();self.stored['evidence_options'][0]['evidence_id']='absent'
        self.assertEqual(self.result()['status'],'UNKNOWN')

    def test_assessment_acl_never_inferred_from_text(self):
        self.assessment();self.allowed=set()
        with self.assertRaisesRegex(AuditError,'SOURCE_OUTSIDE_ACL'):self.result()

    def test_native_generation_version_hash_and_original_receipt_rejected(self):
        for field,value in [('generation_id','wrong'),('text_hash','f'*64),('source_artifact_hash','b'*64)]:
            records=deepcopy(self.records);records[0][field]=value
            with self.assertRaises(AuditError):evidence_index(records,self.checks,self.acquired,self.allowed,'g')
        checks=deepcopy(self.checks);checks[0]['exact_original_match']=False
        with self.assertRaises(AuditError):evidence_index(self.records,checks,self.acquired,self.allowed,'g')

    def test_parent_boolean_offset_not_an_integer(self):
        self.wire['exact_evidence'][0]['text_ref']['start']=False
        with self.assertRaisesRegex(AuditError,'PARENT_TEXT_REF_OUT_OF_RANGE'):self.result()

    def test_empty_entry_has_no_claimed_originals(self):
        result=audit_view({}, {}, {}, self.allowed)
        self.assertEqual(result['status'],'VERIFIED');self.assertEqual(result['occurrence_count'],0)


if __name__=='__main__':unittest.main()
