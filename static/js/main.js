// ============================================
// FPL Squad Lab — frontend logic (all pages)
// Every loader guards on element presence, so this one file is safely
// included on every page without throwing on pages missing certain nodes.
// ============================================

const el = (id) => document.getElementById(id);

async function fetchJSON(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "Request failed");
  return data;
}

function crestImg(url, alt, cls) {
  if (!url) return "";
  return `<img src="${url}" alt="${alt}" class="${cls}" onerror="this.style.display='none'">`;
}

// ---------------- Navbar ----------------

if (el("nav-toggle")) {
  el("nav-toggle").addEventListener("click", () => el("nav-links").classList.toggle("open"));
}

// ---------------- Theme toggle ----------------

function applyThemeButtonIcon() {
  const theme = document.documentElement.getAttribute("data-theme") || "dark";
  const btn = el("theme-toggle");
  if (btn) btn.textContent = theme === "dark" ? "🌙" : "☀️";
}
applyThemeButtonIcon();

if (el("theme-toggle")) {
  el("theme-toggle").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("fpl-theme", next);
    applyThemeButtonIcon();
  });
}

// =========================================================
// DEADLINE REMINDER (home page)
// =========================================================

let deadlineTimestamp = null;
let deadlineIntervalId = null;

function formatCountdown(ms) {
  if (ms <= 0) return "Deadline has passed";
  const totalSeconds = Math.floor(ms / 1000);
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  return `${hours}h ${minutes}m`;
}

function tickDeadlineCountdown() {
  if (!deadlineTimestamp) return;
  const remaining = deadlineTimestamp - Date.now();
  el("deadline-countdown").textContent = formatCountdown(remaining);
}

