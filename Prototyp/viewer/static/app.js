const runtimeSelect = document.querySelector("#runtimeSelect");
const symbolSelect = document.querySelector("#symbolSelect");
const refreshButton = document.querySelector("#refreshButton");
const chartTitle = document.querySelector("#chartTitle");
const chartSubtitle = document.querySelector("#chartSubtitle");
const barsMetric = document.querySelector("#barsMetric");
const signalsMetric = document.querySelector("#signalsMetric");
const tradesMetric = document.querySelector("#tradesMetric");
const errorsMetric = document.querySelector("#errorsMetric");
const candidateList = document.querySelector("#candidateList");
const tradeList = document.querySelector("#tradeList");
const chartEl = document.querySelector("#chart");

let chart;
let candleSeries;
let volumeSeries;
let overlaySeries = [];
let priceLines = [];

function makeChart() {
  chart = LightweightCharts.createChart(chartEl, {
    layout: {
      background: { color: "#f4f6f8" },
      textColor: "#2f3a4c",
    },
    grid: {
      vertLines: { color: "#e4e9f0" },
      horzLines: { color: "#e4e9f0" },
    },
    rightPriceScale: {
      borderColor: "#d7dde5",
    },
    timeScale: {
      borderColor: "#d7dde5",
      timeVisible: true,
      secondsVisible: false,
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
    },
  });

  candleSeries = chart.addCandlestickSeries({
    upColor: "#12915b",
    downColor: "#c53d3d",
    borderVisible: false,
    wickUpColor: "#12915b",
    wickDownColor: "#c53d3d",
  });

  volumeSeries = chart.addHistogramSeries({
    priceFormat: { type: "volume" },
    priceScaleId: "volume",
  });
  chart.priceScale("volume").applyOptions({
    scaleMargins: { top: 0.82, bottom: 0 },
  });
}

function resizeChart() {
  if (!chart) return;
  chart.applyOptions({
    width: chartEl.clientWidth,
    height: chartEl.clientHeight,
  });
}

async function fetchJson(url) {
  const response = await fetch(url);
  const payload = await response.json();
  if (!response.ok || payload.error) {
    throw new Error(payload.error || `HTTP ${response.status}`);
  }
  return payload;
}

function option(value, label) {
  const node = document.createElement("option");
  node.value = value;
  node.textContent = label;
  return node;
}

async function loadRuntimes() {
  const payload = await fetchJson("/api/runtimes");
  runtimeSelect.innerHTML = "";
  payload.runtimes.forEach((runtime) => runtimeSelect.append(option(runtime, runtime)));
}

async function loadSymbols() {
  const runtime = runtimeSelect.value;
  const payload = await fetchJson(`/api/symbols?runtime=${encodeURIComponent(runtime)}`);
  symbolSelect.innerHTML = "";
  payload.symbols.forEach((item) => {
    const label = item.name === item.symbol ? item.symbol : `${item.symbol} · ${item.name}`;
    symbolSelect.append(option(item.symbol, label));
  });
}

function clearOverlays() {
  overlaySeries.forEach((series) => chart.removeSeries(series));
  overlaySeries = [];
  priceLines.forEach((line) => candleSeries.removePriceLine(line));
  priceLines = [];
  candleSeries.setMarkers([]);
}

function addLine(data, color, title) {
  if (!data || data.length < 2) return;
  const series = chart.addLineSeries({
    color,
    lineWidth: 2,
    lastValueVisible: false,
    priceLineVisible: false,
    title,
  });
  series.setData(data);
  overlaySeries.push(series);
}

function markerForCandidate(candidate) {
  const long = candidate.direction === "LONG";
  return {
    time: Math.floor(new Date(candidate.signal_time).getTime() / 1000),
    position: long ? "belowBar" : "aboveBar",
    color: long ? "#12915b" : "#c53d3d",
    shape: long ? "arrowUp" : "arrowDown",
    text: `${candidate.direction || ""} ${candidate.status || ""}`,
  };
}

function markerForTrade(trade) {
  if (!trade.entry_time) return null;
  const long = trade.direction === "LONG";
  return {
    time: Math.floor(new Date(trade.entry_time).getTime() / 1000),
    position: long ? "belowBar" : "aboveBar",
    color: "#2563eb",
    shape: "circle",
    text: `${trade.strategy_id || "Trade"} ${trade.status || ""}`,
  };
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "-";
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  if (Math.abs(num) >= 100) return num.toFixed(2);
  if (Math.abs(num) >= 1) return num.toFixed(4);
  return num.toFixed(6);
}

