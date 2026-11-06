"""Build a standalone notebook repair; preserve every mailed R6 runtime byte."""
import ast
import hashlib
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent / 'agent_layer_zip_20261105_r6'


def build():
    release = json.loads((PARENT/'RELEASE.json').read_text())
    with zipfile.ZipFile(PARENT/'DATAIKU_ZIP_AGENT_GOLD_FLOW_R6.zip') as z:
        assert hashlib.sha256((PARENT/'DATAIKU_ZIP_AGENT_GOLD_FLOW_R6.zip').read_bytes()).hexdigest() == release['flow_zip']
        assert 'flow_install.py' in z.namelist()
    tree = ast.parse((PARENT/'DATAIKU_SETUP_R6.txt').read_text())
    bootstrap = ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and n.targets[0].id=='BOOTSTRAP'))
    source = (HERE/'repair.py').read_text()
    script = "# Dataiku: 실패한 R6와 같은 프로젝트·공유 WORK_DIR의 새 노트북 셀에서 전체를 실행합니다.\nMODE = 'REPAIR'  # 원복은 'ROLLBACK'\nR6_BOOTSTRAP = " + repr(bootstrap) + '\n' + source
    script += "\nimport dataiku\nREPAIR_RESULT = repair(dataiku, R6_BOOTSTRAP, mode=MODE)\n"
    ast.parse(script, feature_version=(3,11))
    (HERE/'DATAIKU_R6_S3_FIX_R1.txt').write_text(script)
    manifest = {'version':'agent-r6-s3-fix-r1','parent_flow_sha256':release['flow_zip'],
                'files':{'repair.py':hashlib.sha256(source.encode()).hexdigest()},
                'scope':'Existing R6 output folders only; no recipe or runtime ZIP change'}
    with zipfile.ZipFile(HERE/'DATAIKU_R6_S3_FIX_20261105_R1.zip','w') as z:
        for name,raw in [('repair.py',source.encode()),('FIX_MANIFEST.json',(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode())]:
            z.writestr(zipfile.ZipInfo(name),raw,compress_type=zipfile.ZIP_DEFLATED)
    (HERE/'RELEASE.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':build()
