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
  var busy = false;

  function csrfToken() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
  }

  function setVerdict(text, cls) {
    verdict.textContent = text;
    verdict.className = 'verdict' + (cls ? ' ' + cls : '');
  }

  function setBusy(on) {
    busy = on;
    input.disabled = on;
    button.disabled = on;
  }

  function render(data, command) {
    if (typeof data.attempts === 'number') attempts.textContent = data.attempts;
    if (typeof data.solved === 'number') solved.textContent = data.solved;
    if (data.status === 'ran') {
      lastCommand.textContent = '$ ' + command;
      output.textContent = data.result.output; // textContent only: output is untrusted
      output.scrollTop = 0;
      setVerdict(data.result.message, data.result.correct ? 'ok' : 'bad');
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
    if (data.finished) {
      window.location.href = form.dataset.doneUrl;
    }
  }

  form.addEventListener('submit', function (ev) {
    ev.preventDefault();
    if (busy) return;
    var command = input.value;
    if (!command.trim()) {
      setVerdict('Type a command first.', 'warn');
      return;
    }
    setBusy(true);
    setVerdict('Running…', 'running');
    var ctrl = new AbortController();
    var timer = setTimeout(function () { ctrl.abort(); }, FETCH_TIMEOUT_MS);
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
        setVerdict(err && err.name === 'AbortError'
          ? 'No answer from the server, try again.'
          : 'Network error, try again.', 'warn');
      })
      .then(function () {
        clearTimeout(timer);
        setBusy(false);
        input.focus();
      });
  });
})();
