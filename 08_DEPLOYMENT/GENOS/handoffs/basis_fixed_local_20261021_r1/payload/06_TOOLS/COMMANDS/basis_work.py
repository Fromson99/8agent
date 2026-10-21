"""Maintained GENOS basis commands; historical data, current verified consumer.

The existing campaign and stage engines own planning, budgets and retries.
Reading a finished campaign does not resume it with a different implementation.
"""
import argparse
from contextlib import redirect_stderr, redirect_stdout
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import traceback
from types import SimpleNamespace
import uuid

import basis_quick as quick

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / '02_BACKEND'), str(ROOT)]


def gate(root):
    """Validate this checkout's registered engines, never an old ZIP's hashes."""
    root = Path(root).resolve(strict=True)
    quick.require(root == ROOT, '실행할 checkout의 06_TOOLS/pipeline.py를 사용하세요.')
    from semantic_runtime.contracts import Contracts
    from semantic_runtime.stage_runner import StageRunner
    contracts = Contracts(root)
    StageRunner(SimpleNamespace(contracts=contracts, profile_id='legal-rag')).verify_profile()
    pipeline = contracts.pipeline
    command_contract = quick.read(root / '00_SYSTEM/BASIS_COMMANDS.json')
    quick.require(command_contract.get('schema_version') == 'basis-commands-v1', '명령 계약 버전이 다릅니다.')
    for name, expected in command_contract['files'].items():
        path = quick.plain(root / name)
        path.relative_to(root)
        quick.require(quick.sha(path) == expected, '현재 명령 코드 해시 불일치: ' + name)
    engines = sorted({n['engine'] for n in pipeline['profiles']['legal-rag']['nodes']})
    files = {}
    for ident in engines:
        manifest = quick.read(root / pipeline['engines'][ident]['manifest'])
        files.update(manifest['files'])
    for name in ('06_TOOLS/pipeline.py', *command_contract['files']):
        files[name] = quick.sha(root / name)
    binding = {'schema': 'basis-current-code-v1', 'pipeline_sha256': quick.sha(root / '00_SYSTEM/PIPELINE.json'),
               'files_sha256': quick.digest(files)}
    print(json.dumps({'event': 'basis.current.code_verified', **binding, 'code_root': str(root),
                      'registered_files': len(files), 'model_calls': 0}), flush=True)
    return binding


class CurrentRunner(quick.Runner):
    def __init__(self, root, transfer, code):
        self.root, self.transfer = root, transfer
        self.identity = code
        self.config_sha256 = quick.sha(root / '00_SYSTEM/GENOS_SERVING_PATHS.json')
        self.lock_fd = None

    def call(self, action, job=None, *, ids=None, count=None, output=None, log=None):
        quick.require(quick.sha(self.root / '00_SYSTEM/GENOS_SERVING_PATHS.json') == self.config_sha256,
                      '실행 도중 generation/runtime 설정이 변경되었습니다.')
        command = [sys.executable, '-B', str(self.root / '06_TOOLS/pipeline.py')]
        if action in ('plan', 'run', 'resume'):
            command += ['basis-links', 'batch-artifacts', 'stage-' + action]
        elif action in ('report', 'export'):
            command += ['basis-links', 'batch-artifacts', action]
        else:
            raise ValueError('지원하지 않는 하위 명령: ' + action)
        command += ['--root', str(self.root), '--job', str(job)]
        if ids:
            command += ['--ids', *ids]
        if count is not None:
            command += ['--count', str(count)]
        if output is not None:
            command += ['--output', str(output)]
        return self.execute(command, log)

    def execute(self, command, log=None):
        # The parent retains the only campaign lock and streams one child at a time.
        child = subprocess.Popen(command, cwd=self.transfer, start_new_session=True,
                                 pass_fds=(() if self.lock_fd is None else (self.lock_fd,)),
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        try:
            for line in child.stdout:
                target = log if log is not None else sys.stdout
                target.write(line)
                target.flush()
            return child.wait()
        except BaseException:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGINT)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
            raise
        finally:
            child.stdout.close()

    def preflight(self, folder, ids=None, listing=False):
        folder = quick.plain(folder)
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / ('PREFLIGHT-' + uuid.uuid4().hex + '.json')
        command = [sys.executable, '-B', str(self.root / '06_TOOLS/pipeline.py'), 'basis-work',
                   '_preflight', '--job', str(folder), '--output', str(output)]
        if ids:
            command += ['--ids', *ids]
        if listing:
            command += ['--catalogue', str(folder / 'LATEST_INTERNAL.csv')]
        with output.with_suffix('.log').open('x', encoding='utf-8') as stream:
            code = self.execute(command, stream)
        quick.require(code == 0, '목록/구조 확인 실패: ' + str(output.with_suffix('.log')))
        return quick.checked(output, 'receipt_sha256')


