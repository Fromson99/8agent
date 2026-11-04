#!/usr/bin/env python3
"""Run serving probes in fresh -I -S children with an image package allowlist.

No package is installed. Local distribution versions are reported separately;
this verifies import availability, not equality to a remote container's ABI.
The child rejects unlisted distributions, including transitive dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import importlib.machinery
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import sysconfig
import traceback

ROOT = Path(__file__).resolve().parents[2]


def canonical(name):
    return re.sub(r'[-_.]+', '-', name).lower()


def inventory(path):
    values = {}
    for line in path.read_text().splitlines():
        line = line.split('#', 1)[0].strip()
        if line:
            name, version = line.split('==')
            values.setdefault(canonical(name), []).append(version)
    return values


class ImageImports(importlib.abc.MetaPathFinder):
    def __init__(self, config):
        self.config = config
        self.allowed = set(config['image'])
        self.sites = [Path(p).resolve() for p in config['sites']]
        self.stdlib = [Path(p).resolve() for p in config['stdlib']]
        self.loaded = {}
        self.denied = []

    def owners(self, origin):
        return self.config['owners'].get(str(Path(origin).resolve()), []) if origin else []

    def find_spec(self, fullname, path=None, target=None):
        top = fullname.split('.')[0]
        spec = importlib.machinery.PathFinder.find_spec(fullname, path)
        origin = spec.origin if spec else None
        if origin in ('built-in', 'frozen'):
            return None
        if origin:
            resolved = Path(origin).resolve()
            external = any(resolved.is_relative_to(p) for p in self.sites)
            if not external and (resolved.is_relative_to(ROOT) or top in sys.stdlib_module_names
                                 or any(resolved.is_relative_to(p) for p in self.stdlib)):
                return spec
            owners = self.owners(origin)
            if owners and any(name in self.allowed for name in owners):
                self.loaded[fullname] = {'owners': owners, 'origin': str(resolved)}
                return spec
        elif top in sys.stdlib_module_names:
            return None
        else:
            parent = getattr(sys.modules.get(top), '__file__', None)
            if parent and Path(parent).resolve().is_relative_to(ROOT) and not self.owners(parent):
                return None  # An absent local submodule is not an image package.
            owners = self.config['top_owners'].get(top, [])
            if owners and any(name in self.allowed for name in owners) and spec:
                self.loaded[fullname] = {'owners': owners, 'origin': None}
                return spec
        frames = traceback.extract_stack(limit=16)
        caller = [{'file': f.filename, 'line': f.lineno, 'name': f.name}
                  for f in frames[:-1] if 'importlib' not in f.filename and f.filename != __file__]
        self.denied.append({'module': fullname, 'owners': owners, 'caller': caller[-4:]})
        raise ModuleNotFoundError('A8_IMAGE_IMPORT_DENIED: ' + fullname, name=fullname)


def child(args):
    sys.dont_write_bytecode = True
    config = json.loads(args.config.read_text())
    # -I -S prevents user site, .pth files and preloaded external modules.
    sys.path[:0] = [str(ROOT), str(ROOT/'02_BACKEND'), str(Path(__file__).parent), *config['sites']]
    guard = ImageImports(config)
    assert not any(guard.owners(getattr(m, '__file__', None)) for m in sys.modules.values())
    sys.meta_path.insert(0, guard)
    os.environ.update(DP='nfs', SEMANTIC_LLM_BACKEND='genos', AD_WORKER_ENABLED='0',
                      GENOS_AUTO_WARMUP='0', GENOS_RESIDENT_DATA='off', PYTHONDONTWRITEBYTECODE='1')
    for name in ('GENOS_DATA_ROOT', 'GENOS_GENERATION', 'GENOS_RUNTIME_DIR', 'GENOS_BASE_URL',
                 'GENOS_LLM_URL', 'GENOS_LLM_KEY', 'GENOS_LLM_SERVING_ID'):
        os.environ.pop(name, None)
    import socket
    network = []
    original_connect = socket.socket.connect
    def connect(sock, address):
        if args.probe == 'oracle-read' and isinstance(address, tuple) and address[0] == '127.0.0.1':
            network.append('loopback')
            return original_connect(sock, address)
        raise AssertionError('External network disabled for image import probes')
    socket.socket.connect = connect
    result = {'probe': args.probe, 'status': 'FAIL'}
    try:
        from serving_image_probes import run
        result['detail'] = run(args.probe)
        result['status'] = 'PASS'
    except Exception as exc:
        result.update(error=type(exc).__name__, message=str(exc), traceback=traceback.format_exc())
    forbidden = []
    for name, module in tuple(sys.modules.items()):
        owners = guard.owners(getattr(module, '__file__', None))
        if owners and not any(owner in guard.allowed for owner in owners):
            forbidden.append({'module': name, 'owners': owners})
    if forbidden:
        result['status'] = 'GUARD_FAILURE'
    result.update(denied_import_attempts=guard.denied, allowed_modules=guard.loaded,
                  unlisted_modules_loaded=forbidden, network=network)
    args.result.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inventory', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--probes', nargs='+')
    parser.add_argument('--probe')
    parser.add_argument('--config', type=Path)
    parser.add_argument('--result', type=Path)
    args = parser.parse_args()
    if args.probe:
        child(args)
        return
    image = inventory(args.inventory)
    sites = sorted({sysconfig.get_paths()['purelib'], sysconfig.get_paths()['platlib']})
    owners, versions, top = {}, {}, {}
    for dist in importlib.metadata.distributions(path=sites):
        name = canonical(dist.metadata['Name'])
        versions[name] = dist.version
        for file in dist.files or []:
            absolute = str(Path(dist.locate_file(file)).resolve())
            owners.setdefault(absolute, []).append(name)
    for module, names in importlib.metadata.packages_distributions().items():
        top[module] = sorted({canonical(name) for name in names})
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error('use a new empty output directory to preserve previous evidence')
    config = {'image': image, 'sites': sites, 'owners': owners, 'top_owners': top,
              'stdlib': sorted({sysconfig.get_paths()['stdlib'], sysconfig.get_paths()['platstdlib']})}
    config_path = args.output/'import-config.json'
    config_path.write_text(json.dumps(config))
    probes = args.probes or ['ping-nfs', 'ping-oracle', 'http-readiness', 'serving-modules',
                            'genos-client', 'ords-client', 'sqlite-original', 'tokenize',
                            'fulltext-phrases', 'pecab-emoji', 'rag-search', 'oracle-read']
    results = []
    for probe in probes:
        path = args.output/(probe+'.json')
        try:
            completed = subprocess.run([sys.executable, '-I', '-S', str(Path(__file__).resolve()),
                '--probe', probe, '--config', str(config_path.resolve()), '--result', str(path.resolve())],
                cwd=ROOT, capture_output=True, text=True, timeout=90)
            (args.output/(probe+'.stdout.log')).write_text(completed.stdout)
            (args.output/(probe+'.stderr.log')).write_text(completed.stderr)
            value = json.loads(path.read_text()) if path.exists() else {'probe': probe, 'status': 'HARNESS_FAILURE', 'exit': completed.returncode}
        except subprocess.TimeoutExpired as exc:
            for suffix, content in [('stdout', exc.stdout), ('stderr', exc.stderr)]:
                (args.output/(probe+'.'+suffix+'.log')).write_text(content.decode(errors='replace') if isinstance(content, bytes) else content or '')
            value = {'probe': probe, 'status': 'TIMEOUT', 'seconds': 90}
            path.write_text(json.dumps(value)+'\n')
        results.append(value)
        print(probe, value['status'], value.get('message', ''), flush=True)
    seen = {owner for r in results for row in r.get('allowed_modules', {}).values() for owner in row['owners'] if owner in image}
    summary = {'inventory_sha256': hashlib.sha256(args.inventory.read_bytes()).hexdigest(),
        'inventory_packages': len(image), 'python': sys.version, 'packages_installed': 0,
        'version_differences_among_imported': {p: {'image': image[p], 'local': versions[p]} for p in sorted(seen) if versions.get(p) not in image[p]},
        'local_versions_among_imported': {p: versions[p] for p in sorted(seen)},
        'passed': sum(r['status'] == 'PASS' for r in results),
        'failed': sum(r['status'] != 'PASS' for r in results),
        'unlisted_modules_loaded': sum(len(r.get('unlisted_modules_loaded', [])) for r in results),
        'results': [{k: v for k, v in r.items() if k != 'allowed_modules'} for r in results],
        'limit': 'Local distribution code with strict image-name allowlist; not a replica of image versions or native ABI.'}
    (args.output/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    print('RESULT', summary['passed'], summary['failed'], 'unlisted loaded', summary['unlisted_modules_loaded'])
    raise SystemExit(1 if summary['failed'] else 0)


if __name__ == '__main__':
    main()
