"""Shared test doubles for the game app."""

from challenges import sandbox


def result(correct=False, *, output='', error='', error_internal='', timed_out=False, duration_s=0.12):
    """A canned ``SandboxResult`` for patching ``sandbox.run_command``."""
    return sandbox.SandboxResult(correct=correct, output=output, error=error, error_internal=error_internal,
                                 exit_code=0, timed_out=timed_out, duration_s=duration_s)
