---
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
---

## Why this stack

bash-dash is a one-week, solo build for a single hackathon day (2026-10-03), so the stack must be battle-tested and batteries-included. Django is the recommended default for a Python web app, and the author already chose Python over Go. Its admin gives booth staff password login, lookup by 6-digit code, nick hiding and "prize given" for free, which covers FR-011 to FR-013 without custom UI. Player pages are Django templates plus a little JS, and the leaderboard refreshes by polling, so no realtime layer is needed. Deployment is self-host on one dedicated VM because the app drives the hardened cmdchallenge sandbox containers through docker.sock, which rules out managed platforms like Fly, Railway and Render. SQLite with an off-VM backup every few minutes meets the durability NFR. The backup is a host-level cron job, not an in-app job queue. CI runs checks on GitHub Actions, and deploys are promoted manually so a mid-event merge cannot disrupt live games. Scaffolding confidence for Django is verified.
