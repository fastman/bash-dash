"""Run one player command in the hardened ``bash-dash-sandbox`` container.

``SANDBOX_RUN_PROFILE`` is the single definition of the hardening profile; the
game and the ``verify_challenges`` harness both run commands through
``run_command`` so a challenge that passes the harness passes in the game.
"""

import base64
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import docker
import docker.errors
import requests.exceptions
from django.conf import settings

from challenges.catalog import Challenge

SANDBOX_LABEL = 'bash-dash.sandbox'
MAX_COMMAND_CHARS = 300  # upstream limit
MAX_OUTPUT_CHARS = 64 * 1024
HOST_TIMEOUT_S = 6  # runcmd's own timeout is 5 s inside the container
# json-file max-size=1m rotates (max-file=1), so an oversized runcmd JSON line
# survives only as an arbitrary tail. runcmd -cmd always prints JSON and exits 0,
# so "unparsable + exit 0" (or a near-cap log) means the line was truncated.
TRUNCATED_LOG_BYTES = 900 * 1024

RUNCMD_TIMEOUT = 'timed out executing command'
MEMORY_ERROR = 'Command used too much memory or output'
TOO_LARGE_ERROR = 'Output too large (limit about 1 MB)'
TAMPER_ERROR = 'Command interfered with the sandbox output'
# sandbox-entry.sh exit codes (outside the range bash/runcmd use).
ENTRYPOINT_ERRORS = {64: 'sandbox-entry usage error', 65: 'sandbox-entry missing fixture dir'}
# The only run kwargs the harness may add (to emulate the event VM's CPUs).
ALLOWED_HOST_OVERRIDES = frozenset({'cpuset_cpus'})

SANDBOX_RUN_PROFILE = {
    'network_mode': 'none',
    'mem_limit': '100m',
    'memswap_limit': '100m',
    'pids_limit': 64,
    'nano_cpus': 500_000_000,  # 0.5 CPU
    'cap_drop': ['ALL'],
    'security_opt': ['no-new-privileges'],
    'user': '1000:1000',
    'read_only': True,
    'tmpfs': {
        '/var/challenges': 'size=16m,mode=1777,exec',
        '/tmp': 'size=16m,mode=1777',
    },
    'shm_size': '1m',
    'environment': {'GOMAXPROCS': '1'},
    'log_config': {'type': 'json-file', 'config': {'max-size': '1m'}},
    'labels': {SANDBOX_LABEL: '1'},
}


class SandboxUnavailable(Exception):
    """Docker failed before the sandbox container existed (daemon down, image missing)."""


@dataclass(frozen=True)
class SandboxResult:
    correct: bool
    output: str
    error: str
    error_internal: str
    exit_code: int | None
    timed_out: bool
    duration_s: float


_client = None
_client_lock = threading.Lock()


def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            _client = docker.from_env()
        return _client


def _stdout_verdict(raw: bytes) -> tuple[str, dict | None]:
    """Classify container stdout: ('json', data) | ('bad_json', None) | ('multi', None) | ('none', None).

    runcmd -cmd prints exactly one JSON line. Anything else on stdout means the
    output was truncated (log rotation) or something other than runcmd wrote to
    it, so a verdict is only trusted when stdout is exactly one non-empty line.
    """
    lines = [ln for ln in raw.decode('utf-8', errors='replace').splitlines() if ln.strip()]
    if len(lines) > 1:
        return 'multi', None
    if not lines:
        return 'none', None
    try:
        data = json.loads(lines[0])
    except ValueError:
        data = None
    if isinstance(data, dict):
        return 'json', data
    if lines[0].lstrip().startswith('{"Correct"'):
        return 'bad_json', None  # a whole runcmd line that fails to parse: our bug, not the player's
    return 'none', None


