// ============================================
// FPL Squad Lab — frontend logic (multi-page)
// Every loader below guards on element presence, so this one file can be
// safely included on every page without throwing on pages that don't have
// the relevant DOM nodes.
// ============================================

const el = (id) => document.getElementById(id);

async function fetchJSON(url, timeoutMs = 12000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Request failed");
    return data;
  } finally {
    clearTimeout(timer);
  }
}

function crestImg(url, cls) {
  if (!url) return "";
  return `<img class="${cls}" src="${url}" alt="" onerror="this.style.display='none'">`;
}

// ---------------- Theme toggle ----------------

if (el("theme-toggle")) {
  const applyIcon = () => {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    el("theme-toggle").textContent = current === "dark" ? "🌙" : "☀️";
  };
  applyIcon();
  el("theme-toggle").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("fpl-theme", next);
    applyIcon();
  });
}

// ---------------- Shared chip renderer ----------------

function chipHTML(player, isCaptain, isVice, pointsLabel) {
  const badge = isCaptain
    ? '<span class="armband">C</span>'
    : isVice
    ? '<span class="armband" style="background:#8D89A0;color:#050505">V</span>'
    : "";
  const capClass = isCaptain ? "captain" : "";
  return `
    <div class="player-chip ${capClass}">
      ${badge}
      <span class="name">${crestImg(player.team_crest, "crest")}${player.name}</span>
      <span class="meta">${player.team} · ${pointsLabel}</span>
    </div>`;
}

// =========================================================
// HOME PAGE — Deadline widget
// =========================================================

let deadlineTimer = null;

function formatCountdown(deadlineIso) {
  const diff = new Date(deadlineIso).getTime() - Date.now();
  if (diff <= 0) return "Deadline has passed";
  const days = Math.floor(diff / (1000 * 60 * 60 * 24));
  const hours = Math.floor((diff / (1000 * 60 * 60)) % 24);
  const mins = Math.floor((diff / (1000 * 60)) % 60);
  const secs = Math.floor((diff / 1000) % 60);
  if (days > 0) return `${days}d ${hours}h ${mins}m`;
  if (hours > 0) return `${hours}h ${mins}m ${secs}s`;
  return `${mins}m ${secs}s`;
}

