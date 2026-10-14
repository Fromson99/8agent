"""Data commands use the installed pipeline, selected SQL and explicit principal."""
def dispatch(spec, argv):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('mode')
    parsed, extra = parser.parse_known_args(argv)
    if not parsed.mode.startswith('data-'):
        return main(spec, argv)
    parser.add_argument('--generation', type=Path)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--principal', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args(argv)
    modes = {'data-check':'package-check','data-import':'package-import',
             'data-verify':'package-verify','data-retire':'package-retire'}
    if args.mode not in modes:
        raise ValueError('Unknown data mode')
    root = args.root.resolve(strict=True)
    if not args.runtime.is_absolute() or not args.principal.is_absolute() or not args.receipt.is_absolute():
        raise ValueError('Absolute runtime/principal/receipt paths required')
    if args.mode != 'data-retire' and (args.generation is None or not args.generation.is_absolute()):
        raise ValueError('Actual selected absolute generation required')
    verify(root,spec)
    directory = root/'TRANSFER/cm-shortcut-data-r1'
    directory.mkdir(parents=True,exist_ok=True)
    package = directory/'CM51_SOURCE_PACKAGE.json'
    raw = base64.b64decode(spec['blobs'][spec['data_package_sha256']],validate=True)
    if sha(raw) != spec['data_package_sha256']:
        raise ValueError('Data package bytes differ')
    if package.exists() and package.read_bytes() != raw:
        raise ValueError('Existing package preserved; different bytes')
    if not package.exists():atomic(package,raw)
    command = [sys.executable,str(root/'06_TOOLS/pipeline.py'),'unified-memory',modes[args.mode],
        '--root',str(root),'--runtime',str(args.runtime),'--principal',str(args.principal),
        '--store-version','4']
    if args.generation is not None:command += ['--generation',str(args.generation)]
    source = args.receipt if args.mode in {'data-verify','data-retire'} else package
    output = args.receipt if args.mode=='data-import' else directory/(args.mode+'-'+sha(args.principal.read_bytes())[:16]+'.json')
    command += ['--source',str(source),'--output',str(output)]
    environment = {**os.environ,'PYTHONPATH':str(root/'02_BACKEND'),
                   'LAWRAG_WORKSPACE_ROOT':str(root),'LAWRAG_TOOL_WORKSPACE_ROOT':str(root)}
    completed = subprocess.run(command,cwd=root,env=environment,capture_output=True,text=True)
    atomic(directory/(args.mode+'-'+uuid.uuid4().hex+'.log'),(completed.stdout+completed.stderr).encode())
    if completed.returncode:
        print(completed.stderr,file=sys.stderr,flush=True)
        raise ValueError('Data command failed; SQL transaction and originals preserved; inspect TRANSFER logs')
    result = json.loads(output.read_bytes())
    identity = {**field_identity(root,args.generation),'runtime':str(args.runtime),
        'state_dir':os.environ.get('GENOS_STATE_DIR'),'principal_sha256':sha(args.principal.read_bytes()),
        'data_package_sha256':spec['data_package_sha256'],'command':args.mode,
        'receipt':str(output),'receipt_sha256':sha(output.read_bytes()),'model_calls':0,
        'cases':len(result.get('records',[])) or result.get('cases') or result.get('units') or result.get('retired')}
    atomic(directory/(args.mode+'-identity-'+uuid.uuid4().hex+'.json'),encoded(identity))
    print(json.dumps(identity,ensure_ascii=False),flush=True)
    return 0
