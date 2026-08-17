const BAR_STATUS_LABEL = {
  final: "Final", provisional: "Provisional — session in progress",
  stale: "Stale — older than the last closed session", unknown: "Unknown freshness",
};

const Detail = {
  async show(sym, rankedContext) {
    State.selected = sym;
    const title = document.getElementById("detail-title");
    const body = document.getElementById("detail-body");
    const addBtn = document.getElementById("add-to-watchlist");
    title.textContent = sym + " …";
    body.innerHTML = '<p class="empty">Loading…</p>';
    let d;
    try {
      d = await API.getTicker(sym);
    } catch (e) {
      title.textContent = sym;
      body.innerHTML = `<p class="empty">No data for ${sym}.</p>`;
      return;
    }
    const namePart = d.name ? ` · ${d.name}` : "";
    title.textContent = `${sym}${namePart} — ${d.latest.state} (${d.latest.price})`;
    addBtn.hidden = false;
    addBtn.dataset.sym = sym;
    body.innerHTML = Detail.summaryHtml(d, rankedContext) +
      '<div id="detail-chart" style="height:520px"></div>';
    Detail.render(d);
    if (window.Watchlist) Watchlist.highlight(sym);
  },

  // rankedContext, when present, is the row this ticker was ranked with in
  // the marketwide grid — shown alongside the freshly-fetched current reading
  // so a click can never silently swap the bar/state out from under the user
  // (P1-5: a Friday-ranked tile could otherwise land on Monday's provisional
  // data with no indication anything had changed).
  summaryHtml(d, rankedContext) {
    const st = d.latest.state;
    const barLabel = BAR_STATUS_LABEL[d.bar_status] || d.bar_status || "Unknown";
    const barClass = "bs-" + (d.bar_status || "unknown");

    let compareHtml = "";
    if (rankedContext) {
      const changed = rankedContext.bar_date !== d.bar_date || rankedContext.state !== st;
      compareHtml = `
        <div class="ranked-compare">
          <div><b>As ranked</b> (scan bar ${rankedContext.bar_date || "—"}):
            ${rankedContext.state} · %R ${rankedContext.wr} · RSI ${rankedContext.rsi} ·
            price ${rankedContext.price}</div>
          <div><b>Current</b> (bar ${d.bar_date || "—"}, ${barLabel}):
            ${st} · %R ${d.latest.wr} · RSI ${d.latest.rsi} · price ${d.latest.price}</div>
          ${changed ? '<div class="ranked-changed-note">⚠ State or bar date has changed since this tile was ranked.</div>' : ""}
        </div>`;
    }

    return `
      <div class="decision-summary">
        <span class="badge badge-obs">Observation</span>
        <span class="badge bar-badge ${barClass}">${barLabel}</span>
        <div class="ds-grid">
          <div><b>Observation:</b> ${st}</div>
          <div><b>Confirmation:</b> not applicable (no validated strategy)</div>
          <div><b>Research status:</b> Observation</div>
          <div><b>Data:</b> daily bar through ${d.bar_date || "—"}</div>
        </div>
        ${compareHtml}
        <div class="ds-note">Factual oscillator state — not a validated trade recommendation.</div>
      </div>`;
  },

  render(d) {
    const s = d.series, t = d.thresholds;
    const traces = [
      { x: s.dates, y: s.close, name: "Close", xaxis: "x", yaxis: "y" },
      { x: s.dates, y: s.wr, name: "Williams %R", xaxis: "x", yaxis: "y2" },
      { x: s.dates, y: s.rsi, name: "RSI", xaxis: "x", yaxis: "y3" },
      { x: s.dates, y: s.stochK, name: "%K", xaxis: "x", yaxis: "y4" },
      { x: s.dates, y: s.stochD, name: "%D", xaxis: "x", yaxis: "y4" },
    ];
    const hline = (yref, yval, color) => ({
      type: "line", xref: "paper", x0: 0, x1: 1, yref, y0: yval, y1: yval,
      line: { color, width: 1, dash: "dot" },
    });
    const layout = {
      showlegend: false, margin: { t: 20, r: 10, b: 20, l: 40 },
      grid: { rows: 4, columns: 1, pattern: "independent" },
      yaxis: { domain: [0.72, 1] }, yaxis2: { domain: [0.48, 0.68] },
      yaxis3: { domain: [0.24, 0.44] }, yaxis4: { domain: [0, 0.20] },
      xaxis: { anchor: "y4" },
      shapes: [
        hline("y2", t.wr_oversold, "green"), hline("y2", t.wr_overbought, "red"),
        hline("y3", t.rsi_oversold, "green"), hline("y3", t.rsi_overbought, "red"),
        hline("y4", t.stoch_oversold, "green"), hline("y4", t.stoch_overbought, "red"),
      ],
      annotations: [
        { text: "Price", x: 0, y: 1, xref: "paper", yref: "paper", showarrow: false, font: { size: 11 } },
        { text: "Williams %R", x: 0, y: 0.68, xref: "paper", yref: "paper", showarrow: false, font: { size: 11 } },
        { text: "RSI", x: 0, y: 0.44, xref: "paper", yref: "paper", showarrow: false, font: { size: 11 } },
        { text: "Stochastic", x: 0, y: 0.20, xref: "paper", yref: "paper", showarrow: false, font: { size: 11 } },
      ],
    };
    Plotly.newPlot("detail-chart", traces, layout, { displayModeBar: false, responsive: true });
  },
};
