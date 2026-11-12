"""R7 전달본 만들기 — R6 수신 파이프라인 + Gold 소유자를 프로젝트 변수로.

바뀌는 것 (Dataiku 쪽만, GENOS 코드·프로토콜 그대로라 GENOS 재배포 없음):
  - 03_LOAD가 실행할 때마다 프로젝트 변수 LGL_GOLD_OWNER(필수)·LGL_GOLD_TABLE_PREFIX(선택)로 대상을 정한다.
  - 옛 개발계 이름(DEV_1, LGL_G19_*_S_1) 경로를 없앤다. 개발계·운영 모두 Gold 이름(IDD_B003_LGL_*).
  - 레시피·결과 폴더·시나리오 이름 LGL_AGENT_R7_*, 작업 폴더 agent-layer-zip-r7 (R6 기록과 섞이지 않게).
  - 증분 셀 R2: TARGET 없앰, 같은 프로젝트 변수로 대상을 정한다.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
R6 = ROOT / '08_DEPLOYMENT/DATAIKU/agent_layer_zip_20261105_r6'
R6_FLOW = 'DATAIKU_ZIP_AGENT_GOLD_FLOW_R6.zip'
R6_FLOW_SHA = '5201fb6d85eb627849187a8224325105a33e365bf5b97b7669833872aa4d7e39'
FLOW = 'DATAIKU_ZIP_AGENT_GOLD_FLOW_R7.zip'
INC_ZIP = 'INCREMENT_CODE_R2.zip'


def sha(raw): return hashlib.sha256(raw).hexdigest()
def encode(obj): return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode()


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError('PARENT_SOURCE_CHANGED:' + old[:80])
    return text.replace(old, new)


def pack(path, files):
    with zipfile.ZipFile(path, 'w') as z:
        for n, raw in sorted(files.items()):
            if Path(n).suffix.lower() in {'.zip', '.js', '.jsx', '.mjs', '.cjs'}:
                raise ValueError('NESTED_OR_JS_MEMBER')
            z.writestr(zipfile.ZipInfo(n), raw, compress_type=zipfile.ZIP_DEFLATED)
    return sha(path.read_bytes())


def flow_files():
    raw = (R6 / R6_FLOW).read_bytes()
    if sha(raw) != R6_FLOW_SHA:
        raise ValueError('PARENT_ZIP_HASH')
    with zipfile.ZipFile(R6 / R6_FLOW) as z:
        flow = {n: z.read(n) for n in z.namelist()}
    flow['gold_owner.py'] = (HERE / 'gold_owner.py').read_bytes()

    runtime = flow['flow_runtime.py'].decode()
    runtime = replace(runtime, "NAMES = {'raw': 'RAW_INPUT.zip', 'support': 'PIPELINE_SUPPORT.zip'}\n",
                      "NAMES = {'raw': 'RAW_INPUT.zip', 'support': 'PIPELINE_SUPPORT.zip'}\n"
                      "WORK_NAME = 'agent-layer-zip-r7'\n\n\n"
                      "def trial_paths(cfg, project, trial):\n"
                      "    return Path(cfg['WORK_DIR'])/WORK_NAME/project/cfg['ENVIRONMENT']/trial\n")
    runtime = replace(runtime, "def load(cfg, paths, folders, variables, trial):\n",
                      "def load(cfg, paths, folders, variables, trial):\n"
                      "    from gold_owner import resolve\n"
                      "    gold=resolve(variables)\n"
                      "    cfg=dict(cfg,GOLD_OWNER=gold['GOLD_OWNER'],TABLE_PREFIX=gold['TABLE_PREFIX'])\n"
                      "    print('GOLD_TARGET',cfg['GOLD_OWNER']+'.'+cfg['TABLE_PREFIX']+'*',flush=True)\n"
                      "    from gold_owner import report_name\n"
                      "    report_path=trial+'/'+report_name(gold)\n"
                      "    previous=saved(folders['load'],report_path)\n"
                      "    if previous is not None and previous.get('gold_owner',cfg['GOLD_OWNER'])!=cfg['GOLD_OWNER']:\n"
                      "        raise ValueError('TRIAL_TARGET_CHANGED: 이 trial은 '+previous['gold_owner']+'에 적재됨. '\n"
                      "                         '다른 소유자로 적재하려면 프로젝트 변수 AGENT_FLOW_TRIAL을 새 이름으로')\n")
    runtime = replace(runtime, "    params=dict(TARGET_MODE='DEV_1' if cfg['ENVIRONMENT']=='DEV' else 'GOLD',\n"
                               "                GOLD_OWNER=cfg['GOLD_OWNER'],",
                      "    params=dict(TARGET_MODE='GOLD',GOLD_OWNER=cfg['GOLD_OWNER'],TABLE_PREFIX=cfg['TABLE_PREFIX'],\n"
                      "                ")
    runtime = replace(runtime, "print('TARGET',cfg['ENVIRONMENT'],step,flush=True)",
                      "print('TARGET',cfg['GOLD_OWNER']+'.'+cfg['TABLE_PREFIX']+'*',step,flush=True)")
    runtime = replace(runtime, "result={'status':cfg['ENVIRONMENT']+'_LOADED','target_layer':'Silver' if cfg['ENVIRONMENT']=='DEV' else 'Gold',",
                      "result={'status':'GOLD_LOADED','target_layer':'Gold','gold_owner':cfg['GOLD_OWNER'],'table_prefix':cfg['TABLE_PREFIX'],")
    runtime = replace(runtime, "    paths=Path(cfg['WORK_DIR'])/'agent-layer-zip-r6'/project/cfg['ENVIRONMENT']/trial\n",
                      "    paths=trial_paths(cfg,project,trial)\n")
    runtime = replace(runtime, "    put(folders['load'],trial+'/report.json',result)\n",
                      "    put(folders['load'],report_path,result)\n")
    if 'DEV_1' in runtime or 'agent-layer-zip-r6' in runtime:
        raise ValueError('OLD_TARGET_LEFT')
    flow['flow_runtime.py'] = runtime.encode()

    install = flow['flow_install.py'].decode()
    install = replace(install, "for key in ('EXPECTED_DB_USER',*(['GOLD_OWNER'] if cfg['ENVIRONMENT']=='PROD' else [])):",
                      "for key in ('EXPECTED_DB_USER',):")
    install = replace(install, "prefix='LGL_AGENT_R6_'+params['ENVIRONMENT']", "prefix='LGL_AGENT_R7_'+params['ENVIRONMENT']")
    install = replace(install, "    cfg=dict(params,project=project.project_key,folders={})\n",
                      "    cfg=dict(params,project=project.project_key,folders={})\n"
                      "    cfg.pop('GOLD_OWNER',None)  # 소유자는 레시피에 넣지 않고 실행 때 프로젝트 변수로\n"
                      "    from gold_owner import resolve\n"
                      "    gold=resolve(dataiku.get_custom_variables())\n"
                      "    print('GOLD_TARGET',gold['GOLD_OWNER']+'.'+gold['TABLE_PREFIX']+'*',"
                      "'(프로젝트 변수 LGL_GOLD_OWNER, 03_LOAD 실행 때마다 다시 읽음)',flush=True)\n")
    flow['flow_install.py'] = install.encode()

    setup = flow['flow_setup.py'].decode()
    setup = replace(setup, '"""Install ZIP upload -> GENOS -> ORDS Agent -> Gold as the default path."""',
                    '"""Install ZIP upload -> GENOS -> ORDS Agent -> Gold. Gold owner comes from project variables."""')
    flow['flow_setup.py'] = setup.encode()

    flow.pop('FLOW_MANIFEST.json')
    flow['FLOW_MANIFEST.json'] = encode({'files': {n: sha(b) for n, b in flow.items()}})
    return flow


def setup_txt(flow_sha):
    text = (R6 / 'DATAIKU_SETUP_R6.txt').read_text()
    params_line = next(l for l in text.splitlines() if l.startswith('PARAMS = '))
    boot_line = next(l for l in text.splitlines() if l.startswith('BOOTSTRAP = '))
    params = eval(params_line[len('PARAMS = '):], {})          # 우리가 만든 R6 파일의 dict 리터럴
    params.pop('GOLD_OWNER')
    boot = replace(boot_line, R6_FLOW, FLOW)
    boot = replace(boot, R6_FLOW_SHA, flow_sha)
    head = ('# 수신 파이프라인 R7 설치 셀 (S3 원문 ZIP → GENOS 구조화·색인 → SIDDA Agent → Gold).\n'
            '# 먼저 프로젝트 변수(Variables)에 LGL_GOLD_OWNER 를 넣으세요: 개발계 "SIDDS", 운영 "SIDDG".\n'
            '# CODE_FOLDER_ID 한 곳에 실제 폴더 ID를 입력합니다. 원문 ZIP 이름·해시는 실제 파일로 바꿉니다.\n')
    body = 'PARAMS = ' + repr(params) + '\n' + boot + '\nexec(BOOTSTRAP)\nfrom flow_setup import install_pipeline\ncfg = install_pipeline(PARAMS, BOOTSTRAP)\n'
    compile(body, 'DATAIKU_SETUP_R7.txt', 'exec')
    return head + body, boot


def increment(boot_line):
    spec = importlib.util.spec_from_file_location('inc_r1_build', ROOT / '08_DEPLOYMENT/DATAIKU/increment_dev_20261109_r1/build.py')
    inc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(inc)
    data = inc.code_zip()
    (HERE / INC_ZIP).write_bytes(data)
    cell = inc.CELL
    cell = replace(cell, '# 증분 처리 개발계 실험 R1 — Dataiku Python 노트북 한 셀 (R6 설치된 같은 프로젝트)\n'
                         '# CODE_FOLDER_ID 폴더에 DATAIKU_ZIP_AGENT_GOLD_FLOW_R6.zip(이미 있음)과 %(zip)s 를 둡니다.\n',
                   '# 증분 처리 R2 — Dataiku Python 노트북 한 셀 (수신 파이프라인 R7을 설치한 같은 프로젝트)\n'
                   '# CODE_FOLDER_ID 폴더에 DATAIKU_ZIP_AGENT_GOLD_FLOW_R7.zip 과 %(zip)s 를 둡니다.\n'
                   '# 대상 Gold는 프로젝트 변수 LGL_GOLD_OWNER(개발계 SIDDS, 운영 SIDDG)와\n'
                   '# LGL_GOLD_TABLE_PREFIX(시험 복사본일 때만, 예 TST_B003_LGL_)로 정합니다. 03_LOAD와 같은 변수입니다.\n')
    cell = replace(cell, "    'R6_RECIPE': 'LGL_AGENT_R6_PROD_02_WAIT_AGENT',   # 설정을 읽을 R6 레시피 이름\n"
                         "    'TARGET': 'DEV_1',               # 개발계 실버 SIDDS.LGL_G19_*_S_1 / 운영은 'GOLD'\n"
                         "    'GOLD_OWNER': 'SIDDG',           # TARGET='GOLD'일 때만 사용\n",
                   "    'R6_RECIPE': 'LGL_AGENT_R7_PROD_02_WAIT_AGENT',   # 설정을 읽을 수신 파이프라인 레시피 이름\n")
    cell = cell % {'zip': INC_ZIP, 'r6_bootstrap_line': boot_line,
                   'inc_bootstrap': inc.INCREMENT_BOOTSTRAP % {'name': INC_ZIP, 'sha': sha(data)}}
    compile(cell, 'DATAIKU_INCREMENT_R2.txt', 'exec')
    (HERE / 'DATAIKU_INCREMENT_R2.txt').write_text(cell, encoding='utf-8')
    return sha(data)


def main():
    flow_sha = pack(HERE / FLOW, flow_files())
    setup, boot = setup_txt(flow_sha)
    (HERE / 'DATAIKU_SETUP_R7.txt').write_text(setup, encoding='utf-8')
    inc_sha = increment(boot)
    print(FLOW, flow_sha)
    print(INC_ZIP, inc_sha)


if __name__ == '__main__':
    main()
