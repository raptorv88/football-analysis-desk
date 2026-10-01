// --- Tab switching ---
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "predict") loadUpcoming();
  });
});

document.querySelectorAll("[data-go]").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelector(`[data-tab="${button.dataset.go}"]`).click();
  });
});

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
  return res.json();
}

async function loadSideRails() {
  try {
    const news = await getJSON("/api/news?limit=5");
    document.getElementById("side-news").innerHTML = news.length
      ? news.map((item, index) => `<a class="side-news-item" href="${item.url}" target="_blank" rel="noreferrer"><span>${String(index + 1).padStart(2, "0")} · ${item.source}</span><strong>${item.title}</strong></a>`).join("")
      : "<p class=\"muted\">No headlines available.</p>";
  } catch (error) {
    document.getElementById("side-news").innerHTML = "<p class=\"muted\">Headlines are temporarily unavailable.</p>";
  }
}

let teamAssets = {};

function teamBadge(team, size = "sm") {
  const asset = teamAssets[team] || {};
  const fallback = asset.initials || team.split(" ").map((part) => part[0]).join("").slice(0, 3);
  return asset.logo
    ? `<img class="team-logo ${size}" src="${asset.logo}" alt="" loading="lazy" onerror="this.outerHTML='<span class=&quot;team-logo fallback ${size}&quot;>${fallback}</span>'">`
    : `<span class="team-logo fallback ${size}">${fallback}</span>`;
}

// --- League table tab ---
async function initTableTab() {
  const seasons = await getJSON("/api/seasons");
  const select = document.getElementById("season-select");
  select.innerHTML = seasons.map((s) => `<option value="${s}">${s}</option>`).join("");
  select.value = seasons[seasons.length - 1];
  select.addEventListener("change", () => loadTable(select.value));
  loadTable(select.value);
  window.setInterval(() => loadTable(select.value), 60_000);
  loadLiveStatus("table-live-output", "table-live-status");
  loadLiveTableLabel();
}

async function loadLiveTableLabel() {
  try {
    const status = await getJSON("/api/live/status");
    const note = document.querySelector("#tab-table .live-table-note");
    if (note) note.textContent = status.live_matches ? "Standings include provisional live results." : "Standings use the latest saved results.";
  } catch (error) {
    // The table itself remains usable if status metadata is unavailable.
  }
}

async function loadTable(season) {
  const rows = await getJSON(`/api/table/${encodeURIComponent(season)}`);
  const tbody = document.querySelector("#table-output tbody");
  tbody.innerHTML = rows.map((r) => `
    <tr>
      <td>${r.position}</td><td><span class="team-name-cell">${teamBadge(r.team)}<strong>${r.team}</strong></span></td><td>${r.matches}</td>
      <td>${r.wins}</td><td>${r.draws}</td><td>${r.losses}</td>
      <td>${r.goals_for}</td><td>${r.goals_against}</td>
      <td>${r.goal_difference}</td><td>${r.points}</td>
    </tr>`).join("");
}

function compactFixture(fixture) {
  const date = new Date(fixture.date).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  return `<div class="home-fixture"><div class="home-fixture-main"><small class="fixture-competition">${fixture.competition || "PL"}</small><div class="home-fixture-match"><span class="fixture-team">${teamBadge(fixture.home_team)}<strong>${fixture.home_team}</strong></span><span>vs</span><span class="fixture-team">${teamBadge(fixture.away_team)}<strong>${fixture.away_team}</strong></span></div></div><span class="fixture-probability">${date}</span></div>`;
}

function liveFixture(fixture, compactPrediction = false) {
  const prediction = fixture.prediction;
  let pick = `<span class="live-prediction muted">No archived pre-match prediction</span>`;
  if (prediction) {
    const pickName = prediction.predicted_result === "HOME_WIN"
      ? fixture.home_team
      : prediction.predicted_result === "AWAY_WIN"
        ? fixture.away_team
        : "Draw";
    pick = compactPrediction
      ? `<span class="live-prediction">Pre-match pick: ${pickName}</span>`
      : `<span class="live-prediction">Pre-match pick: ${pickName} · H ${Math.round(prediction.probabilities.HOME_WIN * 100)}% / D ${Math.round(prediction.probabilities.DRAW * 100)}% / A ${Math.round(prediction.probabilities.AWAY_WIN * 100)}%</span>`;
  }
  return `<div class="live-fixture"><div class="live-fixture-teams"><span class="fixture-team">${teamBadge(fixture.home_team)}<strong>${fixture.home_team}</strong></span><strong class="live-score">${fixture.home_goals} - ${fixture.away_goals}</strong><span class="fixture-team"><strong>${fixture.away_team}</strong>${teamBadge(fixture.away_team)}</span></div><span class="live-label">${fixture.status === "PAUSED" ? "Half-time" : "Live"}</span>${pick}</div>`;
}

