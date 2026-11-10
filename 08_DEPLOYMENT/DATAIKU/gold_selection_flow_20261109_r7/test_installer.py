"""Installer check against a fake Dataiku API (real DSS API not available locally)."""
import io
import json
import sys
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEXT = (HERE/'DATAIKU_CREATE_GOLD_FIX_FLOW_R7.txt').read_text()
CODE = (HERE/'recipe_gold_selection_fix_r7.py').read_text()


class Settings:
    def __init__(self, owner): self.o = owner; self.type = owner.type
    def get_raw_params(self): return self.o.params
    def save(self): self.o.saves += 1


class Folder:
    def __init__(self, fid, name, ftype, conn):
        self.id, self.name, self.type, self.params, self.saves = fid, name, ftype, {'connection': conn, 'path': '/${projectKey}/${odbId}'}, 0
        self.files = {}
    def get_settings(self): return Settings(self)
    def list_contents(self): return {'items': [{'path': '/'+k} for k in self.files]}
    def get_file(self, path):
        data = self.files[path.lstrip('/')]
        class R:
            content = data
            def __enter__(s): return s
            def __exit__(s, *a): return False
        return R()


class RecipeSettings:
    def __init__(self, r): self.r = r
    def get_flat_input_refs(self): return list(self.r['inputs'])
    def get_flat_output_refs(self): return list(self.r['outputs'])
    def get_code(self): return self.r['code']
    def set_code(self, c): self.r['code'] = c
    def set_code_env(self, inherit): self.r['env'] = 'inherit' if inherit else None
    def add_output(self, role, ref): assert role == 'main'; self.r['outputs'].append(ref)
    def save(self): self.r['saves'] += 1


class Builder:
    def __init__(self, p, name): self.p, self.r = p, {'name': name, 'inputs': [], 'outputs': [], 'code': None, 'saves': 0, 'env': None}
    def with_input(self, i): self.r['inputs'].append(i); return self
    def with_output(self, o, append=False): self.r['outputs'].append(o); return self
    def with_script(self, s): self.r['code'] = s; return self
    def create(self):
        if self.p.require_output and not self.r['outputs']: raise RuntimeError('Recipe must have at least one output')
        self.p.recipes[self.r['name']] = self.r
        return types.SimpleNamespace(get_settings=lambda: RecipeSettings(self.r))


class Zone:
    def __init__(self, name): self.name, self.items = name, []
    def add_item(self, x): self.items.append(x.id)


class Project:
    def __init__(self, key):
        self.project_key, self.folders, self.recipes, self.datasets, self.vars, self.zones = key, {}, {}, [], {'standard': {}, 'local': {}}, []
        self.require_output = False
    def list_managed_folders(self): return [{'id': f.id, 'name': f.name} for f in self.folders.values()]
    def get_managed_folder(self, fid): return self.folders[fid]
    def create_managed_folder(self, name, folder_type=None, connection_name='filesystem_folders'):
        f = Folder('F%d' % (len(self.folders)+1)+self.project_key[:3], name, folder_type or 'Filesystem', connection_name)
        self.folders[f.id] = f; return f
    def list_recipes(self): return [{'name': n} for n in self.recipes]
    def get_recipe(self, n): return types.SimpleNamespace(get_settings=lambda: RecipeSettings(self.recipes[n]))
    def new_recipe(self, kind, name): assert kind == 'python'; return Builder(self, name)
    def list_datasets(self): return self.datasets
    def get_variables(self): return json.loads(json.dumps(self.vars))
    def set_variables(self, v): self.vars = v
    def get_flow(self):
        p = self
        def create(n): z = Zone(n); p.zones.append(z); return z
        return types.SimpleNamespace(list_zones=lambda: p.zones, create_zone=create)
    def get_export_stream(self, options):
        assert options['exportManagedFolders'] is False
        return io.BytesIO(json.dumps({'project': self.project_key, 'folders': [f.name for f in self.folders.values()],
                                      'recipes': list(self.recipes)}).encode())


uploads = {}
def run(params, client):
    shim = types.ModuleType('dataiku'); shim.api_client = lambda: client
    shim.Folder = lambda fid: types.SimpleNamespace(upload_stream=lambda name, s: uploads.__setitem__((fid, name), s.read()))
    sys.modules['dataiku'] = shim
    text = TEXT
    for k, v in params.items():
        line = next(l for l in text.splitlines() if l.strip().startswith("'"+k+"': "))
        text = text.replace(line, "    '"+k+"': "+repr(v)+",", 1)
    out = io.StringIO(); old = sys.stdout; sys.stdout = out
    try:
        ns = {}; exec(compile(text, '<installer>', 'exec'), ns)
    finally:
        sys.stdout = old
    return ns['RESULT'], out.getvalue()


