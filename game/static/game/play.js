// Post commands to /play/command and render the JSON result without a page reload.
// The page itself is fully server-rendered, so a reload always shows the true state.
(function () {
  'use strict';

  var FETCH_TIMEOUT_MS = 25000; // server worst case ~17 s (queue 10 s + run 6 s)

  var form = document.getElementById('command-form');
  var input = document.getElementById('command');
  var button = document.getElementById('submit');
  var verdict = document.getElementById('verdict');
  var lastCommand = document.getElementById('last-command');
  var output = document.getElementById('output');
  var attempts = document.getElementById('attempts');
  var solved = document.getElementById('solved');
  var index = document.getElementById('challenge-index');
  var title = document.getElementById('challenge-title');
  var description = document.getElementById('challenge-description');
  var timer = document.getElementById('timer');
  var busy = false;
  var locked = false; // time is up: separate from busy so an in-flight response can't re-enable input
  var deadline = performance.now() + Number(timer.dataset.remainingMs); // monotonic, never Date.now()

  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function setVerdict(text, cls) {
    verdict.textContent = text;
    verdict.className = 'verdict' + (cls ? ' ' + cls : '');
  }

  var flashTimer = null;
  function celebrate() {
    verdict.classList.remove('celebrate');
    void verdict.offsetWidth; // force reflow so the animation restarts
    verdict.classList.add('celebrate');
    form.classList.add('flash');
    document.getElementById('counters').classList.add('flash');
    clearTimeout(flashTimer);
    flashTimer = setTimeout(function () {
      form.classList.remove('flash');
      document.getElementById('counters').classList.remove('flash');
    }, 1100);
  }

  function setBusy(on) {
    busy = on;
    input.disabled = on || locked;
    button.disabled = on || locked;
  }

  function formatClock(ms) {
    var s = Math.ceil(Math.max(0, ms) / 1000);
    return Math.floor(s / 60) + ':' + ('0' + (s % 60)).slice(-2);
  }

  function goDone() { window.location.href = form.dataset.doneUrl; }

  function setRemaining(ms) { deadline = performance.now() + ms; tick(); }

  function tick() {
    var left = deadline - performance.now();
    timer.textContent = formatClock(left);
    timer.classList.toggle('low', left <= 30000);
    if (left <= 0 && !locked) {
      locked = true;
      input.disabled = true;
      button.disabled = true;
      setVerdict("Time's up.", 'warn');
      // absorb client/server skew; an in-flight request navigates via its own response
      setTimeout(function () { if (!busy) goDone(); }, 1000);
    }
  }

  function resync() {
    fetch(form.dataset.stateUrl, {credentials: 'same-origin'})
      .then(function (resp) { return resp.json(); })
      .then(function (data) {
        if (data.finished) { goDone(); return; }
        if (typeof data.remaining_ms === 'number') setRemaining(data.remaining_ms);
      })
      .catch(function () { /* keep the current timer: the server enforces the limit regardless */ });
  }

  setInterval(tick, 250);
  tick();
  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') resync();
  });
  window.addEventListener('pageshow', function (ev) { if (ev.persisted) resync(); });

  function render(data, command) {
    if (typeof data.attempts === 'number') attempts.textContent = data.attempts;
    if (typeof data.solved === 'number') solved.textContent = data.solved;
    if (typeof data.remaining_ms === 'number') setRemaining(data.remaining_ms);
    if (data.status === 'ran') {
      lastCommand.textContent = '$ ' + command;
      output.textContent = data.result.output; // textContent only: output is untrusted
      output.scrollTop = 0;
      setVerdict(data.result.message, data.result.correct ? 'ok' : 'bad');
      if (data.result.correct) celebrate();
      var ch = data.challenge;
      if (ch && index.textContent !== ch.index + ' / ' + ch.total) {
        index.textContent = ch.index + ' / ' + ch.total;
        title.textContent = ch.title;
        description.innerHTML = ch.description_html; // server-escaped by render_description
        input.value = '';
      } else if (data.result.correct) {
        input.value = '';
      }
    } else {
      // Not counted: keep the command in the input so the player can retry.
      setVerdict(data.message || 'Something went wrong, try again.', 'warn');
    }
    if (data.finished) goDone();
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    if (busy || locked) return;
    var command = input.value;
    if (!command.trim()) {
      setVerdict('Type a command first.', 'warn');
      return;
    }
    setBusy(true);
    setVerdict('Running…', 'running');
    var ctrl = new AbortController();
    var fetchTimer = setTimeout(function () { ctrl.abort(); }, FETCH_TIMEOUT_MS);
    fetch(form.dataset.url, {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrfToken()},
      body: JSON.stringify({command: command}),
      credentials: 'same-origin',
      signal: ctrl.signal
    })
      .then(function (resp) {
        return resp.json().catch(function () {
          return {status: 'error', message: 'Server error (' + resp.status + '), try again.'};
        });
      })
      .then(function (data) { render(data, command); })
      .catch(function (err) {
        if (locked) { goDone(); return; }
        setVerdict(err && err.name === 'AbortError'
          ? 'No answer from the server, try again.'
          : 'Network error, try again.', 'warn');
      })
      .then(function () {
        clearTimeout(fetchTimer);
        setBusy(false);
        input.focus();
        // The 0:00 check skipped goDone while this request was busy. If the response didn't
        // carry finished: true, don't leave the player stuck: /done sends unfinished games back to /play.
        if (locked) setTimeout(goDone, 1000);
      });
  });
})();