async function initHomeTab() {
  const competitions = await getJSON("/api/competitions");
  document.getElementById("home-season").textContent = competitions.length;
  loadLiveFixtures();
  loadRecentResults();
  window.setInterval(loadLiveFixtures, 60_000);
  document.getElementById("home-upcoming").innerHTML = "<p class=\"muted\">Loading fixture signals...</p>";
  getJSON("/api/overview/upcoming?limit=12").then((fixtures) => {
    renderMatchTicker(fixtures);
    const nextFixtures = ["PL", "CL"]
      .flatMap((code) => fixtures.filter((fixture) => fixture.competition === code).slice(0, 2))
      .sort((first, second) => new Date(first.date) - new Date(second.date));
    document.getElementById("home-upcoming").innerHTML = nextFixtures.length
      ? nextFixtures.map(compactFixture).join("")
      : "<p class=\"muted\">No upcoming fixtures available.</p>";
  }).catch(() => {
    renderMatchTicker([]);
    document.getElementById("home-upcoming").innerHTML = "<p class=\"muted\">Fixture signals are temporarily unavailable.</p>";
  });
  try {
    const news = await getJSON("/api/news?limit=9");
    document.getElementById("news-output").innerHTML = news.length
      ? news.map((item) => `<article class="news-item">${item.image ? `<img src="${item.image}" alt="" loading="lazy">` : `<div class="news-image-placeholder">PL</div>`}<div class="news-content"><span>${item.source}</span><a href="${item.url}" target="_blank" rel="noreferrer"><strong>${item.title}</strong></a><small>${item.published}</small><a class="x-link" href="${item.x_search}" target="_blank" rel="noreferrer">Discuss on X</a></div></article>`).join("")
      : "<p class=\"muted\">News feeds are temporarily unavailable.</p>";
  } catch (error) {
    document.getElementById("news-output").innerHTML = "<p class=\"muted\">News feeds are temporarily unavailable.</p>";
  }
}

async function loadLiveFixtures() {
  try {
    const fixtures = await getJSON("/api/live");
    document.getElementById("live-output").innerHTML = fixtures.length
      ? fixtures.map((fixture) => liveFixture(fixture, true)).join("")
      : "<p class=\"muted\">No Premier League matches are live right now.</p>";
  } catch (error) {
    document.getElementById("live-output").innerHTML = "<p class=\"muted\">Live scores are temporarily unavailable.</p>";
  }
}

async function loadRecentResults() {
  const container = document.getElementById("results-output");
  try {
    const results = await getJSON("/api/results/recent?days=7");
    if (!results.length) {
      container.innerHTML = "<p class=\"muted\">No finished matches in the last 7 days.</p>";
      return;
    }
    container.innerHTML = results.map((r) => {
      const date = new Date(r.date).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
      const pred = r.prediction;
      let predHtml = `<span class="result-prediction muted">No prediction recorded</span>`;
      if (pred) {
        const pickName = pred.predicted_result === "HOME_WIN"
          ? r.home_team
          : pred.predicted_result === "AWAY_WIN"
            ? r.away_team
            : "Draw";
        const h = Math.round(pred.probabilities.HOME_WIN * 100);
        const d = Math.round(pred.probabilities.DRAW * 100);
        const a = Math.round(pred.probabilities.AWAY_WIN * 100);
        predHtml = `<span class="result-prediction">Pick: <strong>${pickName}</strong> &middot; H ${h}% / D ${d}% / A ${a}%</span>`;
      }
      const verdictHtml = r.correct === null
        ? ""
        : r.correct
          ? `<span class="result-verdict correct">✅ Correct</span>`
          : `<span class="result-verdict wrong">❌ Wrong</span>`;
      return `
        <div class="result-row">
          <div class="result-teams">
            <span class="fixture-team">${teamBadge(r.home_team)}<strong>${r.home_team}</strong></span>
            <span class="result-score">${r.home_goals} – ${r.away_goals}</span>
            <span class="fixture-team"><strong>${r.away_team}</strong>${teamBadge(r.away_team)}</span>
          </div>
          <div class="result-meta">
            <span class="result-date muted">${date}${r.matchday != null ? ` · MD${r.matchday}` : ""}</span>
            ${predHtml}
            ${verdictHtml}
          </div>
        </div>`;
    }).join("");
  } catch (error) {
    container.innerHTML = "<p class=\"muted\">Recent results are temporarily unavailable.</p>";
  }
}

