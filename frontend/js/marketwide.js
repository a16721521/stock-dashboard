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
    const data = await API.getScan(State.scanTab);
    Marketwide.renderStatus(data);
    Marketwide.renderTiles(data.rows);
  },

  renderStatus(data) {
    const el = document.getElementById("scan-status");
    if (data.scanning) { el.textContent = "Scanning…"; return; }
    if (!data.scanned_at) { el.textContent = "No scan yet"; return; }
    const when = new Date(data.scanned_at);
    el.textContent = "Last scan: " + when.toLocaleString();
  },

  renderTiles(rows) {
    const body = document.getElementById("marketwide-body");
    body.innerHTML = "";
    rows.forEach((r) => {
      const tile = document.createElement("div");
      tile.className = "tile " + signalClass(r.signal);
      tile.innerHTML = `<div class="tsym">${r.ticker}</div>
        <div class="tnum">${r.price}</div>`;
      tile.title = `${r.signal} · %R ${r.wr} · RSI ${r.rsi} · %K ${r.stochK}`;
      tile.addEventListener("click", () => Detail.show(r.ticker));
      body.appendChild(tile);
    });
  },

  poll() {
    // While a scan is running, refresh every 3s until it finishes.
    Marketwide.pollTimer = setInterval(async () => {
      const data = await API.getScan(State.scanTab);
      Marketwide.renderStatus(data);
      if (!data.scanning && data.rows.length) {
        Marketwide.renderTiles(data.rows);
      }
    }, 3000);
  },
};
