"""Tiny rejected transport proofs; no network, model or source database."""
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from common import sha
from delivery_spans import text_hash
from physical_transport import rejected_429

class RejectedTransport(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.parent=self.folder/'model/call-001-service';self.parent.mkdir(parents=True)
        self.request=self.parent/'request.json';self.request.write_text('{}')
        self.body={'error':{'code':429,'message':'synthetic rejection'}}
        raw=json.dumps(self.body).encode();self.raw=self.parent/'response-wire.bin.gz'
        self.raw.write_bytes(gzip.compress(raw))
        stream={'complete':True,'http_complete':True,'raw_wire_gzip_sha256':sha(self.raw),'raw_wire_sha256':text_hash(raw.decode())}
        self.receipt={'status_code':429,'acceptance':'KNOWN_REJECTED','stream_complete':True,'body_json':self.body,'stream_receipt':stream}
        self.end={'event':'END','call':1,'status':'PROVIDER_FAILURE','acceptance':'KNOWN_REJECTED','stream_receipt':stream}
        self.write()
    def write(self):
        (self.parent/'response.json').write_text(json.dumps(self.body))
        (self.parent/'response-receipt.json').write_text(json.dumps(self.receipt))
        (self.folder/'physical-calls.jsonl').write_text(json.dumps({'event':'START','call':1})+'\n'+json.dumps(self.end)+'\n')
    def tearDown(self):self.temp.cleanup()
    def test_rejected429_is_counted_and_never_delivered(self):
        result=rejected_429(self.folder,self.request)
        self.assertEqual(result['status'],'KNOWN_REJECTED_HTTP429');self.assertFalse(result['source_delivery'])
        self.assertEqual(result['physical_call'],1)
    def test_raw_response_tamper_is_unknown(self):
        self.raw.write_bytes(gzip.compress(b'{}'))
        self.assertEqual(rejected_429(self.folder,self.request)['status'],'UNKNOWN')
    def test_duplicate_terminal_record_is_unknown(self):
        with (self.folder/'physical-calls.jsonl').open('a') as f:f.write(json.dumps(self.end)+'\n')
        self.assertEqual(rejected_429(self.folder,self.request)['status'],'UNKNOWN')
    def test_timeout_never_counts_as_known_rejection(self):
        self.end.update(status='TRANSPORT_FAILURE',acceptance='UNKNOWN');self.write()
        self.assertNotEqual(rejected_429(self.folder,self.request)['status'],'KNOWN_REJECTED_HTTP429')

if __name__=='__main__':unittest.main()
