// Free Agent Market — League Analysis sub-tab
// Shows projected player value vs. market-adjusted value given the current
// league-wide cap environment.  By default displays free agents only; a toggle
// allows including rostered players for comparison.
//
// Data sources (in priority order):
//   1. FA_MARKET_DATA + FA_MARKET_ENV  (pre-computed CSVs, available after recompute)
//   2. Computed on-the-fly from TV_DATA + CAP_HEALTH_DATA + LEAGUE_CONFIG + TEAM_ADJUSTMENTS

(function () {
  // ── State ──────────────────────────────────────────────────────────────────
  let _initialized     = false;
  let _includeRostered = false;
  let _posFilter       = 'All';
  let _sortKey         = 'projected_value';
  let _sortAsc         = false;

  // ── Cap environment ────────────────────────────────────────────────────────

  function _getCapEnvironment() {
    // Prefer pre-computed CSV data when available
    if (
      typeof FA_MARKET_ENV !== 'undefined' &&
      FA_MARKET_ENV.cap_to_value_ratio != null &&
      !isNaN(FA_MARKET_ENV.cap_to_value_ratio)
    ) {
      return FA_MARKET_ENV;
    }

    // Fallback: compute from already-loaded globals.
    // Uses computeCapRemaining() from view-league.js which applies the same
    // formula as the League Config Cap Remaining column:
    //   base_cap - current_cap_usage - dead_money - cap_transactions + rollover
    const baseCap   = (typeof LEAGUE_CONFIG !== 'undefined' && LEAGUE_CONFIG['cap.base_cap'])   || 300;
    const alpha     = 0.5;

    let totalCapAvailable = 0;
    let totalRollover = 0;
    const teamAdj = typeof TEAM_ADJUSTMENTS !== 'undefined' ? TEAM_ADJUSTMENTS : {};
    (CAP_HEALTH_DATA || []).forEach(r => {
      const remaining = typeof computeCapRemaining === 'function'
        ? computeCapRemaining(r.team, r.current_cap_usage)
        : (baseCap - r.current_cap_usage);
      totalCapAvailable += Math.max(remaining, 0);
      totalRollover += parseFloat((teamAdj[r.team] || {}).rollover || 0);
    });

    const effectiveCapAvailable = Math.max(totalCapAvailable - totalRollover, 0);

    const totalFaValue = (TV_DATA || [])
      .filter(r => !r.is_rostered)
      .reduce((s, r) => s + (r.tv_y0 || 0), 0);

    const cpr        = totalFaValue > 0 ? effectiveCapAvailable / totalFaValue : 1.0;
    const multiplier = Math.pow(Math.max(cpr, 1e-4), alpha);

    return {
      total_cap_available:     totalCapAvailable,
      total_rollover:          totalRollover,
      effective_cap_available: effectiveCapAvailable,
      total_fa_value:          totalFaValue,
      cap_to_value_ratio:      cpr,
      market_multiplier:       multiplier,
      inflation_pct:           (multiplier - 1) * 100,
      alpha,
    };
  }

  // ── Player rows ───────────────────────────────────────────────────────────

  function _getRows(env) {
    let rows;

    if (typeof FA_MARKET_DATA !== 'undefined' && FA_MARKET_DATA.length > 0) {
      rows = FA_MARKET_DATA.slice();
      // When rostered players are requested, merge TV_DATA rostered rows if they
      // aren't already in FA_MARKET_DATA (which exports FA-only by default).
      if (_includeRostered) {
        const inMarket = new Set(rows.map(r => r.player + '||' + r.position));
        const rostered = (TV_DATA || [])
          .filter(r => r.is_rostered && !inMarket.has(r.player + '||' + r.position))
          .map(r => ({
            player:                r.player,
            position:              r.position,
            team:                  r.team,
            adp:                   r.adp,
            is_rostered:           true,
            esv_p25:               r.esv_p25,
            esv_p50:               r.esv_p50,
            esv_p75:               r.esv_p75,
            projected_value:       r.tv_y0 || 0,
            market_adjusted_value: (r.tv_y0 || 0) * env.market_multiplier,
            market_premium_pct:    env.inflation_pct,
          }));
        rows = rows.concat(rostered);
      }
    } else {
      // Fallback: derive from TV_DATA
      rows = (TV_DATA || []).map(r => ({
        player:                r.player,
        position:              r.position,
        team:                  r.team,
        adp:                   r.adp,
        is_rostered:           r.is_rostered,
        esv_p25:               r.esv_p25,
        esv_p50:               r.esv_p50,
        esv_p75:               r.esv_p75,
        projected_value:       r.tv_y0 || 0,
        market_adjusted_value: (r.tv_y0 || 0) * env.market_multiplier,
        market_premium_pct:    env.inflation_pct,
      }));
      if (!_includeRostered) {
        rows = rows.filter(r => !r.is_rostered);
      }
    }

    if (_posFilter !== 'All') {
      rows = rows.filter(r => r.position === _posFilter);
    }

    rows.sort((a, b) => {
      const av = a[_sortKey] ?? 0;
      const bv = b[_sortKey] ?? 0;
      return _sortAsc ? av - bv : bv - av;
    });

    return rows;
  }

  // ── Renderers ─────────────────────────────────────────────────────────────

  function _renderEnvSummary(env) {
    const container = document.getElementById('fa-env-cards');
    if (!container) return;

    const fmtM   = v => (v != null && !isNaN(v)) ? '$' + v.toFixed(1) : '–';
    const fmtX   = v => (v != null && !isNaN(v)) ? v.toFixed(2) + '×' : '–';
    const fmtPct = v => {
      if (v == null || isNaN(v)) return '–';
      return (v >= 0 ? '+' : '') + v.toFixed(1) + '%';
    };

    const inflPct   = env.inflation_pct ?? 0;
    const inflColor = inflPct > 0 ? 'var(--surplus-pos)' : inflPct < 0 ? 'var(--surplus-neg)' : 'var(--text)';
    const envLabel  = inflPct > 5  ? 'Cap-Rich · Prices Inflating'
                    : inflPct < -5 ? 'Cap-Scarce · Prices Deflating'
                    : 'Balanced Market';
    const alphaStr  = (env.alpha != null && !isNaN(env.alpha)) ? env.alpha.toFixed(1) : '0.5';

    const rollover = env.total_rollover ?? 0;

    container.innerHTML = `
      <div class="fa-env-card">
        <div class="fa-env-label">Effective Cap Available</div>
        <div class="fa-env-value">${fmtM(env.effective_cap_available)}</div>
        <div class="fa-env-desc">League cap less rollover (${fmtM(env.total_cap_available)} − ${fmtM(rollover)}) — basis for market adjustment</div>
      </div>
      <div class="fa-env-card">
        <div class="fa-env-label">FA Player Value</div>
        <div class="fa-env-value">${fmtM(env.total_fa_value)}</div>
        <div class="fa-env-desc">Sum of projected values for available free agents</div>
      </div>
      <div class="fa-env-card">
        <div class="fa-env-label">Cap / Value Ratio</div>
        <div class="fa-env-value">${fmtX(env.cap_to_value_ratio)}</div>
        <div class="fa-env-desc">&gt;1× = cap surplus · &lt;1× = cap-constrained</div>
      </div>
      <div class="fa-env-card">
        <div class="fa-env-label">Market Adjustment</div>
        <div class="fa-env-value" style="color:${inflColor};">${fmtPct(inflPct)}</div>
        <div class="fa-env-desc">${envLabel} · α = ${alphaStr}</div>
      </div>
    `;
  }

  function _renderTable(env) {
    const tbody = document.getElementById('fa-market-tbody');
    if (!tbody) return;

    const rows = _getRows(env);

    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--muted);">No players match the current filter.</td></tr>';
      return;
    }

    const inflPct   = env.inflation_pct ?? 0;
    const premColor = inflPct >= 0 ? 'var(--surplus-pos)' : 'var(--surplus-neg)';
    const premStr   = (inflPct >= 0 ? '+' : '') + inflPct.toFixed(1) + '%';

    tbody.innerHTML = rows.map(r => {
      const adpStr  = r.adp > 0 ? r.adp.toFixed(0) : '–';
      const projStr = r.projected_value       > 0 ? r.projected_value.toFixed(1)       : '–';
      const mktStr  = r.market_adjusted_value > 0 ? r.market_adjusted_value.toFixed(1) : '–';
      const pos     = (r.position || '').toLowerCase();
      return `
        <tr>
          <td>${playerLink(r.player)}</td>
          <td><span class="pos-badge pos-${pos}">${r.position}</span></td>
          <td class="team-cell">${r.team || '–'}</td>
          <td class="num mono">${adpStr}</td>
          <td class="num">${projStr}</td>
          <td class="num">${mktStr}</td>
          <td class="num" style="color:${premColor};">${premStr}</td>
        </tr>
      `;
    }).join('');
  }

  // ── Public refresh ────────────────────────────────────────────────────────

  function refresh() {
    const env = _getCapEnvironment();
    _renderEnvSummary(env);
    _renderTable(env);
  }

  // ── Init ──────────────────────────────────────────────────────────────────

  function initFreeAgentMarket() {
    if (_initialized) {
      refresh();
      return;
    }
    _initialized = true;

    // Position filter
    const posSel = document.getElementById('fa-position');
    if (posSel) {
      posSel.addEventListener('change', () => {
        _posFilter = posSel.value;
        refresh();
      });
    }

    // Include-rostered toggle
    const rosterChk = document.getElementById('fa-include-rostered');
    if (rosterChk) {
      rosterChk.addEventListener('change', () => {
        _includeRostered = rosterChk.checked;
        refresh();
      });
    }

    // Column sort
    document.querySelectorAll('#fa-market-table thead th[data-sort]').forEach(th => {
      th.style.cursor = 'pointer';
      th.addEventListener('click', () => {
        if (_sortKey === th.dataset.sort) {
          _sortAsc = !_sortAsc;
        } else {
          _sortKey = th.dataset.sort;
          _sortAsc = _sortKey === 'adp';  // ADP ascending by default; values descending
        }
        document.querySelectorAll('#fa-market-table thead th').forEach(h => {
          h.classList.remove('sort-asc', 'sort-desc');
        });
        th.classList.add(_sortAsc ? 'sort-asc' : 'sort-desc');
        _renderTable(_getCapEnvironment());
      });
    });

    refresh();
  }

  window.initFreeAgentMarket   = initFreeAgentMarket;
  window.refreshFreeAgentMarket = refresh;
  window.getCapEnvironment      = _getCapEnvironment;
})();
