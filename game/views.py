"""Thin HTTP layer over ``game.services``. The player's game is ``request.session['game_id']``."""

import json

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from challenges import catalog, sandbox

from . import services
from .models import GameSession
from .templatetags.game_text import render_description

HTTP_STATUS = {
    services.RAN: 200,
    services.FINISHED: 409,
    services.TOO_LONG: 400,
    services.EMPTY: 400,
    services.UNAVAILABLE: 503,
    services.BUSY: 503,
    services.INTERNAL: 500,
    services.TIME_UP: 409,
}

MESSAGES = {
    services.FINISHED: 'The game is over.',
    services.TOO_LONG: f'Command too long (max {sandbox.MAX_COMMAND_CHARS} characters).',
    services.EMPTY: 'Type a command first.',
    services.UNAVAILABLE: 'Sandbox unavailable, try again.',
    services.BUSY: 'Server busy, try again in a moment.',
    services.INTERNAL: 'Internal error, try again.',
    services.TIME_UP: "Time's up.",
}
# A valid body is at most ~1.2 KB ({"command": <300 chars, JSON-escaped>}); anything
# bigger is rejected before parsing, which also bounds json's recursion depth.
MAX_BODY_BYTES = 4096
BAD_REQUEST = {'status': 'bad_request', 'message': 'Malformed request.'}

CORRECT = 'Correct!'
TIMED_OUT = 'Timed out (5 s limit)'
INCORRECT = 'Incorrect.'


def verdict(correct: bool, error: str, timed_out: bool) -> str:
    """Player-facing verdict for a counted run (never ``error_internal``)."""
    if correct:
        return CORRECT
    if timed_out:
        return TIMED_OUT
    return error or INCORRECT


def _session_game(request) -> GameSession | None:
    game_id = request.session.get('game_id')
    if not game_id:
        return None
    services.expire_overdue(game_id)
    return GameSession.objects.filter(pk=game_id).first()


def _challenge_info(challenge) -> dict | None:
    if challenge is None:
        return None
    playable = catalog.main_set()
    index = next(i for i, c in enumerate(playable) if c.slug == challenge.slug) + 1
    return {
        'index': index,
        'total': len(playable),
        'title': challenge.title,
        'description_html': render_description(challenge.description),
    }


NO_GAME = {'status': 'no_game', 'message': 'No game in progress.'}


def _redirect_existing(game: GameSession):
    return redirect('game:done' if game.is_finished else 'game:play')


def _gate_refusal(request, token):
    """403 refusal page when ``token`` is not a valid start token, else None."""
    status = services.check_start_token(token)
    if status == services.TOKEN_OK:
        return None
    return render(request, 'game/gate.html', {
        'expired': status == services.TOKEN_EXPIRED, 'invalid': status == services.TOKEN_INVALID,
        'code': token, 'digits': services.TOKEN_DIGITS}, status=403)


@require_GET
def home(request):
    game = _session_game(request)
    if game:
        return _redirect_existing(game)
    token = services.normalize_token(request.GET.get('t'))
    refusal = _gate_refusal(request, token)
    if refusal:
        return refusal
    return render(request, 'game/home.html', {'duration': settings.GAME_DURATION_S, 'token': token})


@require_POST
def start(request):
    game = _session_game(request)
    if game:
        return _redirect_existing(game)
    token = services.normalize_token(request.POST.get('t'))
    refusal = _gate_refusal(request, token)
    if refusal:
        return refusal
    nick = request.POST.get('nick', '')
    try:
        game = services.start_game(nick)
    except ValueError:
        return render(request, 'game/home.html', {
            'duration': settings.GAME_DURATION_S, 'token': token,
            'error': f'Use 1-{services.NICK_MAX_CHARS} letters, digits or _ (no spaces).', 'nick': nick})
    request.session['game_id'] = str(game.pk)
    return redirect('game:play')


@require_GET
@ensure_csrf_cookie  # play.js reads the csrftoken cookie
def play(request):
    game = _session_game(request)
    if game is None:
        return redirect('game:home')
    if game.is_finished:
        return redirect('game:done')
    challenge = services.current_challenge(game)
    if challenge is None:
        return redirect('game:done')
    last = services.last_attempt(game)
    return render(request, 'game/play.html', {
        'game': game,
        'challenge': challenge,
        'info': _challenge_info(challenge),
        'last': last,
        'remaining_ms': services.remaining_ms(game),
        'last_verdict': verdict(last.correct, last.error, last.timed_out) if last else '',
    })


@require_GET
def state(request):
    """Authoritative remaining time, for clients whose monotonic clock may have paused."""
    game = _session_game(request)
    if game is None:
        return JsonResponse(NO_GAME, status=403)
    return JsonResponse({'remaining_ms': services.remaining_ms(game), 'finished': game.is_finished})


@require_POST
def command(request):
    game = _session_game(request)
    if game is None:
        return JsonResponse(NO_GAME, status=403)
    if len(request.body) > MAX_BODY_BYTES:
        return JsonResponse({**BAD_REQUEST, 'message': 'Request too large.'}, status=413)
    try:
        body = json.loads(request.body)
        cmd = body['command']
        if not isinstance(cmd, str):
            raise TypeError
        cmd.encode()  # lone surrogates: UnicodeEncodeError (a ValueError), not "too long" later
    except (ValueError, KeyError, TypeError, RecursionError):
        return JsonResponse(BAD_REQUEST, status=400)

    outcome = services.submit_command(game.pk, cmd)
    game = outcome.game
    challenge = None if game.is_finished else services.current_challenge(game)
    data = {
        'status': outcome.status,
        'attempts': game.attempts,
        'solved': game.solved,
        'finished': game.is_finished,
        'remaining_ms': services.remaining_ms(game),
        'challenge': _challenge_info(challenge),
    }
    if outcome.status == services.RAN:
        r = outcome.result
        data['message'] = verdict(r.correct, r.error, r.timed_out)
        data['result'] = {'correct': r.correct, 'output': r.output, 'message': data['message']}
    else:
        data['message'] = MESSAGES[outcome.status]
    return JsonResponse(data, status=HTTP_STATUS[outcome.status])


@require_GET
def done(request):
    game = _session_game(request)
    if game is None:
        return redirect('game:home')
    if not game.is_finished:
        return redirect('game:play')
    total = len(catalog.main_set())
    rank = services.rank_of(game)
    place, ranked_total = rank if rank else (None, None)
    return render(request, 'game/done.html', {
        'game': game,
        'total': total,
        'place': place,
        'ranked_total': ranked_total,
        'timed_out': game.timed_out,
        'all_solved': not game.timed_out and game.solved >= total,
    })