def _interpret(raw: bytes, state: dict, host_timed_out: bool) -> dict:
    """Map container stdout + state to SandboxResult fields (minus duration)."""
    exit_status = state.get('ExitCode')
    kind, data = _stdout_verdict(raw)
    base = dict(correct=False, output='', error='', error_internal='', exit_code=None, timed_out=False)

    if kind == 'json':
        base.update(
            output=str(data.get('Output') or '')[:MAX_OUTPUT_CHARS],
            error=str(data.get('Error') or ''),
            error_internal=str(data.get('ErrorInternal') or ''),
            exit_code=data.get('ExitCode'),
            correct=bool(data.get('Correct')),
        )
        if base['error_internal'] == RUNCMD_TIMEOUT:
            base.update(timed_out=True, correct=False, error_internal='')
        elif exit_status not in (0, None) and not host_timed_out:
            base.update(correct=False, error_internal=base['error_internal']
                        or f'sandbox exited with status {exit_status}')
        return base

    if exit_status in ENTRYPOINT_ERRORS:
        base['error_internal'] = f'{ENTRYPOINT_ERRORS[exit_status]} (status {exit_status})'
    elif state.get('OOMKilled'):
        base['error'] = MEMORY_ERROR
    elif host_timed_out:
        base['timed_out'] = True
    elif exit_status == 137:
        base['error'] = MEMORY_ERROR
    elif kind == 'multi':
        base['error'] = TAMPER_ERROR
    elif len(raw) >= TRUNCATED_LOG_BYTES:
        base['error'] = TOO_LARGE_ERROR
    elif kind == 'bad_json':
        tail = raw[-200:].decode('utf-8', errors='replace').strip()
        base['error_internal'] = f'invalid runcmd JSON (status {exit_status}): {tail!r}'
    elif exit_status == 0 and raw.strip():
        base['error'] = TOO_LARGE_ERROR
    else:
        tail = raw[-200:].decode('utf-8', errors='replace').strip()
        base['error_internal'] = f'unparsable sandbox output (status {exit_status}): {tail!r}'
    return base


def run_command(challenge: Challenge, command: str, *, client=None,
                host_overrides: dict | None = None) -> SandboxResult:
    """Run ``command`` for ``challenge`` under ``SANDBOX_RUN_PROFILE``.

    Raises ``ValueError`` for over-long commands and ``SandboxUnavailable`` if
    Docker fails before the container is running. Every outcome after the
    container has started is returned as a ``SandboxResult``; the container is
    always removed.

    ``host_overrides`` is harness-only: an allowlist (``ALLOWED_HOST_OVERRIDES``,
    i.e. ``cpuset_cpus`` to emulate the event VM) so it can never weaken the profile.
    """
    if len(command) > MAX_COMMAND_CHARS:
        raise ValueError(f'command longer than {MAX_COMMAND_CHARS} characters')
    host_overrides = dict(host_overrides or {})
    refused = sorted(set(host_overrides) - ALLOWED_HOST_OVERRIDES)
    if refused:
        raise ValueError(f'host_overrides not allowed: {", ".join(refused)}')
    client = client or _get_client()
    b64 = base64.b64encode(command.encode()).decode()
    started = time.monotonic()

    try:
        # Check first: create would otherwise fail with a less useful 404.
        client.images.get(settings.SANDBOX_IMAGE)
        container = client.containers.create(
            settings.SANDBOX_IMAGE,
            command=[challenge.dir, challenge.slug, b64],
            **SANDBOX_RUN_PROFILE,
            **host_overrides,
        )
    except docker.errors.DockerException as exc:
        raise SandboxUnavailable(str(exc)) from exc

    try:
        try:
            # Inside the finally: a container that was created but never started is still removed.
            container.start()
        except docker.errors.DockerException as exc:
            raise SandboxUnavailable(str(exc)) from exc
        host_timed_out = False
        try:
            container.wait(timeout=HOST_TIMEOUT_S)
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
            host_timed_out = True
            try:
                container.kill()
            except docker.errors.DockerException:
                pass
        raw = container.logs(stdout=True, stderr=False)
        container.reload()
        fields = _interpret(raw, container.attrs.get('State', {}), host_timed_out)
    except SandboxUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001 — never raise once the container has started
        fields = dict(correct=False, output='', error='', exit_code=None, timed_out=False,
                      error_internal=f'{type(exc).__name__}: {exc}')
    finally:
        try:
            container.remove(force=True, v=True)
        except Exception:  # noqa: BLE001 — reap_stale is the backstop
            pass

    return SandboxResult(duration_s=time.monotonic() - started, **fields)


def _created_at(container) -> datetime:
    created = container.attrs['Created']  # e.g. 2026-09-29T12:00:00.123456789Z
    head, _, frac = created.rstrip('Z').partition('.')
    frac = (frac + '000000')[:6]
    return datetime.fromisoformat(f'{head}.{frac}').replace(tzinfo=timezone.utc)


def reap_stale(max_age_s: float = 60, *, client=None) -> int:
    """Force-remove labelled sandbox containers that never started, exited, or are older than ``max_age_s``.

    Backstop for containers orphaned by a killed caller. Call it when no runs
    from this host are in flight (app startup, start of ``verify_challenges``).
    """
    client = client or _get_client()
    now = datetime.now(timezone.utc)
    removed = 0
    for c in client.containers.list(all=True, filters={'label': SANDBOX_LABEL}):
        age = (now - _created_at(c)).total_seconds()
        if c.status in ('created', 'exited', 'dead') or age > max_age_s:
            try:
                c.remove(force=True, v=True)
                removed += 1
            except docker.errors.NotFound:
                pass
    return removed
