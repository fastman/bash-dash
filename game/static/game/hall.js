(function () {
  'use strict';
  var board = document.getElementById('board');
  var badge = document.getElementById('hall-status');
  if (!board || !badge) return;
  var url = board.dataset.boardUrl;
  var delay = parseInt(board.dataset.refreshMs, 10) || 5000;

  function status(text, cls) {
    badge.hidden = !text;
    badge.textContent = text || '';
    badge.className = 'hall-status' + (cls ? ' ' + cls : '');
  }

  function tick() {
    fetch(url, {cache: 'no-store', credentials: 'same-origin'})
      .then(function (resp) {
        if (resp.status === 403 || resp.redirected) {
          status('Session expired \u2014 log in again', 'bad');
          return null;
        }
        if (!resp.ok) throw new Error('status ' + resp.status);
        return resp.text().then(function (html) {
          board.innerHTML = html;
          status('');
        });
      })
      .catch(function () { status('Reconnecting\u2026', 'warn'); })
      .then(function () { setTimeout(tick, delay); });
  }

  setTimeout(tick, delay);
})();
