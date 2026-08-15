const Settings = {
  init() {
    document.getElementById("settings-btn")
      .addEventListener("click", Settings.open);
  },

  open() {
    const s = State.settings;
    const t = s.thresholds;
    const modal = document.getElementById("settings-modal");
    modal.hidden = false;
    modal.innerHTML = `
      <div class="modal-card">
        <h3>Settings</h3>
        <label>Lookback
          <select id="set-lookback">
            ${["3mo","6mo","1y","2y"].map((o) =>
              `<option ${o===s.lookback?"selected":""}>${o}</option>`).join("")}
          </select>
        </label>
        ${Settings.numRow("wr_oversold","Williams %R oversold",t)}
        ${Settings.numRow("wr_overbought","Williams %R overbought",t)}
        ${Settings.numRow("rsi_oversold","RSI oversold",t)}
        ${Settings.numRow("rsi_overbought","RSI overbought",t)}
        ${Settings.numRow("stoch_oversold","Stochastic oversold",t)}
        ${Settings.numRow("stoch_overbought","Stochastic overbought",t)}
        <div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end">
          <button class="btn" id="set-cancel">Cancel</button>
          <button class="btn" id="set-save">Save</button>
        </div>
      </div>`;
    modal.querySelector("#set-cancel").onclick = () => { modal.hidden = true; };
    modal.querySelector("#set-save").onclick = Settings.save;
  },

  numRow(key, label, t) {
    return `<label>${label}
      <input type="number" id="set-${key}" value="${t[key]}" style="width:80px" /></label>`;
  },

  async save() {
    const modal = document.getElementById("settings-modal");
    const s = State.settings;
    s.lookback = modal.querySelector("#set-lookback").value;
    ["wr_oversold","wr_overbought","rsi_oversold","rsi_overbought",
     "stoch_oversold","stoch_overbought"].forEach((k) => {
      s.thresholds[k] = Number(modal.querySelector(`#set-${k}`).value);
    });
    await API.putSettings(s);
    modal.hidden = true;
    // Re-derive everything that depends on thresholds/lookback.
    await Watchlist.refreshReadings();
    if (State.selected) Detail.show(State.selected);
    Marketwide.refresh();
  },
};