function statusBadge(status) {
  const cls = String(status || "").toLowerCase().replace(/[^a-z]+/g, "-");
  return `<span class="badge ${cls}">${status || "n/a"}</span>`;
}

function renderCandidates(candidates) {
  if (!candidates.length) {
    candidateList.innerHTML = `<div class="item"><p>No candidates for this symbol.</p></div>`;
    return;
  }
  candidateList.innerHTML = candidates
    .map((candidate) => {
      const passCount = candidate.variants.filter((item) => item.status === "PASS").length;
      return `
        <article class="item">
          <strong>
            <span>${candidate.direction || "-"} · ${new Date(candidate.signal_time).toLocaleString()}</span>
            ${statusBadge(candidate.status)}
          </strong>
          <p>Close ${formatNumber(candidate.signal_close)} · Stop ${formatNumber(candidate.stop)} · Target ${formatNumber(candidate.target)} · RR ${formatNumber(candidate.rr)}</p>
          <p>${passCount}/${candidate.variants.length} variants pass</p>
        </article>
      `;
    })
    .join("");
}

function renderTrades(trades) {
  if (!trades.length) {
    tradeList.innerHTML = `<div class="item"><p>No trades for this symbol yet.</p></div>`;
    return;
  }
  tradeList.innerHTML = trades
    .map((trade) => `
      <article class="item">
        <strong>
          <span>${trade.strategy_id || "Trade"}</span>
          ${statusBadge(trade.status)}
        </strong>
        <p>${trade.direction || "-"} · Entry ${formatNumber(trade.entry_price)} · Stop ${formatNumber(trade.stop_initial)} · Target ${formatNumber(trade.target)}</p>
      </article>
    `)
    .join("");
}

async function loadChart() {
  const runtime = runtimeSelect.value;
  const symbol = symbolSelect.value;
  if (!runtime || !symbol) return;

  const payload = await fetchJson(
    `/api/chart?runtime=${encodeURIComponent(runtime)}&symbol=${encodeURIComponent(symbol)}`
  );

  clearOverlays();
  candleSeries.setData(payload.candles);
  volumeSeries.setData(payload.volume);

  const markers = [];
  payload.candidates.forEach((candidate) => {
    addLine(candidate.action_line, "#2563eb", "Action");
    addLine(candidate.safety_line, "#0f9f8f", "Safety");
    markers.push(markerForCandidate(candidate));
    if (candidate.stop) {
      priceLines.push(candleSeries.createPriceLine({
        price: candidate.stop,
        color: "#c53d3d",
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: "Stop",
      }));
    }
    if (candidate.target) {
      priceLines.push(candleSeries.createPriceLine({
        price: candidate.target,
        color: "#12915b",
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: "Target",
      }));
    }
  });
  payload.trades.map(markerForTrade).filter(Boolean).forEach((marker) => markers.push(marker));
  candleSeries.setMarkers(markers);

  chartTitle.textContent = payload.symbol;
  chartSubtitle.textContent = `${payload.runtime} · ${payload.candles.length} finalized 4h candles`;
  barsMetric.textContent = payload.candles.length;
  signalsMetric.textContent = payload.candidates.length;
  tradesMetric.textContent = payload.trades.length;
  errorsMetric.textContent = payload.monitor.errors ?? 0;
  renderCandidates(payload.candidates);
  renderTrades(payload.trades);
  chart.timeScale().fitContent();
}

async function boot() {
  makeChart();
  resizeChart();
  await loadRuntimes();
  await loadSymbols();
  const btc = Array.from(symbolSelect.options).find((item) => item.value === "BTC-USD");
  if (btc) symbolSelect.value = "BTC-USD";
  await loadChart();
}

runtimeSelect.addEventListener("change", async () => {
  await loadSymbols();
  await loadChart();
});
symbolSelect.addEventListener("change", loadChart);
refreshButton.addEventListener("click", loadChart);
window.addEventListener("resize", resizeChart);

boot().catch((error) => {
  chartTitle.textContent = "Viewer error";
  chartSubtitle.textContent = error.message;
});
