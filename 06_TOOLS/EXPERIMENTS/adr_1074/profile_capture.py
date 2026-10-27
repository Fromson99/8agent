"""Collect only coarse timing events from the unchanged service logger."""
from contextlib import contextmanager
from copy import deepcopy
import logging

LIFETIME_EVENTS = {'timing.service.returning','timing.report.enqueued',
                   'timing.report.worker_started','timing.report.worker_finished'}
LIFETIME_NUMBERS = {'duration_ms','returning_ns','enqueued_ns','worker_started_ns',
                    'queue_ms','worker_finished_ns','finalize_ms'}
LIFETIME_LABELS = {'request_id','schema_version','boundary','status'}


@contextmanager
def capture():
    records = []
    class Capture(logging.Handler):
        _genos_system_capture = True
        def emit(self, record):
            name = record.getMessage()
            if name not in {'timing.probe.started','timing.probe.summary','timing.probe.failed'} | LIFETIME_EVENTS:
                return
            try:
                fields=getattr(record, 'fields', {})
                if name in LIFETIME_EVENTS:
                    fields={key:value for key,value in fields.items()
                        if (key in LIFETIME_NUMBERS and type(value) in (int,float) and value>=0)
                        or (key in LIFETIME_LABELS and isinstance(value,str))
                        or (key=='finalizer_included' and type(value) is bool)}
                records.append({'event':name, 'fields':deepcopy(fields)})
            except Exception as exc:
                records.append({'event':'timing.probe.capture_failed', 'error_type':type(exc).__name__})
    handler = Capture()
    logger = logging.getLogger('genos')
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        handler.close()


def receipt(records, *, freeze_hash, code_root, replay, service_seconds, shared_report_enabled=False):
    summaries = [row for row in records if row['event'] == 'timing.probe.summary']
    reports=[row for row in records if row['event'].startswith('timing.report.')]
    finalizers=[row for row in reports if row['event']=='timing.report.worker_finished']
    return {'schema_version':'non-model-service-profile-v1',
            'design_freeze_sha256':freeze_hash, 'code_root':code_root,
            'mode':'coarse', 'replay':replay, 'service_seconds':service_seconds,
            'profile_complete':len(summaries) == 1 and not any(
                row['event'] in {'timing.probe.failed','timing.probe.capture_failed'} for row in records),
            'model_boundary':'MODEL_ATTEMPT is the entire send_once call, including transport overhead.',
            'raw_network_latency_measured':False, 'pure_inference_latency_measured':False,
            'report_finalizer':{'enabled':shared_report_enabled,
                'status':'OBSERVED_WITHIN_CAPTURE' if finalizers else 'NOT_MEASURED',
                'reason':None if finalizers else ('Finalizer did not finish before capture closed.'
                    if shared_report_enabled else 'Shared request reports are disabled in this isolated runner.'),
                'finalizer_wait_added':False,
                'capture_boundary':'After service return or exception; before store close.',
                'late_events_reference':'Worker process stderr log; no late event is presumed to exist.',
                'captured_event_count':len(reports)},
            'events':records}