async function loadLiveStatus(outputId, statusId) {
  try {
    const [fixtures, status] = await Promise.all([getJSON("/api/live"), getJSON("/api/live/status")]);
    document.getElementById(statusId).textContent = fixtures.length ? `${fixtures.length} live now` : "No live matches in saved feed";
    document.getElementById(outputId).innerHTML = fixtures.length
      ? fixtures.map(liveFixture).join("")
      : `<p class="muted">No live scores in the saved feed. Refresh the provider feed with <code>${status.refresh_command}</code>.</p>`;
  } catch (error) {
    document.getElementById(outputId).innerHTML = "<p class=\"muted\">Live score feed unavailable.</p>";
  }
}

// --- Team stats tab ---
async function initTeamTab(teams) {
  const teamSelect = document.getElementById("team-select");
  teamSelect.innerHTML = teams.map((t) => `<option value="${t}">${t}</option>`).join("");
  teamSelect.addEventListener("change", loadTeamStats);

  const seasonSelect = document.getElementById("team-season-select");
  const seasons = await getJSON("/api/seasons");
  seasonSelect.innerHTML += seasons.map((s) => `<option value="${s}">${s}</option>`).join("");
  seasonSelect.addEventListener("change", loadTeamStats);

  loadTeamStats();
}

async function loadTeamStats() {
  const team = document.getElementById("team-select").value;
  const season = document.getElementById("team-season-select").value;
  const url = `/api/teams/${encodeURIComponent(team)}/stats` + (season ? `?season=${encodeURIComponent(season)}` : "");
  const s = await getJSON(url);
  const profileUrl = `/api/teams/${encodeURIComponent(team)}/profile` + (season ? `?season=${encodeURIComponent(season)}` : "");
  const p = await getJSON(profileUrl);
  document.getElementById("team-output").innerHTML = `
    <p class="team-title">${teamBadge(s.team, "md")}<strong>${s.team}</strong> <span>— ${s.season}</span></p>
    <p>Played ${s.matches} · W${s.wins} D${s.draws} L${s.losses}</p>
    <p>Goals: ${s.goals_for} for, ${s.goals_against} against (GD ${s.goal_difference})</p>
    <p>Points: ${s.points}</p>
    <div class="profile-heading"><h3>Current profile</h3><span>${p.matches_available} matches of history</span></div>
    <div class="profile-grid">
      <div><span>Elo</span><strong>${metric(p.elo, 0)}</strong></div>
      <div><span>xG / match</span><strong>${metric(p.xg_last5)}</strong><small>last 5</small></div>
      <div><span>xGA / match</span><strong>${metric(p.xga_last5)}</strong><small>last 5</small></div>
      <div><span>xG / match</span><strong>${metric(p.xg_last10)}</strong><small>last 10</small></div>
      <div><span>xGA / match</span><strong>${metric(p.xga_last10)}</strong><small>last 10</small></div>
      <div><span>Finishing</span><strong>${metric(p.finishing_last5)}</strong><small>goals − xG</small></div>
      <div><span>PPDA</span><strong>${metric(p.ppda_last5)}</strong><small>last 5</small></div>
      <div><span>Deep actions</span><strong>${metric(p.deep_last5)}</strong><small>last 5</small></div>
      <div><span>Rest</span><strong>${metric(p.rest_days, 1)}d</strong><small>${p.matches_last14_days} in last 14d</small></div>
    </div>`;
  const teamSeasons = document.getElementById("team-season-select");
  const scorerSeason = season || teamSeasons.options[teamSeasons.options.length - 1]?.value;
  await loadTeamScorers(team, scorerSeason);
}

