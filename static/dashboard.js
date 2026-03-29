function $(id) {
  return document.getElementById(id);
}

function clampNumber(n) {
  const x = Number(n);
  return Number.isFinite(x) ? x : null;
}

function formatMaybeNumber(n, digits = 1) {
  const x = clampNumber(n);
  if (x === null) return "—";
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
      year: "numeric", month: "short", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit",
    }).format(d);
  } catch {
    return d.toLocaleString();
  }
}

function formatDuration(seconds) {
  const s = Number(seconds);
  if (!s || s <= 0) return "—";
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return rem > 0 ? `${m}m ${rem}s` : `${m}m`;
}

function setText(id, value) {
  const el = $(id);
  if (!el) return;
  el.textContent = value;
}

function renderKpis(latest) {
  setText("kpiSoil", latest ? formatMaybeNumber(latest.soil_moisture, 0) : "—");
  setText("kpiTemp", latest ? `${formatMaybeNumber(latest.temperature, 1)}°C` : "—");
  setText("kpiHumidity", latest ? `${formatMaybeNumber(latest.humidity, 0)}%` : "—");

  const pumpOn = latest && Number(latest.pump_status) === 1;
  const pumpEl = $("kpiPump");
  if (pumpEl) {
    pumpEl.className = `badge ${pumpOn ? "badge--on" : "badge--off"}`;
    pumpEl.textContent = pumpOn ? "ON" : "OFF";
  }

  // Last duration KPI
  const lastDur = latest ? formatDuration(latest.duration_seconds) : "—";
  setText("kpiDuration", lastDur);

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
  const reason = r.reason || "—";
  const duration = formatDuration(r.duration_seconds);

  return `
    <tr>
      <td data-label="Soil">${formatMaybeNumber(r.soil_moisture, 0)}</td>
      <td data-label="Temp">${formatMaybeNumber(r.temperature, 1)}°C</td>
      <td data-label="Humidity">${formatMaybeNumber(r.humidity, 0)}%</td>
      <td data-label="Pump">${pumpBadge}</td>
      <td data-label="Reason" class="td-reason">${reason}</td>
      <td data-label="Duration" class="td-muted">${duration}</td>
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

// ── Chart ─────────────────────────────────────────────────────────────────────
let chartInstance = null;

function renderChart(rows) {
  const canvas = $("pumpChart");
  if (!canvas || !window.Chart) return;

  // Build timeline data — each event is a pump flip
  const labels = [];
  const dataOn = [];   // 1 = ON, 0 = OFF
  const bgColors = [];

  const reversed = [...rows].reverse(); // oldest first for chart
  reversed.forEach((r) => {
    labels.push(formatTimestamp(r.timestamp));
    const on = Number(r.pump_status) === 1;
    dataOn.push(on ? 1 : 0);
    bgColors.push(on ? "rgba(0,255,163,0.75)" : "rgba(255,82,82,0.60)");
  });

  if (chartInstance) {
    chartInstance.data.labels = labels;
    chartInstance.data.datasets[0].data = dataOn;
    chartInstance.data.datasets[0].backgroundColor = bgColors;
    chartInstance.update();
    return;
  }

  chartInstance = new window.Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [{
        label: "Pump state",
        data: dataOn,
        backgroundColor: bgColors,
        borderRadius: 6,
        borderSkipped: false,
        barThickness: 18,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => ctx.raw === 1 ? " Pump ON" : " Pump OFF",
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: "rgba(255,255,255,0.50)",
            font: { size: 10 },
            maxRotation: 35,
            autoSkip: true,
            maxTicksLimit: 10,
          },
          grid: { color: "rgba(255,255,255,0.06)" },
        },
        y: {
          min: 0, max: 1,
          ticks: {
            color: "rgba(255,255,255,0.50)",
            stepSize: 1,
            callback: (v) => v === 1 ? "ON" : "OFF",
          },
          grid: { color: "rgba(255,255,255,0.06)" },
        },
      },
    },
  });
}

// ── Search & filter ───────────────────────────────────────────────────────────
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

// ── Polling ───────────────────────────────────────────────────────────────────
let timer = null;
let lastOk = null;

async function fetchRecent() {
  const res = await fetch("/api/recent?limit=20", { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return await res.json();
}

async function tick() {
  try {
    const payload = await fetchRecent();
    lastOk = true;
    renderKpis(payload.latest);
    renderRows(payload.rows);
    renderChart(payload.rows);
    setText("lastUpdated",
      payload.latest?.timestamp ? formatTimestamp(payload.latest.timestamp) : "—");
    applySearchFilter();
  } catch {
    lastOk = false;
    const pill = $("statusPill");
    if (pill) {
      pill.className = "pill pill--warn";
      const label = pill.querySelector("[data-role='status-label']");
      if (label) label.textContent = "Retrying…";
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

  applySearchFilter();
  if (lastOk === null) renderKpis(null);
});
