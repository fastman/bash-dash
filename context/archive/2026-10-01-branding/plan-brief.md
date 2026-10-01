# Camlin Branding (Sponsor Logo + Link) — Plan Brief

> Full plan: `context/changes/branding/plan.md`
> Design handoff: `context/changes/branding/design_handoff_bash_dash_ui/CAMLIN_LOGO.md`

## What & Why

Add the Camlin Group logo and a clickable `camlingroup.com` link to bash-dash, following the Claude Design handoff. Players see a small sponsor footer on gate, home, play and done. The hall-of-fame booth screen shows a large logo + URL in its header. Staff pages stay unbranded.

## Starting Point

The terminal-style redesign from the same handoff already shipped in the archived `ui-redesign` change. A diff of the two handoff folders shows the only new material is the Camlin logo (`CAMLIN_LOGO.md`, the PNG, and the sponsor markup in mockup screens 01–05). An existing test (`NoAnswerLinksTests`) currently forbids **any** external link on player pages.

## Desired End State

Every player screen ends with a centred logo plus an underlined cyan `camlingroup.com` link, pinned to the viewport bottom on short pages. Existing spacing is unchanged. The booth screen has the 88px logo top-right, with the tagline moved under the ASCII logo, and the full board (10 top + 5 recent) still fits 1600×900. Tests guard all of this.

## Key Decisions Made

These were made autonomously (background run, no live Q&A) using the recommended option. Each is easy to revisit.

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Scope | Only `CAMLIN_LOGO.md`; no redesign re-apply | The README redesign is already live; the handoff diff is only the logo. | Research |
| External-link guard | Narrow to an allowlist of `camlingroup.com`; any other host still fails | The PRD bans links *to answers*, not a sponsor link; deleting the guard would lose real protection. | Plan |
| Footer layout | Flex `main` + one block-flow wrapper around header/content | The handoff's bare flex `main` breaks margin collapsing (+16px on home); a wrapper keeps every gap identical. | Plan (handoff allows deviation) |
| Hall 1600×900 fit | Padding 44→32, header gap 32→24, row padding 7→5px | Measured in headless Chrome: today 889px, handoff as written 936px (overflow), handoff fallback 928px, chosen 874px. | Plan (measured) |
| Staff pages | Empty `sponsor` block on lookup, moderate, hall | Matches the handoff; the hall gets its own large header logo. | Handoff |
| Image | Ship the 49 KB PNG as-is | One browser-cached request per player; optimising is out of scope. | Plan |

## Scope

**In scope:**
- `game/static/game/camlin-logo.png` (copy of the handoff asset)
- `base.html` sponsor block + layout wrapper; empty overrides in the 3 staff templates
- Hall header restructure + large logo
- `game.css` additions and hall spacing tweaks
- Test updates: narrowed external-link guard, footer presence/absence, hall logo, static finder

**Out of scope:**
- Re-applying the redesign; logic, ids, `play.js`/`hall.js`
- Image re-encoding, logo on staff/admin pages, extra copy/CTAs
- Visual-regression tooling

## Architecture / Approach

`base.html` gains a `{% block sponsor %}` after a wrapper `div` that holds the existing header + content blocks. `main:not(.hall)` becomes a min-100dvh flex column, so the footer's `margin-top: auto` pins it to the bottom. Staff templates blank the block. `hall.html` overrides its header with a brand column (logo + tagline) and a sponsor column (logo + URL).

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Player sponsor footer | Asset, footer on 4 player screens, hidden on staff, guard narrowed, new tests | Layout shift if header/content are not wrapped |
| 2. Hall header branding | Large logo + URL on the booth screen, board still fits 1600×900 | Vertical overflow, so the values come from measurement |

**Prerequisites:** none (baseline `manage.py test game`: 174 tests OK on 2026-10-01).
**Estimated effort:** ~1 short session, 2 phases.

## Open Risks & Assumptions

- Assumes the sponsor link does not violate the PRD non-goals ("no links to answers", "no recruiting CTA"). It is a plain logo link with no recruiting copy.
- Hall fit assumes a fullscreen/kiosk browser at 1600×900. A windowed browser loses ~80–100px to browser UI and would scroll, same as today.
- The `100dvh` footer pinning relies on modern mobile browsers; there is a `100vh` fallback.

## Success Criteria (Summary)

- A player sees the Camlin logo + working link at the bottom of every player screen, with no other visual change.
- The booth screen shows the large Camlin logo and still displays the whole board without scrolling.
- `uv run python manage.py test` is green, and the guard still rejects any non-Camlin external link.
