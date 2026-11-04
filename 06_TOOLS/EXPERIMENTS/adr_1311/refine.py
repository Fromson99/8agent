from common import *
d=read(DES/'optimized-path.json');C=ROOT/d['candidate']/'snapshot'/d['code_relative']
p=C/'02_BACKEND/semantic_runtime/legal_agent/query_scope.py';s=p.read_text().replace("        binding = verify() if verify else None\n", "        if verify is None:\n            return scoped(docs)\n        binding = verify()\n");p.write_text(s)
p=C/'02_BACKEND/semantic_runtime/legal_agent/structure_selection.py';s=p.read_text().replace('import json\n','import json\nimport threading\n');s=s.replace('        self.values = OrderedDict()\n        self.bytes = 0', '        self.values = OrderedDict()\n        self.bytes = 0\n        self.lock = threading.Lock()')
s=s.replace('    def get(self, key):\n        if key not', '    def get(self, key):\n        with self.lock:\n            return self._get(key)\n\n    def _get(self, key):\n        if key not')
s=s.replace('    def put(self, key, value):\n        size =', '    def put(self, key, value):\n        with self.lock:\n            return self._put(key, value)\n\n    def _put(self, key, value):\n        size =');p.write_text(s)