function googleCalendarUrl(deadline) {
  const start = new Date(deadline.deadline_time);
  const end = new Date(start.getTime() + 60 * 60 * 1000);
  const fmt = (d) => d.toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
  const text = encodeURIComponent(`FPL Deadline — ${deadline.name}`);
  const dates = `${fmt(start)}/${fmt(end)}`;
  const details = encodeURIComponent("Fantasy Premier League transfer deadline.");
  return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${text}&dates=${dates}&details=${details}`;
}

async function loadDeadlineWidget() {
  try {
    const data = await fetchJSON("/api/deadline");
    el("deadline-label").textContent = data.name || "Next Deadline";

    if (deadlineTimer) clearInterval(deadlineTimer);
    const tick = () => {
      el("deadline-countdown").textContent = formatCountdown(data.deadline_time);
    };
    tick();
    deadlineTimer = setInterval(tick, 1000);

    el("deadline-calendar-btn").onclick = () => {
      window.open(googleCalendarUrl(data), "_blank", "noopener");
    };
  } catch (e) {
    el("deadline-countdown").textContent = "Unavailable right now";
  }
}

// =========================================================
// SQUAD PAGE
// =========================================================

function renderPitch(data) {
  el("pitch-placeholder").style.display = "none";
  el("formation-badge").textContent = data.formation;

  const groups = { GKP: [], DEF: [], MID: [], FWD: [] };
  data.starting_xi.forEach((p) => groups[p.position].push(p));

  const rowMap = { GKP: "row-gkp", DEF: "row-def", MID: "row-mid", FWD: "row-fwd" };
  Object.entries(groups).forEach(([pos, players]) => {
    el(rowMap[pos]).innerHTML = players
      .map((p) => chipHTML(p, p.id === data.captain.id, p.id === data.vice_captain.id, `£${p.price.toFixed(1)} · ${p.predicted_points.toFixed(1)}pts`))
      .join("");
  });

  el("dugout-row").innerHTML = data.bench
    .map((p) => chipHTML(p, false, false, `£${p.price.toFixed(1)} · ${p.predicted_points.toFixed(1)}pts`))
    .join("");

  el("stat-points").textContent = data.projected_points.toFixed(1);
  el("stat-budget").textContent = `£${data.budget_used.toFixed(1)}m / £${data.budget_total.toFixed(1)}m`;
  el("budget-bar-fill").style.width = `${(data.budget_used / data.budget_total) * 100}%`;
  el("stat-captain").textContent = data.captain.name;
  el("stat-vice").textContent = data.vice_captain.name;
  el("gw-tag").textContent = `Gameweek ${data.gameweek} · live FPL data`;
}

async function generateSquad() {
  const btn = el("generate-btn");
  const budget = parseFloat(el("budget-input").value) || 100.0;
  btn.disabled = true;
  btn.textContent = "Crunching numbers…";
  el("pitch-placeholder").style.display = "flex";
  el("pitch-placeholder").textContent = "Fetching live data and optimizing…";

  try {
    const data = await fetchJSON(`/api/squad?budget=${budget}`);
    renderPitch(data);
  } catch (e) {
    el("pitch-placeholder").textContent = `Error: ${e.message}. Check your internet connection.`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate Optimal Squad";
  }
}

async function refreshData() {
  const btn = el("refresh-btn");
  btn.disabled = true;
  btn.textContent = "↻ Refreshing…";
  try {
    await fetchJSON("/api/squad?refresh=1");
    await loadTopPlayers();
  } catch (e) {
    // ignore — user will see error if they click generate
  } finally {
    btn.disabled = false;
    btn.textContent = "↻ Refresh data";
  }
}

// ---------------- Player Explorer (search + filter + expand chart) ----------------

let explorerPlayers = [];
let explorerPos = "ALL";
let expandedPlayerId = null;
let explorerChart = null;

function playerRowHTML(p) {
  return `
    <tr data-player-id="${p.id}">
      <td>${crestImg(p.team_crest, "player-row-crest")}</td>
      <td>${p.name}</td>
      <td>${p.team}</td>
      <td>${p.position}</td>
      <td class="mono-cell">£${p.price.toFixed(1)}</td>
      <td class="mono-cell">${p.form.toFixed(1)}</td>
      <td class="mono-cell">${p.predicted_points.toFixed(2)}</td>
      <td class="mono-cell">${p.value.toFixed(2)}</td>
    </tr>`;
}

function populateTeamFilter() {
  const select = el("team-filter");
  if (!select || select.options.length > 1) return;
  const teams = [...new Set(explorerPlayers.map((p) => p.team))].sort();
  teams.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t;
    select.appendChild(opt);
  });
}

function renderExplorerTable() {
  const tbody = el("table-body");
  const query = (el("player-search")?.value || "").toLowerCase().trim();
  const teamFilter = el("team-filter")?.value || "ALL";

  let visible = explorerPlayers;
  if (explorerPos !== "ALL") visible = visible.filter((p) => p.position === explorerPos);
  if (teamFilter !== "ALL") visible = visible.filter((p) => p.team === teamFilter);
  if (query) visible = visible.filter((p) => p.name.toLowerCase().includes(query));

  if (visible.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="table-empty">No players match your filters.</td></tr>`;
    return;
  }

  tbody.innerHTML = visible.map(playerRowHTML).join("");
}

async function loadTopPlayers() {
  const tbody = el("table-body");
  tbody.innerHTML = `<tr><td colspan="8" class="table-empty">Loading…</td></tr>`;
  try {
    const data = await fetchJSON("/api/top?n=150");
    explorerPlayers = data.players;
    populateTeamFilter();
    renderExplorerTable();
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" class="table-empty">Error: ${e.message}</td></tr>`;
  }
}

