// Data loading and derived metric computation for RSV Fantasy Dashboard
// Reads weekly_detail.csv and season_values.csv via PapaParse at app startup.

// Paths are relative to index.html (served from dashboard/src/)
const DATA_PATHS = {
  weekly: '../data/weekly_detail.csv',
  season: '../data/season_values.csv'
};

// Exported data arrays — populated after loadData() resolves
let WEEKLY_DATA = [];
let SEASON_DATA = [];
let ALL_PLAYERS = [];
let ALL_SEASONS = [];

/**
 * Parse a CSV via PapaParse (download mode — works with both file:// and http://).
 * Returns a promise that resolves to the array of row objects.
 */
function parseCsv(path) {
  return new Promise((resolve, reject) => {
    Papa.parse(path, {
      download: true,
      header: true,
      dynamicTyping: true,
      skipEmptyLines: true,
      complete: (results) => resolve(results.data),
      error: (err) => reject(new Error(`Failed to load ${path}: ${err.message}`))
    });
  });
}

/**
 * Load both CSVs, compute derived metrics, and populate the exported arrays.
 * Returns a promise that resolves when everything is ready.
 */
function loadData() {
  return Promise.all([parseCsv(DATA_PATHS.weekly), parseCsv(DATA_PATHS.season)])
    .then(([weeklyRaw, seasonRaw]) => {

      // ── Weekly data ──────────────────────────────────────────────────────
      // Only keep the columns the dashboard needs; coerce numerics defensively.
      WEEKLY_DATA = weeklyRaw
        .filter(r => r.player && r.position)
        .map(r => ({
          player:     String(r.player),
          position:   String(r.position),
          season:     +r.season,
          week:       +r.week,
          points:     +(r.points     ?? 0) || 0,
          margin:     +(r.margin     ?? 0) || 0,
          rsv_week:   +(r.rsv_week   ?? 0) || 0,
          wmsv:       +(r.wmsv       ?? 0) || 0,
          start_prob: +(r.start_prob ?? 0) || 0
        }));

      // ── Season data — derived metrics ────────────────────────────────────

      // 1. RSV sum per season (used for dollar_value denominator).
      //    Sum all positive and negative RSV values as-is.
      const seasonRsvSum = {};
      seasonRaw.forEach(r => {
        const season = +r.season;
        const rsv    = +(r.rsv ?? 0) || 0;
        seasonRsvSum[season] = (seasonRsvSum[season] || 0) + rsv;
      });

      // 2. pos_rank: rank within (season, position) by rsv desc, 1 = best.
      //    Build groups, sort, then write ranks into a lookup map.
      const posGroups = {};
      seasonRaw.forEach(r => {
        const key = `${r.season}||${r.position}`;
        (posGroups[key] = posGroups[key] || []).push(r);
      });
      const posRankMap = {};
      Object.values(posGroups).forEach(group => {
        group
          .slice()
          .sort((a, b) => (+(b.rsv) || 0) - (+(a.rsv) || 0))
          .forEach((r, i) => {
            posRankMap[`${r.season}||${r.player}`] = i + 1;
          });
      });

      // 3. Assemble SEASON_DATA rows.
      //    Ignore rsv_val — it can contain Excel formula strings.
      SEASON_DATA = seasonRaw
        .filter(r => r.player && r.position)
        .map(r => {
          const season = +r.season;
          const rsv    = +(r.rsv ?? 0) || 0;
          const rsvSum = seasonRsvSum[season] || 1;
          return {
            player:       String(r.player),
            position:     String(r.position),
            season,
            rsv,
            sav:          +(r.sav          ?? 0) || 0,
            par:          +(r.par          ?? 0) || 0,
            total_points: +(r.total_points ?? 0) || 0,
            dollar_value: (rsv / rsvSum) * 3000,
            pos_rank:     posRankMap[`${season}||${r.player}`] ?? null
          };
        });

      // ── Sorted unique index arrays ────────────────────────────────────────
      ALL_PLAYERS = [...new Set(SEASON_DATA.map(r => r.player))].sort();
      ALL_SEASONS = [...new Set(SEASON_DATA.map(r => r.season))].sort((a, b) => a - b);

      // ── Console summary ───────────────────────────────────────────────────
      const sampleRow = SEASON_DATA.find(r => r.rsv > 10);
      console.log('=== RSV Fantasy Dashboard — Data Loaded ===');
      console.log(`Weekly rows  : ${WEEKLY_DATA.length.toLocaleString()}`);
      console.log(`Season rows  : ${SEASON_DATA.length.toLocaleString()}`);
      console.log(`Season range : ${ALL_SEASONS[0]}–${ALL_SEASONS[ALL_SEASONS.length - 1]}`);
      console.log(`Unique players: ${ALL_PLAYERS.length.toLocaleString()}`);
      if (sampleRow) {
        console.log(
          `Sample dollar_value: ${sampleRow.player} ` +
          `(${sampleRow.season}) → $${sampleRow.dollar_value.toFixed(2)}`
        );
      }
      console.log('===========================================');
    });
}
