---
bootstrapped_at: 2026-09-29T12:10:24Z
starter_id: django
starter_name: Django
project_name: bash-dash
language_family: python
package_manager: uv
cwd_strategy: native-cwd
bootstrapper_confidence: verified
phase_3_status: ok
audit_command: pip-audit
---

## Hand-off

```yaml
starter_id: django
package_manager: uv
project_name: bash-dash
hints:
  language_family: python
  team_size: solo
  deployment_target: self-host
  ci_provider: github-actions
  ci_default_flow: manual-promotion
  bootstrapper_confidence: verified
  path_taken: standard
  quality_override: false
  self_check_answers: null
  has_auth: true
  has_payments: false
  has_realtime: false
  has_ai: false
  has_background_jobs: false
```

### Why this stack

bash-dash is a one-week, solo build for a single hackathon day (2026-10-03), so the stack must be battle-tested and batteries-included. Django is the recommended default for a Python web app, and the author already chose Python over Go. Its admin gives booth staff password login, lookup by 6-digit code, nick hiding and "prize given" for free, which covers FR-011 to FR-013 without custom UI. Player pages are Django templates plus a little JS, and the leaderboard refreshes by polling, so no realtime layer is needed. Deployment is self-host on one dedicated VM because the app drives the hardened cmdchallenge sandbox containers through docker.sock, which rules out managed platforms like Fly, Railway and Render. SQLite with an off-VM backup every few minutes meets the durability NFR. The backup is a host-level cron job, not an in-app job queue. CI runs checks on GitHub Actions, and deploys are promoted manually so a mid-event merge cannot disrupt live games. Scaffolding confidence for Django is verified.

## Pre-scaffold verification

| Signal         | Value                                  | Severity | Notes                                                        |
| -------------- | -------------------------------------- | -------- | ------------------------------------------------------------ |
| npm package    | not run                                | —        | non-JS starter                                               |
| GitHub repo    | not run                                | —        | card `docs_url` (https://docs.djangoproject.com) is not GitHub |
| PyPI package   | django v6.1.1 published 2026-09-02     | fresh    | substitute signal from pypi.org JSON API                     |

## Scaffold log

**Registry template**: `django-admin startproject {name} .`
**Resolved invocation**: `uv init --bare --name bash-dash && uv add django && uv run django-admin startproject config .`
**Strategy**: native-cwd
**Exit code**: 0
**Pre-flight files-to-touch**: pyproject.toml, uv.lock, .venv/, manage.py, config/{__init__,settings,urls,asgi,wsgi}.py
**Files written by CLI**: 7 (plus `.venv/`)
**Pre-existing files preserved**: context/ (untouched), .git/ (untouched)

Deviations from the registry template (confirmed with the user):

- Native-cwd substitution `{name}=.` yields `django-admin startproject . .`, which Django rejects (project name must be a Python identifier). `project_name` `bash-dash` is also not a valid identifier. The settings package was named `config` per the user's choice.
- `django-admin` was not installed; the card's `pre` step (`pip install django`) was replaced with `uv init --bare` + `uv add django` to honor `package_manager: uv`.

Resolved versions: Django 6.1.1, asgiref 3.12.1, sqlparse 0.6.0, CPython 3.13.7 (`requires-python >=3.13`).
Sanity check: `uv run python manage.py check` → "System check identified no issues (0 silenced)."

Note: no `.gitignore` was created (uv `--bare` and `startproject` do not write one). `.venv/` self-ignores via `.venv/.gitignore`, but `__pycache__/` and `db.sqlite3` are not yet ignored.

## Post-scaffold audit

**Tool**: pip-audit (run as `uvx pip-audit -r <uv export requirements> --format json`; pip-audit not installed globally)
**Summary**: 0 CRITICAL, 0 HIGH, 0 MODERATE, 0 LOW
**Direct vs transitive**: not distinguished by this tool (direct: django; transitive: asgiref, sqlparse)

Audited: asgiref 3.12.1, django 6.1.1, sqlparse 0.6.0 — no known vulnerabilities.

## Hints recorded but not acted on

| Hint                    | Value            |
| ----------------------- | ---------------- |
| bootstrapper_confidence | verified         |
| quality_override        | false            |
| path_taken              | standard         |
| self_check_answers      | null             |
| team_size               | solo             |
| deployment_target       | self-host        |
| ci_provider             | github-actions   |
| ci_default_flow         | manual-promotion |
| has_auth                | true             |
| has_payments            | false            |
| has_realtime            | false            |
| has_ai                  | false            |
| has_background_jobs     | false            |

## Next steps

Next: a future skill will set up agent context (CLAUDE.md, AGENTS.md). For now, your project is scaffolded and verified — happy hacking.

Useful manual steps in the meantime:
- Add a `.gitignore` (at least `__pycache__/`, `*.pyc`, `db.sqlite3`, `.venv/`) before the first commit.
- Review any `.scaffold` siblings the conflict policy created and decide which version of each file to keep (none this run).
- Address audit findings per your project's risk tolerance — the full breakdown is in this log (none this run).
