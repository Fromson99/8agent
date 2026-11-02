"""Candidate-only explicit Oracle branches at OS descriptor/atomic-file boundaries."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
C=ROOT/'02_BACKEND/lawrag/research/candidates/adr_1242/oracle-records/snapshot'
def edit(name,old,new):
 p=C/name;t=p.read_text()
 assert t.count(old)==1,(name,old[:80],t.count(old))
 p.write_text(t.replace(old,new))

edit('02_BACKEND/semantic_runtime/request_summary.py',
    "    fd, temporary = tempfile.mkstemp(prefix='.qa-', dir=target.parent)",
    "    from .oracle_runtime_paths import virtual\n    if virtual(target):\n        with Path(target).open(mode, **kwargs) as stream:\n            yield stream\n        return\n    fd, temporary = tempfile.mkstemp(prefix='.qa-', dir=target.parent)")
edit('02_BACKEND/semantic_runtime/request_summary.py',
    "    if target.exists():\n        if target.read_text() != encoded: raise ValueError('summary record already has different content')",
    "    from .oracle_runtime_paths import virtual, write_file\n    if virtual(target):\n        try: write_file(target, encoded.encode(), exclusive=True)\n        except FileExistsError:\n            if target.read_text()!=encoded: raise ValueError('summary record conflict')\n        return target\n    if target.exists():\n        if target.read_text() != encoded: raise ValueError('summary record already has different content')")
edit('02_BACKEND/semantic_runtime/request_summary.py',
    "    flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)",
    "    from .oracle_runtime_paths import virtual, records\n    if virtual(directory):\n        with records().lease(['summary',str(directory)],wait=10): yield\n        return\n    flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)")

edit('02_BACKEND/semantic_runtime/request_report.py',
    "                fd = os.open(target, flags, 0o640)\n                with os.fdopen(fd, 'a', encoding='utf-8') as stream:\n                    os.fchmod(stream.fileno(), 0o640)\n                    stream.write(json.dumps(safe, ensure_ascii=False, default=str) + '\\n')",
    "                from .oracle_runtime_paths import virtual, write_file\n                if virtual(target):\n                    write_file(target,(json.dumps(safe,ensure_ascii=False,default=str)+'\\n').encode(),append=True)\n                else:\n                    fd = os.open(target, flags, 0o640)\n                    with os.fdopen(fd, 'a', encoding='utf-8') as stream:\n                        os.fchmod(stream.fileno(), 0o640)\n                        stream.write(json.dumps(safe, ensure_ascii=False, default=str) + '\\n')")
edit('02_BACKEND/semantic_runtime/request_report.py',
    '    fd = os.open(path, flags, 0o640)\n    os.fchmod(fd, 0o640)\n    stream = os.fdopen(fd, "w", encoding="utf-8", buffering=8192)',
    '    from .oracle_runtime_paths import virtual\n    if virtual(path):\n        stream=Path(path).open("x",encoding="utf-8")\n    else:\n        fd = os.open(path, flags, 0o640)\n        os.fchmod(fd, 0o640)\n        stream = os.fdopen(fd, "w", encoding="utf-8", buffering=8192)')
edit('02_BACKEND/semantic_runtime/request_report.py',
    '    fd, temporary = tempfile.mkstemp(prefix=".request-report-", dir=directory)',
    '    from .oracle_runtime_paths import virtual, write_file\n    if virtual(target):\n        write_file(target,(json.dumps(report,ensure_ascii=False,indent=2,default=str)+"\\n").encode(),exclusive=True)\n        return target\n    fd, temporary = tempfile.mkstemp(prefix=".request-report-", dir=directory)')
edit('02_BACKEND/semantic_runtime/request_report.py',
    '    fd, temporary = tempfile.mkstemp(prefix=".request-trace-", dir=report_path.parent)',
    '    from .oracle_runtime_paths import virtual, write_file\n    if virtual(target):\n        write_file(target,format_readable_report(report).encode(),exclusive=True)\n        return target\n    fd, temporary = tempfile.mkstemp(prefix=".request-trace-", dir=report_path.parent)')

edit('02_BACKEND/semantic_runtime/process_trace.py',
    "        fd = os.open(path, flags, 0o640)\n        os.fchmod(fd, 0o640)\n        self.stream = os.fdopen(fd, 'a', encoding='utf-8')",
    "        from .oracle_runtime_paths import virtual\n        if virtual(path):\n            self.stream=Path(path).open('x',encoding='utf-8')\n        else:\n            fd = os.open(path, flags, 0o640)\n            os.fchmod(fd, 0o640)\n            self.stream = os.fdopen(fd, 'a', encoding='utf-8')")
edit('02_BACKEND/semantic_runtime/learning_store.py',
    "    fd, temporary = tempfile.mkstemp(prefix='.learning-', dir=output.parent)",
    "    from .oracle_runtime_paths import virtual, write_file\n    if virtual(output):\n        write_file(output,(json.dumps(bundle,ensure_ascii=False,sort_keys=True,indent=2)+'\\n').encode(),exclusive=True)\n        return {'path':str(output),'sha256':sha(output),'bundle_id':bundle['id'],'expressions':len(bundle['expressions']),'recipes':len(bundle['recipes']),'activated':False}\n    fd, temporary = tempfile.mkstemp(prefix='.learning-', dir=output.parent)")
print('Candidate atomic publication/report/summary/trace paths connected')
