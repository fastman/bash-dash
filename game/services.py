"""Game rules: starting a game, what a command does to it, and sandbox concurrency.

Views and ``bench_game`` call this module; nothing else knows the rules.

Transaction discipline: never hold a DB transaction open across ``run_command``
(0.15-6 s). Each submit is a short read, the sandbox run with no transaction,
then one short ``transaction.atomic()`` for the Attempt + conditional updates.
"""

import logging
import threading
from dataclasses import dataclass

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from challenges import catalog, sandbox
from challenges.catalog import Challenge

from .models import Attempt, GameSession

logger = logging.getLogger('game')

NICK_MAX_CHARS = 20

# SubmitOutcome.status values. Only RAN is counted as an attempt.
RAN = 'ran'
FINISHED = 'finished'
TOO_LONG = 'too_long'
EMPTY = 'empty'
UNAVAILABLE = 'unavailable'
BUSY = 'busy'
INTERNAL = 'internal'


@dataclass(frozen=True)
class SubmitOutcome:
    status: str
    result: sandbox.SandboxResult | None
    game: GameSession


# Per-process cap on concurrent sandbox runs. The harness does not go through here,
# so its own --parallel is never throttled by game settings.
_semaphore = None
_semaphore_lock = threading.Lock()


def _get_semaphore() -> threading.BoundedSemaphore:
    global _semaphore
    with _semaphore_lock:
        if _semaphore is None:
            _semaphore = threading.BoundedSemaphore(settings.SANDBOX_MAX_CONCURRENT)
        return _semaphore


def _reset_semaphore() -> None:
    """Test hook: the next ``_get_semaphore`` is re-sized from settings."""
    global _semaphore
    with _semaphore_lock:
        _semaphore = None


def start_game(nick: str) -> GameSession:
    nick = nick.strip()
    if not 1 <= len(nick) <= NICK_MAX_CHARS:
        raise ValueError(f'nick must be 1-{NICK_MAX_CHARS} characters')
    first = catalog.first_playable()
    if first is None:
        raise RuntimeError('no playable challenges')
    return GameSession.objects.create(nick=nick, current_slug=first.slug)


def current_challenge(game: GameSession) -> Challenge | None:
    """The game's current playable challenge; ``None`` means finished.

    A slug cut mid-game moves the player to the next playable challenge; if none
    follows, the game finishes (without a solve).
    """
    if game.current_slug is None:
        return None
    ch = catalog.playable(game.current_slug)
    if ch is not None:
        return ch
    old = game.current_slug
    nxt = catalog.next_playable(old)
    if nxt is not None:
        GameSession.objects.filter(pk=game.pk, current_slug=old).update(current_slug=nxt.slug)
    else:
        GameSession.objects.filter(pk=game.pk, current_slug=old).update(
            current_slug=None, finished_at=timezone.now())
    game.refresh_from_db()
    return catalog.playable(game.current_slug) if game.current_slug else None


def submit_command(game_id, command: str) -> SubmitOutcome:
    game = GameSession.objects.get(pk=game_id)
    challenge = None if game.is_finished else current_challenge(game)
    if challenge is None:
        return SubmitOutcome(FINISHED, None, game)
    if not command.strip():
        return SubmitOutcome(EMPTY, None, game)
    if len(command) > sandbox.MAX_COMMAND_CHARS:
        return SubmitOutcome(TOO_LONG, None, game)

    sandbox.reap_stale_once()
    sem = _get_semaphore()
    if not sem.acquire(timeout=settings.SANDBOX_QUEUE_TIMEOUT_S):
        return SubmitOutcome(BUSY, None, game)
    try:
        result = sandbox.run_command(challenge, command)
    except sandbox.SandboxUnavailable as exc:
        logger.warning('sandbox unavailable: %s', exc)
        return SubmitOutcome(UNAVAILABLE, None, game)
    except ValueError:  # backstop: length is checked above
        return SubmitOutcome(TOO_LONG, None, game)
    finally:
        sem.release()

    if result.error_internal:
        logger.error('internal sandbox error on %s for command %r: %s',
                     challenge.slug, command, result.error_internal)
        return SubmitOutcome(INTERNAL, result, game)

    counted = _record(game, challenge, command, result)
    game.refresh_from_db()
    return SubmitOutcome(RAN if counted else FINISHED, result if counted else None, game)


def _record(game: GameSession, challenge: Challenge, command: str, result: sandbox.SandboxResult) -> bool:
    """Count the run and store its Attempt, unless the game finished while it ran.

    The counter update goes first and gates the insert, so Attempt rows and
    ``GameSession.attempts`` always agree. Returns whether the run was counted.
    """
    now = timezone.now()
    with transaction.atomic():
        counted = GameSession.objects.filter(pk=game.pk, finished_at__isnull=True).update(
            attempts=F('attempts') + 1)
        if not counted:
            return False
        Attempt.objects.create(
            game=game, slug=challenge.slug, command=command, correct=result.correct,
            output=result.output, error=result.error[:255], timed_out=result.timed_out,
            duration_ms=round(result.duration_s * 1000),
        )
        if result.correct:
            nxt = catalog.next_playable(challenge.slug)
            # The current_slug guard makes a duplicate correct submit advance once.
            GameSession.objects.filter(pk=game.pk, current_slug=challenge.slug).update(
                solved=F('solved') + 1,
                last_solved_at=now,
                current_slug=nxt.slug if nxt else None,
                finished_at=None if nxt else now,
            )
    return True


def last_attempt(game: GameSession) -> Attempt | None:
    return game.attempt_set.order_by('-created_at', '-pk').first()
