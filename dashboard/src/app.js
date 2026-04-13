// Tab switching logic and chart instance management for RSV Fantasy Dashboard

/**
 * Registry of active Chart.js instances, keyed by view name.
 * Always call destroyChart(viewName) before creating a new chart for that view.
 */
const chartInstances = {};

/**
 * Destroy and remove a chart instance by view name.
 * Safe to call even if no instance exists for that key.
 */
function destroyChart(viewName) {
  if (chartInstances[viewName]) {
    chartInstances[viewName].destroy();
    delete chartInstances[viewName];
  }
}

/**
 * Map of tab-id → init function. Called once on first activation; the init
 * functions themselves guard against double-initialisation via their own flags.
 */
const VIEW_INIT_FNS = {
  'value-curves':       () => initValueCurves(),
  'year-over-year':     () => initYearOverYear(),
  'player-timeline':    () => initPlayerTimeline(),
  'value-distribution':    () => initValueDistribution(),
  'wmsv-vs-rsv':           () => initWmsvRsv(),
  'positional-efficiency': () => initPositionalEfficiency()
};

/**
 * Switch the visible tab panel, update active button state, and fire the
 * view's init function if one is registered.
 * @param {string} tabId - matches data-tab attribute and panel id suffix
 */
function switchTab(tabId) {
  document.querySelectorAll('.tab-panel').forEach(panel => {
    panel.classList.remove('active');
  });

  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === tabId);
  });

  const panel = document.getElementById(`panel-${tabId}`);
  if (panel) panel.classList.add('active');

  if (VIEW_INIT_FNS[tabId]) {
    VIEW_INIT_FNS[tabId]();
  }
}

// ── Initialisation ────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Wire up tab click handlers
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Show loading overlay while CSVs are fetched
  document.getElementById('loading-overlay').style.display = 'flex';

  loadData()
    .then(() => {
      document.getElementById('loading-overlay').style.display = 'none';

      // Activate Value Curves as the landing view
      switchTab('value-curves');
    })
    .catch(err => {
      document.getElementById('loading-overlay').innerHTML =
        `<div class="load-error">
          <span class="load-error-icon">&#9888;</span>
          <p>Failed to load data: ${err.message}</p>
          <p class="load-error-hint">
            Serve this directory over HTTP, e.g.
            <code>python -m http.server 8080</code>
          </p>
        </div>`;
      console.error('Data load failed:', err);
    });
});
