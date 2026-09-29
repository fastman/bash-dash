"""A minimal in-memory stand-in for ``docker.DockerClient`` used by unit tests."""

import json
from datetime import datetime, timedelta, timezone

import docker.errors
import requests.exceptions


def runcmd_json(**fields) -> bytes:
    data = {'Correct': False, 'Output': '', 'ExitCode': 0}
    data.update(fields)
    return (json.dumps(data) + '\n').encode()


class FakeContainer:
    def __init__(self, *, logs=b'', exit_code=0, oom_killed=False, wait_timeout=False,
                 status='exited', created=None, logs_error=None):
        self._logs = logs
        self.exit_code = exit_code
        self.oom_killed = oom_killed
        self.wait_timeout = wait_timeout
        self.logs_error = logs_error
        self.status = status
        created = created or datetime.now(timezone.utc)
        self.attrs = {
            'Created': created.strftime('%Y-%m-%dT%H:%M:%S.%f') + '123Z',
            'State': {'ExitCode': exit_code, 'OOMKilled': oom_killed},
        }
        self.killed = False
        self.removed_with = None
        self.wait_calls = []

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        if self.wait_timeout:
            raise requests.exceptions.ReadTimeout('read timed out')
        return {'StatusCode': self.exit_code}

    def logs(self, stdout=True, stderr=True):
        assert stdout and not stderr
        if self.logs_error:
            raise self.logs_error
        return self._logs

    def reload(self):
        pass

    def kill(self):
        self.killed = True
        self.attrs['State']['ExitCode'] = 137

    def remove(self, **kwargs):
        self.removed_with = kwargs


class FakeImages:
    def __init__(self, present=True):
        self.present = present
        self.requested = []

    def get(self, name):
        self.requested.append(name)
        if not self.present:
            raise docker.errors.ImageNotFound(f'No such image: {name}')
        return object()


class FakeContainers:
    def __init__(self, container=None, run_error=None, listed=()):
        self.container = container
        self.run_error = run_error
        self.listed = list(listed)
        self.run_calls = []
        self.list_calls = []

    def run(self, image, command=None, **kwargs):
        self.run_calls.append({'image': image, 'command': command, **kwargs})
        if self.run_error:
            raise self.run_error
        return self.container

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return list(self.listed)


class FakeClient:
    def __init__(self, container=None, *, image_present=True, run_error=None, listed=()):
        self.images = FakeImages(image_present)
        self.containers = FakeContainers(container, run_error, listed)


def aged(seconds: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(seconds=seconds)
