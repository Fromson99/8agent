"""Assemble one standalone terminal TXT with the existing XML validation unchanged."""
import ast
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE = ROOT / '08_DEPLOYMENT/DATAIKU/law_api_20261015_r1/relay_check.py'
OUTPUT = HERE / 'GENOS_RELAY_CHECK_20261023_R2.txt'


def build():
    original = SOURCE.read_text()
    names = {'masked', 'clean_xml', 'first', 'normalized', 'inspect_xml'}
    blocks = [ast.get_source_segment(original, node) for node in ast.parse(original).body
              if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(blocks) == len(names)
    helpers = '\n\n'.join(blocks)
    result = (HERE / 'check_template.py').read_text().replace('__XML_HELPERS__', helpers)
    compile(result, OUTPUT.name, 'exec')
    OUTPUT.write_text(result)
    binding = {'script': OUTPUT.name, 'script_sha256': hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
               'validation_source': str(SOURCE.relative_to(ROOT)),
               'validation_source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
               'reused_functions': sorted(names), 'helpers_sha256': hashlib.sha256(helpers.encode()).hexdigest(),
               'runtime_dependencies': 'Python 3.9+ standard library; Linux; system CA or explicit PEM',
               'field_connection': 'not performed', 'model_calls': 0, 'main_changed': False,
               'serving_changed': False}
    (HERE / 'SOURCE_BINDING.json').write_text(json.dumps(binding, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(binding, ensure_ascii=False))


if __name__ == '__main__':
    build()
