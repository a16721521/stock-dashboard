const State = {
  watchlist: { groups: [] },
  settings: null,
  selected: null,      // currently displayed ticker symbol
  scanTab: "most_oversold",
};

// Factual oscillator states (not trade recommendations).
const STATE_COLORS = {
  "Deeply Oversold": "#1a7f37", "Oversold": "#4caf50", "Mildly Oversold": "#9ccc9a",
  "Neutral": "#8a8a8a",
  "Mildly Overbought": "#eba39a", "Overbought": "#e57373", "Deeply Overbought": "#c62828",
  "Mixed": "#b08900", "Invalid": "#cfcfcf",
};

function stateClass(state) {
  return "st-" + String(state || "invalid").toLowerCase().replace(/\s+/g, "-");
}

function stateColor(state) {
  return STATE_COLORS[state] || "#8a8a8a";
}
