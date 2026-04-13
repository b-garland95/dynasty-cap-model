// Shared constants for the RSV Fantasy Dashboard

const POS_COLORS = {
  QB: '#e06c75',
  RB: '#61afef',
  WR: '#98c379',
  TE: '#d19a66'
};

const POSITIONS = ['QB', 'RB', 'WR', 'TE'];

const THEME = {
  bg:       '#0f1117',
  surface:  '#1a1d27',
  surface2: '#232734',
  border:   '#2e3347',
  text:     '#e2e4ed',
  muted:    '#8b90a5',
  accent:   '#6c8cff'
};

const CHART_DEFAULTS = {
  maintainAspectRatio: false,
  responsive: true,
  plugins: {
    legend: {
      labels: {
        color: THEME.text,
        font: { family: 'DM Sans', size: 12 }
      }
    },
    tooltip: {
      backgroundColor: THEME.surface2,
      borderColor: THEME.border,
      borderWidth: 1,
      titleColor: THEME.text,
      bodyColor: THEME.muted,
      titleFont: { family: 'DM Sans', size: 13, weight: '600' },
      bodyFont: { family: 'DM Sans', size: 12 }
    }
  },
  scales: {
    x: {
      ticks: { color: THEME.muted, font: { family: 'DM Sans', size: 11 } },
      grid:  { color: THEME.border }
    },
    y: {
      ticks: { color: THEME.muted, font: { family: 'DM Sans', size: 11 } },
      grid:  { color: THEME.border }
    }
  }
};
