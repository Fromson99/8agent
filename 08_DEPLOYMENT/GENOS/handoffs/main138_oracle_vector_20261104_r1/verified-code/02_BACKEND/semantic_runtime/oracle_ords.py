"""ORDS SDK or standard-library REST transport; never resend a SQL request.

REST is selected only when genos.ords is absent, before any network activity.
The existing SQL owner validates Oracle errors, complete pages, hashes and budgets.
OAuth tokens are memory-only; SQL errors/timeouts never trigger token-refresh replay.
"""
from __future__ import annotations

import base64
import json as jsonlib
import math
import os
import ssl
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import (HTTPSHandler, HTTPRedirectHandler, ProxyHandler,
                            Request, build_opener)

from .oracle_dp_io import DPError


class _HTTPFailure(DPError):
    def __init__(self, stage, status):
        super().__init__(f'ORDS_{stage}_HTTP: {status}')
        self.status = status


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Credentials and SQL must stay at the configured endpoint.
        return None


class RestClient:
    SQL_PATH = '/_/sql'
    MAX_RESPONSE_BYTES = 65 * 1024 * 1024

    def __init__(self, *, schema, auth_key, base_url, timeout=60, verify=True):
        parsed = urlsplit(base_url)
        if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
                parsed.username is not None or parsed.password is not None or
                parsed.query or parsed.fragment):
            raise DPError('DP_CONFIG: REST requires ORACLE_ORDS_BASE_URL or LLMOPS_ORDS_BASE_URL without credentials/query/fragment')
        if not schema or schema in ('.', '..') or '/' in schema or '\\' in schema:
            raise DPError('DP_CONFIG: invalid ORDS schema alias')
        if verify is not True or not math.isfinite(timeout) or timeout <= 0:
            raise DPError('DP_CONFIG: verified TLS and a positive finite timeout required')
        self.root = base_url.rstrip('/') + '/' + quote(schema, safe='')
        self.auth_key, self.timeout = auth_key, timeout
        self._opener = build_opener(ProxyHandler({}), _NoRedirect(),
                                    HTTPSHandler(context=ssl.create_default_context()))
        self._token_lock = threading.Lock()
        self._bearer, self._expires_at = None, 0.0

    @staticmethod
    def _remaining(deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise DPError('ORDS_TIMEOUT: transport deadline exhausted')
        return remaining

    def _send(self, request, stage, deadline, maximum):
        try:
            with self._opener.open(request, timeout=self._remaining(deadline)) as response:
                raw = response.read(maximum + 1)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            # Do not expose response bodies, URLs, credentials or SQL bind values.
            raise _HTTPFailure(stage, status) from None
        except (URLError, OSError) as exc:
            raise DPError(f'ORDS_{stage}_TRANSPORT: {type(exc).__name__}') from None
        self._remaining(deadline)
        if len(raw) > maximum:
            raise DPError(f'ORDS_{stage}_SIZE: response exceeds bound')
        try:
            body = jsonlib.loads(raw)
        except (ValueError, UnicodeError):
            raise DPError(f'ORDS_{stage}_JSON: invalid response') from None
        if not isinstance(body, dict):
            raise DPError(f'ORDS_{stage}_JSON: expected object')
        return body

    def _token(self, deadline):
        acquired = self._token_lock.acquire(timeout=self._remaining(deadline))
        if not acquired:
            raise DPError('ORDS_TIMEOUT: token lock deadline exhausted')
        try:
            if self._bearer and time.monotonic() < self._expires_at:
                return self._bearer
            client_id, secret = self.auth_key
            basic = base64.b64encode((client_id + ':' + secret).encode()).decode('ascii')
            started = time.monotonic()
            request = Request(self.root + '/oauth/token', method='POST',
                              data=b'grant_type=client_credentials', headers={
                                  'Authorization': 'Basic ' + basic,
                                  'Content-Type': 'application/x-www-form-urlencoded',
                                  'Accept': 'application/json'})
            body = self._send(request, 'AUTH', deadline, 64 * 1024)
            token = body.get('access_token')
            if (not isinstance(token, str) or not token or any(c.isspace() for c in token) or
                    str(body.get('token_type', 'bearer')).lower() != 'bearer'):
                raise DPError('ORDS_AUTH_TOKEN: invalid bearer token')
            try:
                life = float(body.get('expires_in', 0))
            except (TypeError, ValueError):
                life = 0
            # Unknown/invalid expiry: use this token once, renew before the next SQL.
            if not math.isfinite(life) or life <= 0:
                life = 0
            self._expires_at = started + max(0, life - min(60, life / 10))
            self._bearer = token
            return token
        finally:
            self._token_lock.release()

    def request(self, method, path, json=None):
        if method != 'POST' or path != self.SQL_PATH or not isinstance(json, dict):
            raise DPError('ORDS_REQUEST: only the bound SQL POST endpoint is supported')
        # Serialize first, so invalid local input never obtains a token/sends SQL.
        payload = jsonlib.dumps(json, ensure_ascii=False, allow_nan=False).encode()
        deadline = time.monotonic() + self.timeout
        token = self._token(deadline)
        request = Request(self.root + self.SQL_PATH, method='POST', data=payload, headers={
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json', 'Accept': 'application/json'})
        try:
            return self._send(request, 'SQL', deadline, self.MAX_RESPONSE_BYTES)
        except _HTTPFailure as exc:
            # A rejected token is renewed only for a subsequent caller's request.
            # Do not wait behind another refresh or invalidate its newer token.
            if exc.status == 401 and self._token_lock.acquire(blocking=False):
                try:
                    if self._bearer == token:
                        self._expires_at = 0
                finally:
                    self._token_lock.release()
            raise


def create_client(**options):
    try:
        from genos.ords import ORDSClient
    except ModuleNotFoundError as exc:
        if exc.name not in ('genos', 'genos.ords'):
            raise DPError('DP_CONNECT: ORDS SDK dependency is missing') from None
        base_url = (options.get('base_url') or os.environ.get('LLMOPS_ORDS_BASE_URL', '')).strip()
        return RestClient(**{**options, 'base_url': base_url})
    # Installed-but-broken SDKs and HTTP errors do not select another transport.
    return ORDSClient(**options)
