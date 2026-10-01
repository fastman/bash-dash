# Handoff: Camlin logo + link (small addition)

Add the Camlin Group logo and a readable, clickable link to https://camlingroup.com/ on player-facing screens. Everything else stays as is. Reference: `bash-dash Screens.dc.html` (screens 01–05).

## Asset
Copy `assets/camlin-logo.png` → `game/static/game/camlin-logo.png` (720×240, transparent, white wordmark for dark bg). The image already contains the company name — don't add "Camlin" text next to it. `alt="Camlin Group"`.

## Player screens (gate, home, play, done)
In `base.html`, after `{% block content %}{% endblock %}` inside `<main>`:
```django
{% block sponsor %}<a class="sponsor" href="https://camlingroup.com/" target="_blank" rel="noopener">
  <img src="{% static 'game/camlin-logo.png' %}" alt="Camlin Group" width="66" height="22">
  <span>camlingroup.com</span>
</a>{% endblock %}
```
Staff pages `staff/lookup.html` and `staff/moderate.html`: override with an empty `{% block sponsor %}{% endblock %}`.

CSS (`game.css`):
```css
main:not(.hall) { min-height: 100dvh; display: flex; flex-direction: column; }
.sponsor { margin-top: auto; padding-top: 16px; border-top: 1px solid var(--border-soft);
  display: flex; align-items: center; justify-content: center; gap: 12px; font-size: 13px; text-decoration: none; }
.sponsor img { height: 22px; width: auto; display: block; }
.sponsor span { color: var(--cyan); text-decoration: underline; text-underline-offset: 3px; }
```
Footer sits at the bottom of the viewport on short pages and below content on long ones (add `.sponsor { margin-top: auto; }` plus `main:not(.hall) > .sponsor { padding-top: 16px; }` keeps spacing).

If the flex `main` change affects existing layouts, drop the first rule and just give `.sponsor { margin-top: 32px; }`.

## Hall of fame (`staff/hall.html`)
Override `{% block sponsor %}{% endblock %}` (empty). Header: left column = ASCII logo with the tagline ("5 minutes · bash only ·" + cursor) moved **below** it; right = larger Camlin logo with URL under it.
```django
<header class="hall-header">
  <div class="hall-brand">
    {% include 'game/_logo.html' %}
    <p class="hall-tagline">…existing…</p>
  </div>
  <a class="hall-sponsor" href="https://camlingroup.com/" target="_blank" rel="noopener">
    <img src="{% static 'game/camlin-logo.png' %}" alt="Camlin Group" width="264" height="88">
    <span>camlingroup.com</span>
  </a>
</header>
```
```css
.hall-header { align-items: flex-start; }   /* was flex-end */
.hall-brand { display: flex; flex-direction: column; gap: 14px; }
.hall-sponsor { display: flex; flex-direction: column; align-items: flex-end; gap: 12px; text-decoration: none; }
.hall-sponsor img { height: 88px; width: auto; display: block; }
.hall-sponsor span { font-size: 22px; color: var(--cyan); }
@media (max-width: 900px) { .hall-sponsor { align-items: flex-start; } .hall-sponsor img { height: 48px; } }
```
The board moves down ~40px; if rows overflow 900px, reduce `.hall-header` margin-bottom from 32px to 24px.

## Don't change
Logic, ids, JS, tests. Existing tests checking page HTML should still pass; run them.

## Claude Code prompt
> Read `context/changes/branding/design_handoff_bash_dash_ui/CAMLIN_LOGO.md` and apply it: copy the logo to static, add the sponsor footer to base.html (hidden on staff pages) and the logo+link to the hall header. Only template/CSS changes; run the tests.
