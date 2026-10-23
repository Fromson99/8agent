"""Reuse R2's real localhost TLS checks against the final R3 entrypoint."""
import ast
import gzip
import importlib.util
import json
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('relay_r2_regression', HERE.parent / 'relay_terminal_20261023_r2/test_delivery.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
base.SCRIPT = HERE / 'private_delivery/GENOS_RELAY_CHECK_20261023_R3.txt'
for node in ast.parse(base.SCRIPT.read_text()).body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'DEFAULT_CREDENTIALS' for t in node.targets):
        DEFAULTS = ast.literal_eval(node.value)
        break


class DeliveryR3(base.Delivery):
    def clear_overrides(self):
        for key in DEFAULTS:
            self.env.pop(key, None)

    def test_prefilled_notice_without_prompt_and_redacted_echo(self):
        self.clear_overrides()
        values = [DEFAULTS['MAKING_OC'], DEFAULTS['RELAY_COOKIE']]
        values += [p.split('=', 1)[1].strip() for p in DEFAULTS['RELAY_COOKIE'].split(';')]
        type(self).status = 403
        type(self).payload = ('<error>' + ' '.join(values) + '</error>').encode()
        p = self.invoke(expected=2)
        self.assertEqual(1, len(self.records))
        _, path, headers = self.records[0]
        self.assertTrue(parse_qs(urlsplit(path).query)['OC'] == [DEFAULTS['MAKING_OC']], 'wrong default notice OC')
        self.assertTrue(headers.get('Cookie') == DEFAULTS['RELAY_COOKIE'], 'wrong default Cookie')
        folder = self.output / 'notice-01'
        saved = p.stdout.encode() + p.stderr.encode()
        saved += b''.join((folder/n).read_bytes() for n in ('result.json', 'terminal.log', 'events.jsonl'))
        saved += gzip.decompress((folder/'response.body.gz').read_bytes())
        self.assertTrue(all(value.encode() not in saved for value in values), 'credential redaction failed')
        self.assertNotIn('CREDENTIAL_INPUT', p.stdout)

    def test_prefilled_law_uses_separate_local_oc(self):
        self.clear_overrides()
        p = self.invoke('--request', 'law')
        self.assertEqual(1, len(self.records))
        _, path, headers = self.records[0]
        self.assertTrue(parse_qs(urlsplit(path).query)['OC'] == [DEFAULTS['LAW_OC']], 'wrong default law OC')
        self.assertNotIn('CREDENTIAL_INPUT', p.stdout)
        self.assertTrue(DEFAULTS['LAW_OC'] not in p.stdout + p.stderr)
        self.assertEqual('BODY_OK', self.state()['status'])

    def test_explicit_empty_cookie_disables_prefilled_header(self):
        self.clear_overrides()
        self.env['RELAY_COOKIE'] = ''
        self.invoke('--request', 'law')
        self.assertNotIn('Cookie', self.records[0][2])


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(DeliveryR3))
    (HERE/'TEST_STATUS.json').write_text(json.dumps({'status': 'PASS' if result.wasSuccessful() else 'FAIL',
        'checks': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'network': 'localhost TLS only', 'genos_field_execution': False}, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
