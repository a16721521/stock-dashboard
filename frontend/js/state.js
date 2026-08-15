const State = {
  watchlist: { groups: [] },
  settings: null,
  selected: null,      // currently displayed ticker symbol
  scanTab: "top_buy",
};

// Map a signal label to a CSS class.
function signalClass(signal) {
  return "sig-" + signal.toLowerCase()
    .replace(/\(|\)/g, "").trim().replace(/\s+/g, "-");
}
