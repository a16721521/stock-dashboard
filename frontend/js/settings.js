// Only Williams %R and RSI thresholds affect the Observation state and the
// marketwide ranking (see backend.ranking / classify_state). Stochastic
// thresholds only draw the chart overlay lines in the detail view — they are
// deliberately NOT a ranking factor (raw Stochastic %K is ~0.95 correlated
// with Williams %R, so counting both would double-count the same signal).
// Grouping them separately in the UI keeps that distinction visible instead
// of implying all six sliders equally drive the ranking.
const RANKING_KEYS = ["wr_oversold", "wr_overbought", "rsi_oversold", "rsi_overbought"];
const CHART_ONLY_KEYS = ["stoch_oversold", "stoch_overbought"];
const THRESHOLD_KEYS = [...RANKING_KEYS, ...CHART_ONLY_KEYS];

const SLIDER_CONFIG = {
  wr_oversold: { label: "Williams %R oversold", min: -100, max: 0, step: 1 },
  wr_overbought: { label: "Williams %R overbought", min: -100, max: 0, step: 1 },
  rsi_oversold: { label: "RSI oversold", min: 0, max: 100, step: 1 },
  rsi_overbought: { label: "RSI overbought", min: 0, max: 100, step: 1 },
  stoch_oversold: { label: "Stochastic oversold", min: 0, max: 100, step: 1 },
  stoch_overbought: { label: "Stochastic overbought", min: 0, max: 100, step: 1 },
};

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
        <label class="slider-row">
          <span class="sl-label">Lookback</span>
          <select id="set-lookback">
            ${["3mo", "6mo", "1y", "2y"].map((o) =>
              `<option ${o === s.lookback ? "selected" : ""}>${o}</option>`).join("")}
          </select>
        </label>

        <div class="settings-section-label">Ranking factors — drive Observation state &amp; marketwide ranking</div>
        ${RANKING_KEYS.map((k) => Settings.sliderRow(k, t)).join("")}

        <div class="settings-section-label">Chart overlay only — not a ranking factor</div>
        ${CHART_ONLY_KEYS.map((k) => Settings.sliderRow(k, t)).join("")}

        <div id="set-error" class="set-error" hidden></div>
        <div class="modal-actions">
          <button class="btn" id="set-cancel">Cancel</button>
          <button class="btn" id="set-save">Save</button>
        </div>
      </div>`;

    // Live value readouts.
    THRESHOLD_KEYS.forEach((k) => {
      const slider = modal.querySelector(`#set-${k}`);
      const out = modal.querySelector(`#val-${k}`);
      slider.addEventListener("input", () => { out.textContent = slider.value; });
    });
    modal.querySelector("#set-cancel").onclick = () => { modal.hidden = true; };
    modal.querySelector("#set-save").onclick = Settings.save;
  },

  sliderRow(key, t) {
    const c = SLIDER_CONFIG[key];
    return `<label class="slider-row">
      <span class="sl-label">${c.label}</span>
      <input type="range" id="set-${key}" min="${c.min}" max="${c.max}"
             step="${c.step}" value="${t[key]}" />
      <span class="sl-val" id="val-${key}">${t[key]}</span>
    </label>`;
  },

  async save() {
    const modal = document.getElementById("settings-modal");
    const thresholds = {};
    THRESHOLD_KEYS.forEach((k) => {
      thresholds[k] = Number(modal.querySelector(`#set-${k}`).value);
    });
    const candidate = {
      thresholds,
      lookback: modal.querySelector("#set-lookback").value,
    };

    const res = await API.putSettings(candidate);
    if (!res.ok) {
      const err = modal.querySelector("#set-error");
      err.hidden = false;
      err.textContent = "Invalid: each oversold must be below its overbought, " +
        "within range (Williams %R −100…0, RSI & Stochastic 0…100).";
      return;   // keep modal open, don't touch in-memory settings
    }

    State.settings = candidate;   // commit only after the server accepts it
    modal.hidden = true;
    await Watchlist.refreshReadings();
    if (State.selected) Detail.show(State.selected);
    Marketwide.refresh();
  },
};
