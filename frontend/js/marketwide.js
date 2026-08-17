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
    const [scanData, statusData] = await Promise.all([
      API.getScan(State.scanTab), API.getDataStatus(),
    ]);
    Marketwide.renderStatus(scanData, statusData);
    Marketwide.renderTiles(scanData.rows);
  },

  // A compact strip shown on every marketwide view (not hidden inside Data
  // Problems), so integrity issues are impossible to overlook: which bar this
  // is, whether it's the one expected, how much of the universe is covered,
  // whether the last refresh actually succeeded, and whether the current
  // settings still match what was scanned.
  renderStatus(scanData, statusData) {
    const el = document.getElementById("scan-status");
    if (scanData.scanning) { el.textContent = "Scanning…"; return; }
    if (!scanData.scanned_at) { el.textContent = "No scan yet"; return; }

    const bar = statusData.latest_bar_date || "—";
    const expected = statusData.expected_session_date || "—";
    const cov = statusData.coverage || {};
    const covText = (cov.valid != null && cov.requested != null)
      ? `${cov.valid}/${cov.requested} (${Math.round((cov.ratio || 0) * 100)}%)` : "—";
    const compatible = statusData.configuration_compatible;
    const refreshText = Marketwide.refreshSummary(statusData);
    const warnCount = (statusData.warnings || []).length;

    el.innerHTML = `
      <span>Observation only — not trade signals</span> ·
      <span>FINAL BAR ${bar}</span> ·
      <span>EXPECTED ${expected}</span> ·
      <span>COVERAGE ${covText}</span> ·
      <span>${refreshText}</span> ·
      <span class="${compatible ? "" : "strip-warn"}">CONFIG ${compatible ? "compatible" : "PENDING RESCAN"}</span>
      ${warnCount ? `<span class="strip-warn-badge" title="${(statusData.warnings || []).join(" | ")}">⚠ ${warnCount}</span>` : ""}
    `;
  },

  refreshSummary(statusData) {
    const attempt = statusData.last_attempt;
    if (attempt && attempt.commit_outcome && attempt.commit_outcome.committed === false) {
      const when = attempt.completed_at ? new Date(attempt.completed_at).toLocaleString() : "—";
      return `<span class="strip-warn">REFRESH FAILED (${when})</span>`;
    }
    const success = statusData.last_success;
    if (success && success.completed_at) {
      return `REFRESH OK (${new Date(success.completed_at).toLocaleString()})`;
    }
    return "REFRESH —";
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
      tile.addEventListener("click", () => Detail.show(r.ticker, r));
      body.appendChild(tile);
    });
  },

  async renderDataProblems() {
    const el = document.getElementById("scan-status");
    const body = document.getElementById("marketwide-body");
    const s = await API.getDataStatus();
    el.textContent = "Data quality";

    const cov = s.coverage || {};
    const dc = s.date_coverage || {};
    const warns = s.warnings || [];
    const missing = cov.missing_symbols || [];

    const missingHtml = missing.length
      ? `<div class="dp-row"><b>Missing symbols (${missing.length}):</b>
           <span class="dp-missing">${missing.join(", ")}</span></div>`
      : "";
    const dateCoverageHtml = dc.expected_date
      ? `<div class="dp-row"><b>Session-date coverage:</b> ${dc.expected_date_count}/${cov.valid ?? "—"} on
           ${dc.expected_date} (${Math.round((dc.expected_date_ratio || 0) * 100)}%) ·
           ${dc.older_date_count} older · ${dc.newer_date_count} newer</div>`
      : "";
    const lastSuccessHtml = s.last_success
      ? `<div class="dp-row"><b>Last successful scan:</b> ${new Date(s.last_success.completed_at).toLocaleString()}
           (bar ${s.last_success.bar_date || "—"}, ${s.last_success.status})</div>`
      : `<div class="dp-row"><b>Last successful scan:</b> none yet</div>`;
    const attemptOk = s.last_attempt && s.last_attempt.commit_outcome && s.last_attempt.commit_outcome.committed;
    const lastAttemptHtml = s.last_attempt
      ? `<div class="dp-row"><b>Last attempt:</b> ${new Date(s.last_attempt.completed_at).toLocaleString()} — ` +
        (attemptOk ? "succeeded"
                   : `<span class="warn">FAILED (${(s.last_attempt.commit_outcome || {}).reason || "unknown"})</span>`) +
        `</div>`
      : "";
    const configHtml = `<div class="dp-row"><b>Configuration:</b> ` +
      (s.configuration_compatible ? "compatible with current settings"
                                  : '<span class="warn">INCOMPATIBLE with current settings — rescan pending</span>') +
      `</div>`;
    const settingsHtml = `<div class="dp-row"><b>Settings file:</b> ` +
      (s.settings_valid ? "valid"
                        : '<span class="warn">INVALID — using defaults; invalid file preserved</span>') +
      `</div>`;

    body.innerHTML = `
      <div class="data-problems">
        <div class="dp-row"><b>Freshness:</b> ${s.bar_status || "unknown"}
          (latest bar ${s.latest_bar_date || "—"}, expected ${s.expected_session_date || "—"})</div>
        ${dateCoverageHtml}
        <div class="dp-row"><b>Cache:</b> ${s.cache_status || "—"} ·
          coverage ${cov.valid ?? "—"}/${cov.requested ?? "—"} valid,
          ${cov.missing ?? "—"} missing</div>
        ${missingHtml}
        ${lastSuccessHtml}
        ${lastAttemptHtml}
        ${configHtml}
        ${settingsHtml}
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
      const [scanData, statusData] = await Promise.all([
        API.getScan(State.scanTab), API.getDataStatus(),
      ]);
      Marketwide.renderStatus(scanData, statusData);
      if (!scanData.scanning && scanData.rows.length) {
        Marketwide.renderTiles(scanData.rows);
      }
    }, 3000);
  },
};
