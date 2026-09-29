"""Pure logic for the ``verify_challenges`` harness: stats, cut rules, verdict.

Kept free of Docker so it is unit-testable; the management command does the
orchestration and I/O.
"""

import math
import re
import shlex
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from django.conf import settings

from challenges.catalog import Challenge
from challenges.sandbox import MAX_COMMAND_CHARS, SandboxResult

P95_LIMIT_S = 4.0
GO_RANDOMIZERS = Path('sandbox/internal/challenge/randomizers.go')


def percentile(values, q: float) -> float:
    """Nearest-rank percentile; 0.0 for an empty list."""
    ordered = sorted(values)
    if not ordered:
        return 0.0
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]


@lru_cache(maxsize=None)
def randomized_slugs() -> frozenset[str]:
    """Slugs with a randomizer, parsed from the vendored Go ``rndTable``."""
    source = (Path(settings.BASE_DIR) / GO_RANDOMIZERS).read_text()
    table = source.split('var rndTable', 1)[1].split('}', 1)[0]
    return frozenset(re.findall(r'"([^"]+)"\s*:', table))


def printable_command(ch: Challenge) -> str | None:
    """A command that just prints the expected lines, or None if over the length limit."""
    cmd = "printf '%s\\n'" + ''.join(' ' + shlex.quote(line) for line in ch.expected_lines)
    return cmd if len(cmd) <= MAX_COMMAND_CHARS else None


def _describe_failure(r: SandboxResult) -> str:
    if r.error_internal:
        return f'internal: {r.error_internal}'
    if r.timed_out:
        return 'timed out'
    return r.error or 'incorrect'


@dataclass
class ChallengeReport:
    slug: str
    excluded: bool
    sequential: list[SandboxResult]
    parallel: SandboxResult | None
    expected_failures: dict[str, SandboxResult]
    printable: str
    extra: dict = field(default_factory=dict)

    @property
    def runs(self) -> list[SandboxResult]:
        return self.sequential + ([self.parallel] if self.parallel else [])

    @property
    def total_runs(self) -> int:
        return len(self.runs)

    @property
    def pass_count(self) -> int:
        return sum(r.correct for r in self.runs)

    @property
    def internal_count(self) -> int:
        return sum(bool(r.error_internal) for r in self.runs)

    @property
    def seq_p50(self) -> float:
        return percentile([r.duration_s for r in self.sequential], 50)

    @property
    def seq_p95(self) -> float:
        return percentile([r.duration_s for r in self.sequential], 95)

    @property
    def par_duration(self) -> float:
        return self.parallel.duration_s if self.parallel else 0.0

    @property
    def accepted_expected_failures(self) -> list[str]:
        return [cmd for cmd, r in self.expected_failures.items() if r.correct]

    @property
    def failure_reason(self) -> str:
        for r in self.runs:
            if not r.correct:
                return _describe_failure(r)
        return ''

    def cut_reasons(self) -> list[str]:
        """Reasons this challenge must be cut (never includes error_internal)."""
        reasons = []
        for r in self.runs:
            if not r.correct and not r.error_internal and (r.error or r.timed_out):
                reasons.append('timed out' if r.timed_out else f'verifier rejected example: {r.error}')
                break
        if self.seq_p95 > P95_LIMIT_S:
            reasons.append(f'sequential p95 {self.seq_p95:.2f}s > {P95_LIMIT_S:.1f}s')
        if self.par_duration > P95_LIMIT_S:
            reasons.append(f'parallel duration {self.par_duration:.2f}s > {P95_LIMIT_S:.1f}s')
        reasons.extend(f'expected failure accepted: {cmd!r}' for cmd in self.accepted_expected_failures)
        return reasons


def gate_failures(reports: list[ChallengeReport], *, abuse_failures: list[str], leaked: int) -> list[str]:
    """Everything that makes ``verify_challenges`` exit 1. Empty list means green."""
    failures = []
    gating = [r for r in reports if not r.excluded]
    for r in gating:
        if r.pass_count != r.total_runs:
            failures.append(f'{r.slug}: not every run was correct ({r.pass_count}/{r.total_runs}; '
                            f'{r.failure_reason})')
        if r.internal_count:
            failures.append(f'{r.slug}: {r.internal_count} error_internal')
        for cmd in r.accepted_expected_failures:
            failures.append(f'{r.slug}: expected failure accepted: {cmd!r}')
        failures.extend(f'{r.slug}: cut candidate: {reason}'
                        for reason in r.cut_reasons() if 'p95' in reason or 'duration' in reason)
    seq = percentile([x.duration_s for r in gating for x in r.sequential], 95)
    par = percentile([r.par_duration for r in gating if r.parallel], 95)
    if seq > P95_LIMIT_S:
        failures.append(f'overall sequential p95 {seq:.2f}s > {P95_LIMIT_S:.1f}s')
    if par > P95_LIMIT_S:
        failures.append(f'overall parallel p95 {par:.2f}s > {P95_LIMIT_S:.1f}s')
    failures.extend(abuse_failures)
    if leaked:
        failures.append(f'{leaked} sandbox container(s) leaked')
    return failures