// --- Predictions tab ---
function probBar(p) {
  const home = p.probabilities.HOME_WIN * 100;
  const draw = p.probabilities.DRAW * 100;
  const away = p.probabilities.AWAY_WIN * 100;
  return `
    <div class="prob-bar">
      <div class="prob-home" style="width:${home}%"></div>
      <div class="prob-draw" style="width:${draw}%"></div>
      <div class="prob-away" style="width:${away}%"></div>
    </div>
    <p style="font-size:0.8rem;color:#9fb2c2;margin-top:0.3rem">
      Home ${home.toFixed(0)}% &middot; Draw ${draw.toFixed(0)}% &middot; Away ${away.toFixed(0)}%
    </p>`;
}

function metric(value, digits = 2) {
  return Number(value || 0).toFixed(digits);
}

function matchupPanel(p) {
  const e = p.explanation;
  const rows = [
    ["Elo", metric(e.home.elo, 0), metric(e.away.elo, 0)],
    ["xG / match (last 5)", metric(e.home.xg_last5), metric(e.away.xg_last5)],
    ["xGA / match (last 5)", metric(e.home.xga_last5), metric(e.away.xga_last5)],
    ["xG / match (last 10)", metric(e.home.xg_last10), metric(e.away.xg_last10)],
    ["PPDA (last 5)", metric(e.home.ppda_last5), metric(e.away.ppda_last5)],
    ["Deep actions (last 5)", metric(e.home.deep_last5), metric(e.away.deep_last5)],
  ];
  const signals = [
    ["Pressing edge", e.matchup.home_pressing_edge, e.matchup.away_pressing_edge],
    ["Territory edge", e.matchup.home_territory_edge, e.matchup.away_territory_edge],
  ];
  return `
    <section class="matchup-panel card">
      <div class="panel-heading"><h3>Why this matchup looks this way</h3><span>Rolling pre-match data</span></div>
      <div class="comparison-grid">
        <div class="comparison-labels"><strong>Metric</strong>${rows.map((row) => `<span>${row[0]}</span>`).join("")}</div>
        <div class="comparison-team"><strong>${teamBadge(p.home_team, "md")} ${p.home_team}</strong>${rows.map((row) => `<span>${row[1]}</span>`).join("")}</div>
        <div class="comparison-team"><strong>${teamBadge(p.away_team, "md")} ${p.away_team}</strong>${rows.map((row) => `<span>${row[2]}</span>`).join("")}</div>
      </div>
      <div class="signal-list">
        ${signals.map(([label, home, away]) => `
          <div class="signal-row"><span>${label}</span><strong>${home > away ? p.home_team : away > home ? p.away_team : "Even"}</strong><small>${metric(Math.max(Math.abs(home), Math.abs(away)))} signal strength</small></div>`).join("")}
      </div>
    </section>`;
}

async function loadUpcoming() {
  const container = document.getElementById("upcoming-output");
  container.innerHTML = "<p class=\"muted\">Loading fixture probabilities...</p>";
  try {
  const fixtures = await getJSON("/api/predictions/upcoming?limit=8");
  if (fixtures.length === 0) {
    container.innerHTML = "<p>No upcoming fixtures with enough history to predict.</p>";
    return;
  }
  container.innerHTML = fixtures.map((f) => `
    <div class="fixture">
      <div class="fixture-header">
        <div class="fixture-teams"><span class="fixture-team">${teamBadge(f.home_team)}<strong>${f.home_team}</strong></span><span class="fixture-vs">vs</span><span class="fixture-team">${teamBadge(f.away_team)}<strong>${f.away_team}</strong></span></div>
        <span class="matchday">${f.matchday == null ? "Matchday TBC" : `MD${f.matchday}`}</span>
      </div>
      ${probBar(f)}
    </div>`).join("");
  } catch (error) {
    container.innerHTML = "<p class=\"muted\">Fixture probabilities are temporarily unavailable.</p>";
  }
}

