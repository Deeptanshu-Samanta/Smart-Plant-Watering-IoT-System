function $(id) {
  return document.getElementById(id);
}

function clampNumber(n) {
  const x = Number(n);
  return Number.isFinite(x) ? x : null;
}

function formatMaybeNumber(n, digits = 1) {
  const x = clampNumber(n);
  if (x === null) return "\u2014";
  return x.toFixed(digits);
}

function parseTimestamp(ts) {
  if (!ts) return null;
  const s = String(ts).trim();
  const isoish = s.includes("T") ? s : s.replace(" ", "T");
  const d = new Date(isoish);
  return Number.isNaN(d.getTime()) ? null : d;
}

function formatTimestamp(ts) {
  const d = parseTimestamp(ts);
  if (!d) return String(ts ?? "");
  try {
    return new Intl.DateTimeFormat(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    }).format(d);
  } catch {
    return d.toLocaleString();
  }
}

function setText(id, value) {
  const el = $(id);
  if (!el) return;
  el.textContent = value;
}

function renderKpis(latest) {
  setText("kpiSoil", latest ? formatMaybeNumber(latest.soil_moisture, 0) : "\u2014");
  setText("kpiTemp", latest ? `${formatMaybeNumber(latest.temperature, 1)}\u00B0C` : "\u2014");
  setText("kpiHumidity", latest ? `${formatMaybeNumber(latest.humidity, 0)}%` : "\u2014");

  const pumpOn = latest && Number(latest.pump_status) === 1;
  const pumpEl = $("kpiPump");
  if (pumpEl) {
    pumpEl.className = `badge ${pumpOn ? "badge--on" : "badge--off"}`;
    pumpEl.textContent = pumpOn ? "ON" : "OFF";
  }

  const pill = $("statusPill");
  if (pill) {
    const dot = pill.querySelector(".pill__dot");
    const label = pill.querySelector("[data-role='status-label']");
    const ok = !!latest;
    pill.className = `pill ${ok ? "pill--ok" : "pill--warn"}`;
    if (dot) dot.title = ok ? "Connected" : "Waiting for data";
    if (label) label.textContent = ok ? "Live" : "No data";
  }
}

function rowToHtml(r) {
  const pumpOn = Number(r.pump_status) === 1;
  const pumpBadge = `<span class="badge ${pumpOn ? "badge--on" : "badge--off"}">${pumpOn ? "ON" : "OFF"}</span>`;

  return `
    <tr>
      <td data-label="Soil">${formatMaybeNumber(r.soil_moisture, 0)}</td>
      <td data-label="Temp">${formatMaybeNumber(r.temperature, 1)}\u00B0C</td>
      <td data-label="Humidity">${formatMaybeNumber(r.humidity, 0)}%</td>
      <td data-label="Pump">${pumpBadge}</td>
      <td class="td-muted" data-label="Time">${formatTimestamp(r.timestamp)}</td>
    </tr>
  `;
}

function renderRows(rows) {
  const tbody = $("rowsBody");
  if (!tbody) return;

  if (!rows || rows.length === 0) {
    tbody.innerHTML = "";
    const empty = $("emptyState");
    if (empty) empty.hidden = false;
    return;
  }

  const empty = $("emptyState");
  if (empty) empty.hidden = true;
  tbody.innerHTML = rows.map(rowToHtml).join("");
}

async function fetchRecent() {
  const res = await fetch("/api/recent?limit=20", { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

function applySearchFilter() {
  const q = ($("searchInput")?.value || "").trim().toLowerCase();
  const rows = document.querySelectorAll("#rowsBody tr");
  let visible = 0;
  rows.forEach((tr) => {
    const txt = tr.textContent ? tr.textContent.toLowerCase() : "";
    const ok = q === "" || txt.includes(q);
    tr.style.display = ok ? "" : "none";
    if (ok) visible += 1;
  });

  const countEl = $("rowCount");
  if (countEl) countEl.textContent = `${visible} shown`;
}

let timer = null;
let lastOk = null;

async function tick() {
  try {
    const payload = await fetchRecent();
    lastOk = true;
    renderKpis(payload.latest);
    renderRows(payload.rows);
    setText("lastUpdated", payload.latest?.timestamp ? formatTimestamp(payload.latest.timestamp) : "\u2014");
    applySearchFilter();
  } catch {
    lastOk = false;
    const pill = $("statusPill");
    if (pill) {
      pill.className = "pill pill--warn";
      const label = pill.querySelector("[data-role='status-label']");
      if (label) label.textContent = "Retrying\u2026";
    }
  }
}

function startPolling() {
  stopPolling();
  tick();
  timer = window.setInterval(tick, 5000);
}

function stopPolling() {
  if (timer) window.clearInterval(timer);
  timer = null;
}

/* ===== City selector ===== */
async function setCity(city) {
  const res = await fetch("/set_city", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ city }),
  });
  return await res.json();
}

function initCityForm() {
  const form = $("cityForm");
  const input = $("cityInput");
  const btn = $("cityBtn");
  const status = $("cityStatus");
  const label = $("cityLabel");

  if (!form || !input) return;

  async function handleSubmit() {
    const city = input.value.trim();
    if (!city) return;
    btn.textContent = "...";
    btn.disabled = true;
    try {
      const data = await setCity(city);
      if (data.city) {
        if (label) label.textContent = data.city;
        if (status) status.hidden = false;
        input.value = data.city;
        const banner = $("cityBannerName");
        if (banner) banner.textContent = data.city;
      }
    } catch (e) {
      console.error("Failed to set city:", e);
    } finally {
      btn.textContent = "Set City";
      btn.disabled = false;
    }
  }

  form.addEventListener("submit", (e) => { e.preventDefault(); handleSubmit(); });
  btn.addEventListener("click", handleSubmit);
}

document.addEventListener("DOMContentLoaded", () => {
  const toggle = $("autoRefreshToggle");
  const input = $("searchInput");

  if (input) input.addEventListener("input", applySearchFilter);

  if (toggle) {
    const set = () => {
      const on = !!toggle.checked;
      if (on) startPolling();
      else stopPolling();
    };
    toggle.addEventListener("change", set);
    set();
  } else {
    startPolling();
  }

  initCityForm();
  applySearchFilter();
  if (lastOk === null) renderKpis(null);
});
