"""Small runner failure-contract fixtures; no model, DB, candidate, or real ART."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_case as runner


class StreamRunnerTest(unittest.TestCase):
    def test_stall_preserves_known_usage_without_adopting_partial_json(self):
        response = {'body_json':{'model':'qwen/qwen3.8-27b', 'provider':'Parasail',
            'choices':[{'message':{'content':'{"choice":"READ",'},'finish_reason':None}],
            'usage':{'prompt_tokens':41,'completion_tokens':7,'total_tokens':48,'cost':0.1}},
            'stream_receipt':{'complete':False,'client_stop_reason':'OUTPUT_WHITESPACE_STALL',
                'raw_sha256':'fixture-hash','raw_path':'fixture.sse.gz'}}
        before = deepcopy(response)
        result = runner.reception_failure(SimpleNamespace(code='OUTPUT_WHITESPACE_STALL',response=response))
        self.assertEqual(response,before)
        self.assertEqual(result['stop_reason'],'OUTPUT_WHITESPACE_STALL')
        self.assertEqual(result['product_error'],'OUTPUT_RECEPTION')
        self.assertEqual(result['usage']['total_tokens'],48)
        self.assertEqual(result['usage']['cost_usd'],0.1)
        self.assertNotIn('choices',result)
        self.assertFalse(result['stream_receipt']['complete'])

    def test_missing_usage_is_unknown_not_zero(self):
        response = {'body_json':{'usage':None},'stream_receipt':{'complete':False}}
        result = runner.reception_failure(SimpleNamespace(code='STREAM_INCOMPLETE',response=response))
        self.assertEqual(result['stop_reason'],'STREAM_FAILURE')
        self.assertEqual(result['product_error'],'TRANSPORT')
        self.assertEqual(result['acceptance'],'UNKNOWN')
        self.assertIsNone(result['usage']['raw_usage'])
        for key in ('input_tokens','output_tokens','total_tokens','cost_usd'):
            self.assertIsNone(result['usage'][key])

    def test_binding_failures_are_integrity_and_never_native_completion(self):
        for code in ('MODEL_BINDING_MISMATCH','PROVIDER_BINDING_MISMATCH','REASONING_NOT_DISABLED'):
            with self.subTest(code=code):
                result = runner.reception_failure(SimpleNamespace(error_code=code,response={}))
                self.assertEqual(result['product_error'],'INTEGRITY')
                self.assertFalse(runner.native_failure({'error_code':code}))
        for code in ('OUTPUT_WHITESPACE_STALL','STREAM_INCOMPLETE','STREAM_INVALID_UTF8','STREAM_PROVIDER_ERROR'):
            self.assertFalse(runner.native_failure({'error_code':code}))

    def test_first_stop_is_durable_and_does_not_reset_on_later_error(self):
        with TemporaryDirectory() as folder:
            path = Path(folder)/'stop.json'
            with patch.object(runner,'STOP',path):
                runner.stop('OUTPUT_WHITESPACE_STALL',calls=2)
                first = path.read_bytes()
                runner.stop('STREAM_FAILURE',calls=3)
                self.assertEqual(path.read_bytes(),first)
                self.assertEqual(runner.read(path)['calls'],2)


if __name__ == '__main__':
    unittest.main()