function buildGoogleCalendarLink(deadlineISO, gwName) {
  const start = new Date(deadlineISO);
  const end = new Date(start.getTime() + 30 * 60 * 1000); // 30 min block
  const fmt = (d) => d.toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
  const text = encodeURIComponent(`FPL Deadline — ${gwName}`);
  const details = encodeURIComponent("Fantasy Premier League transfer deadline. Set your team before this time!");
  return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${text}&dates=${fmt(start)}/${fmt(end)}&details=${details}`;
}

async function loadDeadlineWidget() {
  if (!el("deadline-banner")) return;
  try {
    const data = await fetchJSON("/api/deadline");
    deadlineTimestamp = new Date(data.deadline_time).getTime();
    el("deadline-label").textContent = `${data.name} Deadline`;
    tickDeadlineCountdown();
    if (deadlineIntervalId) clearInterval(deadlineIntervalId);
    deadlineIntervalId = setInterval(tickDeadlineCountdown, 60 * 1000);

    el("deadline-calendar-btn").addEventListener("click", () => {
      window.open(buildGoogleCalendarLink(data.deadline_time, data.name), "_blank");
    });
  } catch (e) {
    el("deadline-countdown").textContent = "Unable to load deadline";
  }
}

// =========================================================
// SHARED PLAYER CHIP RENDERER (squad + transfers pitches)
// =========================================================

function chipHTML(player, isCaptain, isVice, pointsLabel) {
  const badge = isCaptain
    ? '<span class="armband">C</span>'
    : isVice
    ? '<span class="armband" style="background:#8A9A93;color:#0A0F0D">V</span>'
    : "";
  const capClass = isCaptain ? "captain" : "";
  const crest = crestImg(player.team_crest, player.team, "crest");
  return `
    <div class="player-chip ${capClass}">
      ${badge}
      <span class="name">${crest}${player.name}</span>
      <span class="meta">${player.team} · ${pointsLabel}</span>
    </div>`;
}

// =========================================================
// SQUAD BUILDER PAGE
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
    el("pitch-placeholder").textContent = `Error: ${e.message}`;
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
    // ignore — surfaces on next generate/search
  } finally {
    btn.disabled = false;
    btn.textContent = "↻ Refresh data";
  }
}

// ---- Player Explorer: search + team filter + expand-to-chart ----

let explorerAllPlayers = [];
let explorerCurrentPos = "ALL";
let explorerChart = null;
let explorerOpenRowId = null;

function explorerRowHTML(p) {
  const crest = crestImg(p.team_crest, p.team, "player-row-crest");
  return `
    <tr data-player-id="${p.id}" class="explorer-row">
      <td>${crest}</td>
      <td>${p.name}</td>
      <td>${p.team}</td>
      <td>${p.position}</td>
      <td class="mono-cell">£${p.price.toFixed(1)}</td>
      <td class="mono-cell">${p.form.toFixed(1)}</td>
      <td class="mono-cell">${p.predicted_points.toFixed(2)}</td>
      <td class="mono-cell">${p.value.toFixed(2)}</td>
    </tr>`;
}

function renderExplorerTable() {
  const tbody = el("table-body");
  const query = (el("player-search")?.value || "").toLowerCase().trim();
  const team = el("team-filter")?.value || "ALL";

  let rows = explorerAllPlayers;
  if (explorerCurrentPos !== "ALL") rows = rows.filter((p) => p.position === explorerCurrentPos);
  if (team !== "ALL") rows = rows.filter((p) => p.team === team);
  if (query) rows = rows.filter((p) => p.name.toLowerCase().includes(query));

  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="table-empty">No players match your filters.</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(explorerRowHTML).join("");
}

async function toggleExpandChart(playerId, rowEl) {
  // Close if the same row is already open
  const existing = document.querySelector(".expand-chart-row");
  if (existing) {
    if (explorerChart) explorerChart.destroy();
    existing.remove();
    if (explorerOpenRowId === playerId) {
      explorerOpenRowId = null;
      return;
    }
  }

  explorerOpenRowId = playerId;
  const tr = document.createElement("tr");
  tr.className = "expand-chart-row";
  tr.innerHTML = `<td colspan="8"><div class="expand-chart-wrap"><canvas></canvas></div></td>`;
  rowEl.after(tr);

  try {
    const data = await fetchJSON(`/api/player-history/${playerId}`);
    const canvas = tr.querySelector("canvas");
    const ctx = canvas.getContext("2d");
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
          x: { ticks: { color: "#8D89A0", maxRotation: 0 }, grid: { color: "rgba(255,255,255,0.05)" } },
          y: { ticks: { color: "#8D89A0" }, grid: { color: "rgba(255,255,255,0.05)" }, beginAtZero: true },
        },
      },
    });
  } catch (e) {
    tr.querySelector("td").innerHTML = `<p class="table-empty">Error loading history: ${e.message}</p>`;
  }
}

async function loadTopPlayers() {
  const tbody = el("table-body");
  tbody.innerHTML = `<tr><td colspan="8" class="table-empty">Loading…</td></tr>`;
  try {
    const data = await fetchJSON("/api/top?n=100");
    explorerAllPlayers = data.players;

    const teamFilter = el("team-filter");
    if (teamFilter && teamFilter.options.length === 1) {
      const teams = [...new Set(explorerAllPlayers.map((p) => p.team))].sort();
      teams.forEach((t) => {
        const opt = document.createElement("option");
        opt.value = t;
        opt.textContent = t;
        teamFilter.appendChild(opt);
      });
    }

    renderExplorerTable();
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="8" class="table-empty">Error: ${e.message}</td></tr>`;
  }
}

if (el("generate-btn")) {
  el("generate-btn").addEventListener("click", generateSquad);
  el("refresh-btn").addEventListener("click", refreshData);
  document.querySelectorAll(".pos-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".pos-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      explorerCurrentPos = tab.dataset.pos;
      renderExplorerTable();
    });
  });
  if (el("player-search")) el("player-search").addEventListener("input", renderExplorerTable);
  if (el("team-filter")) el("team-filter").addEventListener("change", renderExplorerTable);

  el("table-body").addEventListener("click", (e) => {
    const row = e.target.closest(".explorer-row");
    if (!row) return;
    toggleExpandChart(parseInt(row.dataset.playerId), row);
  });

  loadTopPlayers();
}
// =========================================================
// TRANSFERS PAGE (FotMob-style pitch + suggestions + injury tracker)
// =========================================================