function renderMatchTicker(fixtures) {
  const ticker = document.getElementById("match-ticker");
  if (!fixtures.length) {
    ticker.innerHTML = '<p class="ticker-empty">No upcoming fixtures available.</p>';
    return;
  }

  ticker.innerHTML = fixtures.map((fixture) => {
    const date = new Date(fixture.date).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    const matchday = fixture.matchday == null ? "FIXTURE" : `MD ${String(fixture.matchday).padStart(2, "0")}`;
    const competition = fixture.competition || "PL";
    return `
      <article class="ticker-card">
        <div class="ticker-card-meta"><span>${competition} · ${matchday}</span><time>${date}</time></div>
        <div class="ticker-teams">
          <span class="ticker-team" title="${fixture.home_team}">${teamBadge(fixture.home_team, "ticker")}<strong>${fixture.home_team}</strong></span>
          <span class="ticker-vs">v</span>
          <span class="ticker-team away" title="${fixture.away_team}"><strong>${fixture.away_team}</strong>${teamBadge(fixture.away_team, "ticker")}</span>
        </div>
        <div class="ticker-kickoff"><span>${fixture.stage ? fixture.stage.replaceAll("_", " ") : "UPCOMING FIXTURE"}</span><span>${competition}</span></div>
      </article>`;
  }).join("");
}

async function loadTeamScorers(team, season) {
  const container = document.getElementById("team-player-output");
  container.innerHTML = '<p class="muted">Loading Premier League scorer summaries...</p>';
  try {
    const query = season ? `?season=${encodeURIComponent(season)}` : "";
    const result = await getJSON(`/api/teams/${encodeURIComponent(team)}/scorers${query}`);
    container.innerHTML = result.players.length
      ? result.players.map((player, index) => `
          <div class="team-player-row">
            <span class="player-rank">${String(index + 1).padStart(2, "0")}</span>
            <strong>${player.player}</strong>
            <span>${player.played_matches} apps</span>
            <b>${player.goals} <small>G</small></b>
            <span>${player.assists || 0} A</span>
          </div>`).join("")
      : '<p class="muted">No PL scorer summary for this team and season. Refresh with scripts.update_competitions --pl-scorers-only.</p>';
  } catch (error) {
    container.innerHTML = '<p class="muted">Premier League player summaries are temporarily unavailable.</p>';
  }
}

function initMatchTicker() {
  const ticker = document.getElementById("match-ticker");
  document.getElementById("ticker-prev").addEventListener("click", () => {
    ticker.scrollBy({ left: -280, behavior: "smooth" });
  });
  document.getElementById("ticker-next").addEventListener("click", () => {
    ticker.scrollBy({ left: 280, behavior: "smooth" });
  });
}

async function initPredictTab(teams) {
  const homeSelect = document.getElementById("predict-home");
  const awaySelect = document.getElementById("predict-away");
  const options = teams.map((t) => `<option value="${t}">${t}</option>`).join("");
  homeSelect.innerHTML = options;
  awaySelect.innerHTML = options;
  awaySelect.selectedIndex = 1;

  document.getElementById("predict-btn").addEventListener("click", async () => {
    const home = homeSelect.value;
    const away = awaySelect.value;
    const out = document.getElementById("predict-output");
    if (home === away) {
      out.innerHTML = "<p>Pick two different teams.</p>";
      return;
    }
    try {
      const p = await getJSON(`/api/predict?home=${encodeURIComponent(home)}&away=${encodeURIComponent(away)}`);
      out.innerHTML = `<p><strong>${p.home_team}</strong> vs <strong>${p.away_team}</strong></p><p class="prediction-label">Model pick: ${p.predicted_result.replace("_", " ")}</p>${probBar(p)}`;
      document.getElementById("matchup-output").innerHTML = matchupPanel(p);
    } catch (e) {
      out.innerHTML = `<p>${e.message}</p>`;
    }
  });

}

let competitionRegistry = [];
let competitionScorerRows = [];
let competitionRequestId = 0;

