"""Staff-facing pages (prize desk). Every view requires a staff login."""

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.timesince import timesince
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from challenges import catalog

from . import services
from .models import GameSession


def _back(code: str):
    return redirect(f'{reverse("game:staff_lookup")}?{urlencode({"code": code})}')


@staff_member_required
def lookup(request):
    raw = request.GET.get('code', '')
    ctx = {'code': raw}
    if raw.strip():
        code = services.normalize_code(raw)
        if code is None:
            ctx['error'] = 'Enter a 6-digit code.'
        else:
            game = services.find_by_code(code)
            if game is None:
                ctx['error'] = f'No game with code {code}.'
            else:
                ctx.update(code=code, game=game, total=len(catalog.main_set()),
                           rank=services.rank_of(game) if game.is_finished else None,
                           solve_time=services.solve_time(game))
    return render(request, 'game/staff/lookup.html', ctx)


@staff_member_required
@require_POST
def give_prize(request):
    raw = request.POST.get('code', '')
    code = services.normalize_code(raw)
    game = services.find_by_code(code) if code else None
    if game is None:
        messages.error(request, f'No game with code {code or raw.strip()}.')
        return _back(raw.strip())
    game, marked = services.mark_prize_given(game.pk)
    if marked:
        messages.success(request, f'Prize given to {game.nick}.')
    elif not game.is_finished:
        messages.error(request, 'Game still in progress — no prize yet.')
    else:
        messages.warning(request, f'Prize was already given {timesince(game.prize_given_at)} ago.')
    return _back(game.code)


def _board_context():
    return {'board': services.hall_of_fame(settings.HALL_TOP_N, settings.HALL_RECENT_N),
            'total': len(catalog.main_set())}


def _hall_context(request):
    ctx = _board_context()
    token = services.issue_start_token()
    ctx['qr_svg'] = services.qr_svg(services.start_url(request, token))
    ctx['start_code'] = f'{token[:3]} {token[3:]}'  # grouped for reading aloud; players may type it either way
    return ctx


@staff_member_required
def hall(request):
    ctx = _hall_context(request)
    ctx.update(board_url=reverse('game:staff_hall_board'), refresh_ms=settings.HALL_REFRESH_S * 1000)
    return render(request, 'game/staff/hall.html', ctx)


@never_cache
def hall_board(request):
    # Polled by hall.js: answer 403 (not a login redirect) so the script can detect an expired session.
    if not (request.user.is_active and request.user.is_staff):
        return HttpResponseForbidden('staff login required')
    return render(request, 'game/staff/_board.html', _hall_context(request))


@staff_member_required
def moderate(request):
    ctx = _board_context()
    ctx['hidden'] = services.hidden_games()
    ttl = services.gate_settings().token_ttl_s
    ctx.update(token_ttl_min=ttl // 60, token_never_expires=ttl == 0)
    return render(request, 'game/staff/moderate.html', ctx)


def _toggle(request, action, done_msg, noop_msg):
    try:
        game, changed = action(request.POST.get('game_id', ''))
    except GameSession.DoesNotExist:
        messages.error(request, 'No such game.')
    else:
        if changed:
            messages.success(request, done_msg.format(nick=game.nick))
        else:
            messages.warning(request, noop_msg.format(nick=game.nick))
    return redirect('game:staff_moderate')


@staff_member_required
@require_POST
def hide(request):
    return _toggle(request, services.hide_game, 'Hidden {nick}.', '{nick} is already hidden.')


@staff_member_required
@require_POST
def unhide(request):
    return _toggle(request, services.unhide_game, '{nick} is back on the Hall of fame.',
                   '{nick} is not hidden.')


@staff_member_required
@require_POST
def set_token_ttl(request):
    try:
        minutes = int(request.POST.get('minutes', ''))
        services.set_token_ttl(minutes * 60)
    except ValueError:
        messages.error(request, 'Enter 0 or 2–1440 minutes.')
    else:
        messages.success(request, f'QR codes now expire after {minutes} min.' if minutes
                         else 'QR codes now never expire.')
    return redirect('game:staff_moderate')
