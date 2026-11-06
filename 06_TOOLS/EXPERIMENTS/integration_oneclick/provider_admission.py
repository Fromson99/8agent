"""Select configured endpoints that currently support the experiment contract."""

REQUIRED = {'response_format', 'structured_outputs', 'reasoning'}


def admit(profiles, endpoints):
    accepted = {}
    skipped = {}
    for name, profile in profiles.items():
        matches = [entry for entry in endpoints if entry.get('tag') == profile['tag']]
        if len(matches) != 1:
            skipped[name] = 'endpoint missing or ambiguous'
            continue
        endpoint = matches[0]
        missing = REQUIRED.difference(endpoint.get('supported_parameters') or ())
        if endpoint.get('status') != 0:
            skipped[name] = 'endpoint unavailable'
        elif missing:
            skipped[name] = 'missing parameters: ' + ', '.join(sorted(missing))
        else:
            accepted[name] = profile
    return accepted, skipped
