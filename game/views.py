"""Thin HTTP layer over ``game.services``. The player's game is ``request.session['game_id']``."""

import json

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
}

MESSAGES = {
    services.FINISHED: 'The game is over.',
    services.TOO_LONG: f'Command too long (max {sandbox.MAX_COMMAND_CHARS} characters).',
    services.EMPTY: 'Type a command first.',
    services.UNAVAILABLE: 'Sandbox unavailable, try again.',
    services.BUSY: 'Server busy, try again in a moment.',
    services.INTERNAL: 'Internal error, try again.',
}
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


def _redirect_existing(game: GameSession):
    return redirect('game:done' if game.is_finished else 'game:play')


@require_GET
def home(request):
    game = _session_game(request)
    if game:
        return _redirect_existing(game)
    return render(request, 'game/home.html')


@require_POST
def start(request):
    game = _session_game(request)
    if game:
        return _redirect_existing(game)
    nick = request.POST.get('nick', '')
    try:
        game = services.start_game(nick)
    except ValueError:
        return render(request, 'game/home.html', {
            'error': f'Enter a nick of 1-{services.NICK_MAX_CHARS} characters.', 'nick': nick})
    request.session['game_id'] = str(game.pk)
    return redirect('game:play')


@require_GET
@ensure_csrf_cookie  # play.js reads the csrftoken cookie
def play(request):
    game = _session_game(request)
    if game is None:
        return redirect('game:home')
    challenge = services.current_challenge(game)
    if challenge is None:
        return redirect('game:done')
    last = services.last_attempt(game)
    return render(request, 'game/play.html', {
        'game': game,
        'challenge': challenge,
        'info': _challenge_info(challenge),
        'last': last,
        'last_verdict': verdict(last.correct, last.error, last.timed_out) if last else '',
    })


@require_POST
def command(request):
    game = _session_game(request)
    if game is None:
        return JsonResponse({'status': 'no_game', 'message': 'No game in progress.'}, status=403)
    try:
        body = json.loads(request.body)
        cmd = body['command']
        if not isinstance(cmd, str):
            raise TypeError
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'status': 'bad_request', 'message': 'Malformed request.'}, status=400)

    outcome = services.submit_command(game.pk, cmd)
    game = outcome.game
    challenge = None if game.is_finished else services.current_challenge(game)
    data = {
        'status': outcome.status,
        'attempts': game.attempts,
        'solved': game.solved,
        'finished': game.is_finished,
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
    return render(request, 'game/done.html', {'game': game, 'total': len(catalog.main_set())})
