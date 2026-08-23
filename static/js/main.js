// ============================================
// FPL Squad Lab — frontend logic
// ============================================

const el = (id) => document.getElementById(id);

async function fetchJSON(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "Request failed");
  return data;
}

function chipHTML(player, isCaptain, isVice) {
  const badge = isCaptain ? '<span class="armband">C</span>' : (isVice ? '<span class="armband" style="background:#8A9A93;color:#0A0F0D">V</span>' : "");
  const capClass = isCaptain ? "captain" : "";
  return `
    <div class="player-chip ${capClass}">
      ${badge}
      <span class="name">${player.name}</span>
      <span class="meta">${player.team} · £${player.price.toFixed(1)} · ${player.predicted_points.toFixed(1)}pts</span>
    </div>`;
}

function renderPitch(data) {
  el("pitch-placeholder").style.display = "none";
  el("formation-badge").textContent = data.formation;

  const groups = { GKP: [], DEF: [], MID: [], FWD: [] };
  data.starting_xi.forEach((p) => groups[p.position].push(p));

  const rowMap = { GKP: "row-gkp", DEF: "row-def", MID: "row-mid", FWD: "row-fwd" };
  Object.entries(groups).forEach(([pos, players]) => {
    const rowEl = el(rowMap[pos]);
    rowEl.innerHTML = players
      .map((p) => chipHTML(p, p.id === data.captain.id, p.id === data.vice_captain.id))
      .join("");
  });

  el("dugout-row").innerHTML = data.bench.map((p) => chipHTML(p, false, false)).join("");

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

function positionClass(pos) {
  return pos.toLowerCase();
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

async function loadInjuries() {
  const listEl = el("injury-list");
  try {
    const data = await fetchJSON("/api/injuries");
    if (data.injuries.length === 0) {
      listEl.innerHTML = `<p class="table-empty">No injury news right now — full squad fitness across the league.</p>`;
      return;
    }
    listEl.innerHTML = data.injuries
      .map((p) => {
        const doubtfulClass = p.status === "d" ? "doubtful" : "";
        const chance = p.chance_of_playing_next_round;
        const chanceText = chance === null || chance === undefined ? "" : ` · ${chance}% chance next GW`;
        return `
      <div class="injury-row ${doubtfulClass}">
        <span class="injury-name">${p.name}</span>
        <span class="injury-meta">${p.team} · ${p.position}${chanceText}</span>
        <span class="injury-status">${p.status_label}</span>
        <span class="injury-news">${p.news}</span>
      </div>`;
      })
      .join("");
  } catch (e) {
    listEl.innerHTML = `<p class="table-empty">Error loading injury news: ${e.message}</p>`;
  }
}

async function checkTransfers() {
  const teamId = el("team-id-input").value;
  const freeTransfers = el("free-transfers-input").value || 1;
  const listEl = el("transfers-list");

  if (!teamId) {
    listEl.innerHTML = `<p class="transfers-hint">Enter a team ID first.</p>`;
    return;
  }

  listEl.innerHTML = `<p class="transfers-hint">Checking your squad…</p>`;
  try {
    const data = await fetchJSON(`/api/transfers?team_id=${teamId}&free_transfers=${freeTransfers}`);
    if (data.suggestions.length === 0) {
      listEl.innerHTML = `<p class="transfers-hint">No beneficial transfers found — your squad looks solid.</p>`;
      return;
    }
    listEl.innerHTML = data.suggestions
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
  } catch (e) {
    listEl.innerHTML = `<p class="transfers-hint">Error: ${e.message}</p>`;
  }
}

// ---------------- Event wiring ----------------

el("generate-btn").addEventListener("click", generateSquad);
el("refresh-btn").addEventListener("click", refreshData);
el("transfers-btn").addEventListener("click", checkTransfers);

document.querySelectorAll(".pos-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".pos-tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    loadTopPlayers(tab.dataset.pos);
  });
});

// Initial load
loadTopPlayers("ALL");
loadInjuries();

// Auto-update injury news every 5 minutes without needing a page reload
setInterval(loadInjuries, 5 * 60 * 1000);