def preflight(args):
    from lawrag.pipeline import basis_batch as batch
    from basis_preflight import inspect
    pipeline = quick.read(ROOT / '00_SYSTEM/PIPELINE.json')
    os.environ['GENOS_RAG_IMPLEMENTATION'] = pipeline['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent']['implementation']
    quick.resources(args.job.parent)
    with batch.heartbeat({'phase': 'current-structure-preflight'}):
        app = batch.boot(ROOT)
        result = inspect(app, batch, args.ids)
    if args.catalogue:
        path = quick.plain(args.catalogue)
        with path.open('x', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=['document_id', 'name', 'chars', 'source_artifact_sha256', 'is_latest'])
            writer.writeheader()
            writer.writerows(result['documents'])
            stream.flush()
            os.fsync(stream.fileno())
    quick.atomic(args.output, result, 'receipt_sha256')
    return 0


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['check', 'paths', 'jobs', 'plan-all', 'all', 'plan', 'run', 'resume',
                                     'status', 'report', 'export', 'fixed-inspect', 'fixed-stage', '_preflight',
                                     'local-prepare', 'local-report', 'local-check', 'local-apply', 'local-status', 'local-rollback'])
    p.add_argument('name', nargs='?', help='작업 이름. 기존 BASIS_RUN의 all/job1 이름도 그대로 사용')
    p.add_argument('--job', type=Path, help='기존 작업의 실제 절대 경로를 명시')
    p.add_argument('--root', type=Path, default=ROOT)
    p.add_argument('--count', type=int, default=3)
    p.add_argument('--ids', nargs='+')
    p.add_argument('--output', type=Path)
    p.add_argument('--catalogue', type=Path, help=argparse.SUPPRESS)
    return p