async function togglePlayerChart(playerId, rowEl) {
  const existing = el("expand-chart-row");
  if (existing) existing.remove();

  if (expandedPlayerId === playerId) {
    expandedPlayerId = null;
    return;
  }
  expandedPlayerId = playerId;

  const chartRow = document.createElement("tr");
  chartRow.id = "expand-chart-row";
  chartRow.className = "expand-chart-row";
  chartRow.innerHTML = `<td colspan="8"><div class="expand-chart-wrap"><canvas id="player-expand-canvas"></canvas></div></td>`;
  rowEl.after(chartRow);

  try {
    const data = await fetchJSON(`/api/player-history/${playerId}`);
    const ctx = el("player-expand-canvas").getContext("2d");
    if (explorerChart) explorerChart.destroy();
    explorerChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: data.history.map((h) => `GW${h.gw}`),
        datasets: [{
          label: "Points",
          data: data.history.map((h) => h.points),
          borderColor: "#9B6BF0",
          backgroundColor: "rgba(155, 107, 240, 0.15)",
          fill: true,
          tension: 0.25,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: "#8D89A0" }, grid: { color: "rgba(255,255,255,0.06)" } },
          y: { ticks: { color: "#8D89A0" }, grid: { color: "rgba(255,255,255,0.06)" }, beginAtZero: true },
        },
      },
    });
  } catch (e) {
    chartRow.innerHTML = `<td colspan="8" class="table-empty">Error loading history: ${e.message}</td>`;
  }
}

if (el("generate-btn")) {
  el("generate-btn").addEventListener("click", generateSquad);
  el("refresh-btn").addEventListener("click", refreshData);

  document.querySelectorAll(".pos-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".pos-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      explorerPos = tab.dataset.pos;
      renderExplorerTable();
    });
  });

  el("player-search").addEventListener("input", renderExplorerTable);
  el("team-filter").addEventListener("change", renderExplorerTable);

  el("table-body").addEventListener("click", (e) => {
    const row = e.target.closest("tr[data-player-id]");
    if (!row) return;
    togglePlayerChart(parseInt(row.dataset.playerId, 10), row);
  });

  loadTopPlayers();
}

// =========================================================
// TRANSFERS PAGE (FotMob-style team view + suggestions + injury tracker)
// =========================================================

function fmChipHTML(player) {
  const badge = player.is_captain
    ? '<span class="armband">C</span>'
    : player.is_vice_captain
    ? '<span class="armband" style="background:#8D89A0;color:#050505">V</span>'
    : "";
  const capClass = player.is_captain ? "captain" : "";
  const flag = player.status !== "a" ? ' <span style="color:#C1483F">●</span>' : "";
  return `
    <div class="player-chip ${capClass}">
      ${badge}
      <span class="name">${crestImg(player.team_crest, "crest")}${player.name}${flag}</span>
      <span class="meta">${player.team} · £${player.price.toFixed(1)}</span>
    </div>`;
}

function renderFotmobPitch(data) {
  const squad = data.squad;
  const starters = squad.filter((p) => p.slot <= 11);
  const bench = squad.filter((p) => p.slot > 11).sort((a, b) => a.slot - b.slot);

  const groups = { GKP: [], DEF: [], MID: [], FWD: [] };
  starters.forEach((p) => groups[p.position] && groups[p.position].push(p));

  const rowMap = { GKP: "fm-row-gkp", DEF: "fm-row-def", MID: "fm-row-mid", FWD: "fm-row-fwd" };
  Object.entries(groups).forEach(([pos, players]) => {
    el(rowMap[pos]).innerHTML = players.map(fmChipHTML).join("");
  });

  el("fm-dugout-row").innerHTML = bench.map(fmChipHTML).join("");

  el("team-name-display").textContent = data.team_name;
  el("manager-name-display").textContent = data.manager_name;
  el("team-points").textContent = data.overall_points ?? "—";
  el("team-rank").textContent = data.overall_rank ? data.overall_rank.toLocaleString() : "—";
  el("team-bank").textContent = `£${data.bank.toFixed(1)}m`;
  el("team-card").style.display = "block";
}

function renderTransferSuggestions(suggestions) {
  const listEl = el("transfers-list");
  if (suggestions.length === 0) {
    listEl.innerHTML = `<p class="transfers-hint">No beneficial transfers found — your squad looks solid.</p>`;
    return;
  }
  listEl.innerHTML = suggestions
    .map(
      (s) => `
    <div class="transfer-row">
      <span class="transfer-out">OUT: ${s.out} (${s.out_points})</span>
      <span class="transfer-arrow">→</span>
      <span class="transfer-in">IN: ${s.in} (${s.in_points})</span>
      <span class="transfer-gain">+${s.gain} pts · ${s.price_delta >= 0 ? "+" : ""}${s.price_delta}m</span>
    </div>`
    )
    .join("");
}