async function initCompetitionsTab() {
  const competitions = await getJSON("/api/competitions");
  competitionRegistry = competitions;
  const select = document.getElementById("competition-select");
  select.innerHTML = competitions.map((item) => `<option value="${item.code}">${item.name}</option>`).join("");
  select.value = competitions.some((item) => item.code === "CL") ? "CL" : competitions[0]?.code || "";
  select.addEventListener("change", loadCompetitionCentre);
  document.getElementById("competition-season-select").addEventListener("change", loadCompetitionPanels);
  document.getElementById("competition-scorer-team").addEventListener("change", () => {
    renderCompetitionScorers(competitionScorerRows);
  });
  await loadCompetitionCentre();
}

async function loadCompetitionCentre() {
  const code = document.getElementById("competition-select").value;
  const requestId = ++competitionRequestId;
  const seasonSelect = document.getElementById("competition-season-select");
  const status = document.getElementById("competition-data-status");
  status.textContent = "Loading competition data...";
  try {
    const seasons = await getJSON(`/api/competitions/${code}/seasons`);
    if (requestId !== competitionRequestId || code !== document.getElementById("competition-select").value) return;
    seasonSelect.innerHTML = seasons.map((season) => `<option value="${season}">${season}</option>`).join("");
    seasonSelect.disabled = !seasons.length;
    if (seasons.length) seasonSelect.value = seasons[seasons.length - 1];
    await loadCompetitionPanels();
  } catch (error) {
    if (requestId === competitionRequestId) status.textContent = error.message;
  }
}

async function loadCompetitionPanels() {
  const requestId = ++competitionRequestId;
  const code = document.getElementById("competition-select").value;
  const season = document.getElementById("competition-season-select").value;
  const config = competitionRegistry.find((item) => item.code === code);
  const status = document.getElementById("competition-data-status");
  if (!config?.fixtures_loaded) {
    status.textContent = `No fixtures loaded. Run scripts.update_competitions for ${code}.`;
    document.getElementById("competition-table-wrap").innerHTML = '<p class="muted">No competition data loaded.</p>';
    document.getElementById("competition-scorers").innerHTML = '<p class="muted">No scorer summaries loaded.</p>';
    document.getElementById("competition-upcoming").innerHTML = '<p class="muted">No fixtures loaded.</p>';
    document.getElementById("competition-predictions").innerHTML = '<p class="muted">No competition data loaded.</p>';
    return;
  }

  status.textContent = `${config.fixtures_loaded.toLocaleString()} fixtures · ${config.model_available ? "model ready" : "isolated model not trained"}`;
  const seasonQuery = season ? `?season=${encodeURIComponent(season)}` : "";
  const [table, scorers, fixtures] = await Promise.allSettled([
    getJSON(`/api/competitions/${code}/table${seasonQuery}`),
    getJSON(`/api/competitions/${code}/scorers${seasonQuery}&limit=100`.replace("?&", "?")),
    getJSON(`/api/competitions/${code}/upcoming?limit=12`),
  ]);
  if (requestId !== competitionRequestId
      || code !== document.getElementById("competition-select").value
      || season !== document.getElementById("competition-season-select").value) return;

  document.getElementById("competition-table-label").textContent = season || "";
  document.getElementById("competition-table-wrap").innerHTML = table.status === "fulfilled"
    ? renderCompetitionTable(table.value)
    : `<p class="muted">${table.reason.message}</p>`;
  competitionScorerRows = scorers.status === "fulfilled" ? scorers.value.players : [];
  renderCompetitionScorers(competitionScorerRows);
  document.getElementById("competition-upcoming").innerHTML = fixtures.status === "fulfilled"
    ? renderCompetitionFixtures(fixtures.value)
    : `<p class="muted">${fixtures.reason.message}</p>`;

  const predictionContainer = document.getElementById("competition-predictions");
  if (!config.model_available) {
    predictionContainer.innerHTML = `<p class="muted">No isolated model for ${code} yet. After importing history, run <code>python -m training.train_competition_models --competition ${code}</code>.</p>`;
    return;
  }
  try {
    const predictions = await getJSON(`/api/competitions/${code}/predictions/upcoming?limit=8`);
    if (requestId === competitionRequestId) {
      predictionContainer.innerHTML = renderCompetitionPredictions(predictions);
    }
  } catch (error) {
    if (requestId === competitionRequestId) {
      predictionContainer.innerHTML = `<p class="muted">${error.message}</p>`;
    }
  }
}

