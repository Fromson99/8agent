"""Read-only tail of one execution's immutable Dataiku log chunks."""
import codecs
import re
import time


class LogTail:
    def __init__(self, folder, prefix):
        self.folder, self.prefix = folder, prefix
        self.offset = None
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')

    def read_new(self):
        files = {}
        for path in self.folder.list_paths_in_partition():
            name = path.lstrip('/')
            if not name.startswith(self.prefix):
                continue
            match = re.fullmatch(r'(\d{16})\.log', name[len(self.prefix):])
            if match:
                offset = int(match[1])
                if offset in files:
                    raise ValueError('DUPLICATE_LOG_OFFSET')
                files[offset] = path
        if not files:
            return
        first = self.offset is None
        if first:
            self.offset = max(files)  # Begin at the latest available chunk.
        while self.offset in files:
            with self.folder.get_download_stream(files[self.offset]) as stream:
                raw = stream.read(2*1024*1024 + 1)
            if not raw or len(raw) > 2*1024*1024:
                raise ValueError('LOG_CHUNK_SIZE')
            value = self.decoder.decode(raw, final=False)
            self.offset += len(raw)
            if first:
                value = ''.join(value.splitlines(keepends=True)[-60:])
                first = False
            if value:
                yield value


def follow(folder, prefix, interval=10):
    reader = LogTail(folder, prefix)
    last_notice = 0.0
    print('TAIL 시작: ' + prefix, flush=True)
    print('Dataiku에 저장된 새 로그를 10초 간격으로 읽습니다. 중단: Kernel → Interrupt.', flush=True)
    try:
        while True:
            received = False
            for value in reader.read_new():
                print(value, end='', flush=True)
                received = True
            if received:
                last_notice = time.monotonic()
            elif time.monotonic() - last_notice >= 30:
                print('\n[' + time.strftime('%H:%M:%S') + '] 새 저장 로그 대기', flush=True)
                last_notice = time.monotonic()
            time.sleep(interval)
    except KeyboardInterrupt:
        print('\n로그 보기만 중단했습니다. 02 작업에는 취소를 보내지 않았습니다.', flush=True)
