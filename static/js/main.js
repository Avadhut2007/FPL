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