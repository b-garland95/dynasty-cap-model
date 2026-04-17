// League Config — League Settings view controller
// Manages config editing, team cap adjustments, roster upload, and recompute.

(function () {
  let _initialized = false;
  let _configData = {};
  let _adjustments = {};
  let _apiAvailable = false;

  // ── Config field definitions ──────────────────────────────────────────────
  // Grouped for UI rendering. Each field maps to a dot-notation config key.

  const CONFIG_FIELD_GROUPS = [
    {
      label: 'Cap',
      fields: [
        { key: 'cap.base_cap', label: 'Base Cap ($)', type: 'number', step: 1 },
        { key: 'cap.annual_inflation', label: 'Annual Inflation', type: 'number', step: 0.01, min: 0, max: 1 },
        { key: 'cap.discount_rate', label: 'Discount Rate', type: 'number', step: 0.01, min: 0.01, max: 0.99 },
      ]
    },
    {
      label: 'Season',
      fields: [
        { key: 'season.current_season', label: 'Current Season', type: 'number', step: 1 },
        { key: 'season.target_season', label: 'Target Season', type: 'number', step: 1 },
      ]
    },
    {
      label: 'League',
      fields: [
        { key: 'league.teams', label: 'Number of Teams', type: 'number', step: 1, min: 1 },
      ]
    },
    {
      label: 'Roster',
      fields: [
        { key: 'roster.bench', label: 'Bench Slots', type: 'number', step: 1, min: 0 },
        { key: 'roster.ir_slots', label: 'IR Slots', type: 'number', step: 1, min: 0 },
        { key: 'roster.practice_squad_slots', label: 'Practice Squad Slots', type: 'number', step: 1, min: 0 },
        { key: 'practice_squad.cap_percent', label: 'PS Cap %', type: 'number', step: 0.01, min: 0, max: 1 },
        { key: 'injured_reserve.cap_percent', label: 'IR Cap %', type: 'number', step: 0.01, min: 0, max: 1 },
      ]
    },
  ];

  // ── Helpers ───────────────────────────────────────────────────────────────

  function fmt1(v) { return typeof v === 'number' ? v.toFixed(1) : '–'; }

  function showStatus(el, message, isError) {
    if (!el) return;
    el.textContent = message;
    el.className = 'save-status ' + (isError ? 'save-status-error' : 'save-status-ok');
    el.hidden = false;
    setTimeout(function () { el.hidden = true; }, isError ? 8000 : 3000);
  }

  function getBaseCap() {
    var v = _configData['cap.base_cap'];
    return typeof v === 'number' ? v : 0;
  }

  // ── Section 1: Config Fields ──────────────────────────────────────────────

  function renderConfigForm() {
    var container = document.getElementById('lc-fields-container');
    if (!container) return;

    container.innerHTML = CONFIG_FIELD_GROUPS.map(function (group) {
      var fieldsHtml = group.fields.map(function (f) {
        var val = _configData[f.key];
        var attrs = 'type="number"';
        if (f.step != null) attrs += ' step="' + f.step + '"';
        if (f.min != null) attrs += ' min="' + f.min + '"';
        if (f.max != null) attrs += ' max="' + f.max + '"';
        return '<div class="config-field-row">' +
          '<label for="cfg-' + f.key + '">' + f.label + '</label>' +
          '<input id="cfg-' + f.key + '" data-key="' + f.key + '" ' + attrs +
          ' value="' + (val != null ? val : '') + '" class="config-input" />' +
          '</div>';
      }).join('');
      return '<div class="config-field-group"><h3>' + group.label + '</h3>' + fieldsHtml + '</div>';
    }).join('');
  }

  function gatherConfigValues() {
    var updates = {};
    var inputs = document.querySelectorAll('#lc-fields-container .config-input');
    inputs.forEach(function (inp) {
      var key = inp.dataset.key;
      var raw = inp.value.trim();
      if (raw === '') return;
      var num = Number(raw);
      if (!isNaN(num)) updates[key] = num;
    });
    return updates;
  }

  function saveConfig() {
    var btn = document.getElementById('lc-save-btn');
    var status = document.getElementById('lc-save-status');
    var updates = gatherConfigValues();

    if (Object.keys(updates).length === 0) {
      showStatus(status, 'No changes to save', true);
      return;
    }

    btn.disabled = true;
    fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updates),
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        btn.disabled = false;
        if (res.ok) {
          _configData = res.config || _configData;
          showStatus(status, 'Config saved', false);
          renderConfigForm();
          recalcAllCapRemaining();
        } else {
          showStatus(status, 'Error: ' + res.error, true);
        }
      })
      .catch(function (err) {
        btn.disabled = false;
        showStatus(status, 'Network error: ' + err.message, true);
      });
  }

  // ── Section 2: Team Cap Adjustments ───────────────────────────────────────

  function getTeamList() {
    // Prefer teams from cap health data; fall back to surplus data
    if (CAP_HEALTH_DATA && CAP_HEALTH_DATA.length) {
      return CAP_HEALTH_DATA.map(function (r) { return r.team; }).sort();
    }
    if (typeof ALL_LG_TEAMS !== 'undefined' && ALL_LG_TEAMS.length) {
      return ALL_LG_TEAMS.slice();
    }
    return Object.keys(_adjustments).sort();
  }

  function renderAdjustmentsTable() {
    var tbody = document.getElementById('ca-table-body');
    if (!tbody) return;

    var teams = getTeamList();
    var baseCap = getBaseCap();

    tbody.innerHTML = teams.map(function (team) {
      var adj = _adjustments[team] || { dead_money: 0, cap_transactions: 0, rollover: 0 };
      var capRow = (CAP_HEALTH_DATA || []).find(function (r) { return r.team === team; });
      var capUsage = capRow ? capRow.current_cap_usage : 0;
      var capRemaining = baseCap - capUsage - adj.dead_money - adj.cap_transactions + adj.rollover;

      return '<tr data-team="' + team.replace(/"/g, '&quot;') + '">' +
        '<td>' + team + '</td>' +
        '<td class="num mono">' + fmt1(baseCap) + '</td>' +
        '<td class="num mono">' + fmt1(capUsage) + '</td>' +
        '<td class="num"><input type="number" class="adj-input" data-field="dead_money" value="' + adj.dead_money + '" step="0.1" min="0" /></td>' +
        '<td class="num"><input type="number" class="adj-input" data-field="cap_transactions" value="' + adj.cap_transactions + '" step="0.1" /></td>' +
        '<td class="num"><input type="number" class="adj-input" data-field="rollover" value="' + adj.rollover + '" step="0.1" min="0" /></td>' +
        '<td class="num mono cap-remaining-cell" style="color:' + (capRemaining >= 0 ? 'var(--surplus-pos)' : 'var(--surplus-neg)') + ';">' + fmt1(capRemaining) + '</td>' +
        '</tr>';
    }).join('');

    // Wire live recalculation on input change
    tbody.querySelectorAll('.adj-input').forEach(function (inp) {
      inp.addEventListener('input', function () {
        recalcRowCapRemaining(inp.closest('tr'));
      });
    });
  }

  function recalcRowCapRemaining(row) {
    if (!row) return;
    var baseCap = getBaseCap();
    var team = row.dataset.team;
    var capRow = (CAP_HEALTH_DATA || []).find(function (r) { return r.team === team; });
    var capUsage = capRow ? capRow.current_cap_usage : 0;

    var dm = parseFloat(row.querySelector('[data-field="dead_money"]').value) || 0;
    var ct = parseFloat(row.querySelector('[data-field="cap_transactions"]').value) || 0;
    var ro = parseFloat(row.querySelector('[data-field="rollover"]').value) || 0;

    var remaining = baseCap - capUsage - dm - ct + ro;
    var cell = row.querySelector('.cap-remaining-cell');
    if (cell) {
      cell.textContent = fmt1(remaining);
      cell.style.color = remaining >= 0 ? 'var(--surplus-pos)' : 'var(--surplus-neg)';
    }
  }

  function recalcAllCapRemaining() {
    var rows = document.querySelectorAll('#ca-table-body tr');
    rows.forEach(function (row) { recalcRowCapRemaining(row); });
  }

  function gatherAdjustments() {
    var result = {};
    var rows = document.querySelectorAll('#ca-table-body tr');
    rows.forEach(function (row) {
      var team = row.dataset.team;
      if (!team) return;
      result[team] = {
        dead_money: parseFloat(row.querySelector('[data-field="dead_money"]').value) || 0,
        cap_transactions: parseFloat(row.querySelector('[data-field="cap_transactions"]').value) || 0,
        rollover: parseFloat(row.querySelector('[data-field="rollover"]').value) || 0,
      };
    });
    return result;
  }

  function saveAdjustments() {
    var btn = document.getElementById('ca-save-btn');
    var status = document.getElementById('ca-save-status');
    var data = gatherAdjustments();

    btn.disabled = true;
    fetch('/api/team-adjustments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        btn.disabled = false;
        if (res.ok) {
          _adjustments = data;
          if (typeof TEAM_ADJUSTMENTS !== 'undefined') {
            Object.keys(TEAM_ADJUSTMENTS).forEach(function (k) { delete TEAM_ADJUSTMENTS[k]; });
            Object.assign(TEAM_ADJUSTMENTS, data);
          }
          showStatus(status, 'Adjustments saved', false);
        } else {
          showStatus(status, 'Error: ' + res.error, true);
        }
      })
      .catch(function (err) {
        btn.disabled = false;
        showStatus(status, 'Network error: ' + err.message, true);
      });
  }

  // ── Section 3: Roster Upload ──────────────────────────────────────────────

  function setupDropZone() {
    var zone = document.getElementById('ru-drop-zone');
    var fileInput = document.getElementById('ru-file-input');
    if (!zone || !fileInput) return;

    zone.addEventListener('click', function () { fileInput.click(); });

    zone.addEventListener('dragover', function (e) {
      e.preventDefault();
      zone.classList.add('drag-over');
    });

    zone.addEventListener('dragleave', function () {
      zone.classList.remove('drag-over');
    });

    zone.addEventListener('drop', function (e) {
      e.preventDefault();
      zone.classList.remove('drag-over');
      var files = e.dataTransfer.files;
      if (files.length > 0) uploadRoster(files[0]);
    });

    fileInput.addEventListener('change', function () {
      if (fileInput.files.length > 0) uploadRoster(fileInput.files[0]);
    });
  }

  function uploadRoster(file) {
    var statusEl = document.getElementById('ru-upload-status');

    if (!file.name.endsWith('.csv')) {
      statusEl.hidden = false;
      statusEl.className = 'upload-status upload-status-error';
      statusEl.textContent = 'File must be a .csv file';
      return;
    }

    statusEl.hidden = false;
    statusEl.className = 'upload-status upload-status-pending';
    statusEl.textContent = 'Uploading and validating…';

    var formData = new FormData();
    formData.append('file', file);

    fetch('/api/roster-upload', { method: 'POST', body: formData })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        if (res.ok) {
          statusEl.className = 'upload-status upload-status-ok';
          statusEl.textContent = 'Uploaded: ' + res.rows + ' players across ' + res.teams.length + ' teams (' + file.name + ')';
        } else {
          statusEl.className = 'upload-status upload-status-error';
          statusEl.textContent = 'Validation failed: ' + res.error;
        }
      })
      .catch(function (err) {
        statusEl.className = 'upload-status upload-status-error';
        statusEl.textContent = 'Upload failed: ' + err.message;
      });
  }

  // ── Recompute ─────────────────────────────────────────────────────────────

  function recompute() {
    var btn = document.getElementById('ru-recompute-btn');
    var status = document.getElementById('ru-recompute-status');

    btn.disabled = true;
    showStatus(status, 'Running pipeline…', false);
    status.className = 'save-status save-status-pending';

    fetch('/api/recompute', { method: 'POST' })
      .then(function (r) { return r.json(); })
      .then(function (res) {
        btn.disabled = false;
        if (res.ok) {
          var msg = 'Done in ' + res.duration_ms + 'ms';
          if (res.tables) {
            var counts = Object.entries(res.tables).map(function (e) { return e[0] + ': ' + e[1]; }).join(', ');
            msg += ' — ' + counts;
          }
          showStatus(status, msg, false);
          // Reload dashboard data to reflect recomputed outputs
          if (typeof loadData === 'function') {
            loadData().then(function () {
              renderAdjustmentsTable();
            });
          }
        } else {
          showStatus(status, 'Error: ' + res.error, true);
        }
      })
      .catch(function (err) {
        btn.disabled = false;
        showStatus(status, 'Recompute failed: ' + err.message, true);
      });
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  function initLeagueSettings() {
    if (_initialized) return;
    _initialized = true;

    var loading = document.getElementById('lc-loading');
    var errorEl = document.getElementById('lc-error');

    // Load config and adjustments from API
    var configPromise = fetch('/api/config')
      .then(function (r) {
        if (!r.ok) throw new Error('Config API returned ' + r.status);
        return r.json();
      })
      .then(function (res) {
        _configData = res.config || {};
        _apiAvailable = true;
      })
      .catch(function () {
        _apiAvailable = false;
      });

    var adjPromise = fetch('/api/team-adjustments')
      .then(function (r) {
        if (!r.ok) throw new Error('Adjustments API returned ' + r.status);
        return r.json();
      })
      .then(function (res) {
        _adjustments = res.adjustments || {};
        if (typeof TEAM_ADJUSTMENTS !== 'undefined') {
          Object.keys(TEAM_ADJUSTMENTS).forEach(function (k) { delete TEAM_ADJUSTMENTS[k]; });
          Object.assign(TEAM_ADJUSTMENTS, _adjustments);
        }
      })
      .catch(function () {
        _adjustments = {};
      });

    Promise.all([configPromise, adjPromise]).then(function () {
      if (loading) loading.hidden = true;

      if (!_apiAvailable) {
        if (errorEl) {
          errorEl.textContent = 'Config API not available. Start the server with: python dashboard/server.py';
          errorEl.hidden = false;
        }
        return;
      }

      renderConfigForm();
      renderAdjustmentsTable();
      setupDropZone();

      // Wire save buttons
      var saveConfigBtn = document.getElementById('lc-save-btn');
      if (saveConfigBtn) saveConfigBtn.addEventListener('click', saveConfig);

      var saveAdjBtn = document.getElementById('ca-save-btn');
      if (saveAdjBtn) saveAdjBtn.addEventListener('click', saveAdjustments);

      var recomputeBtn = document.getElementById('ru-recompute-btn');
      if (recomputeBtn) recomputeBtn.addEventListener('click', recompute);
    });
  }

  window.initLeagueSettings = initLeagueSettings;
})();