function renderInjuryTracker(flagged, suggestions) {
  const panel = el("injury-tracker-panel");
  const listEl = el("injury-tracker-list");

  if (!flagged || flagged.length === 0) {
    panel.style.display = "none";
    return;
  }
  panel.style.display = "block";

  const suggestionByOutId = {};
  suggestions.forEach((s) => { suggestionByOutId[s.out_id] = s; });

  listEl.innerHTML = flagged
    .map((p) => {
      const suggestion = suggestionByOutId[p.id];
      const suggestionHTML = suggestion
        ? `<div class="injury-suggestion">Suggested swap: <span class="transfer-in">${suggestion.in}</span> (+${suggestion.gain} pts · ${suggestion.price_delta >= 0 ? "+" : ""}${suggestion.price_delta}m)</div>`
        : `<div class="injury-suggestion">No affordable upgrade found within your budget.</div>`;
      return `
      <div class="injury-row">
        ${crestImg(p.team_crest, "injury-crest")}
        <span class="injury-name">${p.name}</span>
        <span class="injury-meta">${p.team} · ${p.position}</span>
        <span class="news-status">${p.status_label}</span>
        ${p.news ? `<span class="news-item-text">${p.news}</span>` : ""}
        ${suggestionHTML}
      </div>`;
    })
    .join("");
}