function renderCompetitionTable(rows) {
  if (!rows.length) return '<p class="muted">No standings available for this season yet.</p>';
  let currentGroup = null;
  const body = rows.map((row) => {
    const group = row.group || null;
    const heading = group && group !== currentGroup
      ? `<tr class="group-heading"><th colspan="10">${group}</th></tr>`
      : "";
    currentGroup = group;
    return `${heading}<tr><td>${row.position}</td><td><span class="team-name-cell">${teamBadge(row.team)}<strong>${row.team}</strong></span></td><td>${row.matches}</td><td>${row.wins}</td><td>${row.draws}</td><td>${row.losses}</td><td>${row.goals_for}</td><td>${row.goals_against}</td><td>${row.goal_difference}</td><td><strong>${row.points}</strong></td></tr>`;
  }).join("");
  return `<table class="competition-table"><thead><tr><th>#</th><th>Team</th><th>P</th><th>W</th><th>D</th><th>L</th><th>GF</th><th>GA</th><th>GD</th><th>Pts</th></tr></thead><tbody>${body}</tbody></table>`;
}

function renderCompetitionScorers(rows) {
  const filter = document.getElementById("competition-scorer-team");
  const selectedTeam = filter.value;
  const teams = [...new Set(rows.map((row) => row.team).filter(Boolean))].sort();
  filter.innerHTML = `<option value="">All teams</option>${teams.map((team) => `<option value="${team}">${team}</option>`).join("")}`;
  filter.value = teams.includes(selectedTeam) ? selectedTeam : "";
  const filtered = filter.value ? rows.filter((row) => row.team === filter.value) : rows;
  const container = document.getElementById("competition-scorers");
  container.innerHTML = filtered.length
    ? filtered.slice(0, 12).map((row) => `<div class="scorer-row"><div><strong>${row.player}</strong><span class="scorer-team-name">${teamBadge(row.team)}${row.team}</span></div><strong class="scorer-goals">${row.goals}<small> G</small></strong><span>${row.assists} A · ${row.played_matches} apps</span></div>`).join("")
    : '<p class="muted">No scorer summaries available for this season.</p>';
}

function renderCompetitionFixtures(fixtures) {
  return fixtures.length
    ? fixtures.map((fixture) => `<div class="competition-fixture"><time>${new Date(fixture.date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</time><strong class="competition-team">${teamBadge(fixture.home_team)}${fixture.home_team}</strong><span>v</span><strong class="competition-team">${teamBadge(fixture.away_team)}${fixture.away_team}</strong><small>${fixture.matchday ? `MD ${fixture.matchday}` : fixture.stage || "FIXTURE"}</small></div>`).join("")
    : '<p class="muted">No upcoming fixtures in this feed.</p>';
}

function renderCompetitionPredictions(predictions) {
  return predictions.length
    ? predictions.map((fixture) => `<div class="competition-prediction"><div class="competition-fixture"><time>${new Date(fixture.date).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</time><strong class="competition-team">${teamBadge(fixture.home_team)}${fixture.home_team}</strong><span>v</span><strong class="competition-team">${teamBadge(fixture.away_team)}${fixture.away_team}</strong></div><div class="competition-probabilities"><span>H ${Math.round(fixture.probabilities.HOME_WIN * 100)}%</span><span>D ${Math.round(fixture.probabilities.DRAW * 100)}%</span><span>A ${Math.round(fixture.probabilities.AWAY_WIN * 100)}%</span></div></div>`).join("")
    : '<p class="muted">No predictions available for upcoming fixtures.</p>';
}

// --- Boot ---
(async function init() {
  initMatchTicker();
  const teams = await getJSON("/api/teams");
  teamAssets = await getJSON("/api/team-assets").catch(() => ({}));
  loadSideRails();
  initHomeTab().catch(() => {
    document.getElementById("home-upcoming").innerHTML = "<p class=\"muted\">Dashboard data is temporarily unavailable.</p>";
  });
  initTableTab();
  initTeamTab(teams);
  initPredictTab(teams);
  initCompetitionsTab().catch((error) => {
    document.getElementById("competition-data-status").textContent = error.message;
  });
})();
