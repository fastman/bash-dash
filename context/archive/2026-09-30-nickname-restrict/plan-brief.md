# Restrict Allowed Nicknames — Plan Brief

> Full plan: `context/changes/nickname-restrict/plan.md`

## What & Why

A nick may contain only ASCII letters, digits and `_`, and be at most 12 characters long. The server checks this. Nicks appear on the public Hall of fame screen at the booth. The rule limits what a troll can put there and keeps nicks short enough to show in full in the ranking rows.

## Starting Point

`services.start_game` is the only way a game is created. Today it checks only the length (1-20 characters after stripping), so any characters are accepted. The start form has `maxlength="20"` and no hint. Two existing callers use nicks that the new rule will refuse: the bench command (`bench-<i>`) and one staff escaping test (`<b>x</b>`).

## Desired End State

A nick that does not match `[A-Za-z0-9_]{1,12}` (after trimming surrounding whitespace) is refused, and no game is created. The start form shows "Use 1-12 letters, digits or _ (no spaces).", keeps the typed nick and the QR token, and lets the player retry without rescanning. The form states the rule up front, and the browser checks it before submitting. Existing nicks in the DB are left as they are.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) |
| --- | --- | --- |
| Where the rule lives | Only `services.start_game` (plus a `NICK_RE` constant) | It is the single place games are created; the views, the bench and the tests all go through it. |
| Surrounding whitespace | Strip, then validate | Phone keyboards add trailing spaces; spaces inside the nick are still refused. |
| Letter set | ASCII only, explicit `[A-Za-z0-9_]` with `fullmatch` | `\w` / `isalnum()` would let Unicode letters and digits through. |
| Invalid input | Refuse, never auto-fix | Silently changing a nick would surprise the player at prize pickup. |
| DB schema / old rows | No migration; `max_length=20` and old nicks stay | SQLite does not enforce the length anyway, and hiding a nick still covers moderation. |
| Browser check | `maxlength`, `pattern`, `title` + visible hint; no JS | Catches most mistakes before the POST; the server stays authoritative. |
| Escaping test | Store the HTML nick directly via `update()` | Escaping still matters for old rows and admin edits. |

## Scope

**In scope:** server rule and error text; bench nick prefix `bench_`; test updates and new rule tests; start form hint, `maxlength` and `pattern`; one CSS rule for the hint.

**Out of scope:** profanity filter; unique nicks; migration or model change; checks in the admin form; non-ASCII letters; auto-sanitising nicks.

## Architecture / Approach

`home.html` form → `POST /start` → `views.start` → `services.start_game(nick)` → `NICK_RE.fullmatch(stripped)`. If there is no match, it raises `ValueError`, and the view re-renders the form with the error, the typed nick and the token. The template attributes mirror the same regex for the browser check only.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Server-side nick rule | Rule enforced; error copy; bench and tests fixed; new rule tests | Missing a caller that uses a now-invalid nick (checked: only the bench and one staff test) |
| 2. Start form hint and browser check | Visible rule, `maxlength=12`, `pattern`, hint styling | Template 12 drifting from `NICK_MAX_CHARS` (a test guards it) |

**Prerequisites:** none. The baseline suite is green (231 tests).
**Estimated effort:** ~1 short session, 2 phases.

## Open Risks & Assumptions

- This plan came from a non-interactive run. Whitespace trimming, ASCII-only letters, keeping old rows unchanged and the error wording are the recommended defaults, not answers the user confirmed. Revisit before implementing if any of them is wrong.
- `pattern` checks the raw value, so a trailing space from autocomplete is blocked in the browser even though the server would trim it. The hint makes the rule clear. This is judged acceptable.

## Success Criteria (Summary)

- `neo_42` starts a game; `ab cd`, `zażółć`, `abc-def` and 13-character nicks are refused by the server with a clear message, and the player can retry without rescanning.
- The Hall of fame shows new nicks in full, and old nicks still render escaped.
- `uv run python manage.py test game challenges` is green.
