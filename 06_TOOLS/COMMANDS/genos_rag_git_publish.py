#!/usr/bin/env python3
"""Commit a sealed RAG delivery and publish the same commit to both GENOS remotes.

No pipeline deployment, force push, remote merge, password file or model call.
Authentication uses a host-scoped askpass helper and an eight-hour memory cache.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

REMOTES = {
    'risk_team': 'http://llmops-gitea-service:3000/llmops/623.git',
    'financial_team': 'http://llmops-gitea-service:3000/llmops/701.git',
}
USERNAME = 'TD8461'
BRANCH = 'main'
REF = 'refs/heads/main'
PASSWORD_ENV = 'GENOS_RAG_GIT_PASSWORD'
PROTECTED = {'.git', '.env', '.venv', '01_DATA', 'GENOS_DATA', 'TRANSFER', '90_RUNTIME'}


class PublishError(RuntimeError):
    pass


def plain(path):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise PublishError('Symlink refused: ' + str(path))
    return path


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    path = plain(path)
    fd, name = tempfile.mkstemp(prefix=path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Publisher:
    def __init__(self, root, package, *, generation=None):
        # ~/DEV is an allowed entry alias; descendants may not be symlinks.
        self.root = plain(Path(root).expanduser().resolve(strict=True))
        self.package = plain(Path(package).resolve(strict=True))
        self.generation = Path(generation).resolve(strict=True) if generation else None
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith('GIT_') and k != PASSWORD_ENV}
        self.state_path = plain(self.package / 'PUBLISH_STATE.json')
        raw = plain(self.package / 'PACKAGE.json').read_bytes()
        self.package_hash = digest(raw)
        self.spec = json.loads(raw)
        if self.spec.get('git_publish') != {'scope': 'rag-code-serving', 'branch': BRANCH, 'remotes': REMOTES}:
            raise PublishError('This package is not sealed for RAG Git publication')
        self.paths = sorted(self.spec['code'])
        if not self.paths or set(self.paths) != set(self.spec['patch']):
            raise PublishError('Full sealed code inventory required')
        for name in self.paths:
            p = PurePosixPath(name)
            if (p.is_absolute() or '..' in p.parts or '\\' in name or str(p) != name
                    or any(ord(c) < 32 for c in name)
                    or set(p.parts) & PROTECTED or p.name.startswith('.env')):
                raise PublishError('Protected or unsafe commit target: ' + name)
        for name, expected in self.spec['payload'].items():
            p = PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name:
                raise PublishError('Unsafe package member')
            if digest(plain(self.package / name).read_bytes()) != expected:
                raise PublishError('Package changed: ' + name)
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else None
        if self.state and (self.state['root'] != str(self.root)
                           or self.state['package_sha256'] != self.package_hash):
            raise PublishError('Publication state belongs to another checkout or package')
        self.auth_args = []

    def git(self, *args, check=True, input=None, network=False):
        options = self.auth_args if network else []
        env = self.env if network else {k: v for k, v in self.env.items() if k != PASSWORD_ENV}
        try:
            result = subprocess.run(['git', '-C', str(self.root), *options, *args],
                                    env=env, input=input, capture_output=True,
                                    timeout=180 if network else 60)
        except subprocess.TimeoutExpired as exc:
            raise PublishError('Git operation timed out: ' + args[0]) from exc
        if check and result.returncode:
            # Never copy HTTP headers, credentials or arbitrary helper output to logs.
            raise PublishError('Git ' + args[0] + ' failed (exit ' + str(result.returncode)
                               + '); check authentication, connectivity or branch divergence')
        return result

    def text(self, *args, **kwargs):
        return self.git(*args, **kwargs).stdout.decode().strip()

    def save(self, status, **fields):
        self.state.update(status=status, **fields)
        write(self.state_path, self.state)

    def check_checkout(self):
        if Path(self.text('rev-parse', '--show-toplevel')).resolve() != self.root:
            raise PublishError('DEV must be the Git checkout root')
        if self.text('symbolic-ref', '--quiet', '--short', 'HEAD') != BRANCH:
            raise PublishError('RAG publication requires the existing main branch')
        if self.text('ls-files', '-u'):
            raise PublishError('Unresolved Git merge conflicts')
        for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply'):
            path = Path(self.text('rev-parse', '--git-path', marker))
            if not path.is_absolute():
                path = self.root / path
            if path.exists():
                raise PublishError('Complete the existing Git operation first')
        changed = set()
        for args in [('diff', '--name-only', '-z'), ('diff', '--cached', '--name-only', '-z')]:
            changed.update(p.decode() for p in self.git(*args).stdout.split(b'\0') if p)
        other = changed - set(self.paths)
        if other:
            raise PublishError('Unrelated tracked changes are preserved; finish them first: '
                               + ', '.join(sorted(other)[:8]))
        head = self.text('rev-parse', 'HEAD')
        if self.state and self.state.get('commit') and head != self.state['commit']:
            raise PublishError('HEAD changed after the sealed publication commit')
        return head

    def check_remotes(self):
        names = self.text('remote').splitlines()
        for name, url in REMOTES.items():
            if name not in names:
                self.git('remote', 'add', name, url)
            for direction in [[], ['--push']]:
                values = self.text('remote', 'get-url', *direction, '--all', name).splitlines()
                if values != [url]:
                    raise PublishError('Unexpected ' + name + ' URL; existing remote was not changed')
            effective = self.text('ls-remote', '--get-url', url)
            if effective != url or urlsplit(effective).hostname != 'llmops-gitea-service':
                raise PublishError('Git URL rewriting would change the authorized destination')

    def remote_head(self, name):
        out = self.text('ls-remote', '--exit-code', REMOTES[name], REF, network=True)
        rows = [r.split() for r in out.splitlines() if r]
        if len(rows) != 1 or rows[0][1] != REF or not re.fullmatch('[0-9a-f]{40,64}', rows[0][0]):
            raise PublishError(name + ': existing main branch could not be verified')
        return rows[0][0]

    def ancestor(self, name, remote_sha, commit):
        if remote_sha == commit:
            return
        if self.git('cat-file', '-e', remote_sha + '^{commit}', check=False).returncode:
            self.git('fetch', '--no-tags', '--no-recurse-submodules', REMOTES[name], REF, network=True)
        if self.git('merge-base', '--is-ancestor', remote_sha, commit, check=False).returncode:
            raise PublishError(name + ': remote main diverged; no force push or automatic merge')

    def preflight(self):
        head = self.check_checkout()
        self.check_remotes()
        observed = {}
        for name in REMOTES:
            remote = self.remote_head(name)
            self.ancestor(name, remote, head)
            observed[name] = remote
        write(self.package / 'PUBLISH_PREFLIGHT.json',
              {'root': str(self.root), 'package_sha256': self.package_hash,
               'head': head, 'remote_heads': observed, 'branch': BRANCH})
        print('RAG_GIT_PREFLIGHT_PASS: both main branches accept this checkout', flush=True)

    def check_bytes(self, revision=None):
        for name, expected in self.spec['code'].items():
            if digest(plain(self.root / name).read_bytes()) != expected:
                raise PublishError('Installed code differs: ' + name)
        if revision is not None:
            # One Git process validates the full inventory, including the index.
            requests = ''.join(revision + ':' + name + '\n' for name in self.paths).encode()
            result = self.git('cat-file', '--batch', input=requests).stdout
            offset = 0
            for name in self.paths:
                end = result.find(b'\n', offset)
                fields = result[offset:end].split()
                if end < 0 or len(fields) != 3 or fields[1] != b'blob':
                    raise PublishError('Git object missing or not a file: ' + name)
                size = int(fields[2])
                raw = result[end + 1:end + 1 + size]
                offset = end + size + 2
                if len(raw) != size or digest(raw) != self.spec['code'][name]:
                    raise PublishError('Git bytes differ from sealed code: ' + name)
            if offset != len(result):
                raise PublishError('Unexpected Git batch output')

    def commit(self):
        head = self.check_checkout()
        self.check_bytes()
        marker = 'GENOS-RAG-Package: ' + self.package_hash
        if self.state is None:
            self.state = {'root': str(self.root), 'package_sha256': self.package_hash,
                          'before_commit': head, 'commit': None, 'remotes': {},
                          'generation_verified': False, 'field_revision_verified': False}
            self.save('prepared')
        before = self.state['before_commit']
        if self.state['commit']:
            self.check_bytes(head)
            return head
        if head != before:
            # Recover the narrow crash window after commit but before state write.
            parent = self.text('rev-list', '--parents', '-n', '1', head).split()
            changed = self.text('diff-tree', '--no-commit-id', '--name-only', '-r', head).splitlines()
            if parent != [head, before] or marker not in self.text('log', '-1', '--format=%B') or set(changed) - set(self.paths):
                raise PublishError('Unexpected HEAD change during commit; state retained')
            self.check_bytes(head)
            self.save('committed', commit=head)
            return head
        self.save('committing')
        for start in range(0, len(self.paths), 100):
            self.git('add', '--', *self.paths[start:start + 100])
        self.check_bytes('')  # ':path' means the exact index bytes.
        staged = set(self.text('diff', '--cached', '--name-only').splitlines())
        if staged - set(self.paths):
            raise PublishError('Index contains unrelated paths; no commit made')
        whitespace = self.git('diff', '--cached', '--check', check=False)
        if whitespace.returncode not in (0, 2):
            raise PublishError('Git whitespace inspection failed')
        self.save('committing', source_whitespace_report=whitespace.stdout.decode())
        if whitespace.returncode:
            print('SOURCE_WHITESPACE_WARNING: preserving exact sealed source bytes', flush=True)
        if staged:
            # Existing author identity wins; the fallback is explicitly local, not an email recipient.
            name = self.text('config', '--get', 'user.name', check=False) or USERNAME
            email = self.text('config', '--get', 'user.email', check=False) or USERNAME + '@genos.invalid'
            self.git('-c', 'user.name=' + name, '-c', 'user.email=' + email,
                     'commit', '-m', 'Deploy RAG ' + self.spec['version'], '-m', marker)
        head = self.text('rev-parse', 'HEAD')
        if head != before:
            parents = self.text('rev-list', '--parents', '-n', '1', head).split()
            changed = {p.decode() for p in self.git('diff-tree', '--no-commit-id',
                       '--name-only', '-z', '-r', head).stdout.split(b'\0') if p}
            if parents != [head, before] or changed - set(self.paths):
                raise PublishError('Commit hook changed the authorized commit scope; no push performed')
        self.check_bytes(head)
        self.save('committed', commit=head)
        print('RAG_COMMIT_VERIFIED=' + head, flush=True)
        return head

    def gate(self, commit):
        self.check_checkout()
        self.check_bytes(commit)
        command = [sys.executable, str(self.package / 'genos_release_gate.py'),
                   '--code-zip', str(self.package / 'code.zip'), '--deploy-root', str(self.root)]
        if self.generation:
            command += ['--generation', str(self.generation)]
        else:
            command += ['--code-only']
        result = subprocess.run(command, cwd=self.root,
                                env={k: v for k, v in self.env.items() if k != PASSWORD_ENV}, timeout=1800)
        if result.returncode:
            raise PublishError('Committed checkout failed the release gate; no push performed')
        self.save('validated', generation_verified=bool(self.generation),
                  generation=str(self.generation) if self.generation else None,
                  generation_manifest_sha256=digest((self.generation / 'manifest.json').read_bytes()) if self.generation else None,
                  code_zip_sha256=digest((self.package / 'code.zip').read_bytes()),
                  code_manifest_sha256=digest((self.package / 'CODE_MANIFEST.json').read_bytes()),
                  python=sys.executable, python_version=sys.version)

    def publish(self):
        self.check_remotes()
        commit = self.commit()
        self.gate(commit)
        for name in REMOTES:
            self.check_checkout()
            self.check_bytes(commit)
            remote = self.remote_head(name)
            if remote == commit:
                self.state['remotes'][name] = {'status': 'confirmed', 'commit': commit}
                self.save('pushing')
                print('RAG_PUSH_ALREADY_CONFIRMED=' + name, flush=True)
                continue
            self.ancestor(name, remote, commit)
            self.state['remotes'][name] = {'status': 'attempting', 'before': remote, 'commit': commit}
            self.save('pushing')
            try:
                result = self.git('-c', 'remote.' + name + '.mirror=false', '-c', 'push.followTags=false',
                                  'push', '--porcelain', '--no-follow-tags', name,
                                  commit + ':' + REF, network=True, check=False)
                code = result.returncode
            except PublishError:
                code = None
            # A lost push acknowledgement is reconciled by reading, never blind retry.
            try:
                confirmed = self.remote_head(name) == commit
            except PublishError:
                confirmed = False
            self.state['remotes'][name].update(status='confirmed' if confirmed else 'unconfirmed',
                                               push_exit=code)
            self.save('pushing' if confirmed else 'incomplete')
            if not confirmed:
                raise PublishError(name + ': push not confirmed; rerun the same TXT to reconcile and resume')
            print('RAG_PUSH_CONFIRMED=' + name + ' COMMIT=' + commit, flush=True)
        self.save('complete')
        print('RAG_GIT_COMPLETE: risk_team/main and financial_team/main = ' + commit, flush=True)


class Authentication:
    def __init__(self, publisher):
        self.publisher = publisher

    def __enter__(self):
        p = self.publisher
        git_dir = Path(p.text('rev-parse', '--absolute-git-dir'))
        cache = plain(git_dir / 'genos-rag-auth')
        cache.mkdir(mode=0o700, exist_ok=True)
        cache.chmod(0o700)
        self.temporary = tempfile.TemporaryDirectory(prefix='rag-git-auth-')
        helper = Path(self.temporary.name) / 'askpass.py'
        helper.write_text('''#!/usr/bin/env python3
import getpass, os, re, sys
from urllib.parse import urlsplit
prompt = sys.argv[1] if len(sys.argv) > 1 else ''
match = re.search(r"'(https?://[^']+)'", prompt)
url = urlsplit(match.group(1)) if match else None
if not url or url.scheme != 'http' or url.hostname != 'llmops-gitea-service' or url.port != 3000 or url.username not in (None, 'TD8461'):
    raise SystemExit(2)
if prompt.lower().startswith('username'):
    print('TD8461')
elif prompt.lower().startswith('password'):
    value = os.environ.get('GENOS_RAG_GIT_PASSWORD')
    if value is None:
        with open('/dev/tty', 'r+') as tty:
            value = getpass.getpass('GENOS Git password (hidden; memory cache 8h): ', stream=tty)
    if not value or '\\n' in value or '\\r' in value:
        raise SystemExit(2)
    print(value)
else:
    raise SystemExit(2)
''')
        helper.chmod(0o700)
        p.env.update(GIT_ASKPASS=str(helper), GIT_TERMINAL_PROMPT='0', GIT_TRACE='0',
                     GIT_TRACE_CURL='0', GIT_CURL_VERBOSE='0', LC_ALL='C')
        if PASSWORD_ENV in os.environ:
            p.env[PASSWORD_ENV] = os.environ[PASSWORD_ENV]
        socket = cache / 'socket'
        if ' ' in str(socket) or "'" in str(socket):
            raise PublishError('Credential cache path contains unsupported spaces or quotes')
        p.auth_args = ['-c', 'credential.helper=', '-c',
                       'credential.helper=cache --timeout=28800 --socket=' + str(socket),
                       '-c', 'credential.username=' + USERNAME,
                       '-c', 'credential.useHttpPath=false', '-c', 'http.followRedirects=false']
        return self

    def __exit__(self, *args):
        self.publisher.env.pop(PASSWORD_ENV, None)
        self.temporary.cleanup()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('command', choices=['preflight', 'publish', 'status'])
    parser.add_argument('--root', type=Path, default=Path.home() / 'DEV')
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--generation', type=Path)
    args = parser.parse_args(argv)
    publisher = Publisher(args.root, args.package, generation=args.generation)
    git_dir = Path(publisher.text('rev-parse', '--absolute-git-dir'))
    with plain(git_dir / 'genos-rag-publish.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.command == 'status':
            print(json.dumps(publisher.state or {'status': 'not_started'}, ensure_ascii=False, indent=2))
        else:
            with Authentication(publisher):
                if args.command == 'preflight':
                    publisher.preflight()
                else:
                    publisher.publish()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (PublishError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print('RAG_GIT_FAILED: ' + str(exc), file=sys.stderr, flush=True)
        raise SystemExit(2)
