"""The parent records resource exits after wait(), without replaying a request."""
def record_resource_exit(artifacts, cell, case_id, provider, returncode, read, put):
    stop = cell/'resource-stop.json'
    if not returncode or not stop.exists():
        return
    calls = read(cell/'calls.json') if (cell/'calls.json').exists() else []
    receipt = {
        'case_id': case_id, 'provider': provider, 'exit_code': returncode,
        'reason': read(stop)['reason'], 'physical_calls': len(calls), 'turns': [],
        'unknown': sum(c['status'] in ('started','unknown') for c in calls),
        'local_resource_stop': True, 'remote_cancellation_confirmed': False, 'no_retry': True,
    }
    put(artifacts/'RESOURCE_STOP.json',receipt)
    if (cell/'binding.json').is_file() and not (cell/'result.json').exists():
        put(cell/'result.json',receipt)