def main():
    checks = []
    legal = Project('LEGAL_RAG'); ref = legal.create_managed_folder('existing', 'S3', 'S3_PROD'); ref.params['bucket'] = 'prod-bucket'
    fresh = Project('GOLD_SELECTION_FIX')
    projects = {'LEGAL_RAG': legal, 'GOLD_SELECTION_FIX': fresh}
    current = {'p': fresh}
    client = types.SimpleNamespace(get_default_project=lambda: current['p'], get_project=lambda k: projects[k],
                                   create_project=lambda *a: (_ for _ in ()).throw(AssertionError('must not create projects')))
    r, log = run({'REFERENCE_FOLDER': 'LEGAL_RAG.'+ref.id}, client)
    assert sorted(f.name for f in fresh.folders.values()) == ['gold_selection_input', 'gold_selection_noop']
    for f in fresh.folders.values():
        assert f.type == 'S3' and f.params == {'connection': 'S3_PROD', 'path': '/${projectKey}/'+f.name, 'bucket': 'prod-bucket'}
    rec = fresh.recipes['GOLD_SELECTION_FIX_R7']
    assert rec['code'] == CODE and rec['env'] == 'inherit' and rec['inputs'] == [r['input']] and rec['outputs'] == [r['output']]
    assert fresh.vars['standard'] == {'GOLD_FIX_MODE': 'APPLY', 'GOLD_FIX_ORACLE_CONNECTION': 'AIDP',
                                      'GOLD_FIX_EXPECTED_DB_USER': 'PIDD2APP', 'GOLD_FIX_GOLD_OWNER': 'SIDDG'}
    assert len(legal.folders) == 1 and not legal.recipes and not uploads and 'FLOW_READY' in log and 'Export' in log
    checks.append('user_created_project_gets_input_folder_and_recipe_only_no_project_creation_no_export')
    fresh.vars['standard']['GOLD_FIX_MODE'] = 'CHECK'
    r2, log2 = run({'REFERENCE_FOLDER': 'LEGAL_RAG.'+ref.id}, client)
    assert len(fresh.folders) == 2 and len(fresh.recipes) == 1 and fresh.vars['standard']['GOLD_FIX_MODE'] == 'CHECK' and '재사용' in log2
    checks.append('rerun_reuses_objects_keeps_changed_variables')
    fresh.recipes['GOLD_SELECTION_FIX_R7']['code'] = 'old'
    run({'REFERENCE_FOLDER': 'LEGAL_RAG.'+ref.id}, client); assert fresh.recipes['GOLD_SELECTION_FIX_R7']['code'] == CODE
    checks.append('rerun_updates_recipe_code')
    inp = next(f for f in fresh.folders.values() if f.name == 'gold_selection_input')
    inp.files['SEARCH_SELECTION_GENERATION.json'] = json.dumps({'schema_version': 'filename-search-selection-v2',
        'generation_id': 'term-source-533a15307cda1265e17e', 'manifest_sha256': 'bf643c59'+'0'*56, 'excluded': [{'document_id': 'a'}]}).encode()
    _, log4 = run({'REFERENCE_FOLDER': 'LEGAL_RAG.'+ref.id}, client)
    assert '입력 JSON 확인' in log4 and 'term-source-533a15307cda1265e17e' in log4 and '빠지는 옛 판본 1' in log4
    inp.files['second.json'] = b'{}'
    try: run({'REFERENCE_FOLDER': 'LEGAL_RAG.'+ref.id}, client)
    except ValueError as exc: assert 'INPUT_FOLDER_HAS_MANY_JSON' in str(exc)
    else: raise AssertionError('two json accepted')
    del inp.files['second.json']
    checks.append('rerun_checks_uploaded_json_in_input_folder')
    # earlier install without output (the field error) is repaired on rerun
    old = Project('OLD'); current['p'] = old
    i = old.create_managed_folder('gold_selection_input', None, 'filesystem_folders')
    old.recipes['GOLD_SELECTION_FIX_R7'] = {'name': 'GOLD_SELECTION_FIX_R7', 'inputs': [i.id], 'outputs': [], 'code': CODE, 'saves': 0, 'env': 'inherit'}
    r3, log3 = run({'REFERENCE_FOLDER': ''}, client)
    assert old.recipes['GOLD_SELECTION_FIX_R7']['outputs'] == [r3['output']] and '빈 출력 폴더 연결' in log3
    assert all(f.params['connection'] == 'filesystem_folders' for f in old.folders.values())
    checks.append('rerun_attaches_output_to_earlier_install_without_output')
    current['p'] = legal
    try: run({'REFERENCE_FOLDER': ''}, client)
    except ValueError as exc: assert 'PROJECT_NOT_EMPTY' in str(exc) and "'existing'" in str(exc)
    else: raise AssertionError('busy project accepted')
    assert len(legal.folders) == 1 and not legal.recipes
    checks.append('existing_project_with_other_objects_refused_and_listed')
    print(json.dumps({'status': 'PASS', 'checks': checks}, ensure_ascii=False, indent=1))


main()