async function analyzeMyTeam() {
  const teamId = el("team-id-input").value;
  const freeTransfers = el("free-transfers-input").value || 1;
  const listEl = el("transfers-list");
  const btn = el("load-team-btn");

  if (!teamId) {
    listEl.innerHTML = `<p class="transfers-hint">Enter a team ID first.</p>`;
    return;
  }

  btn.disabled = true;
  btn.textContent = "Analyzing…";
  listEl.innerHTML = `<p class="transfers-hint">Fetching your squad and checking for upgrades…</p>`;
  el("injury-tracker-panel").style.display = "none";

  try {
    const [teamData, transferData, injuryData] = await Promise.all([
      fetchJSON(`/api/team/${teamId}`),
      fetchJSON(`/api/transfers?team_id=${teamId}&free_transfers=${freeTransfers}`),
      fetchJSON(`/api/injury-tracker/${teamId}`),
    ]);

    renderFotmobPitch(teamData);
    renderTransferSuggestions(transferData.suggestions);
    renderInjuryTracker(injuryData.flagged_players, injuryData.suggestions);
  } catch (e) {
    listEl.innerHTML = `<p class="transfers-hint">Error: ${e.message}</p>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Analyze My Team";
  }
}

if (el("load-team-btn")) {
  el("load-team-btn").addEventListener("click", analyzeMyTeam);
}

// =========================================================
// PLAYER NEWS PAGE
// =========================================================

async function loadPlayerNews() {
  const listEl = el("news-list");
  try {
    const data = await fetchJSON("/api/news");
    if (data.news.length === 0) {
      listEl.innerHTML = `<p class="table-empty">No player news right now.</p>`;
      return;
    }
    listEl.innerHTML = data.news
      .map((p) => {
        const rowClass = p.status === "d" ? "doubtful" : p.status !== "a" ? "unavailable" : "";
        const chance = p.chance_of_playing_next_round;
        const chanceText = chance === null || chance === undefined ? "" : ` · ${chance}% chance next GW`;
        return `
      <div class="news-row ${rowClass}">
        ${crestImg(p.team_crest, "news-crest")}
        <span class="news-name">${p.name}</span>
        <span class="news-meta">${p.team} · ${p.position}${chanceText}</span>
        <span class="news-status">${p.status_label}</span>
        <span class="news-item-text">${p.news}</span>
      </div>`;
      })
      .join("");
  } catch (e) {
    listEl.innerHTML = `<p class="table-empty">Error loading player news: ${e.message}</p>`;
  }
}

if (el("news-list")) {
  loadPlayerNews();
  setInterval(loadPlayerNews, 5 * 60 * 1000);
}

// =========================================================
// FIXTURES PAGE (team x gameweek FDR grid)
// =========================================================

function fdrCellHTML(cell) {
  if (!cell) return `<td><span class="table-empty-cell">—</span></td>`;
  const venue = cell.is_home ? "H" : "A";
  return `<td><span class="fdr-cell fdr-${cell.difficulty}">${cell.opponent} (${venue})</span></td>`;
}

async function loadFdrGrid() {
  const table = el("fdr-grid");
  try {
    const data = await fetchJSON("/api/fixtures");

    const headRow = data.gameweeks.map((gw) => `<th>GW${gw}</th>`).join("");
    table.querySelector("thead").innerHTML = `<tr><th>Team</th>${headRow}</tr>`;

    if (data.teams.length === 0) {
      table.querySelector("tbody").innerHTML = `<tr><td class="table-empty">No fixtures found.</td></tr>`;
      return;
    }

    table.querySelector("tbody").innerHTML = data.teams
      .map((t) => {
        const cells = t.fixtures.map(fdrCellHTML).join("");
        return `<tr><td class="fdr-team-cell">${crestImg(t.team_crest, "")}${t.team}</td>${cells}</tr>`;
      })
      .join("");
  } catch (e) {
    table.querySelector("tbody").innerHTML = `<tr><td class="table-empty">Error loading fixtures: ${e.message}</td></tr>`;
  }
}

if (el("fdr-grid")) {
  loadFdrGrid();
}

// =========================================================
// PAST PERFORMANCE PAGE (paginated — covers ALL players)
// =========================================================

let historyOffset = 0;
const HISTORY_PAGE_SIZE = 50;
let historyAllRows = []; // accumulated {html, name} for client-side search

function historyRowHTML(p) {
  const seasonCells = [0, 1, 2]
    .map((i) => {
      const s = p.seasons[i];
      return s
        ? `<td class="mono-cell">${s.season}: ${s.points}</td>`
        : `<td class="mono-cell table-empty-cell">—</td>`;
    })
    .join("");
  return `
    <tr>
      <td>${p.name}</td>
      <td>${p.team}</td>
      <td>${p.position}</td>
      <td class="mono-cell">${p.current_points}</td>
      ${seasonCells}
    </tr>`;
}

function renderHistoryRows() {
  const tbody = el("history-body");
  const query = (el("history-search")?.value || "").toLowerCase().trim();
  const visible = query
    ? historyAllRows.filter((r) => r.name.toLowerCase().includes(query))
    : historyAllRows;

  tbody.innerHTML = visible.length
    ? visible.map((r) => r.html).join("")
    : `<tr><td colspan="7" class="table-empty">No players match "${query}".</td></tr>`;
}

async function loadHistoryPage() {
  const btn = el("load-more-btn");
  const status = el("history-status");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Loading…";
  }

  try {
    const data = await fetchJSON(`/api/history?offset=${historyOffset}&limit=${HISTORY_PAGE_SIZE}`);
    data.players.forEach((p) => historyAllRows.push({ name: p.name, html: historyRowHTML(p) }));
    historyOffset += data.limit;

    renderHistoryRows();

    if (status) {
      status.textContent = `Showing ${historyAllRows.length} of ${data.total} players`;
      if (!data.has_more) {
        status.textContent += " — that's everyone.";
      }
    }
    if (!data.has_more && btn) {
      btn.style.display = "none";
    }
  } catch (e) {
    if (status) status.textContent = `Error: ${e.message}`;
  } finally {
    if (btn && btn.style.display !== "none") {
      btn.disabled = false;
      btn.textContent = "Load More Players";
    }
  }
}

if (el("history-body")) {
  loadHistoryPage(); // first page on load
  el("load-more-btn").addEventListener("click", loadHistoryPage);
  el("history-search").addEventListener("input", renderHistoryRows);
}

// =========================================================
// CHART PAGE (Chart.js bar chart: predicted vs total points)
// =========================================================

let pointsChart = null;

async function loadChartData() {
  const n = parseInt(el("chart-n-input")?.value) || 12;
  const position = el("chart-position-select")?.value || "ALL";
  const metric = el("chart-metric-select")?.value || "predicted_points";

  try {
    const data = await fetchJSON(`/api/chart-data?n=${n}&position=${position}&metric=${metric}`);
    el("chart-gw-tag").textContent = `Gameweek ${data.gameweek}`;

    const ctx = el("points-chart").getContext("2d");
    const values = metric === "total_points" ? data.total_points : data.predicted_points;
    const label = metric === "total_points" ? "Total points (season)" : "Predicted points (next GW)";

    if (pointsChart) pointsChart.destroy();
    pointsChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: data.labels,
        datasets: [
          {
            label,
            data: values,
            backgroundColor: "#9B6BF0",
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { ticks: { color: "#8D89A0" }, grid: { color: "rgba(255,255,255,0.06)" } },
          y: { ticks: { color: "#8D89A0" }, grid: { color: "rgba(255,255,255,0.06)" } },
        },
        plugins: { legend: { labels: { color: "#EDEBF2" } } },
      },
    });
  } catch (e) {
    el("chart-gw-tag").textContent = `Error: ${e.message}`;
  }
}

if (el("points-chart")) {
  loadChartData();
  el("chart-refresh-btn").addEventListener("click", loadChartData);
  el("chart-position-select").addEventListener("change", loadChartData);
  el("chart-metric-select").addEventListener("change", loadChartData);
}

// =========================================================
// LIVE SCORES PAGE
// =========================================================

async function loadLiveScores() {
  const listEl = el("live-scores-list");
  try {
    const data = await fetchJSON("/api/live-scores");
    if (data.games.length === 0) {
      listEl.innerHTML = `<p class="table-empty">No games scheduled today.</p>`;
      return;
    }
    listEl.innerHTML = data.games
      .map((g) => {
        const statusClass = g.is_live ? "is-live" : "";
        return `
      <div class="live-score-row">
        <span class="live-score-teams">
          ${crestImg(g.home_crest, "")}${g.home_team} ${g.home_score} — ${g.away_score} ${g.away_team}${crestImg(g.away_crest, "")}
        </span>
        <span class="live-score-status ${statusClass}">${g.status}</span>
      </div>`;
      })
      .join("");
  } catch (e) {
    listEl.innerHTML = `<p class="table-empty">Live scores unavailable right now.</p>`;
  }
}

async function loadStandings() {
  const tbody = el("standings-body");
  try {
    const data = await fetchJSON("/api/standings");
    if (data.table.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" class="table-empty">Standings unavailable right now.</td></tr>`;
      return;
    }
    tbody.innerHTML = data.table
      .map(
        (t) => `
      <tr>
        <td class="mono-cell">${t.rank ?? "—"}</td>
        <td>${crestImg(t.crest, "standings-crest")}</td>
        <td>${t.team}</td>
        <td class="mono-cell">${t.played ?? "—"}</td>
        <td class="mono-cell">${t.won ?? "—"}</td>
        <td class="mono-cell">${t.drawn ?? "—"}</td>
        <td class="mono-cell">${t.lost ?? "—"}</td>
        <td class="mono-cell">${t.goal_diff ?? "—"}</td>
        <td class="mono-cell">${t.points ?? "—"}</td>
      </tr>`
      )
      .join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="9" class="table-empty">Standings unavailable right now.</td></tr>`;
  }
}

if (el("live-scores-list")) {
  loadLiveScores();
  loadStandings();
}

// =========================================================
// TRANSFER NEWS PAGE
// =========================================================

async function loadTransferNews() {
  const listEl = el("transfer-news-list");
  try {
    const data = await fetchJSON("/api/transfer-news");
    if (data.news.length === 0) {
      listEl.innerHTML = `<p class="table-empty">No transfer news right now.</p>`;
      return;
    }
    listEl.innerHTML = data.news
      .map(
        (n) => `
      <div class="transfer-news-item">
        <a href="${n.link}" target="_blank" rel="noopener">${n.title}</a>
        <span class="news-meta">${n.published}</span>
      </div>`
      )
      .join("");
  } catch (e) {
    listEl.innerHTML = `<p class="table-empty">Transfer news unavailable right now.</p>`;
  }
}

if (el("transfer-news-list")) {
  loadTransferNews();
}