def run(argv=None):
    argsv = list(sys.argv[1:] if argv is None else argv)
    for index, token in enumerate(argsv):
        if token == '--root':
            quick.require(index + 1 < len(argsv) and Path(argsv[index + 1]).resolve() == ROOT,
                          '대상 checkout의 pipeline.py를 직접 호출하세요.')
        elif token.startswith('--root='):
            quick.require(Path(token.split('=', 1)[1]).resolve() == ROOT,
                          '대상 checkout의 pipeline.py를 직접 호출하세요.')
    if argsv and argsv[0] in ('source-plan', 'source-apply', 'source-rollback'):
        gate(ROOT)
        from basis_source import main as source_selection
        return source_selection(argsv, ROOT)
    # Current checkout imports the portable data using the same existing consumer.
    if argsv[:1] == ['transfer']:
        gate(ROOT)
        quick.require(os.environ.get('DP', '').strip().lower() not in ('oracle', '1', 'true'),
                      '이 관계 이관은 기존 공유 SQLite 전용입니다. Oracle 적재를 대신하지 않습니다.')
        from lawrag.pipeline.basis_batch_artifacts import main as artifacts
        return artifacts([*argsv[1:], '--root', str(ROOT)])
    args = parser().parse_args(argsv)
    code = gate(args.root)
    if args.action == 'check':
        return 0
    config = quick.read(ROOT / '00_SYSTEM/GENOS_SERVING_PATHS.json')
    if args.action == 'paths':
        from lawrag.pipeline.genos_stages import offline_data_root
        print(json.dumps({'code_root': str(ROOT), 'data_root': str(offline_data_root(ROOT)),
                          'selected_generation': config['generation'], 'runtime': config['runtime']},
                         ensure_ascii=False, indent=2), flush=True)
        return 0
    runtime = quick.plain(config['runtime'])
    quick.require(Path(config['runtime']).is_absolute() and runtime.is_dir(), '기존 외부 공유 runtime이 필요합니다.')
    if args.action == 'jobs':
        for folder in sorted((runtime / 'basis-batch').glob('*')):
            if (folder / 'ALL_PLAN.json').is_file() or (folder / 'PLAN.json').is_file():
                print('JOB=' + str(folder), flush=True)
        return 0
    if args.action == '_preflight':
        quick.require(args.job is not None and args.output is not None, '내부 사전 확인의 경로가 없습니다.')
        return preflight(args)
    quick.require(bool(args.name) != bool(args.job), '작업 이름 또는 --job 실제경로 중 하나를 지정하세요.')
    quick.require(args.name is None or quick.NAME.fullmatch(args.name), '잘못된 작업 이름입니다.')
    quick.require(1 <= args.count <= 20, '개별 계획은 1~20문서입니다.')
    job = quick.plain(args.job if args.job else runtime / 'basis-batch' / ('pilot-review-user-' + args.name))
    if args.action.startswith('local-'):
        quick.require(not (job/'ALL_PLAN.json').exists(), '개별 확정 연결 작업 이름을 사용하세요. 예: fixed-001')
        from basis_local import run as local
        parameters = quick.read(ROOT/'00_SYSTEM/PIPELINE.json')['profiles']['legal-rag']['nodes'][0]['parameters']['term_agent']
        output = args.output or Path.cwd()/('basis-local-'+(args.name or job.name))
        action = args.action.removeprefix('local-')
        if action == 'prepare':
            from basis_local import prepare
            prepare(ROOT,job,quick.plain(config['generation']),runtime,(ROOT,parameters))
            action = 'report'
        result = local(action,job,output,quick.plain(config['generation']),runtime,(ROOT,parameters))
        print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
        return 0
    runner = CurrentRunner(ROOT, Path.cwd(), code)
    binding = {'runner': code, 'root': str(ROOT), 'runtime': str(runtime),
               'config_sha256': runner.config_sha256, 'coordinator_sha256': quick.sha(Path(__file__)),
               'preflight_sha256': quick.sha(Path(__file__).with_name('basis_preflight.py'))}
    campaign = quick.Campaign(runner, job, runtime, binding)
    is_all = (job / 'ALL_PLAN.json').exists() or args.action in ('plan-all', 'all')
    if args.action == 'status':
        if is_all:
            campaign.status()
        else:
            plan = quick.checked(job / 'PLAN.json', 'plan_sha256')
            state = quick.checked(job / 'STATE.json', 'state_sha256') if (job / 'STATE.json').exists() else None
            quick.require(state is None or state['plan_sha256'] == plan['plan_sha256'], '다른 계획의 상태입니다.')
            print(json.dumps({'job': str(job), 'plan': plan, 'state': state}, ensure_ascii=False), flush=True)
        return 0
    if args.action in ('report', 'export'):
        output = args.output or Path.cwd() / ('basis-' + args.action + '-' + (args.name or job.name))
        if is_all:
            if args.action == 'export' and args.output is None:
                output /= datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:8]
            return campaign.render(output, export=args.action == 'export')
        if args.output is None:
            output = output.with_suffix('.html') if args.action == 'report' else output.with_name(output.name + '-' + uuid.uuid4().hex[:12])
        return runner.call(args.action, job, output=output)
    with quick.lock(runtime / 'basis-batch/basis-quick.lock') as fd:
        runner.lock_fd = fd
        if args.action in ('fixed-inspect', 'fixed-stage'):
            if is_all:
                campaign.load(read_only=True)
                children = [campaign.child(part) for part in campaign.plan['parts']]
                job = next((folder for folder, plan, _ in children if plan is not None), None)
                quick.require(job is not None, '먼저 plan-all로 조사 계획을 만드세요.')
            from lawrag.pipeline.risk_basis_seed_cli import main as fixed
            print('FIXED_JOB=' + str(job), flush=True)
            return fixed([args.action.removeprefix('fixed-'), '--root', str(ROOT), '--job', str(job)])
        if is_all:
            quick.require(args.action in ('plan-all', 'all', 'run', 'resume'), '전체 작업에는 plan-all/all/resume을 사용하세요.')
            campaign.initialize()
            if args.action == 'plan-all':
                campaign.load()
                for part in campaign.plan['parts']:
                    campaign.child(part, create=True)
                campaign.status()
                return 0
            return campaign.run()
        quick.resources(runtime)
        quick.require(args.action in ('plan', 'run', 'resume'), '지원하지 않는 개별 작업 명령입니다.')
        return runner.call(args.action, job, ids=args.ids, count=args.count)


class Tee:
    def __init__(self, terminal, log):
        self.terminal, self.log = terminal, log

    def write(self, value):
        self.terminal.write(value)
        self.log.write(value)
        self.flush()

    def flush(self):
        self.terminal.flush()
        self.log.flush()


def main():
    os.umask(0o077)
    logroot = ROOT / '09_ARTIFACTS/AUDITS' if Path.cwd().resolve() == ROOT else Path.cwd()
    directory = quick.plain(logroot / 'basis-work-logs')
    directory.mkdir(parents=True, exist_ok=True)
    logfile = directory / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:12] + '.log')
    rc = 1
    with logfile.open('x', encoding='utf-8') as log, redirect_stdout(Tee(sys.stdout, log)), redirect_stderr(Tee(sys.stderr, log)):
        try:
            rc = run()
        except KeyboardInterrupt:
            rc = 130
            print('중단 기록을 보존했습니다. 같은 코드·계획에서는 resume을 사용하세요.', file=sys.stderr)
        except SystemExit as exc:
            rc = exc.code if isinstance(exc.code, int) else 1
        except Exception:
            traceback.print_exc()
        finally:
            logfile.with_suffix('.log.exit').write_text(str(rc) + '\n')
            print(f'BASIS_WORK_EXIT={rc} LOG={logfile}', flush=True)
    return rc


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt('SIGTERM')))
    raise SystemExit(main())
