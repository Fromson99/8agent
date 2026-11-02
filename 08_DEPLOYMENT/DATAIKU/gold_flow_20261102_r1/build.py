from pathlib import Path
import hashlib
import json
import sys
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE/'package'
sys.path.insert(0,str(ROOT))
from flow_spec import validate_spec
from flow_view import render
validate_spec()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
files={str(p.relative_to(ROOT)):sha(p) for p in sorted(ROOT.rglob('*'))
       if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='FLOW_MANIFEST.json'}
if any(Path(n).suffix.lower() in {'.zip','.js','.jsx','.mjs','.cjs'} for n in files):raise ValueError('UNEXPECTED_ARCHIVE_MEMBER')
manifest={'version':'gold-flow-20261102-r1','files':files,
          'parent_engine_manifest_sha256':sha(ROOT/'engine/CODE_MANIFEST.json')}
(ROOT/'FLOW_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2))
name='DATAIKU_GOLD_FLOW_20261102_R1.zip'
with zipfile.ZipFile(HERE/name,'w',zipfile.ZIP_DEFLATED) as z:
    for n in sorted([*files,'FLOW_MANIFEST.json']):
        info=zipfile.ZipInfo(n,date_time=(2026,11,2,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16
        z.writestr(info,(ROOT/n).read_bytes())
bootstrap=(HERE/'bootstrap_template.py').read_text().replace('__ZIP_NAME__',name).replace('__ZIP_SHA256__',sha(HERE/name))
install=bootstrap+'\n# 아래 문자열은 레시피가 매번 동일 코드 ZIP을 검증하여 읽는 공통 실행부입니다.\n'
install+='from install_flow import install\nFLOW_CONFIG=install(dataiku.api_client().get_project("LEGAL_RAG"), '+repr(bootstrap)+', LANDING_ID)\n'
compile(install,'INSTALL.txt','exec')
(HERE/'DATAIKU_GOLD_FLOW_INSTALL_R1.txt').write_text(install)
monitor=bootstrap+'\nREFRESH_SECONDS=15  # 0이면 한 번만 표시. 중단은 노트북 Stop 버튼.\n'
monitor+='project=dataiku.api_client().get_project("LEGAL_RAG")\n'
monitor+='folders=[f for f in project.list_managed_folders() if f["name"]=="G19F1_07_RESULT_RESULT"]\n'
monitor+='if len(folders)!=1:raise ValueError("먼저 FLOW_INSTALL_R1.txt를 실행하세요.")\n'
monitor+='with dataiku.Folder(folders[0]["id"]).get_download_stream("installation.json") as f:cfg=json.loads(f.read())\n'
monitor+='from flow_monitor import watch\nwatch(cfg,REFRESH_SECONDS)\n'
compile(monitor,'MONITOR.txt','exec')
(HERE/'DATAIKU_GOLD_FLOW_MONITOR_R1.txt').write_text(monitor)
(HERE/'PREVIEW.html').write_text(render({},preview=True))
print(json.dumps({'zip':name,'bytes':(HERE/name).stat().st_size,'sha256':sha(HERE/name),'files':len(files)+1}))
