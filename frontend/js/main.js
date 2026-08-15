async function boot() {
  State.settings = await API.getSettings();
  await Watchlist.load();
  Marketwide.init();
  Settings.init();

  document.getElementById("add-to-watchlist").addEventListener("click", (e) => {
    const sym = e.currentTarget.dataset.sym;
    if (sym) Watchlist.addTicker(sym);
  });

  const addInput = document.getElementById("add-ticker");
  addInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { Watchlist.addTicker(addInput.value); addInput.value = ""; }
  });
  document.getElementById("add-group").addEventListener("click", () => Watchlist.addGroup());
}
document.addEventListener("DOMContentLoaded", boot);
