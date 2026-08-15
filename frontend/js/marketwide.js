const Marketwide = {
  pollTimer: null,

  init() {
    document.querySelectorAll("#marketwide-tabs .tab").forEach((tab) => {
      tab.addEventListener("click", () => {
        document.querySelectorAll("#marketwide-tabs .tab")
          .forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        State.scanTab = tab.dataset.tab;
        Marketwide.refresh();
      });
    });
    Marketwide.refresh();
    Marketwide.poll();
  },

  async refresh() {
    if (State.scanTab === "data_problems") {
      await Marketwide.renderDataProblems();
      return;
    }
    const data = await API.getScan(State.scanTab);
    Marketwide.renderStatus(data);
    Marketwide.renderTiles(data.rows);
  },

  renderStatus(data) {
    const el = document.getElementById("scan-status");
    if (data.scanning) { el.textContent = "Scanning…"; return; }
    if (!data.scanned_at) { el.textContent = "No scan yet"; return; }
    const when = new Date(data.scanned_at).toLocaleString();
    const bar = data.latest_bar_date ? ` · bar ${data.latest_bar_date}` : "";
    const status = data.status ? ` · ${data.status}` : "";
    el.textContent = `Observation only — not trade signals · scanned ${when}${bar}${status}`;
  },

  renderTiles(rows) {
    const body = document.getElementById("marketwide-body");
    body.innerHTML = "";
    rows.forEach((r) => {
      const tile = document.createElement("div");
      tile.className = "tile " + stateClass(r.state);
      tile.innerHTML = `<div class="tsym">${r.ticker}</div>
        <div class="tstate">${r.state}</div>`;
      tile.title = `${r.state} · %R ${r.wr} · RSI ${r.rsi} · price ${r.price} · Observation`;
      tile.addEventListener("click", () => Detail.show(r.ticker));
      body.appendChild(tile);
    });
  },

  async renderDataProblems() {
    const el = document.getElementById("scan-status");
    const body = document.getElementById("marketwide-body");
    const s = await API.getDataStatus();
    el.textContent = "Data quality";
    const cov = s.coverage || {};
    const warns = (s.warnings || []);
    body.innerHTML = `
      <div class="data-problems">
        <div class="dp-row"><b>Freshness:</b> ${s.bar_status || "unknown"}
          (latest bar ${s.latest_bar_date || "—"}, expected ${s.expected_session_date || "—"})</div>
        <div class="dp-row"><b>Cache:</b> ${s.cache_status || "—"} ·
          coverage ${cov.valid ?? "—"}/${cov.requested ?? "—"} valid,
          ${cov.missing ?? "—"} missing</div>
        <div class="dp-row"><b>Algorithm:</b> ${s.algorithm_version || "—"}</div>
        <div class="dp-warnings">
          ${warns.length ? warns.map((w) => `<div class="warn">⚠ ${w}</div>`).join("")
                         : '<div class="ok">No data problems reported.</div>'}
        </div>
      </div>`;
  },

  poll() {
    // While a scan is running, refresh every 3s until it finishes.
    Marketwide.pollTimer = setInterval(async () => {
      if (State.scanTab === "data_problems") return;
      const data = await API.getScan(State.scanTab);
      Marketwide.renderStatus(data);
      if (!data.scanning && data.rows.length) {
        Marketwide.renderTiles(data.rows);
      }
    }, 3000);
  },
};
