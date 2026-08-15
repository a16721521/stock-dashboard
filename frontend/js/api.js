const API = {
  async getWatchlist() { return (await fetch("/api/watchlist")).json(); },
  async putWatchlist(data) {
    await fetch("/api/watchlist", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  },
  async getSettings() { return (await fetch("/api/settings")).json(); },
  async putSettings(data) {
    await fetch("/api/settings", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  },
  async getTicker(sym) {
    const r = await fetch(`/api/ticker/${encodeURIComponent(sym)}`);
    if (!r.ok) throw new Error(`No data for ${sym}`);
    return r.json();
  },
  async getScan(tab) { return (await fetch(`/api/scan?tab=${tab}`)).json(); },
  async runScan() { await fetch("/api/scan/run", { method: "POST" }); },
};
