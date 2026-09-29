"""Staff-facing pages (prize desk). Every view requires a staff login."""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.utils.timesince import timesince
from django.views.decorators.http import require_POST

from challenges import catalog

from . import services


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
