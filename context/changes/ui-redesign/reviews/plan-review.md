<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Web UI Redesign Implementation Plan

- **Plan**: context/changes/ui-redesign/plan.md
- **Mode**: Deep (checked in this session; the codebase is small, so no sub-agent was used)
- **Date**: 2026-09-30
- **Verdict**: SOUND
- **Findings**: 0 critical · 3 warnings · 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | PASS |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | WARNING |
| Plan Completeness | WARNING |

## Grounding
11/11 paths ✓, 8/8 symbols ✓ (1 line ref off: play.js:100 is really :90), brief↔plan ✓

## Findings

### F1 — Pop/glow replays on every reload; the stated restart problem doesn't happen

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Blind Spots
- **Location**: Critical Implementation Details; Phase 2 §2 and §3
- **Detail**: The plan puts the `pop` and `glow` animations on `.verdict.ok`. But play.html:21 already renders `class="verdict ok"` from the server whenever the last answer was correct, so the celebration replays on every reload and every bfcache restore. The plan also gives the wrong reason for the restart trick: it says two correct answers in a row leave the class unchanged, but every submit first calls `setVerdict('Running…', 'running')` (play.js:114). The class always goes running → ok, so the animation starts again anyway.
- **Fix**: Put the animations on a class that only JS adds, e.g. `.verdict.ok.celebrate`. The helper adds `celebrate` after `setVerdict()`, with a remove, `void offsetWidth`, add sequence. `setVerdict()` already clears it on the next answer by resetting className.
  - Strength: The effect runs only on a real correct answer, and the restart logic is explicit, so it no longer depends on the `running` step coming in between.
  - Tradeoff: One more class name in CSS and JS.
  - Confidence: HIGH, based on play.html:21 and play.js:31 and :114.
  - Blind spot: None significant.
- **Decision**: FIXED (Fix in plan)

### F2 — Accent colours use oklch() with no fallback

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 1 §1 (tokens); brief "Open Risks"
- **Detail**: On a browser without oklch(), `background: var(--pink)` fails and the background becomes transparent. Primary buttons would then show ink #0f0e14 text on the #0f0e14 page background, so the Start, Run and Continue buttons can't be seen. Players bring their own phones, so you can't check this ahead of time. The brief only says to react "if not supported".
- **Fix**: Convert the six accent tokens to hex once, in Phase 1. If you want the oklch versions, add them inside `@supports (color: oklch(0 0 0))`.
- **Decision**: FIXED (Fix in plan)

### F3 — Progress titles reword the criteria instead of copying them

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: ## Progress (manual rows 2.3–2.10, 3.2, 4.2–4.4, 5.3)
- **Detail**: The counts and numbering match the criteria 1:1, but the Progress titles are shortened or reworded. For example, 2.4 reads "Verdict states (running, wrong, warn, correct) render correctly", while the phase body says "Wrong answer shows red '✗ …'; …". If /10x-implement matches rows by title, these won't match.
- **Fix**: Copy each Manual Verification bullet word for word into its Progress row.
- **Decision**: FIXED (Fix in plan)

### F4 — The test assertion rewrites are too loose or not written down

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 3 §3 and Phase 5 §1
- **Detail**: The suggested pattern `Attempts\s*</span>.*?<strong>3</strong>` with DOTALL would match any `<strong>3</strong>` further down the page. The replacement for test_staff_views.py:87 isn't written down at all.
- **Fix**: Anchor both assertions to the markup: `Attempts</span>\s*<span class="leader"></span>\s*<strong>3</strong>` and `Solve time</span>\s*<span class="leader"></span>\s*<strong>—</strong>`.
- **Decision**: FIXED (Fix in plan)

### F5 — The cursor overlay can catch taps and is read by screen readers

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 2 §1 (cursor overlay)
- **Detail**: The overlay sits right where a player taps to focus the input. The plan doesn't say it should let taps through or be hidden from screen readers. It also doesn't say which element it is positioned against.
- **Fix**: Give the overlay `pointer-events: none` and `aria-hidden="true"`, and position it absolutely inside the bordered command box, which gets `position: relative`.
- **Decision**: FIXED (Fix in plan)

### F6 — Small factual errors in the plan

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 4 criteria and contract; Key Discoveries
- **Detail**: Phase 4 expects "about 6 recent rows", but HALL_RECENT_N defaults to 5 (config/settings.py:162). "Lift the 110rem cap for 1600px" is already done, since 110rem is 1760px. The index comparison is at play.js:90, not :100.
- **Fix**: Change "6" to "5 (HALL_RECENT_N)", remove the cap note, and correct the line reference.
- **Decision**: FIXED (Fix in plan)
