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
 * Switch the visible tab panel and update the active tab button state.
 * @param {string} tabId - matches the data-tab attribute on tab buttons
 *                         and the panel id suffix (panel-{tabId})
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
}

// ── Initialisation ────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Wire up tab click handlers
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Show a loading state while CSVs are fetched
  document.getElementById('loading-overlay').style.display = 'flex';

  loadData()
    .then(() => {
      document.getElementById('loading-overlay').style.display = 'none';

      // Activate the first tab by default
      switchTab('value-curves');

      console.log('Dashboard ready — chart panels will be wired in later milestones.');
    })
    .catch(err => {
      document.getElementById('loading-overlay').innerHTML =
        `<div class="load-error">
          <span class="load-error-icon">⚠</span>
          <p>Failed to load data: ${err.message}</p>
          <p class="load-error-hint">Serve this directory over HTTP (e.g. <code>python -m http.server 8080</code>)</p>
        </div>`;
      console.error('Data load failed:', err);
    });
});
