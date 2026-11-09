"""Run the frozen schedule once: one model call at a time, at most one corrective call per group.

An outcome that is not known (transport failure after sending) ends that group and is
never re-sent. The runner waits while any other experiment tool is running on this host.
"""
from common import *
import json, os, time

GIB, MIB = 1024 ** 3, 1024 ** 2
sys.path.insert(0, str(ROOT / '02_BACKEND'))


def log(*parts):
    print(time.strftime('%H:%M:%S'), *parts, flush=True)


def sample():
    mem = {x.split(':')[0]: int(x.split()[1]) * 1024 for x in Path('/proc/meminfo').read_text().splitlines()
           if x.startswith(('MemAvailable:', 'SwapTotal:', 'SwapFree:'))}
    own = next(int(x.split()[1]) * 1024 for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmSwap:'))
    return {'time': time.time(), 'available': mem['MemAvailable'], 'swap_used': mem['SwapTotal'] - mem['SwapFree'],
            'swap_free': mem['SwapFree'], 'worker_swap': own}


def violation(now, base, limits, startup=False):
    if now['available'] < (limits['ram_start_gib'] if startup else limits['ram_floor_gib']) * GIB:
        return 'available RAM below frozen minimum'
    if now['swap_free'] < limits['swap_free_floor_gib'] * GIB:
        return 'global free swap below frozen minimum'
    if now['worker_swap'] - base['worker_swap'] > limits['worker_swap_growth_mib'] * MIB:
        return 'worker swap growth above frozen limit since admission'
    if now['swap_used'] - base['swap_used'] > limits['global_swap_growth_mib'] * MIB:
        return 'global swap growth above frozen limit since admission'
    return None


def others():
    """Other experiment tools on this host (their cells must run alone)."""
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            command = (entry / 'cmdline').read_bytes().replace(b'\0', b' ').decode('utf-8', 'replace')
        except OSError:
            continue
        if '06_TOOLS/EXPERIMENTS/adr_' in command and 'adr_1425' not in command:
            found.append(int(entry.name))
    return found


def wait_alone(limits):
    waited, announced = 0, False
    while others():
        if not announced:
            log('WAIT other experiment tool running', others()); announced = True
        if waited >= limits['wait_other_seconds']:
            return False
        time.sleep(20); waited += 20
    if announced:
        log('RESUME after waiting', waited, 'seconds'); time.sleep(20)
        return wait_alone(limits) if others() else True
    return True


def main():
    freeze = read(DES / 'freeze.json')
    changed = [name for name, expected in freeze['files'].items() if sha(ROOT / name) != expected]
    assert not changed, 'frozen file changed: ' + ', '.join(changed)
    criteria, schedule = read(DES / 'criteria.json'), read(DES / 'schedule.json')
    limits = criteria['limits']
    from lawrag.research.experiment_client import (ExperimentClient, ExperimentCallError, ExperimentFormatError,
                                                   ExperimentProviderError, ExperimentTransportError)
    RUN.mkdir(parents=True, exist_ok=True)
    journal = RUN / 'journal.jsonl'
    past = [json.loads(line) for line in journal.read_text('utf-8').splitlines()] if journal.exists() else []

    def record(event):
        with journal.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'at': time.time(), **event}, ensure_ascii=False) + '\n'); stream.flush(); os.fsync(stream.fileno())

    finals = {e['key'] for e in past if e['event'] == 'FINAL'}
    # A group interrupted before its final record is closed as it stands; nothing is re-sent.
    for key in {e['key'] for e in past if e['event'] in ('INTENT', 'RESULT')} - finals:
        results = [e for e in past if e['key'] == key and e['event'] == 'RESULT']
        intents = [e for e in past if e['key'] == key and e['event'] == 'INTENT']
        record({'event': 'FINAL', 'key': key, 'final': 'UNKNOWN' if len(intents) > len(results) else results[-1]['status'],
                'interrupted': True, 'resent': False}); finals.add(key)
    # Every HTTP request counts, including the first request of a known-429 provider switch.
    answered = {(e['key'], e['attempt']) for e in past if e['event'] == 'RESULT'}
    physical = (sum(e.get('physical_requests', 1) for e in past if e['event'] == 'RESULT')
                + sum(1 for e in past if e['event'] == 'INTENT' and (e['key'], e['attempt']) not in answered))
    cost = sum((e.get('usage') or {}).get('cost_usd') or 0 for e in past if e['event'] == 'RESULT')
    base = sample()
    why = violation(base, base, limits, startup=True)
    assert why is None, 'admission refused: ' + why
    if not wait_alone(limits):
        put(RUN / ('stopped-%d.json' % int(time.time())), {'state': 'STOPPED', 'reason': 'another experiment tool kept running', 'physical_calls': physical})
        return 3
    base = sample()
    session = RUN / 'calls' / ('s%02d' % (len(list((RUN / 'calls').glob('s*'))) + 1 if (RUN / 'calls').exists() else 1))
    client = ExperimentClient(ROOT, session, max_calls=limits['physical_total'] - physical)
    store = Store()
    loaded, built = {}, {}

    def group_of(item):
        code = CODE[item['arm']]
        if code not in loaded:
            loaded[code] = modules(code)
        slot = (item['case'], item['arm'])
        if slot not in built:
            built[slot] = loaded[code][0].build(store, CASES[item['case']], max_rows=ARMS[item['arm']], **FIXED)['groups']
        group = built[slot][item['group_index']]
        assert group['group_id'] == item['group_id'], 'group binding changed'
        return group, loaded[code][1]

    started, streak, reason = time.monotonic(), {'UNKNOWN': 0, 'REJECTED': 0}, None
    for item in schedule:
        key = '/'.join((item['case'], item['arm'], item['group_id']))
        if key in finals:
            continue
        if (ART / 'STOP_EXTERNAL.json').exists() or (RUN / 'resource-stop.json').exists():
            reason = 'stop file present'; break
        now = sample(); why = violation(now, base, limits)
        if why:
            put(RUN / 'resource-stop.json', {'reason': why, 'baseline': base, 'current': now, 'no_retry': True}); reason = why; break
        if physical >= limits['physical_total'] or cost >= limits['reported_cost_usd'] or time.monotonic() - started > limits['wall_seconds']:
            reason = 'frozen call, cost or wall limit reached'; break
        if not wait_alone(limits):
            reason = 'another experiment tool kept running'; break
        group, review = group_of(item)
        did = CASES[item['case']]
        data = review.payload(store.name(did), group, lambda segments: store.text(did, segments))
        schema = review.schema(group)
        attempts, previous, errors, value = [], None, None, None
        for attempt in (1, 2):
            phase = '%s-%s-g%03d-a%d' % (item['arm'], item['case'].split('-')[0], item['group_index'], attempt)
            known, sent = len(client.usage), client.calls
            record({'event': 'INTENT', 'key': key, 'attempt': attempt, 'session': session.name, 'call': client.calls + 1,
                    'phase': phase, 'payload_sha256': digest(data)})
            begun = time.monotonic(); report = None
            try:
                if attempt == 1:
                    value = client.generate(review.SYSTEM, data, schema, phase=phase)
                else:
                    value = client.generate(review.SYSTEM + review.REPAIR, {**data, 'previous_output': previous, 'errors': errors}, schema, phase=phase)
                report = review.accounting(value, group)
                status = 'COMPLETE' if review.complete(report) else 'INCOMPLETE'
                previous, errors = value, {'missing': report['missing'], 'duplicated': report['duplicated']}
            except ExperimentTransportError as error:
                status, detail = ('UNKNOWN' if error.unknown else 'REJECTED'), str(error)
            except ExperimentProviderError as error:
                status, detail = 'REJECTED', str(error)
            except ExperimentFormatError as error:
                status, detail = 'FORMAT', str(error)
            except ExperimentCallError as error:
                detail = str(error)
                status = 'BUDGET' if 'budget' in detail else 'REJECTED' if 'deadline' in detail.lower() else 'FORMAT'
            if status == 'FORMAT':
                saved = session / ('call-%03d-%s' % (client.calls, phase)) / 'response.json'
                try:
                    previous = read(saved)['choices'][0]['message'].get('content')
                except (OSError, KeyError, IndexError, TypeError, ValueError):
                    previous = None
                errors = {'format': detail[:300]}
            usage = client.usage[-1] if len(client.usage) > known else None
            physical += client.calls - sent
            cost += (usage or {}).get('cost_usd') or 0
            result = {'event': 'RESULT', 'key': key, 'attempt': attempt, 'status': status, 'seconds': round(time.monotonic() - begun, 3),
                      'physical_requests': client.calls - sent,
                      'usage': {k: usage.get(k) for k in ('seconds', 'input_tokens', 'output_tokens', 'cost_usd', 'upstream_provider')} if usage else None}
            if report is not None:
                result.update(missing=report['missing'], duplicated=report['duplicated'],
                              units=len(value['units']), placed={p: sum(v == p for v in report['placed_once'].values()) for p in review.PLACES})
            else:
                result['detail'] = detail[:300]
            record(result); attempts.append(result)
            # Only a content problem gets the single corrective call.
            if status not in ('INCOMPLETE', 'FORMAT'):
                break
        final = attempts[-1]['status']
        record({'event': 'FINAL', 'key': key, 'final': final, 'attempts': len(attempts), 'rows': len(group['rows']), 'chars': group['chars']})
        log('%d/%d' % (item['seq'], len(schedule)), item['case'], item['arm'], 'g%03d' % item['group_index'], 'rows', len(group['rows']),
            ' '.join('a%d=%s/%.1fs' % (a['attempt'], a['status'], a['seconds']) for a in attempts))
        for name in streak:
            streak[name] = streak[name] + 1 if final == name else 0
        if final == 'BUDGET' or max(streak.values()) >= 3:
            reason = 'call budget exhausted' if final == 'BUDGET' else 'three consecutive unknown or rejected groups'; break
    done = sum(1 for line in journal.read_text('utf-8').splitlines() if json.loads(line)['event'] == 'FINAL') if journal.exists() else 0
    state = {'state': 'STOPPED' if reason else 'COMPLETED', 'reason': reason, 'groups_final': done, 'groups_planned': len(schedule),
             'physical_calls': physical, 'reported_cost_usd': round(cost, 8), 'provider_switches': getattr(client, 'provider_switches', []),
             'seconds': round(time.monotonic() - started, 3)}
    put(RUN / ('batch-%s-%d.json' % (state['state'].lower(), int(time.time()))), state)
    log('BATCH', state['state'], reason or '', 'groups', done, 'calls', physical, 'cost', round(cost, 6))
    return 0 if not reason else 2


if __name__ == '__main__':
    sys.exit(main())
