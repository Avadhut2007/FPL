// ============================================
// FPL Squad Lab — frontend logic (multi-page)
// Every loader below guards on element presence, so this one file can be
// safely included on every page without throwing on pages that don't have
// the relevant DOM nodes.
// ============================================

const el = (id) => document.getElementById(id);

async function fetchJSON(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "Request failed");
  return data;
}

// ---------------- Navbar (mobile toggle) ----------------

if (el("nav-toggle")) {
  el("nav-toggle").addEventListener("click", () => {
    el("nav-links").classList.toggle("open");
  });
}

// ---------------- Shared chip renderer ----------------

function chipHTML(player, isCaptain, isVice, pointsLabel) {
  const badge = isCaptain
    ? '<span class="armband">C</span>'
    : isVice
    ? '<span class="armband" style="background:#8A9A93;color:#0A0F0D">V</span>'
    : "";
  const capClass = isCaptain ? "captain" : "";
  return `
    <div class="player-chip ${capClass}">
      ${badge}
      <span class="name">${player.name}</span>
      <span class="meta">${player.team} · ${pointsLabel}</span>
    </div>`;
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
    await loadTopPlayers("ALL");
  } catch (e) {
    // ignore — user will see error if they click generate
  } finally {
    btn.disabled = false;
    btn.textContent = "↻ Refresh data";
  }
}

async function loadTopPlayers(position) {
  const tbody = el("table-body");
  tbody.innerHTML = `<tr><td colspan="7" class="table-empty">Loading…</td></tr>`;
  try {
    const url = position === "ALL" ? "/api/top?n=25" : `/api/top?n=25&position=${position}`;
    const data = await fetchJSON(url);
    if (data.players.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="table-empty">No players found</td></tr>`;
      return;
    }
    tbody.innerHTML = data.players
      .map(
        (p) => `
      <tr>
        <td>${p.name}</td>
        <td>${p.team}</td>
        <td>${p.position}</td>
        <td class="mono-cell">£${p.price.toFixed(1)}</td>
        <td class="mono-cell">${p.form.toFixed(1)}</td>
        <td class="mono-cell">${p.predicted_points.toFixed(2)}</td>
        <td class="mono-cell">${p.value.toFixed(2)}</td>
      </tr>`
      )
      .join("");
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="7" class="table-empty">Error: ${e.message}</td></tr>`;
  }
}

if (el("generate-btn")) {
  el("generate-btn").addEventListener("click", generateSquad);
  el("refresh-btn").addEventListener("click", refreshData);
  document.querySelectorAll(".pos-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".pos-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      loadTopPlayers(tab.dataset.pos);
    });
  });
  loadTopPlayers("ALL");
}

// =========================================================
// TRANSFERS PAGE (FotMob-style team view + suggestions)
// =========================================================

function fmChipHTML(player) {
  const badge = player.is_captain
    ? '<span class="armband">C</span>'
    : player.is_vice_captain
    ? '<span class="armband" style="background:#8A9A93;color:#0A0F0D">V</span>'
    : "";
  const capClass = player.is_captain ? "captain" : "";
  const flag = player.status !== "a" ? ' <span style="color:#C1483F">●</span>' : "";
  return `
    <div class="player-chip ${capClass}">
      ${badge}
      <span class="name">${player.name}${flag}</span>
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
        const chance = p.chance_of_playing_next_round;
        const chanceText = chance === null || chance === undefined ? "" : ` · ${chance}% chance next GW`;
        return `
      <div class="news-row ${rowClass}">
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
// FIXTURES PAGE (single gameweek at a time, via dropdown)
// =========================================================

function difficultyClass(d) {
  if (d <= 2) return "fdr-easy";
  if (d === 3) return "fdr-mid";
  return "fdr-hard";
}

async function loadFixtures(gw) {
  const box = el("fixtures-scroll");
  box.innerHTML = `<p class="table-empty">Loading fixtures…</p>`;

  try {
    const url = gw ? `/api/fixtures?gw=${gw}` : "/api/fixtures";
    const data = await fetchJSON(url);

    const select = el("fixtures-gw-select");
    if (select.options.length === 0) {
      data.available_gameweeks.forEach((g) => {
        const opt = document.createElement("option");
        opt.value = g;
        opt.textContent = g === data.current_gameweek ? `Gameweek ${g} (current)` : `Gameweek ${g}`;
        select.appendChild(opt);
      });
    }
    select.value = data.gameweek;
    el("fixtures-gw-badge").textContent = `GW ${data.gameweek}`;

    if (data.fixtures.length === 0) {
      box.innerHTML = `<p class="table-empty">No fixtures found for this gameweek.</p>`;
      return;
    }

    box.innerHTML = data.fixtures
      .map(
        (f) => `
      <div class="fixture-row">
        <span class="fixture-team ${difficultyClass(f.home_difficulty)}">${f.home}</span>
        <span class="fixture-vs">vs</span>
        <span class="fixture-team ${difficultyClass(f.away_difficulty)}">${f.away}</span>
      </div>`
      )
      .join("");
  } catch (e) {
    box.innerHTML = `<p class="table-empty">Error loading fixtures: ${e.message}</p>`;
  }
}

if (el("fixtures-scroll")) {
  loadFixtures();
  el("fixtures-gw-select").addEventListener("change", (e) => loadFixtures(parseInt(e.target.value)));
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
            backgroundColor: "#C9A227",
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { ticks: { color: "#8A9A93" }, grid: { color: "rgba(255,255,255,0.06)" } },
          y: { ticks: { color: "#8A9A93" }, grid: { color: "rgba(255,255,255,0.06)" } },
        },
        plugins: { legend: { labels: { color: "#ECEDEA" } } },
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
