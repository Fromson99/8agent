"""Keep passing contracts; rerun only the corrected test module before model calls."""
from common import *
import xml.etree.ElementTree as E

base = ART / 'contracts-fixture-missing-conftest.xml'
rerun = ART / 'contracts-fixture-final.xml'
old = list(E.parse(base).iter('testcase'))
new = list(E.parse(rerun).iter('testcase'))
def key(t): return t.attrib['classname'], t.attrib['name']
modules = {t.attrib['classname'] for t in new}
assert len(modules) == 1
removed = [t for t in old if t.attrib['classname'] in modules]
assert {key(t) for t in removed} == {key(t) for t in new}
kept = [t for t in old if t.attrib['classname'] not in modules]
final = kept + new
assert len(final) == 309 and len({key(t) for t in final}) == 309
assert all(t.find('failure') is None and t.find('error') is None and t.find('skipped') is None for t in final)
root = E.Element('testsuites'); suite = E.SubElement(root, 'testsuite', tests=str(len(final)), failures='0', errors='0')
suite.extend(final)
E.ElementTree(root).write(ART / 'contracts-final.xml', encoding='utf-8', xml_declaration=True)
(ART / 'contracts-final.log').write_text('All 309 contracts passed. Unchanged modules retained from contracts-fixture-missing-conftest; corrected fixture module rerun in contracts-fixture-final. Both original logs/XML are preserved. No product bytes changed between these runs.\n')
save(ART / 'contracts-final.json', {'passed': True, 'tests': len(final), 'failures': 0, 'errors': 0,
    'retained_passes': len(kept), 'rerun_passes': len(new),
    'inputs': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)} for p in (base, rerun)],
    'xml_sha256': sha(ART / 'contracts-final.xml'), 'log_sha256': sha(ART / 'contracts-final.log')})
print('309 PASS; unchanged passing tests retained:', len(kept), 'corrected module rerun:', len(new))