function fmChipHTML(player) {
  const badge = player.is_captain
    ? '<span class="armband">C</span>'
    : player.is_vice_captain
    ? '<span class="armband" style="background:#8A9A93;color:#0A0F0D">V</span>'
    : "";
  const capClass = player.is_captain ? "captain" : "";
  const flag = player.status !== "a" ? ' <span style="color:#C1483F">●</span>' : "";
  const crest = crestImg(player.team_crest, player.team, "crest");
  return `
    <div class="player-chip ${capClass}">
      ${badge}
      <span class="name">${crest}${player.name}${flag}</span>
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

async function loadInjuryTracker(teamId) {
  const panel = el("injury-tracker-panel");
  const list = el("injury-tracker-list");
  if (!panel) return;

  try {
    const data = await fetchJSON(`/api/injury-tracker/${teamId}`);
    if (data.flagged_players.length === 0) {
      panel.style.display = "none";
      return;
    }
    panel.style.display = "block";

    const suggestionByOutId = {};
    data.suggestions.forEach((s) => { suggestionByOutId[s.out_id] = s; });

    list.innerHTML = data.flagged_players
      .map((p) => {
        const crest = crestImg(p.team_crest, p.team, "injury-crest");
        const suggestion = suggestionByOutId[p.id];
        const suggestionHTML = suggestion
          ? `<div class="injury-suggestion"><span class="transfer-out">${suggestion.out}</span> → <span class="transfer-in">${suggestion.in}</span> <span class="mono-cell">(+${suggestion.gain} pts)</span></div>`
          : `<div class="injury-suggestion table-empty-cell">No clear upgrade found right now.</div>`;
        return `
        <div class="injury-row">
          ${crest}
          <span class="injury-name">${p.name}</span>
          <span class="injury-meta">${p.team} · ${p.position}</span>
          <span class="news-status">${p.status_label}</span>
          ${p.news ? `<span class="news-item-text">${p.news}</span>` : ""}
          ${suggestionHTML}
        </div>`;
      })
      .join("");
  } catch (e) {
    panel.style.display = "block";
    list.innerHTML = `<p class="table-empty">Error loading injury tracker: ${e.message}</p>`;
  }
}

async function loadBestLineup(teamId) {
  const panel = el("lineup-panel");
  if (!panel) return;

  try {
    const data = await fetchJSON(`/api/best-lineup/${teamId}`);
    panel.style.display = "block";
    el("lineup-formation-badge").textContent = data.formation;

    const groups = { GKP: [], DEF: [], MID: [], FWD: [] };
    data.starting_xi.forEach((p) => groups[p.position].push(p));

    const rowMap = { GKP: "lineup-row-gkp", DEF: "lineup-row-def", MID: "lineup-row-mid", FWD: "lineup-row-fwd" };
    Object.entries(groups).forEach(([pos, players]) => {
      el(rowMap[pos]).innerHTML = players
        .map((p) => chipHTML(p, p.id === data.captain.id, p.id === data.vice_captain.id, `${p.predicted_points.toFixed(1)}pts`))
        .join("");
    });

    el("lineup-dugout-row").innerHTML = data.bench
      .map((p) => chipHTML(p, false, false, `${p.predicted_points.toFixed(1)}pts`))
      .join("");
  } catch (e) {
    panel.style.display = "block";
    panel.querySelector(".pitch").innerHTML = `<p class="pitch-placeholder">Error loading recommended lineup: ${e.message}</p>`;
  }
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

  try {
    const [teamData, transferData] = await Promise.all([
      fetchJSON(`/api/team/${teamId}`),
      fetchJSON(`/api/transfers?team_id=${teamId}&free_transfers=${freeTransfers}`),
    ]);

    renderFotmobPitch(teamData);
    loadBestLineup(teamId);
    loadInjuryTracker(teamId);

    if (transferData.suggestions.length === 0) {
      listEl.innerHTML = `<p class="transfers-hint">No beneficial transfers found — your squad looks solid.</p>`;
    } else {
      listEl.innerHTML = transferData.suggestions
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
        const crest = crestImg(p.team_crest, p.team, "news-crest");
        const chance = p.chance_of_playing_next_round;
        const chanceText = chance === null || chance === undefined ? "" : ` · ${chance}% chance next GW`;
        return `
      <div class="news-row ${rowClass}">
        ${crest}
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
// FIXTURES PAGE (FDR color grid)
// =========================================================

function fdrClass(d) {
  return `fdr-${d}`;
}

async function loadFdrGrid() {
  const table = el("fdr-grid");
  if (!table) return;

  try {
    const data = await fetchJSON("/api/fixtures");
    const thead = table.querySelector("thead tr");
    thead.innerHTML = `<th>Team</th>` + data.gameweeks.map((gw) => `<th>GW${gw}</th>`).join("");

    const tbody = table.querySelector("tbody") || table.createTBody();
    tbody.innerHTML = data.teams
      .map((row) => {
        const crest = crestImg(row.team_crest, row.team, "");
        const cells = row.fixtures
          .map((f) => {
            if (!f) return `<td><span class="fdr-cell fdr-3">—</span></td>`;
            const venue = f.is_home ? "H" : "A";
            return `<td><span class="fdr-cell ${fdrClass(f.difficulty)}">${f.opponent} (${venue})</span></td>`;
          })
          .join("");
        return `<tr><td class="fdr-team-cell">${crest}${row.team}</td>${cells}</tr>`;
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
let historyAllRows = [];

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

    status.textContent = `Showing ${historyAllRows.length} of ${data.total} players`;
    if (!data.has_more) {
      btn.style.display = "none";
      status.textContent += " — that's everyone.";
    }
  } catch (e) {
    status.textContent = `Error: ${e.message}`;
  } finally {
    if (btn && btn.style.display !== "none") {
      btn.disabled = false;
      btn.textContent = "Load More Players";
    }
  }
}

if (el("history-body")) {
  loadHistoryPage();
  el("load-more-btn").addEventListener("click", loadHistoryPage);
  el("history-search").addEventListener("input", renderHistoryRows);
}

// =========================================================
// LIVE SCORES & LEAGUE TABLE PAGE
// =========================================================

async function loadLiveScores() {
  const box = el("live-scores-list");
  if (!box) return;
  try {
    const data = await fetchJSON("/api/live-scores");
    if (data.games.length === 0) {
      box.innerHTML = `<p class="table-empty">No games scheduled today.</p>`;
      return;
    }
    box.innerHTML = data.games
      .map((g) => {
        const homeCrest = crestImg(g.home_crest, g.home_team, "");
        const awayCrest = crestImg(g.away_crest, g.away_team, "");
        const statusClass = g.is_live ? "is-live" : "";
        return `
        <div class="live-score-row">
          <div class="live-score-teams">${homeCrest}${g.home_team} ${g.home_score} - ${g.away_score} ${g.away_team}${awayCrest}</div>
          <span class="live-score-status ${statusClass}">${g.status}</span>
        </div>`;
      })
      .join("");
  } catch (e) {
    box.innerHTML = `<p class="table-empty">Error loading scores: ${e.message}</p>`;
  }
}

async function loadStandings() {
  const tbody = el("standings-body");
  if (!tbody) return;
  try {
    const data = await fetchJSON("/api/standings");
    if (data.table.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" class="table-empty">Standings unavailable right now.</td></tr>`;
      return;
    }
    tbody.innerHTML = data.table
      .map((t) => {
        const crest = crestImg(t.crest, t.team, "standings-crest");
        return `
        <tr>
          <td class="mono-cell">${t.rank}</td>
          <td>${crest}</td>
          <td>${t.team}</td>
          <td class="mono-cell">${t.played}</td>
          <td class="mono-cell">${t.won}</td>
          <td class="mono-cell">${t.drawn}</td>
          <td class="mono-cell">${t.lost}</td>
          <td class="mono-cell">${t.goal_diff}</td>
          <td class="mono-cell">${t.points}</td>
        </tr>`;
      })
      .join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="9" class="table-empty">Error loading table: ${e.message}</td></tr>`;
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
  const box = el("transfer-news-list");
  if (!box) return;
  try {
    const data = await fetchJSON("/api/transfer-news");
    if (data.news.length === 0) {
      box.innerHTML = `<p class="table-empty">No transfer headlines found right now.</p>`;
      return;
    }
    box.innerHTML = data.news
      .map(
        (n) => `
      <div class="transfer-news-item">
        <a href="${n.link}" target="_blank" rel="noopener">${n.title}</a>
        <span class="news-meta">${n.published}</span>
      </div>`
      )
      .join("");
  } catch (e) {
    box.innerHTML = `<p class="table-empty">Error loading transfer news: ${e.message}</p>`;
  }
}

if (el("transfer-news-list")) {
  loadTransferNews();
}