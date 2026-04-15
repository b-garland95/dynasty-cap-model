// Tab/section switching logic and chart instance management for ESV Fantasy Dashboard

/**
 * Registry of active Chart.js instances, keyed by view name.
 * Always call destroyChart(viewName) before creating a new chart for that view.
 */
const chartInstances = {};

function destroyChart(viewName) {
  if (chartInstances[viewName]) {
    chartInstances[viewName].destroy();
    delete chartInstances[viewName];
  }
}

// ── Section definitions ───────────────────────────────────────────────────────
// Each section owns a set of tab-ids. Navigating to a section shows only that
// section's tab buttons and switches to its default tab.

const SECTIONS = {
  historical: {
    tabs: ['value-curves', 'player-timeline', 'value-distribution',
           'positional-efficiency', 'year-over-year'],
    defaultTab: 'value-curves'
  },
  forecasted: {
    tabs: ['forecasted'],
    defaultTab: 'forecasted'
  },
  league: {
    tabs: ['league'],
    defaultTab: 'league'
  }
};

// ── View init functions ───────────────────────────────────────────────────────

const VIEW_INIT_FNS = {
  'value-curves':          () => initValueCurves(),
  'year-over-year':        () => initYearOverYear(),
  'player-timeline':       () => initPlayerTimeline(),
  'value-distribution':    () => initValueDistribution(),
  'positional-efficiency': () => initPositionalEfficiency(),
  'forecasted':            () => initForecasted(),
  'league':                () => initLeague(),
};

// ── Tab switching ─────────────────────────────────────────────────────────────

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

// ── Section switching ─────────────────────────────────────────────────────────

function switchSection(sectionId) {
  const sectionDef = SECTIONS[sectionId];
  if (!sectionDef) return;

  // Update section button active state
  document.querySelectorAll('.section-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.section === sectionId);
  });

  // Show/hide tab buttons by section
  document.querySelectorAll('.tab-btn').forEach(btn => {
    const belongsToSection = btn.dataset.section === sectionId;
    btn.hidden = !belongsToSection;
  });

  // Activate the default tab for this section
  switchTab(sectionDef.defaultTab);
}

// ── Initialisation ────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  // Wire up section click handlers
  document.querySelectorAll('.section-btn').forEach(btn => {
    btn.addEventListener('click', () => switchSection(btn.dataset.section));
  });

  // Wire up tab click handlers
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Show loading overlay while CSVs are fetched
  document.getElementById('loading-overlay').style.display = 'flex';

  loadData()
    .then(() => {
      document.getElementById('loading-overlay').style.display = 'none';

      // Activate Historical section (Value Curves) as the landing view
      switchSection('historical');
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
