# Correct Answer Time Bonus Session

## Goal
Add server-authoritative time after each correct answer, configurable by staff and defaulting to 15 seconds.

## Changes
- Added singleton `GameSettings` persistence and migration `0007_gamesettings`.
- Extended `GameSession.deadline_at` atomically when a correct answer advances to another challenge.
- Added `/staff/moderate` configuration with a supported range of 0–3600 seconds; 0 disables the bonus.
- Added the configured bonus to the player onboarding instructions.
- Updated `README.md` and the product requirements.
- Added tests for defaults, validation, timer behavior, concurrency, timeout reopening, UI, and staff access.

## Verification
- `manage.py test`: 252 passed, 4 skipped.
- `manage.py check`: passed.
- `manage.py makemigrations --check --dry-run`: no changes detected.
- `git diff --check`: passed.

## Notes
- Verification used an isolated temporary virtual environment because `uv` was unavailable and the Docker daemon was not running.
