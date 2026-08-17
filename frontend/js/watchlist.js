const Watchlist = {
  async load() {
    State.watchlist = await API.getWatchlist();
    Watchlist.render();
    await Watchlist.refreshReadings();
  },

  async save() { await API.putWatchlist(State.watchlist); },

  render() {
    const body = document.getElementById("watchlist-body");
    body.innerHTML = "";
    State.watchlist.groups.forEach((group, gi) => {
      const g = document.createElement("div");
      g.className = "group" + (group.collapsed ? " collapsed" : "");
      g.dataset.gi = gi;

      const head = document.createElement("div");
      head.className = "group-head";
      head.innerHTML = `<span class="gname">${group.name}</span>
        <span class="gtoggle">${group.collapsed ? "▸" : "▾"}</span>`;
      head.addEventListener("click", () => {
        group.collapsed = !group.collapsed;
        Watchlist.save(); Watchlist.render(); Watchlist.refreshReadings();
      });

      const rows = document.createElement("div");
      rows.className = "group-rows";
      rows.dataset.gi = gi;
      group.tickers.forEach((sym) => rows.appendChild(Watchlist.rowEl(sym)));

      g.appendChild(head); g.appendChild(rows);
      body.appendChild(g);
    });
    if (window.Sortable) Watchlist.enableDnd();
  },

  rowEl(sym) {
    const row = document.createElement("div");
    row.className = "row" + (State.selected === sym ? " selected" : "");
    row.dataset.sym = sym;
    row.innerHTML = `
      <span class="sym">${sym}</span>
      <span class="num price"></span>
      <span class="num wr"></span>
      <span class="num rsi"></span>
      <span class="dot"></span>
      <span class="del">✕</span>`;
    row.addEventListener("click", (e) => {
      if (e.target.classList.contains("del")) { Watchlist.removeTicker(sym); return; }
      Detail.show(sym);
    });
    return row;
  },

  highlight(sym) {
    document.querySelectorAll("#watchlist-body .row").forEach((r) =>
      r.classList.toggle("selected", r.dataset.sym === sym));
  },

  async refreshReadings() {
    const syms = new Set();
    State.watchlist.groups.forEach((g) => g.tickers.forEach((t) => syms.add(t)));
    for (const sym of syms) {
      try {
        const d = await API.getTicker(sym);
        document.querySelectorAll(`#watchlist-body .row[data-sym="${sym}"]`).forEach((row) => {
          row.querySelector(".price").textContent = d.latest.price;
          row.querySelector(".wr").textContent = d.latest.wr;
          row.querySelector(".rsi").textContent = d.latest.rsi;
          const dot = row.querySelector(".dot");
          dot.style.background = stateColor(d.latest.state);
          dot.title = d.latest.state;
        });
      } catch (e) { /* skip unreadable ticker */ }
    }
  },

  addTicker(symRaw) {
    const sym = symRaw.trim().toUpperCase();
    if (!sym) return;
    const groups = State.watchlist.groups;
    if (groups.some((g) => g.tickers.includes(sym))) { Detail.show(sym); return; }
    (groups[0] || (groups[0] = { name: "Watchlist", collapsed: false, tickers: [] }))
      .tickers.push(sym);
    Watchlist.save(); Watchlist.render(); Watchlist.refreshReadings();
    Detail.show(sym);
  },

  removeTicker(sym) {
    State.watchlist.groups.forEach((g) => {
      g.tickers = g.tickers.filter((t) => t !== sym);
    });
    Watchlist.save(); Watchlist.render(); Watchlist.refreshReadings();
  },

  addGroup() {
    const name = prompt("Group name:");
    if (!name) return;
    State.watchlist.groups.push({ name, collapsed: false, tickers: [] });
    Watchlist.save(); Watchlist.render();
  },

  enableDnd() {
    // Reorder tickers within/between groups.
    document.querySelectorAll("#watchlist-body .group-rows").forEach((rowsEl) => {
      new Sortable(rowsEl, {
        group: "tickers", animation: 120, draggable: ".row",
        onEnd: () => Watchlist.syncFromDom(),
      });
    });
    // Reorder groups themselves.
    new Sortable(document.getElementById("watchlist-body"), {
      group: "groups", animation: 120, draggable: ".group", handle: ".group-head",
      onEnd: () => Watchlist.syncFromDom(),
    });
  },

  syncFromDom() {
    const body = document.getElementById("watchlist-body");
    const groups = [];
    body.querySelectorAll(".group").forEach((gEl) => {
      const gi = Number(gEl.dataset.gi);
      const existing = State.watchlist.groups[gi] || { name: "Group", collapsed: false };
      const tickers = [...gEl.querySelectorAll(".row")].map((r) => r.dataset.sym);
      groups.push({ name: existing.name, collapsed: existing.collapsed, tickers });
    });
    State.watchlist.groups = groups;
    Watchlist.save();
    Watchlist.render();
    Watchlist.refreshReadings();
  },
};
