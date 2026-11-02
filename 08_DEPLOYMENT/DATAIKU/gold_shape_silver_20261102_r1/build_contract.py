"""Build the development placement from the exact R19 registration contract."""
from pathlib import Path
import hashlib
import json
import re
import zipfile

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
PACKAGE = OUT / 'package'


def build():
    PACKAGE.mkdir(exist_ok=True)
    registration = ROOT / '08_DEPLOYMENT/LOCAL/gold_connection_engine_r12/mapping_r18_registration.json'
    raw = registration.read_bytes()
    original = json.loads(raw)
    tables = {}
    for key, entry in original['tables'].items():
        owner, suffix = ('SIDDA', 'A') if key.startswith('ONTL_') else ('SIDDS', 'S')
        t = dict(entry, owner=owner, name='LGL_G19_' + key + '_' + suffix, group='GOLD_R19')
        tables[key] = t
    agent_dir = ROOT / '08_DEPLOYMENT/DATAIKU/agent_record_oracle_20261030_r3'
    agent_files = ['01_CREATE_LGL_AGT_RUN_A.sql', '02_CREATE_LGL_AGT_REC_A.sql',
                   '03_CREATE_LGL_AGT_BODY_A.sql', 'optional/90_CREATE_STATE_ONLY_IF_MISSING.sql']
    ddl_refs = {}
    for key, filename in zip(['AGT_RUN', 'AGT_REC', 'AGT_BODY', 'EXEC_ST'], agent_files):
        ddl = (agent_dir / filename).read_text()
        name = re.search(r'CREATE TABLE SIDDA\.(\w+)', ddl)[1]
        columns = {}
        for line in ddl.splitlines()[1:]:
            m = re.match(r'  ([A-Z][A-Z0-9_]*) ((?:VARCHAR2\(\d+ BYTE\)|NUMBER\(\d+\)|CLOB|TIMESTAMP\(6\) WITH TIME ZONE))( NOT NULL)?', line)
            if m:
                c, typ, required = m.groups()
                columns[c] = {'name': c, 'type': typ, 'required': bool(required), 'default': None}
        pk = re.search(r'PRIMARY KEY \(([^)]+)\)', ddl)[1].replace(' ', '').split(',')
        index_sql = []
        for f in sorted(agent_dir.glob('*CREATE*I*_A.sql')):
            text = f.read_text()
            if re.search(r'ON SIDDA\.' + name + r'\s*\(', text):
                index_sql.append(text.strip())
        tables[key] = {'owner': 'SIDDA', 'name': name, 'columns': columns,
                       'primary_key': pk, 'indexes': [], 'index_sql': index_sql,
                       'group': 'AGENT', 'create_sql': ddl.strip()}
        ddl_refs[filename] = hashlib.sha256((agent_dir / filename).read_bytes()).hexdigest()
    assert len(tables) == 17 and sum(len(t['columns']) for t in tables.values() if t['group']=='GOLD_R19') == 60
    model = {'version': 'gold-shape-development-20261102-r1',
             'registration_sha256': hashlib.sha256(raw).hexdigest(), 'agent_ddl_sha256': ddl_refs, 'tables': tables}
    (PACKAGE / 'contract.json').write_text(json.dumps(model, ensure_ascii=False, indent=2)+'\n')
    (PACKAGE / 'registration_r18.json').write_bytes(raw)
    base = ROOT / '08_DEPLOYMENT/DATAIKU/existing_nfs_set_bulk_20261031_r11/DATAIKU_EXISTING_NFS_CLIENT_20261031_R11.zip'
    assert hashlib.sha256(base.read_bytes()).hexdigest() == 'dfc0c769fc1b20093fd3c5549a750ca6557ddcb65d4d0f1b380d75cb43b9f21c'
    with zipfile.ZipFile(base) as z:
        for name in z.namelist():
            if name.startswith('client/02_BACKEND/') and name.endswith('.py'):
                target = PACKAGE / 'vendor' / name.removeprefix('client/')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(name))
        (PACKAGE / 'vendor/strict_resume.py').write_bytes(z.read('strict_resume.py'))
    return model


if __name__ == '__main__':
    model = build()
    print(json.dumps({'tables': len(model['tables']), 'gold_columns': 60, 'base_r11_verified': True}))
