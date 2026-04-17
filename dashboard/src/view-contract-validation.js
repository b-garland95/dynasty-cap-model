// Contract Schedule Validation view controller

(function () {
  let _initialized = false;
  let _queue = [];
  let _validated = [];

  // ── Helpers ───────────────────────────────────────────────────────────────

  function fmt$(v) {
    if (v == null || isNaN(v)) return '–';
    return '$' + Number(v).toFixed(1);
  }

  function showStatus(el, message, isError) {
    if (!el) return;
    el.textContent = message;
    el.className = 'save-status ' + (isError ? 'save-status-error' : 'save-status-ok');
    el.hidden = false;
    setTimeout(function () { el.hidden = true; }, isError ? 8000 : 3000);
  }

  function posClass(pos) {
    var p = (pos || '').toUpperCase();
    if (p === 'QB') return 'pos-qb';
    if (p === 'RB') return 'pos-rb';
    if (p === 'WR') return 'pos-wr';
    if (p === 'TE') return 'pos-te';
    return '';
  }

  // ── Render ────────────────────────────────────────────────────────────────

  function renderQueue() {
    var pendingSection = document.getElementById('cv-pending-section');
    var list = document.getElementById('cv-pending-list');
    var badge = document.getElementById('cv-queue-count');

    if (!list) return;

    if (_queue.length === 0) {
      list.innerHTML = '<p class="cv-empty-state">No players currently require schedule validation.</p>';
    } else {
      list.innerHTML = _queue.map(function (p, idx) {
        return renderPlayerCard(p, idx, false);
      }).join('');
      wirePlayerCards(list, false);
    }

    if (pendingSection) pendingSection.hidden = false;
    if (badge) {
      badge.textContent = _queue.length + ' pending';
      badge.hidden = false;
    }
  }

  function renderValidated() {
    var validatedSection = document.getElementById('cv-validated-section');
    var list = document.getElementById('cv-validated-list');
    var countInline = document.getElementById('cv-validated-count-inline');
    var badge = document.getElementById('cv-validated-count');

    if (!list) return;

    if (_validated.length === 0) {
      list.innerHTML = '<p class="cv-empty-state">No players have been validated yet.</p>';
    } else {
      list.innerHTML = _validated.map(function (p, idx) {
        return renderPlayerCard(p, idx, true);
      }).join('');
      wirePlayerCards(list, true);
    }

    if (validatedSection) validatedSection.hidden = false;
    if (countInline) countInline.textContent = '(' + _validated.length + ')';
    if (badge) {
      badge.textContent = _validated.length + ' validated';
      badge.hidden = false;
    }
  }

  function renderPlayerCard(player, idx, isValidated) {
    var pos = player.position || (isValidated ? '' : '');
    var formId = 'cv-form-' + (isValidated ? 'v' : 'p') + idx;
    var statusLabel = isValidated
      ? '<span class="cv-status cv-status-validated">Validated ' +
        (player.validated_at ? new Date(player.validated_at).toLocaleDateString() : '') + '</span>'
      : '<span class="cv-status cv-status-pending">Pending Review</span>';

    var scheduleHtml = renderScheduleTable(player.schedule, formId, isValidated);

    return '<div class="cv-player-card" id="cv-card-' + formId + '">' +
      '<div class="cv-player-card-header">' +
        '<span class="cv-player-name">' + escHtml(player.player) + '</span>' +
        '<span class="cv-player-meta">' +
          '<span class="cv-pos-badge ' + posClass(pos) + '">' + escHtml(pos) + '</span>' +
          '<span class="cv-team-name">' + escHtml(player.team) + '</span>' +
        '</span>' +
        statusLabel +
        (isValidated ? '' : '<button class="cv-edit-toggle action-btn action-btn-secondary" data-form="' + formId + '">Edit</button>') +
      '</div>' +
      '<div class="cv-schedule-wrapper" id="cv-wrapper-' + formId + '" ' + (isValidated ? '' : 'hidden') + '>' +
        scheduleHtml +
        (isValidated ? '' :
          '<div class="cv-form-actions">' +
            '<button class="cv-save-btn action-btn action-btn-primary" data-form="' + formId + '" ' +
              'data-player="' + escAttr(player.player) + '" ' +
              'data-team="' + escAttr(player.team) + '" ' +
              'data-pos="' + escAttr(pos) + '">Save & Validate</button>' +
            '<span class="cv-save-status save-status" hidden></span>' +
          '</div>'
        ) +
      '</div>' +
    '</div>';
  }

  function renderScheduleTable(schedule, formId, readOnly) {
    if (!schedule || schedule.length === 0) {
      return '<p class="cv-empty-state">No schedule rows.</p>';
    }

    var rows = schedule.map(function (row) {
      var yr = row.year_index;
      var realVal = row.cap_hit_real != null ? row.cap_hit_real : '';
      var currentDisplay = row.cap_hit_current != null ? fmt$(row.cap_hit_current) : '–';
      var srcDisplay = row.schedule_source || '–';
      var realCell = readOnly
        ? '<td class="num mono">' + fmt$(row.cap_hit_real) + '</td>'
        : '<td class="num"><input type="number" class="cv-cap-input config-input" ' +
            'data-form="' + formId + '" data-yr="' + yr + '" ' +
            'min="0" step="0.5" value="' + realVal + '" /></td>';

      return '<tr>' +
        '<td class="num mono">Y' + yr + '</td>' +
        realCell +
        '<td class="num mono">' + currentDisplay + '</td>' +
        '<td class="cv-src-cell">' + escHtml(srcDisplay) + '</td>' +
        '</tr>';
    }).join('');

    return '<div class="table-wrapper cv-schedule-table">' +
      '<table class="data-table">' +
        '<thead><tr>' +
          '<th>Year</th>' +
          '<th class="num">Cap Hit (Real)</th>' +
          '<th class="num">Cap Hit (Current)</th>' +
          '<th>Source</th>' +
        '</tr></thead>' +
        '<tbody>' + rows + '</tbody>' +
      '</table>' +
    '</div>';
  }

  // ── Wire interactive elements ─────────────────────────────────────────────

  function wirePlayerCards(container, isValidated) {
    if (isValidated) return;

    // Toggle edit/collapse
    container.querySelectorAll('.cv-edit-toggle').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var formId = btn.dataset.form;
        var wrapper = document.getElementById('cv-wrapper-' + formId);
        if (!wrapper) return;
        var hidden = wrapper.hidden;
        wrapper.hidden = !hidden;
        btn.textContent = hidden ? 'Collapse' : 'Edit';
      });
    });

    // Save & Validate
    container.querySelectorAll('.cv-save-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var formId = btn.dataset.form;
        var player = btn.dataset.player;
        var team = btn.dataset.team;
        var position = btn.dataset.pos;
        var statusEl = btn.nextElementSibling;
        saveValidation(btn, formId, player, team, position, statusEl);
      });
    });
  }

  // ── Save logic ────────────────────────────────────────────────────────────

  function gatherScheduleRows(formId) {
    var inputs = document.querySelectorAll('.cv-cap-input[data-form="' + formId + '"]');
    var rows = [];
    inputs.forEach(function (inp) {
      var yr = parseInt(inp.dataset.yr, 10);
      var val = parseFloat(inp.value);
      if (isNaN(yr) || isNaN(val)) return;
      rows.push({ year_index: yr, cap_hit_real: val, schedule_source: 'manual_override' });
    });
    return rows;
  }

  function saveValidation(btn, formId, player, team, position, statusEl) {
    var rows = gatherScheduleRows(formId);
    if (rows.length === 0) {
      showStatus(statusEl, 'No schedule rows to save', true);
      return;
    }

    btn.disabled = true;
    showStatus(statusEl, 'Saving…', false);

    fetch('/api/contract-validation/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ player: player, team: team, position: position, schedule: rows }),
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        btn.disabled = false;
        if (res.ok) {
          showStatus(statusEl, 'Saved and validated', false);
          // Reload queue after short delay to let user see confirmation
          setTimeout(function () { loadQueue(); }, 1200);
        } else {
          showStatus(statusEl, 'Error: ' + res.error, true);
        }
      })
      .catch(function (err) {
        btn.disabled = false;
        showStatus(statusEl, 'Network error: ' + err.message, true);
      });
  }

  // ── Data loading ──────────────────────────────────────────────────────────

  function loadQueue() {
    var loadingEl = document.getElementById('cv-loading');
    var errorEl = document.getElementById('cv-error');
    var pendingSection = document.getElementById('cv-pending-section');
    var validatedSection = document.getElementById('cv-validated-section');

    if (loadingEl) { loadingEl.hidden = false; loadingEl.textContent = 'Loading validation queue…'; }
    if (errorEl) errorEl.hidden = true;
    if (pendingSection) pendingSection.hidden = true;
    if (validatedSection) validatedSection.hidden = true;

    var queuePromise = fetch('/api/contract-validation/queue')
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.error || 'Queue fetch failed');
        _queue = res.queue || [];
      });

    var validatedPromise = fetch('/api/contract-validation/validated')
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (!res.ok) throw new Error(res.error || 'Validated fetch failed');
        _validated = res.validated || [];
      });

    Promise.all([queuePromise, validatedPromise])
      .then(function () {
        if (loadingEl) loadingEl.hidden = true;
        renderQueue();
        renderValidated();
      })
      .catch(function (err) {
        if (loadingEl) loadingEl.hidden = true;
        if (errorEl) {
          errorEl.textContent = 'Failed to load validation data: ' + err.message +
            '. Make sure the server is running (python dashboard/server.py) and a roster has been uploaded.';
          errorEl.hidden = false;
        }
      });
  }

  // ── Escape helpers ────────────────────────────────────────────────────────

  function escHtml(str) {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function escAttr(str) {
    return String(str || '').replace(/"/g, '&quot;');
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  function initContractValidation() {
    if (!_initialized) {
      _initialized = true;
      var refreshBtn = document.getElementById('cv-refresh-btn');
      if (refreshBtn) {
        refreshBtn.addEventListener('click', function () { loadQueue(); });
      }
    }
    loadQueue();
  }

  window.initContractValidation = initContractValidation;
})();
