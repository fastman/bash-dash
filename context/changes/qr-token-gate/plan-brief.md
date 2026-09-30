# QR Token Gate — Plan Brief

> Full plan: `context/changes/qr-token-gate/plan.md`

## What & Why

Only people physically at the booth should be able to start a game (FR-001, FR-017, roadmap S-06). The Hall of fame screen shows a rotating QR code whose URL carries a short-lived start token. Without a valid token, the player sees "Scan the QR code at the booth to play" instead of the start form. Staff set the token lifetime (default 15 min; 0 = never expires, the fallback if the screen dies).

## Starting Point

Anyone who opens `/` can read the rules and start a game (`game/views.py` `home`/`start`). S-05 built the staff-only Hall of fame screen. It has a 5 s polled board fragment that already handles an expired session (403) and failed polls, and it left an empty `{% block qr %}` slot for this slice. No QR library is installed, and no setting can be changed at runtime.

## Desired End State

Scanning the QR on `/staff/hall` opens the start form. Any other entry (no token, a tampered token or an old token) gets a 403 refusal page, and no game is created. Games already in progress, and resume-after-refresh, are untouched. On `/staff/moderate`, staff see the current lifetime in minutes and can change it. The change applies at once, even to codes already shown. When the lifetime is 0, the page shows a warning.

## Key Decisions Made

The skill's interactive questions were **not asked**: this ran as a background job without a question channel. For each decision below, the recommended option was taken. Override any of them before `/10x-implement`.

| Decision            | Choice                                                                          | Why (1 sentence)                                                                                                    |
| ------------------- | ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Token form          | Stateless, signed issue time (`signing.Signer`), no token table                | Nothing to store or clean up; the current TTL is applied at check time, so staff changes are retroactive.           |
| Where it's enforced | On `GET /` **and** again on `POST /start` (authoritative); token in URL + hidden field | The PRD says the token lets a player *start* within ~15 min, and the POST check can't be skipped by keeping the form open. |
| Resume              | Gate runs after the existing "you already have a game" redirect                | Refreshing `/` mid-game must never hit the gate (FR-006).                                                           |
| TTL storage         | Single DB row `GateSettings`, seeded from `BASHDASH_START_TOKEN_TTL_S=900`      | Staff (not the operator) change it at runtime; it survives restarts and the backup.                                 |
| TTL input           | Minutes on `/staff/moderate`; 0 or 2–1440                                       | 2 min minimum keeps a freshly shown code valid for at least 1 min with 60 s rotation.                               |
| Rotation            | Issue time bucketed to 60 s (`BASHDASH_START_TOKEN_ROTATE_S`)                  | The QR stays identical across 5 s polls and changes once a minute, giving players about 14 min to press Start.     |
| QR rendering        | Server-side inline SVG via `segno` (new pure-Python dependency), inside the polled board | No CDN or JS; inherits S-05's auth, 403 handling and no-flash refresh without touching `hall.js`.                  |
| QR URL host         | `BASHDASH_PUBLIC_URL` if set, else `build_absolute_uri`                         | F-02 (HTTPS proxy) isn't done; this avoids QR codes pointing at `http://` or an internal host.                     |
| Refusal UX          | 403 page with "Scan the QR code at the booth to play" (+ "expired" line)        | Matches the PRD; no start form, no links.                                                                            |

## Scope

**In scope:** token issue/check services, the `GateSettings` model and migration 0006, the gate on `home`/`start`, the refusal template, the QR on the Hall screen, the TTL form on moderation, and tests.

**Out of scope:** single-use or per-player tokens, a token-less fallback, FR-016 (second-game soft block), a countdown or URL on the public screen, staff-editable rotation, `SECRET_KEY` rotation, and proxy/HTTPS settings (F-02).

## Architecture / Approach

`services.issue_start_token()` signs `floor(now/60)*60`. The Hall board fragment (polled every 5 s) renders `PUBLIC_BASE_URL + /?t=<token>` as SVG. A player's `GET /?t=…` checks the token and renders the form with `t` hidden. `POST /start` checks it again against the current TTL in `GateSettings` and only then calls `start_game`. `bench_game` and the integration test call `start_game` directly and are unaffected.

## Phases at a Glance

| Phase                                   | What it delivers                                            | Key risk                                                                  |
| --------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------- |
| 1. Token rules and player gate          | Tokens, TTL row, 403 refusal, resume untouched; testable without a QR | Breaking resume or existing view tests (the helper must mint a token)    |
| 2. QR on screen and staff TTL control   | Scannable rotating QR on `/staff/hall`, TTL form on `/staff/moderate` | QR size or layout on the real booth screen; wrong host in the URL before F-02 |

**Prerequisites:** S-01 and S-05 done (they are); `uv add segno` needs network access.
**Estimated effort:** ~1 session, 2 phases.

## Open Risks & Assumptions

- All design decisions above are assumed defaults (no interactive Q&A happened). The biggest judgement calls are the strict POST re-check and the 60 s rotation.
- Until F-02 sets a public URL, the QR only works on the local network. `BASHDASH_PUBLIC_URL` must be set at the event.
- With TTL 0, a photo of the QR posted online lets anyone start a game. Staff can end this by setting any TTL > 0 again, because old tokens then expire.
- The token signature depends on `SECRET_KEY`. Changing it during the event invalidates the QR currently shown (the next rotation fixes it within 60 s).

## Success Criteria (Summary)

- A phone that scans the booth QR can start a game; a bare or old link gets the "scan the code" page.
- A game in progress is never interrupted by token expiry or TTL changes.
- Staff can switch to "never expires" and back from their phone, and the change takes effect immediately.
