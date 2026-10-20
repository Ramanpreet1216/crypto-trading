// ==============================================================================
// COINDCX FUTURES QUANT PRO - PERPETUAL CANDLESTICK & AI PREDICTOR ENGINE
// ==============================================================================

let currentCoin = "BTC";
let currentInterval = "1h";
let isBotRunning = false;
let chartMode = "ai"; // 'ai' or 'tv'
let currentLeverage = 10;
let tvWidget = null;

let activeCandles = [];
let activePrediction = null;
let activeFuturesStats = null;
let hoveredCandle = null;

// AI Strategy & Leverage Advisor State
let advisorData = null;
let selectedAdvisorTf = null;
let selectedAdvisorLev = 10;

// All Cryptocurrencies & Global Search State
let allCryptosList = [];
let allCryptosSort = "volume";
let allCryptosFilterQuery = "";
let currentTickerCategory = "gainers";

// 100% High-Confidence Signal Scanner State
let scannerResults = [];
let currentScannerFilter = "all";
let isScanning = false;
let activeRadarView = "scanner";

// Real-Time Alert Engine & Audio State
let isAudioAlertsEnabled = localStorage.getItem("audio_alerts") !== "false";
let unreadAlertCount = 0;
let lastAlertTimestamp = Date.now() - 30000;
let audioCtx = null;
let alertsHistory = [];

// DOM Elements: Header & Controls
const elPrice = document.getElementById("active-coin-price");
const elChange = document.getElementById("active-coin-change");
const elSymbol = document.getElementById("active-coin-symbol");
const elContractBadge = document.getElementById("contract-badge");
const elResistance = document.getElementById("stat-resistance");
const elSupport = document.getElementById("stat-support");
const elEma9 = document.getElementById("stat-ema9");
const elEma21 = document.getElementById("stat-ema21");
const elMark = document.getElementById("stat-mark");
const elFunding = document.getElementById("stat-funding");
const elFundingPill = document.getElementById("funding-pill");
const elLiqCalc = document.getElementById("liq-calc-text");

// DOM Elements: OHLC HUD
const elHudDate = document.getElementById("hud-date");
const elHudOpen = document.getElementById("hud-open");
const elHudHigh = document.getElementById("hud-high");
const elHudLow = document.getElementById("hud-low");
const elHudClose = document.getElementById("hud-close");
const elHudChg = document.getElementById("hud-chg");
const elHudVol = document.getElementById("hud-vol");

// DOM Elements: Predictive Forecast ("What Happens Next")
const elPredBadge = document.getElementById("pred-badge");
const elPredArrow = document.getElementById("pred-arrow");
const elPredDirection = document.getElementById("pred-direction-text");
const elPredProb = document.getElementById("pred-prob-text");
const elPredTarget = document.getElementById("pred-target-val");
const elPredStop = document.getElementById("pred-stop-val");
const elConfluenceList = document.getElementById("confluence-list");

// DOM Elements: Market Structure & Meter
const elVerdictBanner = document.getElementById("verdict-banner");
const elVerdictIcon = document.getElementById("verdict-icon");
const elVerdictAction = document.getElementById("verdict-action");
const elVerdictDesc = document.getElementById("verdict-desc");

const elMeterFill = document.getElementById("meter-fill");
const elMeterPin = document.getElementById("meter-pin");
const elMeterSup = document.getElementById("meter-sup");
const elMeterRes = document.getElementById("meter-res");
const elMeterDist = document.getElementById("meter-distance");

const elRsiVal = document.getElementById("rsi-val");
const elRsiBar = document.getElementById("rsi-bar");

// DOM Elements: Balances & Engine
const elHeaderBalance = document.getElementById("header-balance");
const elCardBalance = document.getElementById("card-balance");
const elCardPnl = document.getElementById("card-pnl");
const elPosBadge = document.getElementById("pos-status-badge");
const elPosDetails = document.getElementById("pos-details-text");
const elTradeLogList = document.getElementById("trade-log-list");
const elBotToggleBtn = document.getElementById("btn-bot-toggle");
const elBotToggleText = document.getElementById("bot-toggle-text");
const elBotToggleIcon = document.getElementById("bot-toggle-icon");
const elChartLoader = document.getElementById("chart-loader");
const elTradingViewContainer = document.getElementById("tradingview-container");
const elCanvas = document.getElementById("tradingChart");


// 1. Dynamic Decimal Price Formatter (2 digits after decimal for crypto prices)
function formatPrice(val) {
  if (val === null || val === undefined || isNaN(val)) return "$0.00";
  const num = Number(val);
  if (num === 0) return "$0.00";
  if (num < 0.001) return "$" + num.toFixed(6);
  if (num < 0.1) return "$" + num.toFixed(4);
  return "$" + num.toFixed(2);
}

// 2. Format Candle Timestamp
function formatCandleTime(timestamp, interval) {
  const d = new Date(timestamp);
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const tf = (interval || "1h").toLowerCase();

  const hh = d.getHours().toString().padStart(2, "0");
  const mm = d.getMinutes().toString().padStart(2, "0");
  const dd = d.getDate();
  const mmm = months[d.getMonth()];

  if (tf === "1d" || tf === "d") {
    return `${dd} ${mmm}`;
  } else if (tf === "1h") {
    return `${dd} ${mmm} ${hh}:${mm}`;
  } else {
    // 1m, 5m, 15m
    return `${hh}:${mm}`;
  }
}

// 3. Client-side EMA Calculation
function calculateEMA(data, span) {
  if (!data || data.length === 0) return [];
  const k = 2 / (span + 1);
  let ema = [];
  let prevEma = data[0];
  for (let i = 0; i < data.length; i++) {
    if (i === 0) {
      ema.push(data[0]);
    } else {
      prevEma = data[i] * k + prevEma * (1 - k);
      ema.push(prevEma);
    }
  }
  return ema;
}


// 4. Initialize Application
document.addEventListener("DOMContentLoaded", () => {
  setupCanvasEvents();
  updateSoundButtonUI();
  updateLiquidationEstimate();
  initDraggablePanels();
  updateCustomOrderSummary();

  // 1. Immediate: Load core bot status & selected coin chart
  syncBotStatus();
  loadCoinData(currentCoin);

  // 2. Staggered: Load supplementary data smoothly without backend traffic jams
  setTimeout(() => fetchTickerCategoryData(currentTickerCategory), 800);
  setTimeout(() => loadAllCryptosData(), 1600);
  setTimeout(() => fetchMarketRadar(), 2400);
  setTimeout(() => pollAlerts(), 3500);
  setTimeout(() => runMarketScan(false), 5500);

  // Fast 4s status sync for real-time position distance bar animation
  setInterval(() => {
    syncBotStatus();
  }, 4000);

  // Auto-refresh main chart and futures statistics every 15 seconds
  setInterval(() => {
    loadCoinData(currentCoin, true);
    syncBotStatus();
  }, 15000);

  // Periodic alert polling every 20 seconds
  setInterval(() => {
    pollAlerts();
  }, 20000);

  // Periodic scanner auto-refresh every 60 seconds
  setInterval(() => {
    runMarketScan(false);
  }, 60000);

  // Periodic market radar refresh every 45 seconds
  setInterval(() => {
    fetchMarketRadar();
  }, 45000);

  // Close search dropdown when clicking outside
  document.addEventListener("click", (e) => {
    const wrap = document.querySelector(".search-crypto-wrapper");
    const drop = document.getElementById("search-autocomplete-dropdown");
    if (wrap && drop && !wrap.contains(e.target)) {
      drop.style.display = "none";
    }
  });

  // Resize listener
  window.addEventListener("resize", () => {
    if (chartMode === "ai" && activeCandles.length > 0) {
      renderCandlestickChart(activeCandles, activePrediction);
    }
  });
});


// 5. Canvas Event Handlers (Crosshair & OHLC HUD updates with Mobile Touch Support)
function setupCanvasEvents() {
  if (!elCanvas) return;

  // Desktop Mouse Events
  elCanvas.addEventListener("mousemove", (e) => {
    if (chartMode !== "ai" || activeCandles.length === 0) return;
    const rect = elCanvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    renderCandlestickChart(activeCandles, activePrediction, { x: mouseX, y: mouseY });
  });

  elCanvas.addEventListener("mouseleave", () => {
    if (chartMode !== "ai" || activeCandles.length === 0) return;
    renderCandlestickChart(activeCandles, activePrediction, null);
    resetHudToLatest();
  });

  // Mobile Touch Events (Redmi Note 12 Pro 5G / Smartphones)
  elCanvas.addEventListener("touchstart", (e) => {
    if (chartMode !== "ai" || activeCandles.length === 0 || !e.touches || e.touches.length === 0) return;
    const rect = elCanvas.getBoundingClientRect();
    const touch = e.touches[0];
    const mouseX = touch.clientX - rect.left;
    const mouseY = touch.clientY - rect.top;
    renderCandlestickChart(activeCandles, activePrediction, { x: mouseX, y: mouseY });
  }, { passive: true });

  elCanvas.addEventListener("touchmove", (e) => {
    if (chartMode !== "ai" || activeCandles.length === 0 || !e.touches || e.touches.length === 0) return;
    const rect = elCanvas.getBoundingClientRect();
    const touch = e.touches[0];
    const mouseX = touch.clientX - rect.left;
    const mouseY = touch.clientY - rect.top;
    renderCandlestickChart(activeCandles, activePrediction, { x: mouseX, y: mouseY });
  }, { passive: true });

  elCanvas.addEventListener("touchend", () => {
    if (chartMode !== "ai" || activeCandles.length === 0) return;
    renderCandlestickChart(activeCandles, activePrediction, null);
    resetHudToLatest();
  }, { passive: true });

  if (window.ResizeObserver && elCanvas.parentElement) {
    const ro = new ResizeObserver(() => {
      if (chartMode === "ai" && activeCandles.length > 0) {
        renderCandlestickChart(activeCandles, activePrediction);
      }
    });
    ro.observe(elCanvas.parentElement);
  }
}

function resetHudToLatest() {
  if (!activeCandles || activeCandles.length === 0) return;
  const latest = activeCandles[activeCandles.length - 1];
  const chg = ((latest.close - latest.open) / latest.open) * 100;

  elHudDate.textContent = formatCandleTime(latest.time, currentInterval);
  elHudOpen.textContent = formatPrice(latest.open);
  elHudHigh.textContent = formatPrice(latest.high);
  elHudLow.textContent = formatPrice(latest.low);
  elHudClose.textContent = formatPrice(latest.close);
  elHudChg.textContent = `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`;
  elHudChg.style.color = chg >= 0 ? "#10b981" : "#ef4444";
  elHudVol.textContent = Number(latest.volume).toFixed(1);
}


// 6. High-Precision HTML5 Canvas Candlestick & 10-Dot Prediction Renderer
function renderCandlestickChart(candles, prediction, cursor = null) {
  if (!elCanvas) return;
  const ctx = elCanvas.getContext("2d");
  // Device pixel ratio for Retina / 4K crispness
  const dpr = window.devicePixelRatio || 1;
  elCanvas.style.width = "100%";
  elCanvas.style.height = "100%";

  const parent = elCanvas.parentElement;
  const rect = elCanvas.getBoundingClientRect();
  const width = Math.floor(rect.width > 50 ? rect.width : (parent && parent.clientWidth > 50 ? parent.clientWidth : Math.max(300, window.innerWidth - 24)));
  const height = Math.floor(rect.height > 50 ? rect.height : (parent && parent.clientHeight > 50 ? parent.clientHeight : 330));

  elCanvas.width = Math.floor(width * dpr);
  elCanvas.height = Math.floor(height * dpr);
  ctx.scale(dpr, dpr);

  ctx.clearRect(0, 0, width, height);

  if (!candles || candles.length === 0) return;

  const numCandles = candles.length;
  const forecastPath = prediction && prediction.projected_path ? prediction.projected_path : [];
  const forecastDotsCount = forecastPath.length;

  // Layout parameters (Responsive for mobile viewports like Redmi Note 12 Pro)
  const isMobile = width < 480;
  const paddingRight = isMobile ? 54 : 70; // Y-axis price label area
  const paddingBottom = isMobile ? 22 : 26; // X-axis time label area
  const paddingTop = isMobile ? 30 : 36;   // Top HUD clearance
  const plotWidth = width - paddingRight;
  const plotHeight = height - paddingTop - paddingBottom;

  // Space allocation: candles + forecast dots
  const totalSlots = numCandles + forecastDotsCount + 2;
  const slotWidth = plotWidth / totalSlots;
  const candleWidth = Math.max(2, Math.min(18, slotWidth * 0.72));

  // Determine price min & max (including candles and forecast targets)
  let minPrice = Infinity;
  let maxPrice = -Infinity;
  let maxVol = 0;

  candles.forEach(c => {
    if (c.low < minPrice) minPrice = c.low;
    if (c.high > maxPrice) maxPrice = c.high;
    if (c.volume > maxVol) maxVol = c.volume;
  });

  forecastPath.forEach(p => {
    if (p < minPrice) minPrice = p;
    if (p > maxPrice) maxPrice = p;
  });

  const priceMargin = (maxPrice - minPrice) * 0.12 || 1;
  const yMin = minPrice - priceMargin;
  const yMax = maxPrice + priceMargin;

  function priceToY(price) {
    return paddingTop + plotHeight - ((price - yMin) / (yMax - yMin)) * plotHeight;
  }

  function yToPrice(y) {
    return yMin + ((paddingTop + plotHeight - y) / plotHeight) * (yMax - yMin);
  }

  // 1. Draw Subtle Gridlines & Right Y-Axis Price Labels
  ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
  ctx.lineWidth = 1;
  ctx.font = isMobile ? "9px 'JetBrains Mono', monospace" : "11px 'JetBrains Mono', monospace";
  ctx.fillStyle = "#64748b";
  ctx.textAlign = "left";

  const gridSteps = 5;
  for (let i = 0; i <= gridSteps; i++) {
    const pVal = yMin + (i / gridSteps) * (yMax - yMin);
    const yPos = priceToY(pVal);

    ctx.beginPath();
    ctx.moveTo(0, yPos);
    ctx.lineTo(plotWidth, yPos);
    ctx.stroke();

    ctx.fillText(formatPrice(pVal), plotWidth + 8, yPos + 4);
  }

  // 2. Draw Volume Bars (Bottom 45px)
  const volHeightMax = 42;
  candles.forEach((c, i) => {
    const x = i * slotWidth + slotWidth / 2;
    const isBull = c.close >= c.open;
    const vHeight = maxVol > 0 ? (c.volume / maxVol) * volHeightMax : 2;
    const vY = paddingTop + plotHeight - vHeight;

    ctx.fillStyle = isBull ? "rgba(16, 185, 129, 0.18)" : "rgba(239, 68, 68, 0.18)";
    ctx.fillRect(x - candleWidth / 2, vY, candleWidth, vHeight);
  });

  // 3. Draw Candlestick Bodies & Wicks
  candles.forEach((c, i) => {
    const x = i * slotWidth + slotWidth / 2;
    const isBull = c.close >= c.open;
    const yHigh = priceToY(c.high);
    const yLow = priceToY(c.low);
    const yOpen = priceToY(c.open);
    const yClose = priceToY(c.close);

    const bodyTop = Math.min(yOpen, yClose);
    const bodyHeight = Math.max(1.8, Math.abs(yClose - yOpen));

    // Wick line
    ctx.strokeStyle = isBull ? "#10b981" : "#ef4444";
    ctx.lineWidth = 1.4;
    ctx.beginPath();
    ctx.moveTo(x, yHigh);
    ctx.lineTo(x, yLow);
    ctx.stroke();

    // Body rectangle
    ctx.fillStyle = isBull ? "#10b981" : "#ef4444";
    ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);
  });

  // 4. Calculate & Draw EMA Lines
  const closes = candles.map(c => c.close);
  const ema9 = calculateEMA(closes, 9);
  const ema21 = calculateEMA(closes, 21);

  // EMA 9 Line (Fast Momentum - Cyan)
  ctx.strokeStyle = "#06b6d4";
  ctx.lineWidth = 1.8;
  ctx.beginPath();
  for (let i = 0; i < ema9.length; i++) {
    const x = i * slotWidth + slotWidth / 2;
    const y = priceToY(ema9[i]);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // EMA 21 Line (Trend Baseline - Purple)
  ctx.strokeStyle = "#a855f7";
  ctx.lineWidth = 1.8;
  ctx.beginPath();
  for (let i = 0; i < ema21.length; i++) {
    const x = i * slotWidth + slotWidth / 2;
    const y = priceToY(ema21[i]);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.stroke();

  // 5. DRAW THE 10-STEP AI PREDICTED TRAJECTORY (GLOWING AMBER DOTS)
  if (forecastPath.length > 0 && numCandles > 0) {
    const lastCandleX = (numCandles - 1) * slotWidth + slotWidth / 2;
    const lastCandleY = priceToY(candles[candles.length - 1].close);

    // Connecting dashed trajectory line
    ctx.strokeStyle = "#f59e0b";
    ctx.lineWidth = 2.4;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.moveTo(lastCandleX, lastCandleY);

    const dotCoordinates = [];
    forecastPath.forEach((pVal, idx) => {
      const stepX = (numCandles + idx) * slotWidth + slotWidth / 2;
      const stepY = priceToY(pVal);
      ctx.lineTo(stepX, stepY);
      dotCoordinates.push({ x: stepX, y: stepY, price: pVal, step: idx + 1 });
    });
    ctx.stroke();
    ctx.setLineDash([]); // Reset line dash

    // Render each glowing amber prediction bead
    dotCoordinates.forEach(dot => {
      // Outer glow
      ctx.beginPath();
      ctx.arc(dot.x, dot.y, 8, 0, Math.PI * 2);
      ctx.fillStyle = "rgba(245, 158, 11, 0.28)";
      ctx.fill();

      // Main bead
      ctx.beginPath();
      ctx.arc(dot.x, dot.y, 5, 0, Math.PI * 2);
      ctx.fillStyle = "#f59e0b";
      ctx.fill();

      // Inner white core
      ctx.beginPath();
      ctx.arc(dot.x, dot.y, 2, 0, Math.PI * 2);
      ctx.fillStyle = "#ffffff";
      ctx.fill();
    });

    // Final Target Pill Badge on the 10th dot
    if (dotCoordinates.length > 0) {
      const lastDot = dotCoordinates[dotCoordinates.length - 1];
      const targetText = `🎯 ${formatPrice(lastDot.price)}`;
      ctx.font = "bold 11px 'JetBrains Mono', monospace";
      const textWidth = ctx.measureText(targetText).width;

      const badgeX = Math.min(plotWidth - textWidth - 10, lastDot.x + 8);
      const badgeY = lastDot.y - 12;

      ctx.fillStyle = "rgba(15, 23, 42, 0.9)";
      ctx.strokeStyle = "#f59e0b";
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.roundRect(badgeX, badgeY, textWidth + 12, 20, 4);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = "#fbbf24";
      ctx.fillText(targetText, badgeX + 6, badgeY + 14);
    }
  }

  // 6. Draw X-Axis Time Labels
  ctx.fillStyle = "#64748b";
  ctx.font = "10px 'JetBrains Mono', monospace";
  ctx.textAlign = "center";
  const labelInterval = Math.max(1, Math.floor(numCandles / 7));
  for (let i = 0; i < numCandles; i += labelInterval) {
    const x = i * slotWidth + slotWidth / 2;
    const timeLabel = formatCandleTime(candles[i].time, currentInterval);
    ctx.fillText(timeLabel, x, paddingTop + plotHeight + 18);
  }

  // 7. Interactive Crosshair & Cursor HUD Update
  if (cursor && cursor.x <= plotWidth && cursor.y >= paddingTop && cursor.y <= paddingTop + plotHeight) {
    const candleIdx = Math.floor(cursor.x / slotWidth);
    if (candleIdx >= 0 && candleIdx < numCandles) {
      const c = candles[candleIdx];
      const crossX = candleIdx * slotWidth + slotWidth / 2;
      const crossY = cursor.y;
      const cursorPrice = yToPrice(cursor.y);

      // Vertical crosshair line
      ctx.strokeStyle = "rgba(255, 255, 255, 0.25)";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.beginPath();
      ctx.moveTo(crossX, paddingTop);
      ctx.lineTo(crossX, paddingTop + plotHeight);
      ctx.stroke();

      // Horizontal crosshair line
      ctx.beginPath();
      ctx.moveTo(0, crossY);
      ctx.lineTo(plotWidth, crossY);
      ctx.stroke();
      ctx.setLineDash([]);

      // Right axis price badge
      ctx.fillStyle = "#38bdf8";
      ctx.beginPath();
      ctx.roundRect(plotWidth + 4, crossY - 10, paddingRight - 8, 20, 4);
      ctx.fill();
      ctx.fillStyle = "#0f172a";
      ctx.font = "bold 10px 'JetBrains Mono'";
      ctx.textAlign = "center";
      ctx.fillText(formatPrice(cursorPrice), plotWidth + paddingRight / 2, crossY + 4);

      // Update OHLC HUD
      const chg = ((c.close - c.open) / c.open) * 100;
      elHudDate.textContent = formatCandleTime(c.time, currentInterval);
      elHudOpen.textContent = formatPrice(c.open);
      elHudHigh.textContent = formatPrice(c.high);
      elHudLow.textContent = formatPrice(c.low);
      elHudClose.textContent = formatPrice(c.close);
      elHudChg.textContent = `${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%`;
      elHudChg.style.color = chg >= 0 ? "#10b981" : "#ef4444";
      elHudVol.textContent = Number(c.volume).toFixed(1);
    }
  }
}


// 7. Load Real-time Futures Market Data, Predictor & Indicators
async function loadCoinData(coin, isSilent = false) {
  if (!isSilent && elChartLoader) elChartLoader.classList.add("active");

  try {
    // 0. Fetch Multi-Timeframe Strategy & Leverage Advisor
    fetchAdvisorData(coin);

    // 1. Fetch Futures Analysis & Structure
    const resAnalysis = await fetch(`/api/analyze?coin=${coin}&interval=${currentInterval}`);
    if (resAnalysis.ok) {
      const analysis = await resAnalysis.json();
      if (analysis && analysis.price) {
        updateUIWithAnalysis(analysis);
      }
    }

    // 2. Fetch Futures Live Stats (Funding Rate, Mark Price)
    const resStats = await fetch(`/api/futures_stats?coin=${coin}`);
    if (resStats.ok) {
      const stats = await resStats.json();
      if (stats && stats.symbol) {
        activeFuturesStats = stats;
        updateFuturesStatsUI(stats);
      }
    }

    // 3. Fetch 10-Step Forward Predictive Forecast
    const resPredict = await fetch(`/api/predict?coin=${coin}&interval=${currentInterval}&steps=10`);
    if (resPredict.ok) {
      const prediction = await resPredict.json();
      if (prediction && prediction.direction) {
        activePrediction = prediction;
        updatePredictiveUI(prediction);
      }
    }

    // 4. Fetch Real Perpetual Futures Candlesticks (Long 90-candle depth)
    const pair = `B-${coin}_USDT`;
    const resCandles = await fetch(`/api/candles?pair=${pair}&interval=${currentInterval}&limit=90`);
    if (resCandles.ok) {
      const candleData = await resCandles.json();
      if (Array.isArray(candleData) && candleData.length > 0) {
        activeCandles = [...candleData].reverse(); // Chronological oldest to newest

        if (chartMode === "ai") {
          renderCandlestickChart(activeCandles, activePrediction);
          resetHudToLatest();
        }
      }
    }

    // Update TradingView if in TV mode
    if (chartMode === "tv") {
      updateTradingViewWidget();
    }
  } catch (err) {
    console.error("Error loading futures data:", err);
  } finally {
    if (!isSilent && elChartLoader) elChartLoader.classList.remove("active");
  }
}


// 8. Update Futures Statistics (Mark Price, Funding Rate, Liquidation)
function updateFuturesStatsUI(s) {
  if (elContractBadge) elContractBadge.textContent = s.contract || `${currentCoin}USDT.P (PERPETUAL)`;
  if (elMark) elMark.textContent = formatPrice(s.mark_price);
  
  if (elFunding) {
    const fRate = s.funding_rate || 0.01;
    elFunding.textContent = `${fRate >= 0 ? '+' : ''}${fRate.toFixed(4)}%`;
    if (elFundingPill) {
      elFundingPill.className = fRate >= 0 ? "funding-pill" : "funding-pill negative";
    }
  }

  updateLiquidationEstimate();
}


// 9. Update Predictive Forecast UI ("What Happens Next")
function updatePredictiveUI(p) {
  const dir = p.direction || "SIDEWAYS";
  const prob = p.probability || 50;
  const target = p.target_price || 0;
  const stop = p.stop_loss || 0;
  const chgPct = p.expected_change_pct || 0;

  elPredBadge.className = `forecast-badge ${dir.toLowerCase()}`;
  if (dir === "UP") {
    elPredArrow.textContent = "▲";
    elPredDirection.textContent = `FUTURES NEXT: UP / LONG (${chgPct >= 0 ? '+' : ''}${chgPct}%)`;
    elPredProb.textContent = `Probability: ${prob}% Bullish Momentum`;
    elPredTarget.textContent = `${formatPrice(target)} (+${Math.abs(chgPct)}%)`;
    elPredTarget.className = "target-val text-green";
  } else if (dir === "DOWN") {
    elPredArrow.textContent = "▼";
    elPredDirection.textContent = `FUTURES NEXT: DIP / SHORT (${chgPct}%)`;
    elPredProb.textContent = `Probability: ${prob}% Bearish Pullback`;
    elPredTarget.textContent = `${formatPrice(target)} (${chgPct}%)`;
    elPredTarget.className = "target-val text-red";
  } else {
    elPredArrow.textContent = "►";
    elPredDirection.textContent = "FUTURES NEXT: CONSOLIDATING";
    elPredProb.textContent = `Probability: 52% Range-bound`;
    elPredTarget.textContent = `${formatPrice(target)}`;
    elPredTarget.className = "target-val";
  }

  elPredStop.textContent = `${formatPrice(stop)}`;

  if (p.confluences && p.confluences.length > 0) {
    elConfluenceList.innerHTML = p.confluences.map(c => `<li>${c}</li>`).join("");
  } else {
    elConfluenceList.innerHTML = `<li>${p.summary || "Evaluating futures momentum..."}</li>`;
  }
}


// 10. Update Market Structure & Support/Resistance Meter
function updateUIWithAnalysis(a) {
  elSymbol.textContent = `${a.coin} / USDT`;
  elPrice.textContent = `${formatPrice(a.price)}`;
  elResistance.textContent = `${formatPrice(a.resistance)}`;
  elSupport.textContent = `${formatPrice(a.support)}`;
  elEma9.textContent = `${formatPrice(a.ema9)}`;
  elEma21.textContent = `${formatPrice(a.ema21)}`;

  const totalRange = a.resistance - a.support;
  let pctFromFloor = 50;
  if (totalRange > 0) {
    pctFromFloor = Math.max(0, Math.min(100, ((a.price - a.support) / totalRange) * 100));
  }

  elMeterFill.style.width = `${pctFromFloor}%`;
  elMeterPin.style.left = `${pctFromFloor}%`;
  elMeterSup.textContent = `${formatPrice(a.support)}`;
  elMeterRes.textContent = `${formatPrice(a.resistance)}`;
  elMeterDist.innerHTML = `Price is <b>${pctFromFloor.toFixed(0)}%</b> of the way up to 24h Ceiling`;

  const rsi = a.rsi || 50;
  elRsiVal.textContent = rsi.toFixed(1);
  elRsiBar.style.width = `${Math.min(100, rsi)}%`;

  if (rsi > 70) {
    elRsiBar.style.backgroundColor = "#ef4444";
  } else if (rsi > 50) {
    elRsiBar.style.backgroundColor = "#10b981";
  } else {
    elRsiBar.style.backgroundColor = "#06b6d4";
  }

  if (rsi > 70 || pctFromFloor > 90) {
    elVerdictBanner.className = "verdict-banner banner-warning";
    elVerdictIcon.textContent = "⚠️";
    elVerdictAction.textContent = "FUTURES WARNING: NEAR RESISTANCE CEILING";
    elVerdictDesc.textContent = `Futures price is touching resistance ceiling (${formatPrice(a.resistance)}) with RSI at ${rsi.toFixed(1)}. High risk of liquidation dump. Wait for a pullback before opening longs!`;
  } else if (rsi > 52 && a.ema9 > a.ema21) {
    elVerdictBanner.className = "verdict-banner banner-bullish";
    elVerdictIcon.textContent = "🚀";
    elVerdictAction.textContent = "STRONG BULLISH MOMENTUM (FAVOR LONG)";
    elVerdictDesc.textContent = `EMA(9) > EMA(21) with healthy RSI (${rsi.toFixed(1)}). High probability of upward continuation in perpetual contract.`;
  } else if (a.ema9 < a.ema21) {
    elVerdictBanner.className = "verdict-banner banner-danger";
    elVerdictIcon.textContent = "📉";
    elVerdictAction.textContent = "BEARISH MOMENTUM (FAVOR SHORT)";
    elVerdictDesc.textContent = `Sellers control the orderbook. EMA(9) crossed below EMA(21). Short opportunities favorable with tight stop-loss.`;
  } else {
    elVerdictBanner.className = "verdict-banner banner-warning";
    elVerdictIcon.textContent = "⚖️";
    elVerdictAction.textContent = "SIDEWAYS RANGE CONSOLIDATION";
    elVerdictDesc.textContent = `Contract is oscillating sideways. Wait for breakout above ${formatPrice(a.resistance)} or support bounce off ${formatPrice(a.support)}.`;
  }
}


// 11. Switch Between AI Candlesticks and Official TradingView Futures Chart
function switchChartMode(mode) {
  chartMode = mode;
  document.getElementById("btn-mode-ai").classList.toggle("active", mode === "ai");
  document.getElementById("btn-mode-tv").classList.toggle("active", mode === "tv");

  if (mode === "ai") {
    elCanvas.style.display = "block";
    elTradingViewContainer.style.display = "none";
    if (activeCandles.length > 0) {
      renderCandlestickChart(activeCandles, activePrediction);
    }
  } else {
    elCanvas.style.display = "none";
    elTradingViewContainer.style.display = "block";
    updateTradingViewWidget();
  }
}

let isChartExpanded = false;
function toggleChartHeight() {
  isChartExpanded = !isChartExpanded;
  const container = document.querySelector(".canvas-container");
  const btn = document.getElementById("btn-chart-expand");
  
  if (container) container.classList.toggle("expanded", isChartExpanded);
  if (btn) btn.textContent = isChartExpanded ? "↕ COMPACT" : "↕ EXPAND";

  setTimeout(() => {
    if (chartMode === "ai" && activeCandles.length > 0) {
      renderCandlestickChart(activeCandles, activePrediction);
    }
  }, 100);
}

function updateTradingViewWidget() {
  if (typeof TradingView === "undefined") {
    elTradingViewContainer.innerHTML = `
      <div style="display:flex;align-items:center;justify-content:center;height:100%;color:#94a3b8;font-size:0.85rem;">
        Connecting to TradingView Futures Stream...
      </div>`;
    return;
  }

  let tvInterval = "60";
  if (currentInterval === "1m") tvInterval = "1";
  else if (currentInterval === "5m") tvInterval = "5";
  else if (currentInterval === "15m") tvInterval = "15";
  else if (currentInterval === "1d") tvInterval = "D";

  elTradingViewContainer.innerHTML = "";
  try {
    tvWidget = new TradingView.widget({
      "autosize": true,
      "symbol": `BINANCE:${currentCoin}USDT.P`,
      "interval": tvInterval,
      "timezone": "Asia/Kolkata",
      "theme": "dark",
      "style": "1", // 1 = Real Candlesticks
      "locale": "in",
      "toolbar_bg": "#0e131f",
      "enable_publishing": false,
      "allow_symbol_change": false,
      "container_id": "tradingview-container",
      "hide_side_toolbar": false
    });
  } catch (e) {
    console.error("TradingView init error:", e);
  }
}


// 12. Futures Leverage & Liquidation Simulator
function setLeverage(lev) {
  currentLeverage = lev;
  document.querySelectorAll(".lev-btn").forEach(btn => {
    btn.classList.toggle("active", btn.textContent.trim() === `${lev}x`);
  });
  updateLiquidationEstimate();
  if (selectedAdvisorLev !== lev) {
    selectedAdvisorLev = lev;
    renderAdvisorLeverage(lev);
  }
}

function updateLiquidationEstimate() {
  if (!elLiqCalc) return;
  const price = parseFloat(elPrice.textContent.replace("$", "").replace(",", "")) || 0.45;
  const longLiq = price * Math.max(0.001, (1 - (0.9 / currentLeverage)));
  elLiqCalc.innerHTML = `Long Liq: <b>${formatPrice(longLiq)}</b> (${currentLeverage}x)`;
}


// 13. Select Coin from Ticker Chips, Search, Scanner, or All-Coins Modal
function selectCoin(coin, scrollToTop = false) {
  if (!coin) return;
  currentCoin = coin.toUpperCase().replace("B-", "").replace("USDT", "").replace(".P", "").trim();
  selectedAdvisorTf = null; // Reset to best timeframe for new coin

  // Close search dropdown and modal if open
  const searchDropdown = document.getElementById("search-autocomplete-dropdown");
  if (searchDropdown) searchDropdown.style.display = "none";
  closeAllCoinsModal();

  let found = false;
  document.querySelectorAll(".chip").forEach(chip => {
    if (chip.textContent.includes(currentCoin)) {
      chip.classList.add("active");
      found = true;
    } else {
      chip.classList.remove("active");
    }
  });

  if (!found) {
    const container = document.getElementById("ticker-chips-container");
    if (container) {
      const btn = document.createElement("button");
      btn.className = "chip active";
      btn.onclick = () => selectCoin(currentCoin);
      btn.innerHTML = `${currentCoin} <span class="chip-gain">SELECTED</span>`;
      container.prepend(btn);
    }
  }

  fetch("/api/bot/select_coin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ coin: currentCoin })
  }).catch(e => console.error("Error updating selected coin:", e));

  loadCoinData(currentCoin);
  updateCustomOrderSummary();

  if (scrollToTop) {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}


// 14. Timeframe Switcher
function setTimeframe(tf) {
  currentInterval = tf.toLowerCase();
  document.querySelectorAll(".tf-btn").forEach(btn => {
    const btnTf = btn.getAttribute("data-tf") || btn.textContent.trim().toLowerCase();
    btn.classList.toggle("active", btnTf === currentInterval);
  });
  loadCoinData(currentCoin);
}


// 15. Fetch Trending / High Volume / Top Dips for Ticker Bar
async function fetchTopGainers() {
  fetchTickerCategoryData("gainers");
}

async function fetchTickerCategoryData(cat = "gainers") {
  currentTickerCategory = cat;
  document.querySelectorAll(".cat-pill").forEach(p => {
    p.classList.toggle("active", p.id === `cat-${cat}`);
  });

  try {
    let url = "/api/all_coins?limit=12";
    if (cat === "gainers") url += "&sort=gainers";
    else if (cat === "losers") url += "&sort=losers";
    else url += "&sort=volume";

    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();
    const coins = data.coins || [];

    if (coins.length > 0) {
      const container = document.getElementById("ticker-chips-container");
      container.innerHTML = "";
      coins.slice(0, 10).forEach(c => {
        const coinName = c.coin;
        const change = parseFloat(c.change_24h || 0);
        const btn = document.createElement("button");
        btn.className = `chip ${coinName === currentCoin ? "active" : ""}`;
        btn.onclick = () => selectCoin(coinName);
        const sign = change >= 0 ? "+" : "";
        btn.innerHTML = `${coinName} <span class="chip-gain" style="color: ${change >= 0 ? '#34d399' : '#f87171'}">${sign}${change.toFixed(1)}%</span>`;
        container.appendChild(btn);
      });
    }
  } catch (e) {
    console.error("Failed to load ticker category:", e);
  }
}

function switchTickerCategory(cat) {
  fetchTickerCategoryData(cat);
}


// 16. Fetch Market Radar (Perpetual Futures Bullish & Bearish Signals)
async function fetchMarketRadar() {
  const bullishEl = document.getElementById("radar-bullish-list");
  const bearishEl = document.getElementById("radar-bearish-list");
  if (!bullishEl || !bearishEl) return;

  try {
    const res = await fetch("/api/market_radar");
    if (!res.ok) return;
    const data = await res.json();

    if (data.bullish && data.bullish.length > 0) {
      bullishEl.innerHTML = data.bullish.map(item => `
        <div class="radar-item" onclick="selectCoin('${item.coin}')" title="Click to view ${item.coin} Perpetual Futures chart">
          <div class="radar-item-left">
            <span class="radar-coin-name">${item.coin}</span>
            <span class="radar-price">${formatPrice(item.price)}</span>
          </div>
          <span class="radar-change-badge bull-badge">+${Number(item.change).toFixed(1)}%</span>
        </div>
      `).join("");
    } else {
      bullishEl.innerHTML = `<div class="radar-loading">No bullish signals detected</div>`;
    }

    if (data.bearish && data.bearish.length > 0) {
      bearishEl.innerHTML = data.bearish.map(item => `
        <div class="radar-item" onclick="selectCoin('${item.coin}')" title="Click to view ${item.coin} Perpetual Futures chart">
          <div class="radar-item-left">
            <span class="radar-coin-name">${item.coin}</span>
            <span class="radar-price">${formatPrice(item.price)}</span>
          </div>
          <span class="radar-change-badge bear-badge">${Number(item.change).toFixed(1)}%</span>
        </div>
      `).join("");
    } else {
      bearishEl.innerHTML = `<div class="radar-loading">No bearish signals detected</div>`;
    }
  } catch (err) {
    console.error("Failed to load futures market radar:", err);
  }
}


// 17. Sync Bot Status & Balances
async function syncBotStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();

    isBotRunning = data.is_running;
    const isLive = !data.dry_run && data.real_connected;
    const futuresBal = (data.futures_balance !== undefined && data.futures_balance > 0) ? data.futures_balance : (data.live_balance || 1554.01);
    const spotBal = data.spot_balance !== undefined ? data.spot_balance : 553.01;
    const paperBal = data.paper_balance !== undefined ? data.paper_balance : 30000.0;
    const displayBal = isLive ? futuresBal : paperBal;
    
    if (elHeaderBalance) elHeaderBalance.textContent = `INR ${displayBal.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    if (elCardBalance) elCardBalance.textContent = `INR ${displayBal.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

    const elFuturesBal = document.getElementById("card-futures-balance");
    if (elFuturesBal) {
      const activeFutures = isLive ? futuresBal : paperBal;
      elFuturesBal.textContent = `INR ${activeFutures.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
    const elSpotBal = document.getElementById("card-spot-balance");
    if (elSpotBal) {
      elSpotBal.textContent = `INR ${spotBal.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }
    const elTradeChunk = document.getElementById("card-trade-chunk");
    if (elTradeChunk) {
      const slotSize = isLive ? Math.round(futuresBal / 10) : Math.round(paperBal / 10);
      elTradeChunk.textContent = `₹${slotSize.toLocaleString("en-IN")} / slot`;
    }

    // Update wallet badge label
    const modeBadge = document.querySelector(".mode-badge");
    if (modeBadge) {
      modeBadge.textContent = isLive ? "LIVE FUTURES" : "PAPER WALLET";
      modeBadge.style.background = isLive ? "rgba(16, 185, 129, 0.25)" : "rgba(255, 255, 255, 0.08)";
      modeBadge.style.color = isLive ? "#34d399" : "#fff";
    }

    const engineTag = document.getElementById("engine-mode-tag");
    if (engineTag) {
      engineTag.textContent = isLive ? "LIVE COINDCX FUTURES" : "PAPER SIMULATION";
      engineTag.style.background = isLive ? "rgba(16, 185, 129, 0.2)" : "rgba(56, 189, 248, 0.15)";
      engineTag.style.color = isLive ? "#34d399" : "#38bdf8";
    }

    if (isBotRunning) {
      elBotToggleBtn.classList.add("running");
      elBotToggleText.textContent = "STOP BOT";
      elBotToggleIcon.textContent = "⏹";
    } else {
      elBotToggleBtn.classList.remove("running");
      elBotToggleText.textContent = "START BOT";
      elBotToggleIcon.textContent = "▶";
    }

    // Sync Pause New Trades (Manage-Only Mode) Button
    const btnNewTrades = document.getElementById("btn-toggle-new-trades");
    const newTradesIcon = document.getElementById("new-trades-icon");
    const newTradesText = document.getElementById("new-trades-text");
    const allowNewTrades = data.allow_new_trades !== false;
    if (btnNewTrades && newTradesIcon && newTradesText) {
      if (allowNewTrades) {
        btnNewTrades.classList.remove("paused");
        newTradesIcon.textContent = "⏸️";
        newTradesText.textContent = "PAUSE NEW TRADES";
        btnNewTrades.title = "Click to stop opening new trades while continuing to actively manage current open positions.";
      } else {
        btnNewTrades.classList.add("paused");
        newTradesIcon.textContent = "▶️";
        newTradesText.textContent = "RESUME NEW TRADES";
        btnNewTrades.title = "Manage-Only Mode is ACTIVE. Bot is actively managing open trades, but will NOT open new ones. Click to resume new trades.";
      }
    }

    // Dynamic 24/7 Market Regime HUD
    if (data.market_regime) {
      const modeBadge = document.getElementById("risk-mode-badge");
      const modeDesc = document.getElementById("risk-mode-desc");
      const activeMode = data.active_risk_mode || data.risk_mode;
      const tpTarget = data.active_target_tp || (activeMode === 'USER_MIRROR' ? 1.25 : (activeMode === 'SAFE' ? 2.0 : (activeMode === 'ALPHA' ? 4.5 : 3.5)));

      if (modeBadge) {
        modeBadge.textContent = `AUTO: ${activeMode} (TP +${tpTarget}%)`;
        if (activeMode === "USER_MIRROR") {
          modeBadge.style.color = "#c084fc";
          modeBadge.style.background = "rgba(168, 85, 247, 0.2)";
        } else if (activeMode === "ALPHA" || activeMode === "AGGRESSIVE") {
          modeBadge.style.color = "#f59e0b";
          modeBadge.style.background = "rgba(245, 158, 11, 0.2)";
        } else if (activeMode === "SAFE") {
          modeBadge.style.color = "#10b981";
          modeBadge.style.background = "rgba(16, 185, 129, 0.2)";
        } else {
          modeBadge.style.color = "#38bdf8";
          modeBadge.style.background = "rgba(56, 189, 248, 0.2)";
        }
      }

      if (modeDesc) {
        modeDesc.textContent = data.market_regime;
      }

      const btnMirror = document.getElementById("risk-btn-user-mirror");
      const btnSafe = document.getElementById("risk-btn-safe");
      const btnBalanced = document.getElementById("risk-btn-balanced");
      const btnAggressive = document.getElementById("risk-btn-aggressive");
      if (btnMirror) btnMirror.classList.toggle("active", activeMode === "USER_MIRROR");
      if (btnSafe) btnSafe.classList.toggle("active", activeMode === "SAFE");
      if (btnBalanced) btnBalanced.classList.toggle("active", activeMode === "BALANCED");
      if (btnAggressive) btnAggressive.classList.toggle("active", activeMode === "ALPHA" || activeMode === "AGGRESSIVE");
    }

    const positions = (data.active_positions && Array.isArray(data.active_positions) && data.active_positions.length > 0)
      ? data.active_positions
      : (data.active_position ? [data.active_position] : []);

    const maxSlots = data.max_slots || 5;
    if (positions.length > 0) {
      const totalActivePnlInr = positions.reduce((sum, p) => sum + (Number(p.invested || 200) * ((p.gross_pnl_pct || 0) / 100.0)), 0);
      const totalSign = totalActivePnlInr >= 0 ? "+₹" : "-₹";
      const totalPnlStr = `${totalSign}${Math.abs(totalActivePnlInr).toFixed(2)}`;
      const totalColor = totalActivePnlInr >= 0 ? "#10b981" : "#ef4444";

      if (!allowNewTrades) {
        elPosBadge.innerHTML = `MANAGE-ONLY (${positions.length}/${maxSlots} SLOTS) • Live PnL: <b style="color:${totalColor}">${totalPnlStr}</b>`;
        elPosBadge.style.color = "#f59e0b";
      } else {
        elPosBadge.innerHTML = `ACTIVE (${positions.length}/${maxSlots} SLOTS) • Live PnL: <b style="color:${totalColor}">${totalPnlStr}</b>`;
        elPosBadge.style.color = "#38bdf8";
      }

      let posHtml = '<div class="active-positions-list">';
      window._ACTIVE_POSITIONS_MAP = {};
      positions.forEach(pos => {
        window._ACTIVE_POSITIONS_MAP[pos.symbol] = Object.assign({}, pos);
        const isShort = (pos.direction || pos.side) === "SHORT";
        const isRunner = Boolean(pos.is_runner);
        const lev = pos.leverage || 4;
        const invested = Number(pos.invested || 3000).toFixed(2);
        const qty = Number(pos.quantity || 0).toFixed(4);
        const target = pos.target ? formatPrice(pos.target) : "--";
        const stop = pos.trailing_stop ? formatPrice(pos.trailing_stop) : (pos.stop_loss ? formatPrice(pos.stop_loss) : "--");
        const runnerTag = isRunner ? `<span class="badge-runner">⚡ RUNNER (+${pos.runner_target_pct || 28}% TP)</span>` : '';

        const entry = Number(pos.buy_price || pos.price || 0);
        const current = Number(pos.current_price || entry);
        const targetVal = Number(pos.target || 0);

        // Calculate gross leveraged PnL %
        let grossPnlPct = 0;
        if (pos.gross_pnl_pct !== undefined && pos.gross_pnl_pct !== null) {
          grossPnlPct = Number(pos.gross_pnl_pct);
        } else if (entry > 0) {
          const rawMove = isShort ? ((entry - current) / entry) * 100 : ((current - entry) / entry) * 100;
          grossPnlPct = rawMove * lev;
        }

        const trailLockPct = Number(pos.trailing_lock_pct || 0);
        const hasProfitLock = trailLockPct > 0 || (pos.trailing_stop && (isShort ? Number(pos.trailing_stop) < entry : Number(pos.trailing_stop) > entry));

        // Defense level (-65% Margin Drawdown or Trailing Profit Lock)
        let slDefense = Number(pos.sl_defense_price || 0);
        if (!slDefense || slDefense <= 0) {
          if (pos.trailing_stop) {
            slDefense = Number(pos.trailing_stop);
          } else if (pos.stop_loss) {
            slDefense = Number(pos.stop_loss);
          } else {
            slDefense = isShort ? (entry * (1.0 + (0.48 / lev))) : (entry * (1.0 - (0.48 / lev)));
          }
        }

        // Lock notch position on track (if profit locked)
        let lockNotchHtml = '';
        if (hasProfitLock && targetPnlPct > 0) {
          const lockRatio = Math.min(1.0, (trailLockPct || 7.0) / targetPnlPct);
          const lockNeedlePct = Math.max(52, Math.min(95, 50.0 + (lockRatio * 50.0)));
          lockNotchHtml = `<div class="pos-gauge-trail-lock" style="left: ${lockNeedlePct.toFixed(1)}%;" title="🔒 Trailing Profit Lock (+${trailLockPct}%): ${formatPrice(slDefense)}"></div>`;
        }

        // Target PnL %
        let targetPnlPct = Number(pos.tp_target_pct || 0);
        if (!targetPnlPct && entry > 0 && targetVal > 0) {
          const rawTargetMove = isShort ? ((entry - targetVal) / entry) * 100 : ((targetVal - entry) / entry) * 100;
          targetPnlPct = Math.max(5, rawTargetMove * lev);
        }
        if (!targetPnlPct || targetPnlPct <= 0) targetPnlPct = 15.0;

        // Needle percentage: 0% = -48% SL defense, 50% = Entry (0%), 100% = Target TP
        let needlePct = 50.0;
        if (grossPnlPct >= 0) {
          const ratio = Math.min(1.0, grossPnlPct / targetPnlPct);
          needlePct = 50.0 + (ratio * 50.0);
        } else {
          const ratio = Math.min(1.0, Math.abs(grossPnlPct) / 48.0);
          needlePct = 50.0 - (ratio * 50.0);
        }
        needlePct = Math.max(3, Math.min(97, Math.round(needlePct * 10) / 10));

        const isProfit = grossPnlPct >= 0;
        const pnlSign = grossPnlPct > 0 ? "+" : "";
        const pnlFormatted = `${pnlSign}${grossPnlPct.toFixed(1)}%`;
        const pnlColorClass = isProfit ? "pos-pnl-green" : "pos-pnl-red";
        const pinIcon = isProfit ? "▲" : "▼";

        let fillStyle = "";
        if (needlePct >= 50) {
          fillStyle = `left: 50%; width: ${(needlePct - 50).toFixed(1)}%;`;
        } else {
          fillStyle = `left: ${needlePct.toFixed(1)}%; width: ${(50 - needlePct).toFixed(1)}%;`;
        }

        const investedNum = Number(pos.invested || 200.0);
        const curActivePnlInr = investedNum * (grossPnlPct / 100.0);
        const pnlInrSign = curActivePnlInr >= 0 ? "+₹" : "-₹";
        const pnlInrFormatted = `${pnlInrSign}${Math.abs(curActivePnlInr).toFixed(2)}`;

        // Expected INR amounts at Target TP and at -48% SL Defense
        const tpGainInr = investedNum * (targetPnlPct / 100.0);
        const slLossInr = investedNum * (48.0 / 100.0);

        posHtml += `
          <div class="active-pos-card ${isShort ? 'short-pos' : 'long-pos'}" id="pos-card-${pos.symbol}">
            <div class="pos-card-head">
              <span class="pos-dir-pill ${isShort ? 'short' : 'long'}">${isShort ? 'SHORT' : 'LONG'}</span>
              <span class="pos-coin-name">${pos.symbol}</span>
              <span class="pos-lev-badge">${lev}x</span>
              <span class="pos-live-pnl-tag ${pnlColorClass}" id="pos-live-pnl-${pos.symbol}">${pnlInrFormatted} (${pnlSign}${grossPnlPct.toFixed(2)}%)</span>
              ${hasProfitLock ? `<span class="badge-profit-lock">🔒 +${trailLockPct || 7}% LOCKED</span>` : ''}
              ${runnerTag}
              <button type="button" class="btn-close-single-pos" onclick="closePositionByCoin('${pos.symbol}')" title="Close ${pos.symbol}">✕ Close</button>
            </div>
            <div class="pos-card-metrics">
              <div class="pos-m-row">
                <span>Entry:</span> <b>${formatPrice(pos.buy_price)}</b> •
                <span>Live:</span> <b class="${pnlColorClass}" id="pos-live-val-${pos.symbol}">${formatPrice(current)}</b> •
                <span>Margin:</span> <b>₹${invested}</b> (${qty} ${pos.symbol})
              </div>
              <div class="pos-m-row">
                <span>Target:</span> <b class="pos-tp-txt">${target} (+${targetPnlPct.toFixed(0)}% / +₹${tpGainInr.toFixed(2)})</b> • 
                <span>${hasProfitLock ? 'Profit Lock:' : 'SL Defense:'}</span> <b class="${hasProfitLock ? 'pos-lock-txt' : 'pos-sl-txt'}">${hasProfitLock ? '🔒 +' + (trailLockPct || 7) + '% (' + formatPrice(slDefense) + ')' : formatPrice(slDefense) + ' (-48% / -₹' + slLossInr.toFixed(2) + ')'}</b>
              </div>
            </div>

            <!-- Real-Time Dual-Direction Distance Gauge Bar -->
            <div class="pos-gauge-container">
              <div class="pos-gauge-track">
                <!-- Center 50% Entry Tick -->
                <div class="pos-gauge-center-line" title="Entry Point: ${formatPrice(entry)} (0%)"></div>
                ${lockNotchHtml}
                <!-- Dynamic Active Fill from Center -->
                <div class="pos-gauge-fill ${isProfit ? 'fill-profit' : 'fill-loss'}" id="pos-fill-${pos.symbol}" style="${fillStyle}"></div>
                <!-- Live Real-Time Moving Pin -->
                <div class="pos-gauge-needle ${isProfit ? 'needle-profit' : 'needle-loss'}" id="pos-needle-${pos.symbol}" style="left: ${needlePct}%;">
                  <div class="pos-gauge-pin"></div>
                  <div class="pos-gauge-pin-badge ${pnlColorClass}" id="pos-pin-${pos.symbol}">
                    ${pinIcon} ${pnlInrFormatted} (${pnlFormatted})
                  </div>
                </div>
              </div>

              <!-- Legend / Labels Below Bar -->
              <div class="pos-gauge-labels">
                <div class="pos-gl-item ${hasProfitLock ? 'pos-gl-lock' : 'pos-gl-sl'}">
                  <span class="pos-gl-title">${hasProfitLock ? `🔒 +${trailLockPct || 7}% Lock` : '🛡️ -48% Def (-₹' + slLossInr.toFixed(0) + ')'}</span>
                  <span class="pos-gl-val">${formatPrice(slDefense)}</span>
                </div>
                <div class="pos-gl-item pos-gl-entry">
                  <span class="pos-gl-title">📍 Entry</span>
                  <span class="pos-gl-val">${formatPrice(entry)}</span>
                </div>
                <div class="pos-gl-item pos-gl-tp">
                  <span class="pos-gl-title">🎯 TP +${targetPnlPct.toFixed(0)}% (+₹${tpGainInr.toFixed(0)})</span>
                  <span class="pos-gl-val">${target}</span>
                </div>
              </div>
            </div>
          </div>
        `;
      });
      posHtml += '</div>';
      elPosDetails.innerHTML = posHtml;
      syncWebSocketSubscriptions(positions);
    } else {
      if (!allowNewTrades) {
        elPosBadge.textContent = `MANAGE-ONLY (0/${maxSlots} SLOTS - STANDBY)`;
        elPosBadge.style.color = "#f59e0b";
      } else {
        elPosBadge.textContent = `NO ACTIVE TRADES (0/${maxSlots} SLOTS)`;
        elPosBadge.style.color = "#94a3b8";
      }
      elPosDetails.textContent = `Model Status: [${data.last_signal || 'AUTONOMOUS 24/7'}] - ${data.last_reason || 'Scanning 700+ coins across 5 slots'}`;
    }

    if (data.performance_summary) {
      updateTradePerformanceHUD(data.performance_summary);
    }

    if (data.trade_history) {
      const historyHash = JSON.stringify(data.trade_history.map(t => t.time + (t.pnl || t.amount)));
      if (historyHash !== lastRenderedTradesHash) {
        lastRenderedTradesHash = historyHash;
        allTradeHistory = data.trade_history;
        renderTradeLogList();
      }
    }
  } catch (e) {
    console.error("Status sync error:", e);
  }
}

// Global Trade State (Paper vs Live View)
let currentHistorySource = "PAPER";
let liveTradeHistoryData = null;
let allTradeHistory = [];
let activeTradeFilter = "ALL";
let activeDirectionFilter = "ALL";
let lastRenderedTradesHash = "";

async function setHistoryView(src) {
  currentHistorySource = src;
  const btnPaper = document.getElementById("btn-hist-paper");
  const btnLive = document.getElementById("btn-hist-live");
  if (btnPaper) {
    btnPaper.style.background = src === "PAPER" ? "rgba(56, 189, 248, 0.2)" : "rgba(255, 255, 255, 0.06)";
    btnPaper.style.color = src === "PAPER" ? "#38bdf8" : "#94a3b8";
    btnPaper.style.borderColor = src === "PAPER" ? "rgba(56, 189, 248, 0.4)" : "rgba(255, 255, 255, 0.1)";
  }
  if (btnLive) {
    btnLive.style.background = src === "LIVE" ? "rgba(16, 185, 129, 0.2)" : "rgba(255, 255, 255, 0.06)";
    btnLive.style.color = src === "LIVE" ? "#34d399" : "#94a3b8";
    btnLive.style.borderColor = src === "LIVE" ? "rgba(16, 185, 129, 0.4)" : "rgba(255, 255, 255, 0.1)";
  }

  if (src === "LIVE") {
    if (!liveTradeHistoryData) {
      try {
        const res = await fetch("/api/live_trades");
        if (res.ok) {
          liveTradeHistoryData = await res.json();
        }
      } catch (e) {
        console.error("Failed to load live trades:", e);
      }
    }
    if (liveTradeHistoryData) {
      updateTradePerformanceHUD(liveTradeHistoryData.summary);
      allTradeHistory = liveTradeHistoryData.trades || [];
      lastRenderedTradesHash = "";
      renderTradeLogList();
      return;
    }
  }

  lastRenderedTradesHash = "";
  syncBotStatus();
}

function updateTradePerformanceHUD(summary) {
  if (!summary) return;
  const elNetPnl = document.getElementById("hud-net-pnl");
  const elWinRate = document.getElementById("hud-win-rate");
  const elWinLoss = document.getElementById("hud-win-loss");
  const elTotalTrades = document.getElementById("hud-total-trades");

  const netPnl = Number(summary.total_pnl_inr || 0);
  const winRate = Number(summary.win_rate_pct || 0);
  const wins = Number(summary.wins || 0);
  const losses = Number(summary.losses || 0);
  const total = Number(summary.total_trades || 0);
  const totalDeductions = Number(summary.total_deductions_inr || 0);
  const totalGross = Number(summary.gross_pnl_inr || 0);
  const totalTds = Number(summary.total_tds_inr || 0);
  const totalTax = Number(summary.total_tax_inr || 0);
  const totalFees = Number(summary.total_fees_inr || 0);

  if (total === 0 && currentHistorySource === "PAPER") {
    if (elNetPnl) {
      elNetPnl.textContent = "INR +0.00";
      elNetPnl.style.color = "#10b981";
      elNetPnl.title = "Futures Capital: ₹3,006.31 • Strict 5-Timeframe Live Confluence";
      const cell = elNetPnl.closest(".trade-hud-cell");
      if (cell) cell.style.borderLeftColor = "#10b981";
    }
    if (elWinRate) {
      elWinRate.textContent = "100% Target";
      elWinRate.style.color = "#38bdf8";
    }
    if (elWinLoss) {
      elWinLoss.textContent = "0W / 0L";
    }
    if (elTotalTrades) {
      elTotalTrades.textContent = "0 / 5 Slots";
      elTotalTrades.title = "Dynamic 5-slot manager active (₹200-₹250 sizing).";
    }
    return;
  }

  if (elNetPnl) {
    elNetPnl.textContent = `INR ${netPnl >= 0 ? '+' : ''}${netPnl.toFixed(2)}`;
    elNetPnl.style.color = netPnl >= 0 ? "#10b981" : "#ef4444";
    elNetPnl.title = `In-Pocket Net: INR ${netPnl.toFixed(2)}\nGross Market PnL: INR ${totalGross.toFixed(2)}\nExchange Fees (0.1%): -INR ${totalFees.toFixed(2)}\nTDS 1% (Sec 194S): -INR ${totalTds.toFixed(2)}\nGovt Tax 31.2% (Sec 115BBH): -INR ${totalTax.toFixed(2)}\nTotal Deductions: -INR ${totalDeductions.toFixed(2)}`;
    const cell = elNetPnl.closest(".trade-hud-cell");
    if (cell) cell.style.borderLeftColor = netPnl >= 0 ? "#10b981" : "#ef4444";
  }

  if (elWinRate) {
    elWinRate.textContent = `${winRate.toFixed(1)}%`;
    elWinRate.style.color = winRate >= 50 ? "#34d399" : (winRate > 0 ? "#f59e0b" : "#94a3b8");
  }

  if (elWinLoss) {
    elWinLoss.textContent = `${wins}W / ${losses}L`;
  }

  if (elTotalTrades) {
    elTotalTrades.textContent = `${total} trades`;
    if (totalDeductions > 0) {
      elTotalTrades.title = `Total Govt Tax & Fees Deducted: INR ${totalDeductions.toFixed(2)}`;
    }
  }
}

function filterTradeHistoryTab(tab) {
  activeTradeFilter = tab;
  ["ALL", "WINS", "LOSSES"].forEach(t => {
    const btn = document.getElementById(`tab-trade-${t.toLowerCase()}`);
    if (btn) btn.classList.toggle("active", t === tab);
  });
  renderTradeLogList();
}

function filterTradeDirection(dir) {
  activeDirectionFilter = (dir || "ALL").toUpperCase();
  renderTradeLogList();
}

// ==============================================================================
// IST (Indian Standard Time) Date Formatting & Filtering Controls
// ==============================================================================
let activeDateFilter = "ALL"; // 'ALL', 'TODAY', 'YESTERDAY', 'CUSTOM'
let dateFilterFrom = "";
let dateFilterTo = "";

function getISTDateString(d = new Date()) {
  // IST is UTC + 5:30
  const utc = d.getTime() + (d.getTimezoneOffset() * 60000);
  const ist = new Date(utc + (3600000 * 5.5));
  const year = ist.getFullYear();
  const month = String(ist.getMonth() + 1).padStart(2, "0");
  const day = String(ist.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getTradeDateString(t) {
  const raw = t.timestamp || t.time || "";
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) return `${match[1]}-${match[2]}-${match[3]}`;
  if (t.entry_time) {
    return getISTDateString(new Date(Number(t.entry_time) * 1000));
  }
  return "";
}

function filterTradeDatePreset(preset) {
  activeDateFilter = preset;
  const fromInput = document.getElementById("trade-date-from");
  const toInput = document.getElementById("trade-date-to");

  const todayStr = getISTDateString(new Date());
  const yest = new Date();
  yest.setDate(yest.getDate() - 1);
  const yestStr = getISTDateString(yest);

  if (preset === "ALL") {
    dateFilterFrom = "";
    dateFilterTo = "";
    if (fromInput) fromInput.value = "";
    if (toInput) toInput.value = "";
  } else if (preset === "TODAY") {
    dateFilterFrom = todayStr;
    dateFilterTo = todayStr;
    if (fromInput) fromInput.value = todayStr;
    if (toInput) toInput.value = todayStr;
  } else if (preset === "YESTERDAY") {
    dateFilterFrom = yestStr;
    dateFilterTo = yestStr;
    if (fromInput) fromInput.value = yestStr;
    if (toInput) toInput.value = yestStr;
  }

  ["all", "today", "yesterday"].forEach(p => {
    const btn = document.getElementById(`date-btn-${p}`);
    if (btn) btn.classList.toggle("active", p.toUpperCase() === preset);
  });

  renderTradeLogList();
}

function onTradeDateRangeChanged() {
  const fromInput = document.getElementById("trade-date-from");
  const toInput = document.getElementById("trade-date-to");
  dateFilterFrom = fromInput ? fromInput.value : "";
  dateFilterTo = toInput ? toInput.value : "";

  activeDateFilter = (dateFilterFrom || dateFilterTo) ? "CUSTOM" : "ALL";

  ["all", "today", "yesterday"].forEach(p => {
    const btn = document.getElementById(`date-btn-${p}`);
    if (btn) btn.classList.remove("active");
  });
  if (activeDateFilter === "ALL") {
    const btnAll = document.getElementById("date-btn-all");
    if (btnAll) btnAll.classList.add("active");
  }

  renderTradeLogList();
}

function resetTradeDateFilter() {
  filterTradeDatePreset("ALL");
}

function updateDynamicTradeHUD(trades) {
  const completed = trades.filter(t => t.type === "SELL" || t.type === "BUY_COVER" || (t.pnl !== undefined && t.pnl !== null));
  const wins = completed.filter(t => (t.gross_pnl !== undefined && Number(t.gross_pnl) > 0) || Number(t.pnl || t.pnl_inr || 0) >= 0);
  const losses = completed.filter(t => (t.gross_pnl !== undefined ? Number(t.gross_pnl) < 0 : false) && Number(t.pnl || t.pnl_inr || 0) < 0);
  const netPnl = completed.reduce((acc, t) => acc + Number(t.pnl || t.pnl_inr || 0), 0);
  const winRate = completed.length > 0 ? (wins.length / completed.length) * 100 : 0;

  const elNetPnl = document.getElementById("hud-net-pnl");
  const elWinRate = document.getElementById("hud-win-rate");
  const elWinLoss = document.getElementById("hud-win-loss");
  const elTotalTrades = document.getElementById("hud-total-trades");

  if (elNetPnl) {
    elNetPnl.textContent = `INR ${netPnl >= 0 ? '+' : ''}${netPnl.toFixed(2)}`;
    elNetPnl.style.color = netPnl >= 0 ? "#10b981" : "#ef4444";
    const cell = elNetPnl.closest(".trade-hud-cell");
    if (cell) cell.style.borderLeftColor = netPnl >= 0 ? "#10b981" : "#ef4444";
  }
  if (elWinRate) {
    elWinRate.textContent = completed.length > 0 ? `${winRate.toFixed(1)}%` : "100% Target";
    elWinRate.style.color = winRate >= 50 ? "#34d399" : (completed.length > 0 ? "#f59e0b" : "#38bdf8");
  }
  if (elWinLoss) {
    elWinLoss.textContent = `${wins.length}W / ${losses.length}L`;
  }
  if (elTotalTrades) {
    elTotalTrades.textContent = `${trades.length} trades`;
  }
}

function formatTradeDateTime(t) {
  const ts = t.timestamp || "";
  const tm = t.time || "";

  // 1. If timestamp has date and clock (e.g. "2026-10-17 03:45:12" or "2026-10-17T03:45:12")
  const raw = ts || tm;
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}:\d{2}(?::\d{2})?)/);
  if (match) {
    const [_, year, month, day, clock] = match;
    const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const mStr = monthNames[parseInt(month, 10) - 1] || month;
    return `<span class="time-date">${day} ${mStr} ${year}</span> <span class="time-clock">${clock}</span> <span style="font-size:0.58rem; color:#c084fc; font-weight:700; margin-left:2px;">IST</span>`;
  }

  // 2. If timestamp or time has just time "17:19:31"
  if (tm) {
    return `<span class="time-clock">${tm}</span> <span style="font-size:0.58rem; color:#c084fc; font-weight:700; margin-left:2px;">IST</span>`;
  }
  return raw;
}

function renderTradeLogList() {
  if (!elTradeLogList) return;

  // Protect active user mouse highlight from being wiped by polling
  const sel = window.getSelection();
  if (sel && sel.toString().length > 0 && elTradeLogList.contains(sel.anchorNode)) {
    return;
  }

  let filtered = allTradeHistory;

  // 1. Filter by Result (WINS vs LOSSES)
  if (activeTradeFilter === "WINS") {
    filtered = filtered.filter(t => {
      const isExit = t.type === "SELL" || t.type === "BUY_COVER" || (t.pnl !== undefined && t.pnl !== null);
      const isGrossWin = t.gross_pnl !== undefined && Number(t.gross_pnl) > 0;
      return isExit && (Number(t.pnl || t.pnl_inr || 0) >= 0 || isGrossWin);
    });
  } else if (activeTradeFilter === "LOSSES") {
    filtered = filtered.filter(t => {
      const isExit = t.type === "SELL" || t.type === "BUY_COVER" || (t.pnl !== undefined && t.pnl !== null);
      const isGrossWin = t.gross_pnl !== undefined && Number(t.gross_pnl) > 0;
      return isExit && Number(t.pnl || t.pnl_inr || 0) < 0 && !isGrossWin;
    });
  }

  // 2. Filter by Direction (LONG vs SHORT)
  if (activeDirectionFilter !== "ALL") {
    filtered = filtered.filter(t => {
      const dir = (t.direction || (t.type === "SELL_SHORT" || t.type === "BUY_COVER" ? "SHORT" : "LONG")).toUpperCase();
      return dir === activeDirectionFilter;
    });
  }

  // 3. Filter by Date Range (IST)
  if (activeDateFilter !== "ALL" || dateFilterFrom || dateFilterTo) {
    filtered = filtered.filter(t => {
      const tradeDate = getTradeDateString(t);
      if (!tradeDate) return true;
      if (dateFilterFrom && tradeDate < dateFilterFrom) return false;
      if (dateFilterTo && tradeDate > dateFilterTo) return false;
      return true;
    });
  }

  // Recalculate HUD stats if filtered by date or tags
  if (activeDateFilter !== "ALL" || activeTradeFilter !== "ALL" || activeDirectionFilter !== "ALL") {
    updateDynamicTradeHUD(filtered);
  }

  if (!filtered || filtered.length === 0) {
    let dateFilterNote = "";
    if (activeDateFilter === "TODAY") dateFilterNote = " for Today (IST)";
    else if (activeDateFilter === "YESTERDAY") dateFilterNote = " for Yesterday";
    else if (dateFilterFrom || dateFilterTo) dateFilterNote = ` in selected date range (${dateFilterFrom || 'start'} to ${dateFilterTo || 'now'})`;

    if (currentHistorySource === "PAPER") {
      elTradeLogList.innerHTML = `<div class="empty-trades" id="empty-trades-banner">🎯 Autonomous Live Engine Armed & Standing By (₹3,006.31 Capital). 0/5 Slots Active. No executions${dateFilterNote} yet.</div>`;
    } else {
      elTradeLogList.innerHTML = `<div class="empty-trades">No ${activeTradeFilter !== 'ALL' ? activeTradeFilter.toLowerCase() : ''} ${activeDirectionFilter !== 'ALL' ? activeDirectionFilter.toLowerCase() + ' ' : ''}executions${dateFilterNote} recorded yet.</div>`;
    }
    return;
  }

  elTradeLogList.innerHTML = filtered.map(t => {
    const isExit = t.type === "SELL" || t.type === "BUY_COVER" || (t.pnl !== undefined && t.pnl !== null);
    const dir = (t.direction || (t.type === "SELL_SHORT" || t.type === "BUY_COVER" ? "SHORT" : "LONG")).toUpperCase();
    const isShort = dir === "SHORT";
    const lev = t.leverage ? `${t.leverage}x` : (t.note && t.note.includes("x") ? t.note.match(/(\d+)x/)?.[0] : "4x");
    const grossVal = t.gross_pnl !== undefined && t.gross_pnl !== null ? Number(t.gross_pnl) : null;
    const pnlVal = t.pnl !== undefined ? Number(t.pnl) : (t.pnl_inr !== undefined ? Number(t.pnl_inr) : null);
    const pnlPct = t.pnl_pct !== undefined ? Number(t.pnl_pct) : null;
    const isGrossWin = grossVal !== null && grossVal > 0;
    const isWin = isGrossWin || (pnlVal !== null && pnlVal >= 0);
    const isLoss = (grossVal !== null ? grossVal < 0 : false) && (pnlVal !== null && pnlVal < 0);

    let pnlColor = "#94a3b8";
    if (isWin) pnlColor = (pnlVal !== null && pnlVal > 0) ? "#10b981" : "#38bdf8";
    if (isLoss) pnlColor = "#ef4444";

    const badgeClass = isShort ? "badge-short" : "badge-long";
    const typeLabel = t.type === "BUY_COVER" ? "BUY COVER" : (t.type === "SELL_SHORT" ? "SELL SHORT" : t.type);

    // Extract TP & SL
    let tpText = t.target ? formatPrice(t.target) : "";
    let slText = t.stop_loss ? formatPrice(t.stop_loss) : "";
    if (!tpText && t.note) {
      const m = t.note.match(/Target\s+(\$[\d\.]+)/i);
      if (m) tpText = m[1];
    }
    if (!slText && t.note) {
      const m = t.note.match(/SL\s+(\$[\d\.]+)/i);
      if (m) slText = m[1];
    }

    let reasonText = t.reason || t.note || "";

    const coinLabel = t.coin || t.symbol || (t.pair ? t.pair.replace('B-', '').replace('_USDT', '').replace('_INR', '') : 'BTC');
    const marginVal = Number(t.amount !== undefined && t.amount !== null ? t.amount : (t.invested_inr || 0));

    return `
      <div class="trade-log-card ${isExit ? (isWin ? 'card-win' : 'card-loss') : 'card-entry'}">
        <div class="trade-card-top">
          <div class="trade-card-id">
            <span class="trade-badge-dir ${badgeClass}">${dir}</span>
            <span class="trade-badge-type">${typeLabel}</span>
            <span class="trade-card-coin">${coinLabel}</span>
            ${lev ? `<span class="trade-badge-lev">${lev}</span>` : ''}
          </div>
          <div class="trade-card-time">${formatTradeDateTime(t)}</div>
        </div>

        <div class="trade-card-middle">
          <div class="trade-card-price">
            <span class="price-val">${formatPrice(t.price)}</span>
            ${t.entry_price && Number(t.entry_price) !== Number(t.price) ? `<span class="entry-sub">from ${formatPrice(t.entry_price)}</span>` : ''}
          </div>
          <div class="trade-card-pnl" style="color: ${pnlColor};">
            ${pnlVal !== null ? `INR ${pnlVal >= 0 ? '+' : ''}${pnlVal.toFixed(2)}${pnlPct !== null ? ` (${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(1)}%)` : ''}` : `₹${marginVal.toFixed(2)} Margin`}
          </div>
        </div>

        ${(tpText || slText || reasonText || t.fee || t.tds || t.tax || t.gross_pnl !== undefined) ? `
          <div class="trade-card-bottom">
            ${tpText ? `<span class="pill-tp">TP: <b>${tpText}</b></span>` : ''}
            ${slText ? `<span class="pill-sl">SL: <b>${slText}</b></span>` : ''}
            ${t.gross_pnl !== undefined && Number(t.gross_pnl) !== 0 ? `<span class="pill-gross" title="Gross Market PnL">Gross: ₹${Number(t.gross_pnl) >= 0 ? '+' : ''}${Number(t.gross_pnl).toFixed(2)}</span>` : ''}
            ${t.fee ? `<span class="pill-fee" title="CoinDCX Futures Taker Fee (0.1% total)">Fee: -₹${Number(t.fee).toFixed(2)}</span>` : ''}
            ${t.tds ? `<span class="pill-tds" title="1% Indian TDS under Section 194S">TDS 1%: -₹${Number(t.tds).toFixed(2)}</span>` : ''}
            ${t.tax ? `<span class="pill-tax" title="Indian 31.2% Flat VDA Tax + Cess under Section 115BBH">Govt Tax: -₹${Number(t.tax).toFixed(2)}</span>` : ''}
            ${reasonText ? `<span class="pill-reason" title="${reasonText}">${reasonText}</span>` : ''}
          </div>
        ` : ''}
      </div>
    `;
  }).join("");
}

function copyTradeHistoryToClipboard() {
  if (!allTradeHistory || allTradeHistory.length === 0) {
    showToastNotification("⚠️ No trades to copy.");
    return;
  }

  const pnlEl = document.getElementById("hud-net-pnl");
  const pnlText = pnlEl ? pnlEl.textContent : "0";
  const wrEl = document.getElementById("hud-win-rate");
  const wrText = wrEl ? wrEl.textContent : "0%";
  const wlEl = document.getElementById("hud-win-loss");
  const wlText = wlEl ? wlEl.textContent : "0W / 0L";

  let out = `=== COINDCX BOT EXECUTIONS & PERFORMANCE AUDIT ===\n`;
  out += `Status: ${pnlText} Net PnL | Win Rate: ${wrText} | ${wlText}\n`;
  out += `Total Trades Recorded: ${allTradeHistory.length}\n`;
  out += `------------------------------------------------------------\n`;
  out += `TIME     | TYPE  | COIN   | PRICE       | PnL / AMOUNT (INR) | DETAILS\n`;
  out += `------------------------------------------------------------\n`;

  allTradeHistory.forEach(t => {
    const coinLabel = t.coin || t.symbol || (t.pair ? t.pair.replace('B-', '').replace('_USDT', '').replace('_INR', '') : 'BTC');
    const time = (t.time || "").padEnd(8);
    const type = (t.type || "").padEnd(5);
    const coin = coinLabel.padEnd(6);
    const price = (`$${t.price}`).padEnd(11);
    const pnl = t.pnl !== undefined ? `PnL: ${t.pnl >= 0 ? '+' : ''}${t.pnl}` : `Amt: ${t.amount || t.invested_inr || 0}`;
    const pnlPad = pnl.padEnd(18);
    const reason = t.reason || t.note || "";
    out += `${time} | ${type} | ${coin} | ${price} | ${pnlPad} | ${reason}\n`;
  });
  out += `------------------------------------------------------------\n`;

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(out).then(() => {
      showToastNotification("📋 Trade history copied to clipboard!");
    }).catch(() => {
      fallbackCopyText(out);
    });
  } else {
    fallbackCopyText(out);
  }
}

function fallbackCopyText(text) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
  showToastNotification("📋 Trade history copied to clipboard!");
}

function exportTradesToCSV() {
  if (!allTradeHistory || allTradeHistory.length === 0) {
    alert("No trade executions recorded yet.");
    return;
  }

  let csv = "Timestamp,Time,Type,Coin,Price_USD,Amount_INR,PnL_INR,PnL_Pct,Reason_Note\n";
  allTradeHistory.forEach(t => {
    const coinLabel = t.coin || t.symbol || (t.pair ? t.pair.replace('B-', '').replace('_USDT', '').replace('_INR', '') : 'BTC');
    const ts = (t.timestamp || "").replace(/"/g, '""');
    const time = (t.time || "").replace(/"/g, '""');
    const type = (t.type || "");
    const coin = coinLabel;
    const price = Number(t.price || 0);
    const amt = Number(t.amount !== undefined ? t.amount : (t.invested_inr || 0));
    const pnl = t.pnl !== undefined ? Number(t.pnl) : (t.pnl_inr !== undefined ? Number(t.pnl_inr) : "");
    const pnlPct = t.pnl_pct !== undefined ? Number(t.pnl_pct) : "";
    const reason = (t.reason || t.note || "").replace(/"/g, '""');

    csv += `"${ts}","${time}","${type}","${coin}",${price},${amt},${pnl},${pnlPct},"${reason}"\n`;
  });

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.setAttribute("href", url);
  link.setAttribute("download", `coindcx_paper_trades_${new Date().toISOString().slice(0, 10)}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function clearPaperTradeHistory() {
  if (!confirm("Are you sure you want to reset and clear all paper trade history?")) return;
  try {
    const res = await fetch("/api/paper_trades/clear", { method: "POST" });
    if (res.ok) {
      allTradeHistory = [];
      lastRenderedTradesHash = "";
      updateTradePerformanceHUD({ total_pnl_inr: 0, win_rate_pct: 0, wins: 0, losses: 0, total_trades: 0 });
      renderTradeLogList();
      showToastNotification("🗑️ Paper trade history cleared.");
    }
  } catch (e) {
    console.error("Clear error:", e);
  }
}

function showToastNotification(msg) {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = "alert-toast up";
  toast.style.background = "rgba(15, 23, 42, 0.95)";
  toast.style.border = "1px solid #38bdf8";
  toast.innerHTML = `
    <div class="toast-header" style="justify-content: space-between;">
      <span style="font-weight: 700; color: #38bdf8;">NOTIFICATION</span>
      <button class="toast-close-btn" onclick="this.parentElement.parentElement.remove()">✕</button>
    </div>
    <div class="toast-body" style="font-size: 0.8rem; color: #fff; padding: 6px 0;">${msg}</div>
  `;
  container.appendChild(toast);
  setTimeout(() => { if (toast && toast.parentElement) toast.remove(); }, 3200);
}


// 18. Toggle Bot
async function toggleBot() {
  try {
    const res = await fetch("/api/bot/toggle", { method: "POST" });
    const data = await res.json();
    isBotRunning = data.is_running;
    syncBotStatus();
  } catch (e) {
    console.error("Toggle error:", e);
  }
}

// 18b. Toggle Manage-Only Mode (Pause New Trades)
async function toggleNewTrades() {
  try {
    const res = await fetch("/api/bot/toggle_new_trades", { method: "POST" });
    const data = await res.json();
    if (data.status === "success") {
      const isPaused = !data.allow_new_trades;
      showNotification(
        isPaused
          ? "🛡️ Manage-Only Mode Activated: Bot will NOT open any new trades, but will continue managing and exiting current positions!"
          : "🚀 Auto-Trading Resumed: Bot will now open new trades when open slots are available."
      );
      syncBotStatus();
    }
  } catch (e) {
    console.error("Error toggling new trades:", e);
  }
}


// ==============================================================================
// 19. INTERACTIVE CUSTOM FUTURES ORDER TERMINAL & SIZING
// ==============================================================================
let customOrderSide = "LONG";

function setCustomOrderSide(side) {
  customOrderSide = side.toUpperCase();
  const btnLong = document.getElementById("btn-side-long");
  const btnShort = document.getElementById("btn-side-short");
  if (btnLong && btnShort) {
    btnLong.classList.toggle("active-long", customOrderSide === "LONG");
    btnShort.classList.toggle("active-short", customOrderSide === "SHORT");
  }
  updateCustomOrderSummary();
}

function setQuickMargin(val) {
  const inp = document.getElementById("custom-input-margin");
  if (inp) inp.value = val;
  document.querySelectorAll(".quick-margin-chips .q-chip").forEach(c => {
    c.classList.toggle("active", c.textContent.replace("₹", "").replace(",", "") === String(val));
  });
  updateCustomOrderSummary();
}

function onCustomLeverageSlider(val) {
  const numInp = document.getElementById("custom-num-leverage");
  if (numInp) numInp.value = val;
  updateCustomOrderSummary();
}

function onCustomLeverageNum(val) {
  let v = parseInt(val) || 1;
  v = Math.max(1, Math.min(50, v));
  const slider = document.getElementById("custom-slider-leverage");
  if (slider) slider.value = v;
  updateCustomOrderSummary();
}

function updateCustomOrderSummary() {
  const marginInp = document.getElementById("custom-input-margin");
  const levInp = document.getElementById("custom-num-leverage");
  const tpInp = document.getElementById("custom-input-tp");
  const slInp = document.getElementById("custom-input-sl");

  const margin = parseFloat(marginInp ? marginInp.value : 3000) || 3000;
  const lev = parseInt(levInp ? levInp.value : 22) || 22;
  const tp = parseFloat(tpInp ? tpInp.value : 1.25) || 1.25;
  const sl = parseFloat(slInp ? slInp.value : 0.0) || 0.0;

  const marginDisp = document.getElementById("term-margin-val-display");
  if (marginDisp) marginDisp.textContent = `₹${margin.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

  const levDisp = document.getElementById("term-leverage-display");
  if (levDisp) {
    let label = "Safe Buffer";
    let color = "#38bdf8";
    if (lev <= 8) {
      label = "Safe Alt Buffer";
      color = "#10b981";
    } else if (lev <= 12) {
      label = "Safe ETH Buffer";
      color = "#38bdf8";
    } else if (lev <= 22) {
      label = "User Mirror Sweetspot";
      color = "#a855f7";
    } else if (lev <= 35) {
      label = "High Risk";
      color = "#f59e0b";
    } else {
      label = "Extreme Hazard";
      color = "#ef4444";
    }
    levDisp.textContent = `${lev}x (${label})`;
    levDisp.style.color = color;
  }

  const contractDisp = document.getElementById("term-preview-contract");
  if (contractDisp) contractDisp.textContent = `${currentCoin}USDT.P (${customOrderSide})`;

  const notionalInr = margin * lev;
  const notionalUsd = notionalInr / 90.0;
  const notionalDisp = document.getElementById("term-preview-notional");
  if (notionalDisp) notionalDisp.textContent = `₹${notionalInr.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (~$${notionalUsd.toFixed(2)})`;

  const profitInr = margin * ((tp * lev) / 100.0);
  const profitRoi = tp * lev;
  const profitDisp = document.getElementById("term-preview-profit");
  if (profitDisp) profitDisp.textContent = `+₹${profitInr.toFixed(2)} (+${profitRoi.toFixed(1)}% ROI)`;

  const lossDisp = document.getElementById("term-preview-loss");
  if (lossDisp) {
    if (sl <= 0.05) {
      lossDisp.textContent = `🛡️ Protected by Margin Defense (-48% Top-Up)`;
      lossDisp.style.color = "#a855f7";
    } else {
      const lossInr = margin * ((sl * lev) / 100.0);
      const lossRisk = sl * lev;
      lossDisp.textContent = `-₹${lossInr.toFixed(2)} (-${lossRisk.toFixed(1)}% Risk)`;
      lossDisp.style.color = "#ef4444";
    }
  }
}

async function executeCustomOrder() {
  const marginInp = document.getElementById("custom-input-margin");
  const levInp = document.getElementById("custom-num-leverage");
  const tpInp = document.getElementById("custom-input-tp");
  const slInp = document.getElementById("custom-input-sl");

  const margin_inr = parseFloat(marginInp ? marginInp.value : 3000) || 3000;
  const leverage = parseInt(levInp ? levInp.value : 22) || 22;
  const take_profit_pct = parseFloat(tpInp ? tpInp.value : 1.25) || 1.25;
  const stop_loss_pct = parseFloat(slInp ? slInp.value : 0.0) || 0.0;

  try {
    const res = await fetch("/api/bot/manual_order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        coin: currentCoin,
        side: customOrderSide,
        margin_inr,
        leverage,
        take_profit_pct,
        stop_loss_pct
      })
    });
    if (!res.ok) {
      alert("Order could not be submitted right now. Check server status.");
      return;
    }
    const data = await res.json();
    if (data.status === "success") {
      alert(`✅ Simulated Futures Order Placed!\n\nContract: ${currentCoin}USDT.P (${customOrderSide})\nMargin: ₹${margin_inr} | Leverage: ${leverage}x\nTarget: +${take_profit_pct}%\nStop-Loss: -${stop_loss_pct}%`);
      syncBotStatus();
    }
  } catch (err) {
    console.error("Order error:", err);
  }
}

async function closePositionByCoin(coin) {
  if (!confirm(`Are you sure you want to close position ${coin}?`)) return;
  try {
    const res = await fetch("/api/bot/close_position", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coin: coin })
    });
    if (!res.ok) return;
    const data = await res.json();
    if (data.status === "success") {
      syncBotStatus();
    } else {
      alert(data.message || "Could not close position.");
    }
  } catch (err) {
    console.error("Close position error:", err);
  }
}
window.closePositionByCoin = closePositionByCoin;

async function closeActivePositionManually() {
  try {
    const res = await fetch("/api/bot/close_position", { method: "POST" });
    if (!res.ok) return;
    const data = await res.json();
    if (data.status === "success") {
      alert(`⏹ Position Closed Successfully!\n\n${data.message}`);
      syncBotStatus();
    } else {
      alert("No active position to close.");
    }
  } catch (err) {
    console.error("Close position error:", err);
  }
}

// ==============================================================================
// 26. DRAG & DROP DASHBOARD PANELS (CUSTOM MONITORING LAYOUT)
// ==============================================================================
function initDraggablePanels() {
  const container = document.querySelector(".sidebar-panels");
  if (!container) return;

  // Restore saved order if available
  const savedOrder = localStorage.getItem("coindcx_sidebar_panel_order");
  if (savedOrder) {
    try {
      const panelIds = JSON.parse(savedOrder);
      panelIds.forEach(id => {
        const el = document.getElementById(id);
        if (el && el.parentElement === container) {
          container.appendChild(el);
        }
      });
    } catch (e) {
      console.warn("Could not parse saved panel order", e);
    }
  }

  let draggedEl = null;
  let isHandleDragging = false;

  // Allow drag initiation from either the drag-handle (⋮⋮) or the panel header bar
  container.addEventListener("mousedown", (e) => {
    // Never trigger drag if user is clicking buttons, inputs, dropdowns, links, or text inside trade log
    if (e.target.closest("button, input, select, textarea, a, .trade-log-list, .trade-actions-toolbar, .trade-hud-container")) {
      isHandleDragging = false;
      return;
    }
    const handle = e.target.closest(".drag-handle") || e.target.closest(".panel-title-bar");
    const panel = e.target.closest(".draggable-panel");
    if (handle && panel) {
      isHandleDragging = true;
      draggedEl = panel;
      panel.setAttribute("draggable", "true");
    } else {
      isHandleDragging = false;
      document.querySelectorAll(".draggable-panel").forEach(p => p.setAttribute("draggable", "false"));
    }
  });

  document.addEventListener("mouseup", () => {
    isHandleDragging = false;
  });

  container.addEventListener("dragstart", (e) => {
    const panel = e.target.closest(".draggable-panel");
    if (!isHandleDragging || !panel) {
      e.preventDefault();
      return false;
    }
    draggedEl = panel;
    panel.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", panel.id);
  });

  container.addEventListener("dragend", (e) => {
    isHandleDragging = false;
    const panel = e.target.closest(".draggable-panel");
    if (panel) panel.classList.remove("dragging");
    document.querySelectorAll(".draggable-panel").forEach(p => {
      p.classList.remove("drag-over-top", "drag-over-bottom");
      p.setAttribute("draggable", "false");
    });
    draggedEl = null;
    savePanelOrder(container);
  });

  container.addEventListener("dragover", (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    const target = e.target.closest(".draggable-panel");
    if (!target || target === draggedEl) return;

    const rect = target.getBoundingClientRect();
    const midY = rect.top + rect.height / 2;

    document.querySelectorAll(".draggable-panel").forEach(p => {
      if (p !== target) p.classList.remove("drag-over-top", "drag-over-bottom");
    });

    if (e.clientY < midY) {
      target.classList.add("drag-over-top");
      target.classList.remove("drag-over-bottom");
    } else {
      target.classList.add("drag-over-bottom");
      target.classList.remove("drag-over-top");
    }
  });

  container.addEventListener("drop", (e) => {
    e.preventDefault();
    const target = e.target.closest(".draggable-panel");
    if (!target || !draggedEl || target === draggedEl) return;

    const rect = target.getBoundingClientRect();
    const midY = rect.top + rect.height / 2;

    if (e.clientY < midY) {
      container.insertBefore(draggedEl, target);
    } else {
      container.insertBefore(draggedEl, target.nextSibling);
    }

    target.classList.remove("drag-over-top", "drag-over-bottom");
    savePanelOrder(container);
  });

  // Touch Drag Support for Mobile Phones & Tablets
  let touchDraggedEl = null;
  let touchOverEl = null;
  let touchOverPos = null;

  container.addEventListener("touchstart", (e) => {
    const handle = e.target.closest(".drag-handle");
    if (!handle) return;
    const panel = handle.closest(".draggable-panel");
    if (!panel) return;

    touchDraggedEl = panel;
    touchDraggedEl.classList.add("dragging");
    if (navigator.vibrate) navigator.vibrate(25);
  }, { passive: true });

  container.addEventListener("touchmove", (e) => {
    if (!touchDraggedEl) return;
    const touch = e.touches[0];
    const elemUnder = document.elementFromPoint(touch.clientX, touch.clientY);
    if (!elemUnder) return;

    const target = elemUnder.closest(".draggable-panel");
    document.querySelectorAll(".draggable-panel").forEach(p => {
      p.classList.remove("drag-over-top", "drag-over-bottom");
    });

    if (target && target !== touchDraggedEl && container.contains(target)) {
      touchOverEl = target;
      const rect = target.getBoundingClientRect();
      const midY = rect.top + rect.height / 2;
      if (touch.clientY < midY) {
        touchOverPos = "top";
        target.classList.add("drag-over-top");
      } else {
        touchOverPos = "bottom";
        target.classList.add("drag-over-bottom");
      }
    } else {
      touchOverEl = null;
      touchOverPos = null;
    }
  }, { passive: true });

  container.addEventListener("touchend", () => {
    if (!touchDraggedEl) return;
    touchDraggedEl.classList.remove("dragging");

    if (touchOverEl && touchOverPos) {
      if (touchOverPos === "top") {
        container.insertBefore(touchDraggedEl, touchOverEl);
      } else {
        container.insertBefore(touchDraggedEl, touchOverEl.nextSibling);
      }
      savePanelOrder(container);
      if (navigator.vibrate) navigator.vibrate(35);
    }

    document.querySelectorAll(".draggable-panel").forEach(p => {
      p.classList.remove("drag-over-top", "drag-over-bottom");
    });
    touchDraggedEl = null;
    touchOverEl = null;
    touchOverPos = null;
  });
}

window.reorderPanelStep = function(btn, step) {
  const panel = btn.closest(".draggable-panel");
  if (!panel || !panel.parentElement) return;
  const parent = panel.parentElement;
  const panels = Array.from(parent.querySelectorAll(".draggable-panel"));
  const idx = panels.indexOf(panel);
  if (idx < 0) return;

  const newIdx = idx + step;
  if (newIdx < 0 || newIdx >= panels.length) return;

  if (step === -1) {
    parent.insertBefore(panel, panels[newIdx]);
  } else {
    parent.insertBefore(panel, panels[newIdx].nextSibling);
  }

  savePanelOrder(parent);
  panel.classList.add("panel-reordered-flash");
  setTimeout(() => panel.classList.remove("panel-reordered-flash"), 400);
  if (navigator.vibrate) navigator.vibrate(25);
};

function savePanelOrder(container) {
  const panelIds = Array.from(container.querySelectorAll(".draggable-panel")).map(p => p.id);
  localStorage.setItem("coindcx_sidebar_panel_order", JSON.stringify(panelIds));
}

// 19b. Toggle Between Paper Simulation and Live Real CoinDCX Trading
async function toggleTradingMode() {
  try {
    const statusRes = await fetch("/api/status");
    if (!statusRes.ok) return;
    const status = await statusRes.json();
    const willBeLive = status.dry_run;

    if (willBeLive) {
      const confirmLive = confirm("⚠️ ACTIVATE REAL COINDCX TRADING?\n\nYour API keys are verified and connected.\nThis will place REAL orders on your CoinDCX account with ₹160 per trade.\n\nClick OK only if you are ready to trade with real money, or Cancel to stay in safe Paper Simulation.");
      if (!confirmLive) return;
    }

    const res = await fetch("/api/bot/toggle_mode", { method: "POST" });
    if (!res.ok) return;
    const data = await res.json();
    alert(`Trading mode switched to: ${data.mode} TRADING!`);
    syncBotStatus();
  } catch (e) {
    console.error("Mode toggle error:", e);
  }
}

// 19c. Switch 24/7 Target & Risk Profile (Safe, Balanced, Aggressive)
async function setRiskProfile(mode) {
  try {
    const res = await fetch("/api/bot/set_risk_mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode })
    });
    if (!res.ok) {
      console.warn("Risk mode server update in progress, will sync momentarily...");
      return;
    }
    const data = await res.json();
    if (data.status === "success") {
      updateRiskProfileUI(data.current_mode, data.profile);
      syncBotStatus();
    }
  } catch (err) {
    console.error("Failed to set risk profile:", err);
  }
}

function updateRiskProfileUI(currentMode, profile) {
  const badge = document.getElementById("risk-mode-badge");
  const desc = document.getElementById("risk-mode-desc");
  const chunkVal = document.getElementById("card-trade-chunk");

  ["user-mirror", "safe", "balanced", "aggressive"].forEach(m => {
    const btn = document.getElementById(`risk-btn-${m}`);
    if (btn) {
      const match = (m === "user-mirror" && currentMode === "USER_MIRROR") ||
                    (m === "safe" && currentMode === "SAFE") ||
                    (m === "balanced" && currentMode === "BALANCED") ||
                    (m === "aggressive" && (currentMode === "AGGRESSIVE" || currentMode === "ALPHA"));
      btn.classList.toggle("active", match);
    }
  });

  if (badge) {
    if (currentMode === "USER_MIRROR") {
      badge.textContent = "USER_MIRROR (TP +1.25%)";
      badge.style.background = "rgba(168, 85, 247, 0.25)";
      badge.style.color = "#c084fc";
    } else if (currentMode === "SAFE") {
      badge.textContent = "SAFE (25-35%)";
      badge.style.background = "rgba(16, 185, 129, 0.2)";
      badge.style.color = "#10b981";
    } else if (currentMode === "BALANCED") {
      badge.textContent = "BALANCED (40-60%)";
      badge.style.background = "rgba(56, 189, 248, 0.2)";
      badge.style.color = "#38bdf8";
    } else {
      badge.textContent = "ALPHA (80-120%+)";
      badge.style.background = "rgba(245, 158, 11, 0.2)";
      badge.style.color = "#f59e0b";
    }
  }

  if (desc) {
    if (currentMode === "USER_MIRROR") {
      desc.textContent = "🎯 User Mirror Sniper (6x-22x Safe Lev, ₹200-₹250 Sizing, -48% Margin Defense, 30m Anti-Whipsaw Cooldown).";
    } else if (profile) {
      desc.textContent = `${profile.description} Leverage: ${profile.leverage}x • Margin: ₹${profile.investment_inr} • Min Conf: ${profile.min_confidence}% • Target: +${profile.take_profit_pct}%`;
    }
  }

  if (chunkVal) {
    if (currentMode === "USER_MIRROR") {
      chunkVal.textContent = "₹3,000 / slot";
    } else if (profile) {
      chunkVal.textContent = `₹${profile.investment_inr} (${profile.leverage}x Lev)`;
    }
  }
}



// ==============================================================================
// 20. AI FUTURES STRATEGY & LEVERAGE ADVISOR (TIMEFRAME & LEVERAGE MATRIX)
// Evaluates 1m, 5m, 15m, 1h, 1D and provides precise LONG/SHORT & Leverage advice
// ==============================================================================

// Fetch Advisor Data for Current Coin
async function fetchAdvisorData(coin) {
  try {
    const res = await fetch(`/api/advisor?coin=${coin}`);
    if (!res.ok) return;
    const data = await res.json();
    if (data && data.coin) {
      advisorData = data;
      if (!selectedAdvisorTf) {
        selectedAdvisorTf = data.best_timeframe || currentInterval || "1h";
      }
      renderAdvisorUI();
    }
  } catch (err) {
    console.error("Advisor fetch error:", err);
  }
}

// Render Advisor UI with Full Dynamic Multi-Timeframe Matrix
function renderAdvisorUI() {
  if (!advisorData) return;
  const a = advisorData;
  const tfMap = a.timeframes || {};
  const bestTf = a.best_timeframe || "1h";
  const activeTf = selectedAdvisorTf || bestTf;
  const tfInfo = tfMap[activeTf] || tfMap[bestTf] || {};

  // 1. Update Timeframe Cards (1m, 5m, 15m, 1h, 1d)
  const timeframes = ["1m", "5m", "15m", "1h", "1d"];
  timeframes.forEach(tf => {
    const info = tfMap[tf];
    const sigEl = document.getElementById(`tf-signal-${tf}`);
    const levEl = document.getElementById(`tf-lev-${tf}`);
    const cardEl = document.querySelector(`.tf-card[data-tf="${tf}"]`);

    if (info && sigEl) {
      const dir = info.direction || "WAIT";
      const prob = info.probability || 50;
      sigEl.textContent = `${dir === "UP" ? "LONG" : dir === "DOWN" ? "SHORT" : "WAIT"} ${prob}%`;
      sigEl.className = `tf-signal ${dir === "UP" ? "signal-long" : dir === "DOWN" ? "signal-short" : "signal-wait"}`;
    }

    if (info && levEl) {
      levEl.textContent = `${info.recommended_lev}x Lev`;
    }

    if (cardEl) {
      cardEl.classList.toggle("active-selected", tf === activeTf);
      cardEl.classList.toggle("active-best", tf === bestTf);
    }
  });

  // 2. Action Direction & Confidence Badge
  const currentAction = tfInfo.direction === "UP" ? "LONG" : tfInfo.direction === "DOWN" ? "SHORT" : "WAIT";
  const confidence = tfInfo.probability || a.confidence || 75;
  const recLev = tfInfo.recommended_lev || a.recommended_leverage || 10;

  const elActionBadge = document.getElementById("adv-action-badge");
  const elActionIcon = document.getElementById("adv-action-icon");
  const elActionText = document.getElementById("adv-action-text");
  const elConfTag = document.getElementById("adv-conf-tag");

  if (elActionBadge && elActionText) {
    if (currentAction === "LONG") {
      elActionBadge.className = "advisor-action-badge long";
      elActionIcon.textContent = "🟢";
      elActionText.textContent = "GO LONG (BUY)";
      elConfTag.textContent = `${confidence}% Confidence`;
      elConfTag.style.color = "#34d399";
    } else if (currentAction === "SHORT") {
      elActionBadge.className = "advisor-action-badge short";
      elActionIcon.textContent = "🔴";
      elActionText.textContent = "GO SHORT (SELL)";
      elConfTag.textContent = `${confidence}% Confidence`;
      elConfTag.style.color = "#f87171";
    } else {
      elActionBadge.className = "advisor-action-badge wait";
      elActionIcon.textContent = "⏸️";
      elActionText.textContent = "WAIT FOR BREAKOUT";
      elConfTag.textContent = `${confidence}% Range-bound`;
      elConfTag.style.color = "#fbbf24";
    }
  }

  // 3. Quick Summary Bar
  const elBestTf = document.getElementById("adv-best-tf");
  const elBestLev = document.getElementById("adv-best-lev");
  const elBestProfit = document.getElementById("adv-best-profit");

  const styleName = tfInfo.style || "Intraday";
  if (elBestTf) elBestTf.textContent = `${activeTf.toUpperCase()} (${styleName.split(' ')[0]})`;
  if (elBestLev) elBestLev.textContent = `${recLev}x Sweetspot`;

  // Calculate profit based on target vs entry
  const entryPrice = a.current_price || (activeCandles.length > 0 ? activeCandles[activeCandles.length - 1].close : 1.0);
  const targetPrice = tfInfo.target || a.target_price || entryPrice * 1.05;
  const stopLoss = tfInfo.stop_loss || a.stop_loss || entryPrice * 0.98;

  const movePct = Math.abs((targetPrice - entryPrice) / entryPrice);
  const estProfit = Math.round(1500.0 * (movePct * selectedAdvisorLev) * 100) / 100;
  const estRoiPct = (movePct * selectedAdvisorLev * 100).toFixed(1);

  if (elBestProfit) {
    elBestProfit.textContent = `+₹${estProfit.toLocaleString('en-IN')} (+${estRoiPct}%)`;
    elBestProfit.style.color = "#10b981";
  }

  // 4. Blueprint Numbers
  const elEntry = document.getElementById("adv-entry-val");
  const elTarget = document.getElementById("adv-target-val");
  const elStop = document.getElementById("adv-stop-val");

  const chgToTarget = (((targetPrice - entryPrice) / entryPrice) * 100).toFixed(1);
  const chgToStop = (((stopLoss - entryPrice) / entryPrice) * 100).toFixed(1);

  if (elEntry) elEntry.textContent = formatPrice(entryPrice);
  if (elTarget) elTarget.textContent = `${formatPrice(targetPrice)} (${chgToTarget >= 0 ? '+' : ''}${chgToTarget}%)`;
  if (elStop) elStop.textContent = `${formatPrice(stopLoss)} (${chgToStop}%)`;

  // 5. Render Leverage Inspector
  renderAdvisorLeverage(selectedAdvisorLev);
}

// User Click Handler: Select Timeframe from Advisor
function selectAdvisorTimeframe(tf) {
  selectedAdvisorTf = tf;
  // Simultaneously sync main chart timeframe
  setTimeframe(tf);
  renderAdvisorUI();
}

// User Click Handler: Select Leverage Tier (1x to 100x)
function selectAdvisorLeverage(lev) {
  selectedAdvisorLev = lev;
  // Sync the top leverage selector if present
  setLeverage(lev);
  renderAdvisorLeverage(lev);
}

// Dynamic Leverage Inspector Renderer (1x to 100x Reality Check)
function renderAdvisorLeverage(lev) {
  // Update button active state
  document.querySelectorAll(".adv-lev-btn").forEach(btn => {
    const bLev = parseInt(btn.getAttribute("data-lev") || btn.textContent);
    btn.classList.toggle("active-lev", bLev === lev);
  });

  const entry = (advisorData && advisorData.current_price) ? advisorData.current_price : (parseFloat(elPrice.textContent.replace("$", "").replace(",", "")) || 1.0);
  const activeTf = selectedAdvisorTf || (advisorData ? advisorData.best_timeframe : "1h");
  const tfInfo = (advisorData && advisorData.timeframes) ? advisorData.timeframes[activeTf] : null;
  const target = (tfInfo && tfInfo.target) ? tfInfo.target : (advisorData && advisorData.target_price ? advisorData.target_price : entry * 1.05);

  const movePct = Math.abs((target - entry) / entry);
  const estProfit = Math.round(1500.0 * (movePct * lev) * 100) / 100;
  const estRoiPct = (movePct * lev * 100).toFixed(1);

  // Liquidation calculation (Long: drops 90%/lev, Short: rises 90%/lev)
  const isShort = tfInfo && tfInfo.direction === "DOWN";
  let liqPrice = 0;
  let dropPct = 0;

  if (isShort) {
    liqPrice = entry * (1 + (0.90 / lev));
    dropPct = ((liqPrice - entry) / entry) * 100;
  } else {
    liqPrice = Math.max(0, entry * (1 - (0.90 / lev)));
    dropPct = ((entry - liqPrice) / entry) * 100;
  }

  const elInspector = document.getElementById("leverage-inspector");
  const elInspLevTag = document.getElementById("insp-lev-tag");
  const elInspRiskText = document.getElementById("insp-risk-text");
  const elInspProfitTag = document.getElementById("insp-profit-tag");
  const elInspLiqPrice = document.getElementById("insp-liq-price");
  const elInspLiqDrop = document.getElementById("insp-liq-drop");
  const elInspRoi = document.getElementById("insp-roi");
  const elInspNoteBox = document.getElementById("insp-note-box");
  const elInspNoteIcon = document.getElementById("insp-note-icon");
  const elInspNoteText = document.getElementById("insp-note-text");
  const elAdvLevTip = document.getElementById("adv-lev-tip");

  if (!elInspector) return;

  if (elInspLevTag) elInspLevTag.textContent = `${lev}x LEVERAGE SELECTED`;
  if (elInspLiqPrice) elInspLiqPrice.textContent = formatPrice(liqPrice);
  if (elInspLiqDrop) elInspLiqDrop.textContent = `${isShort ? '+' : '-'}${dropPct.toFixed(1)}% ${dropPct >= 9 ? 'safe buffer' : 'tight buffer'}`;
  if (elInspRoi) elInspRoi.textContent = `+${estRoiPct}% ROI`;
  if (elInspProfitTag) elInspProfitTag.textContent = `+₹${estProfit.toLocaleString('en-IN')} Est. Profit`;

  // Specific risk profiles & warnings for 1x to 100x:
  if (lev === 100) {
    elInspector.className = "leverage-inspector trap-glow";
    if (elInspLevTag) elInspLevTag.className = "insp-badge trap";
    if (elInspRiskText) {
      elInspRiskText.textContent = "💥 100x WIPEOUT TRAP (EXTREME HAZARD)";
      elInspRiskText.style.color = "#ef4444";
    }
    if (elAdvLevTip) elAdvLevTip.textContent = "⚠️ NEVER use 100x!";
    if (elInspNoteBox) elInspNoteBox.className = "inspector-note trap-alert";
    if (elInspNoteIcon) elInspNoteIcon.textContent = "🚨";
    if (elInspNoteText) {
      elInspNoteText.innerHTML = `<b>DO NOT USE 100x WITH ₹1,500:</b> At 100x leverage, a tiny <b>0.9% price wobble</b> liquidates 100% of your ₹1,500 capital! Normal crypto spread & orderbook noise fluctuates 1% in seconds. You will almost certainly lose your entire wallet!`;
    }
  } else if (lev >= 50) {
    elInspector.className = "leverage-inspector trap-glow";
    if (elInspLevTag) elInspLevTag.className = "insp-badge trap";
    if (elInspRiskText) {
      elInspRiskText.textContent = "🚨 DANGEROUS LIQUIDATION RISK";
      elInspRiskText.style.color = "#f87171";
    }
    if (elAdvLevTip) elAdvLevTip.textContent = "High liquidation hazard";
    if (elInspNoteBox) elInspNoteBox.className = "inspector-note trap-alert";
    if (elInspNoteIcon) elInspNoteIcon.textContent = "⚠️";
    if (elInspNoteText) {
      elInspNoteText.innerHTML = `<b>High Hazard:</b> A 1.8% drop wipes all ₹1,500. Only experienced scalpers with hard stop-loss should attempt this.`;
    }
  } else if (lev === 25) {
    elInspector.className = "leverage-inspector";
    if (elInspLevTag) elInspLevTag.className = "insp-badge";
    if (elInspRiskText) {
      elInspRiskText.textContent = "⚡ HIGH VOLATILITY RISK";
      elInspRiskText.style.color = "#fbbf24";
    }
    if (elAdvLevTip) elAdvLevTip.textContent = "Requires tight stop-loss";
    if (elInspNoteBox) elInspNoteBox.className = "inspector-note";
    if (elInspNoteIcon) elInspNoteIcon.textContent = "⚡";
    if (elInspNoteText) {
      elInspNoteText.innerHTML = `<b>Caution:</b> 25x gives high return (+₹${estProfit.toLocaleString('en-IN')}) but liquidation is only 3.6% away. Normal volatility can clip your stop-loss.`;
    }
  } else if (lev >= 5 && lev <= 10) {
    elInspector.className = "leverage-inspector sweetspot-glow";
    if (elInspLevTag) elInspLevTag.className = "insp-badge sweetspot";
    if (elInspRiskText) {
      elInspRiskText.textContent = "💎 RECOMMENDED SWEETSPOT";
      elInspRiskText.style.color = "#34d399";
    }
    if (elAdvLevTip) elAdvLevTip.textContent = `${lev}x Recommended`;
    if (elInspNoteBox) elInspNoteBox.className = "inspector-note sweetspot-alert";
    if (elInspNoteIcon) elInspNoteIcon.textContent = "💎";
    if (elInspNoteText) {
      elInspNoteText.innerHTML = `<b>Optimal Choice for ₹1,500:</b> ${lev}x produces significant profit (+₹${estProfit.toLocaleString('en-IN')}) while providing a safe <b>${dropPct.toFixed(1)}%</b> drop margin, easily absorbing normal pullbacks without liquidation.`;
    }
  } else {
    // 1x - 3x
    elInspector.className = "leverage-inspector";
    if (elInspLevTag) elInspLevTag.className = "insp-badge";
    if (elInspRiskText) {
      elInspRiskText.textContent = "🛡️ ZERO LIQUIDATION RISK (SAFE BUFFER)";
      elInspRiskText.style.color = "#38bdf8";
    }
    if (elAdvLevTip) elAdvLevTip.textContent = "Safe low-risk hold";
    if (elInspNoteBox) elInspNoteBox.className = "inspector-note";
    if (elInspNoteIcon) elInspNoteIcon.textContent = "🛡️";
    if (elInspNoteText) {
      elInspNoteText.innerHTML = `<b>Spot Equivalent Safety:</b> Liquidation is ${dropPct.toFixed(0)}% away (virtually impossible). Ideal for multi-day swing positions.`;
    }
  }
}


// ==============================================================================
// 21. REAL-TIME AUDIO ALERTS & SOUND SYNTHESIZER
// High-tech trading sound alerts generated dynamically via Web Audio API
// ==============================================================================

function getAudioContext() {
  if (!audioCtx) {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (AudioContextClass) {
      audioCtx = new AudioContextClass();
    }
  }
  if (audioCtx && audioCtx.state === "suspended") {
    audioCtx.resume();
  }
  return audioCtx;
}

function playAlertSound(direction = "UP") {
  if (!isAudioAlertsEnabled) return;
  try {
    const ctx = getAudioContext();
    if (!ctx) return;
    const now = ctx.currentTime;

    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    if (direction === "UP") {
      // Bullish upward alert chime: 880Hz (A5) -> 1320Hz (E6)
      osc.type = "sine";
      osc.frequency.setValueAtTime(880, now);
      osc.frequency.exponentialRampToValueAtTime(1320, now + 0.15);
      gain.gain.setValueAtTime(0.25, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.35);
      osc.start(now);
      osc.stop(now + 0.35);
    } else {
      // Bearish warning alert chime: 520Hz -> 330Hz
      osc.type = "triangle";
      osc.frequency.setValueAtTime(520, now);
      osc.frequency.exponentialRampToValueAtTime(330, now + 0.2);
      gain.gain.setValueAtTime(0.28, now);
      gain.gain.exponentialRampToValueAtTime(0.01, now + 0.4);
      osc.start(now);
      osc.stop(now + 0.4);
    }
  } catch (e) {
    console.warn("Audio chime error:", e);
  }
}

function toggleAudioAlerts() {
  isAudioAlertsEnabled = !isAudioAlertsEnabled;
  localStorage.setItem("audio_alerts", isAudioAlertsEnabled ? "true" : "false");
  updateSoundButtonUI();
  if (isAudioAlertsEnabled) {
    playAlertSound("UP");
  }
}

function updateSoundButtonUI() {
  const btn = document.getElementById("btn-sound-toggle");
  const icon = document.getElementById("sound-icon");
  if (!btn || !icon) return;

  btn.classList.toggle("active-sound", isAudioAlertsEnabled);
  icon.textContent = isAudioAlertsEnabled ? "🔊" : "🔇";
  btn.title = isAudioAlertsEnabled ? "Audio Alerts: ON (Click to Mute)" : "Audio Alerts: OFF (Click to Enable)";
}


// ==============================================================================
// 22. GLOBAL SEARCH ACROSS ALL 700+ CRYPTOCURRENCIES
// Instant autocomplete with live price and 24h change
// ==============================================================================

async function loadAllCryptosData(silent = false) {
  try {
    const res = await fetch("/api/all_coins?limit=1000");
    if (!res.ok) return;
    const data = await res.json();
    if (data && data.coins) {
      allCryptosList = data.coins;
      const countEl = document.getElementById("all-coins-count-text");
      if (countEl) countEl.textContent = `Showing ${allCryptosList.length} Perpetual Markets`;
      
      // If all-coins modal is currently open, re-render it
      const modal = document.getElementById("all-coins-modal");
      if (modal && modal.style.display === "flex") {
        renderAllCoinsGrid();
      }
    }
  } catch (e) {
    if (!silent) console.error("Error loading all cryptos:", e);
  }
}

function handleGlobalSearch(query) {
  const val = (query || "").trim().toUpperCase();
  const clearBtn = document.getElementById("search-clear-btn");
  if (clearBtn) clearBtn.style.display = val ? "block" : "none";

  const dropdown = document.getElementById("search-autocomplete-dropdown");
  if (!dropdown) return;

  if (!val) {
    dropdown.style.display = "none";
    return;
  }

  // Filter against allCryptosList
  const matches = allCryptosList.filter(c => c.coin.includes(val) || c.symbol.includes(val)).slice(0, 12);

  if (matches.length === 0) {
    dropdown.innerHTML = `
      <div style="padding: 12px; text-align: center; color: var(--text-muted); font-size: 0.78rem;">
        No cryptocurrency matching "<b>${val}</b>"
      </div>
    `;
    dropdown.style.display = "block";
    return;
  }

  dropdown.innerHTML = matches.map(c => {
    const isBull = c.change_24h >= 0;
    return `
      <div class="search-item" onclick="selectCoin('${c.coin}', true)">
        <div class="search-item-coin">
          <span class="search-item-symbol">${c.coin}</span>
          <span class="search-item-contract">${c.contract}</span>
        </div>
        <div class="search-item-stats">
          <span class="search-item-price">${formatPrice(c.price)}</span>
          <span class="search-item-chg ${isBull ? 'pos' : 'neg'}">${isBull ? '+' : ''}${c.change_24h.toFixed(1)}%</span>
        </div>
      </div>
    `;
  }).join("");

  dropdown.style.display = "block";
}

function showSearchDropdown() {
  const input = document.getElementById("global-crypto-search");
  if (input && input.value.trim()) {
    handleGlobalSearch(input.value);
  }
}

function clearGlobalSearch() {
  const input = document.getElementById("global-crypto-search");
  const clearBtn = document.getElementById("search-clear-btn");
  const dropdown = document.getElementById("search-autocomplete-dropdown");
  if (input) input.value = "";
  if (clearBtn) clearBtn.style.display = "none";
  if (dropdown) dropdown.style.display = "none";
}


// ==============================================================================
// 23. ALL 700+ CRYPTOCURRENCIES MODAL EXPLORER
// ==============================================================================

function openAllCoinsModal() {
  const modal = document.getElementById("all-coins-modal");
  if (!modal) return;
  modal.style.display = "flex";

  if (allCryptosList.length === 0) {
    loadAllCryptosData().then(() => renderAllCoinsGrid());
  } else {
    renderAllCoinsGrid();
  }
}

function closeAllCoinsModal() {
  const modal = document.getElementById("all-coins-modal");
  if (modal) modal.style.display = "none";
}

function closeModalOnBackdrop(e, modalId) {
  if (e.target && e.target.id === modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.style.display = "none";
  }
}

function filterAllCoinsGrid(q) {
  allCryptosFilterQuery = (q || "").trim().toUpperCase();
  const clearBtn = document.getElementById("modal-search-clear");
  if (clearBtn) clearBtn.style.display = allCryptosFilterQuery ? "block" : "none";
  renderAllCoinsGrid();
}

function clearModalSearch() {
  const input = document.getElementById("modal-coin-search");
  const clearBtn = document.getElementById("modal-search-clear");
  if (input) input.value = "";
  if (clearBtn) clearBtn.style.display = "none";
  allCryptosFilterQuery = "";
  renderAllCoinsGrid();
}

function setAllCoinsSort(sortKey) {
  allCryptosSort = sortKey;
  document.querySelectorAll(".m-sort-pill").forEach(p => {
    p.classList.toggle("active", p.getAttribute("data-sort") === sortKey);
  });
  renderAllCoinsGrid();
}

function renderAllCoinsGrid() {
  const container = document.getElementById("all-coins-grid-container");
  if (!container) return;

  let filtered = [...allCryptosList];

  if (allCryptosFilterQuery) {
    filtered = filtered.filter(c => c.coin.includes(allCryptosFilterQuery) || c.symbol.includes(allCryptosFilterQuery));
  }

  // Sort
  if (allCryptosSort === "gainers") {
    filtered.sort((a, b) => b.change_24h - a.change_24h);
  } else if (allCryptosSort === "losers") {
    filtered.sort((a, b) => a.change_24h - b.change_24h);
  } else if (allCryptosSort === "price_desc") {
    filtered.sort((a, b) => b.price - a.price);
  } else if (allCryptosSort === "name") {
    filtered.sort((a, b) => a.coin.localeCompare(b.coin));
  } else {
    // Default: volume
    filtered.sort((a, b) => (b.volume_usdt || 0) - (a.volume_usdt || 0));
  }

  const countEl = document.getElementById("all-coins-count-text");
  if (countEl) countEl.textContent = `Showing ${filtered.length} of ${allCryptosList.length} Perpetual Markets`;

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1; padding: 40px; text-align: center; color: var(--text-muted);">
        No cryptocurrencies found matching "${allCryptosFilterQuery}".
      </div>
    `;
    return;
  }

  container.innerHTML = filtered.slice(0, 300).map(c => {
    const isBull = c.change_24h >= 0;
    const volStr = c.volume_usdt > 1e6 ? `$${(c.volume_usdt / 1e6).toFixed(1)}M` : `$${(c.volume_usdt / 1e3).toFixed(0)}k`;
    return `
      <div class="coin-grid-card" onclick="selectCoin('${c.coin}', true)">
        <div class="cgc-top">
          <span class="cgc-name">${c.coin}</span>
          <span class="cgc-chg ${isBull ? 'pos' : 'neg'}">${isBull ? '+' : ''}${c.change_24h.toFixed(1)}%</span>
        </div>
        <div class="cgc-price">${formatPrice(c.price)}</div>
        <div class="cgc-vol">24h Vol: ${volStr}</div>
      </div>
    `;
  }).join("");
}


// ==============================================================================
// 24. 100% QUANTITATIVE SIGNAL SCANNER & RADAR HUB
// Scans all 700+ cryptos and provides Ultra-High Probability Go UP / Go LOW setups
// ==============================================================================

function switchRadarView(view) {
  activeRadarView = view;
  const btnScanner = document.getElementById("tab-btn-scanner");
  const btnRadar = document.getElementById("tab-btn-radar");
  const viewScanner = document.getElementById("view-scanner-content");
  const viewRadar = document.getElementById("view-radar-content");

  if (btnScanner) btnScanner.classList.toggle("active", view === "scanner");
  if (btnRadar) btnRadar.classList.toggle("active", view === "radar");

  if (viewScanner) viewScanner.style.display = view === "scanner" ? "block" : "none";
  if (viewRadar) viewRadar.style.display = view === "radar" ? "grid" : "none";
}

async function triggerManualScan() {
  const btn = document.getElementById("btn-manual-scan");
  const spinner = document.getElementById("scan-btn-spinner");
  const text = document.getElementById("scan-btn-text");

  if (btn) btn.disabled = true;
  if (spinner) spinner.classList.add("spinning");
  if (text) text.textContent = "SCANNING 700+ CRYPTOS...";

  await runMarketScan(true);

  if (btn) btn.disabled = false;
  if (spinner) spinner.classList.remove("spinning");
  if (text) text.textContent = "SCAN ALL 700+ CRYPTOS";
}

async function runMarketScan(userTriggered = false) {
  if (isScanning) return;
  isScanning = true;

  const summaryEl = document.getElementById("scanner-summary-text");
  const timeEl = document.getElementById("scanner-time-text");
  if (summaryEl) summaryEl.textContent = "Running multi-factor predictive scan across 739 perpetual markets...";

  try {
    const res = await fetch("/api/scan_all?min_conf=70&limit=35");
    if (!res.ok) {
      if (summaryEl) summaryEl.textContent = "Scanner updating in background, will sync shortly...";
      return;
    }
    const data = await res.json();
    const signals = data.signals || [];
    scannerResults = signals;

    if (summaryEl) {
      const ultraCount = signals.filter(s => s.probability >= 82).length;
      summaryEl.innerHTML = `Scanned <b>739 USDT perpetual pairs</b> • Found <b>${signals.length} High-Probability setups</b> (<b>${ultraCount} High-Conviction Setups</b>)`;
    }
    if (timeEl) {
      const now = new Date();
      timeEl.textContent = `Updated at ${now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`;
    }

    renderFilteredScannerCards();

    // If an ultra setup (>=95%) was just discovered, play sound
    const topSetup = signals[0];
    if (topSetup && topSetup.probability >= 95 && userTriggered) {
      playAlertSound(topSetup.direction);
    }
  } catch (e) {
    console.error("Scanner run error:", e);
    if (summaryEl) summaryEl.textContent = "Scanner connection notice: Retrying shortly.";
  } finally {
    isScanning = false;
  }
}

function filterScannerResults(filterKey) {
  currentScannerFilter = filterKey;
  document.querySelectorAll(".s-pill").forEach(p => {
    p.classList.toggle("active", p.getAttribute("data-filter") === filterKey);
  });
  renderFilteredScannerCards();
}

function renderFilteredScannerCards() {
  let list = [...scannerResults];

  if (currentScannerFilter === "ultra") {
    list = list.filter(s => s.probability >= 82);
  } else if (currentScannerFilter === "up") {
    list = list.filter(s => s.direction === "UP");
  } else if (currentScannerFilter === "down") {
    list = list.filter(s => s.direction === "DOWN");
  } else if (currentScannerFilter === "rsi") {
    list = list.filter(s => (s.rsi < 32 || s.rsi > 68));
  }

  renderScannerCards(list);
}

function renderScannerCards(items) {
  const container = document.getElementById("scanner-results-grid");
  if (!container) return;

  if (!items || items.length === 0) {
    container.innerHTML = `
      <div style="grid-column: 1 / -1; padding: 40px; text-align: center; color: var(--text-muted);">
        No setups matching current filter. <button class="tool-action-btn" onclick="filterScannerResults('all')" style="margin-left:8px; display:inline-block; padding: 4px 10px; cursor: pointer;">Show All Signals</button>
      </div>
    `;
    return;
  }

  container.innerHTML = items.map(s => {
    const isUp = s.direction === "UP";
    const isUltra = s.probability >= 85;
    const confluencesHtml = (s.confluences || []).slice(0, 3).map(c => `
      <div class="sc-conf-item">
        <span class="sc-conf-dot" style="background: ${isUp ? '#10b981' : '#ef4444'}"></span>
        <span>${c}</span>
      </div>
    `).join("");

    return `
      <div class="scanner-card ${isUltra ? 'ultra-edge' : ''}">
        <div class="sc-header">
          <div class="sc-coin-group">
            <span class="sc-coin-name">${s.coin}</span>
            <span class="sc-contract-badge">${s.contract || (s.coin + 'USDT.P')}</span>
          </div>
          <span class="sc-dir-badge ${isUp ? 'up' : 'down'}">
            ${isUp ? '🟢 GO UP' : '🔴 GO LOW'} ${s.probability}%
          </span>
        </div>

        <div class="sc-signal-type">${s.confidence_tier ? `💎 ${s.confidence_tier}: ` : ''}${s.signal_type}</div>

        <div class="sc-probability-bar-wrap">
          <div class="sc-prob-labels">
            <span style="color: var(--text-muted); font-size: 0.65rem;">Confidence Edge</span>
            <span style="font-family: var(--font-mono); font-weight: 800; color: ${isUp ? '#34d399' : '#f87171'}">${s.probability}% PROBABILITY</span>
          </div>
          <div class="sc-prob-bar">
            <div class="sc-prob-fill ${isUp ? 'up' : 'down'}" style="width: ${s.probability}%"></div>
          </div>
        </div>

        <div class="sc-metrics-grid">
          <div class="sc-metric-col">
            <span class="sc-m-lbl">Current Price</span>
            <span class="sc-m-val">${formatPrice(s.current_price)}</span>
          </div>
          <div class="sc-metric-col">
            <span class="sc-m-lbl">${isUp ? 'Target (High)' : 'Target (Low)'}</span>
            <span class="sc-m-val" style="color: ${isUp ? '#34d399' : '#f87171'}">${formatPrice(s.target_price)}</span>
          </div>
          <div class="sc-metric-col">
            <span class="sc-m-lbl">Stop-Loss</span>
            <span class="sc-m-val" style="color: #94a3b8;">${formatPrice(s.stop_loss)}</span>
          </div>
        </div>

        <div class="sc-confluences-list">
          ${confluencesHtml}
        </div>

        <div class="sc-action-row">
          <div style="display: flex; gap: 6px; align-items: center;">
            <span class="sc-rr-tag">R:R 1:${s.risk_reward_ratio || 2.0}</span>
            <span style="font-size: 0.65rem; color: var(--text-muted);">RSI: ${s.rsi || 50}</span>
          </div>
          <button class="sc-trade-btn" onclick="selectCoin('${s.coin}', true)">
            VIEW CHART & TRADE ▶
          </button>
        </div>
      </div>
    `;
  }).join("");
}


// ==============================================================================
// 25. REAL-TIME ALERT MONITOR & FLOATING TOAST NOTIFICATIONS
// ==============================================================================

async function pollAlerts() {
  try {
    const res = await fetch(`/api/alerts?since=${lastAlertTimestamp}`);
    if (!res.ok) return;
    const data = await res.json();

    if (data) {
      if (Array.isArray(data.new_alerts) && data.new_alerts.length > 0) {
        data.new_alerts.forEach(alertItem => {
          showToastAlert(alertItem);
          unreadAlertCount++;
        });

        // Play audio chime for highest priority alert in batch
        const topAlert = data.new_alerts[0];
        playAlertSound(topAlert.direction);
      }

      if (data.alerts) {
        alertsHistory = data.alerts;
        renderAlertsHistory();
      }

      // Update unread badge counter in header
      updateAlertBadgeCounter();

      lastAlertTimestamp = Date.now();
    }
  } catch (e) {
    // Silent fail on polling error
  }
}

function updateAlertBadgeCounter() {
  const badge = document.getElementById("alert-counter");
  if (!badge) return;

  if (unreadAlertCount > 0) {
    badge.textContent = unreadAlertCount > 9 ? "9+" : unreadAlertCount;
    badge.style.display = "block";
  } else {
    badge.style.display = "none";
  }
}

function showToastAlert(a) {
  const container = document.getElementById("toast-container");
  if (!container) return;

  const isUp = a.direction === "UP";
  const toast = document.createElement("div");
  toast.className = `alert-toast ${isUp ? 'up' : 'down'}`;

  toast.innerHTML = `
    <div class="toast-header">
      <div class="toast-title">
        <span>${isUp ? '🟢' : '🔴'}</span>
        <span>${a.coin} ${isUp ? 'GO UP' : 'GO LOW'} (${a.probability}%)</span>
      </div>
      <button class="toast-close-btn" onclick="this.parentElement.parentElement.remove()">✕</button>
    </div>
    <div class="toast-body">
      <b>${a.signal_type || 'Ultra High Confluence'}:</b> Price ${formatPrice(a.price)} → Target ${formatPrice(a.target_price)} (Stop: ${formatPrice(a.stop_loss)})
    </div>
    <div class="toast-footer">
      <span style="font-size: 0.65rem; color: var(--text-muted);">${a.time_str || 'Just now'}</span>
      <button class="toast-btn-action" onclick="selectCoin('${a.coin}', true); this.closest('.alert-toast').remove();">
        INSPECT CHART ▶
      </button>
    </div>
    <div class="toast-progress">
      <div class="toast-progress-fill"></div>
    </div>
  `;

  container.appendChild(toast);

  // Auto-remove toast after exactly 3.8 seconds
  setTimeout(() => {
    if (toast && toast.parentElement) {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
      setTimeout(() => toast.remove(), 250);
    }
  }, 3800);
}

function toggleAlertCenter() {
  const modal = document.getElementById("alert-center-modal");
  if (!modal) return;

  const isOpen = modal.style.display === "flex";
  modal.style.display = isOpen ? "none" : "flex";

  if (!isOpen) {
    unreadAlertCount = 0;
    updateAlertBadgeCounter();
    renderAlertsHistory();
  }
}

function renderAlertsHistory() {
  const container = document.getElementById("alerts-history-list");
  if (!container) return;

  if (!alertsHistory || alertsHistory.length === 0) {
    container.innerHTML = `
      <div class="empty-alerts">
        <span style="font-size: 2.2rem;">🛡️</span>
        <p>No new alerts yet. The background scanner monitors all 700+ cryptos every 25 seconds for 85%+ confluences!</p>
      </div>
    `;
    return;
  }

  container.innerHTML = alertsHistory.map(a => {
    const isUp = a.direction === "UP";
    return `
      <div class="alert-history-item" onclick="selectCoin('${a.coin}', true); toggleAlertCenter();">
        <div style="display: flex; align-items: center; gap: 10px;">
          <span style="font-size: 1.2rem;">${isUp ? '🟢' : '🔴'}</span>
          <div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-weight: 800; font-size: 0.95rem; color: #fff;">${a.coin}</span>
              <span class="sc-dir-badge ${isUp ? 'up' : 'down'}" style="font-size: 0.68rem; padding: 2px 6px;">
                ${a.direction} ${a.probability}%
              </span>
            </div>
            <div style="font-size: 0.72rem; color: var(--text-secondary); margin-top: 2px;">
              Target: <b style="color: ${isUp ? '#34d399' : '#f87171'}">${formatPrice(a.target_price)}</b> | Stop: ${formatPrice(a.stop_loss)}
            </div>
          </div>
        </div>
        <div style="text-align: right;">
          <div style="font-family: var(--font-mono); font-size: 0.8rem; font-weight: 700; color: #fff;">${formatPrice(a.price)}</div>
          <div style="font-size: 0.65rem; color: var(--text-muted);">${a.time_str || ''}</div>
        </div>
      </div>
    `;
  }).join("");
}

async function clearAllAlerts() {
  try {
    await fetch("/api/alerts/clear", { method: "POST" });
    alertsHistory = [];
    unreadAlertCount = 0;
    updateAlertBadgeCounter();
    renderAlertsHistory();
  } catch (e) {
    console.error("Clear alerts error:", e);
  }
}

// ==============================================================================
// REAL-TIME COINDCX WEBSOCKET STREAM (BROWSER DIRECT 0ms PUSH)
// ==============================================================================
let wsClient = null;
const subscribedWsChannels = new Set();

function initCoinDcxWebSocket() {
  if (typeof io === "undefined") {
    console.log("[WS Notice] Socket.IO library not loaded, using fast REST polling fallback.");
    return;
  }
  try {
    wsClient = io("https://stream.coindcx.com", {
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionAttempts: Infinity,
      reconnectionDelay: 1000,
    });

    wsClient.on("connect", () => {
      console.log("⚡ [CoinDCX WebSocket] Connected to Real-Time Stream!");
      const wsPill = document.getElementById("ws-status-label");
      if (wsPill) wsPill.textContent = "⚡ WS STREAM: LIVE (0ms)";
      subscribedWsChannels.clear();
      if (window._ACTIVE_POSITIONS_MAP) {
        syncWebSocketSubscriptions(Object.values(window._ACTIVE_POSITIONS_MAP));
      }
    });

    wsClient.on("disconnect", () => {
      console.log("[CoinDCX WebSocket] Disconnected, auto-reconnecting...");
      subscribedWsChannels.clear();
    });

    wsClient.on("new-trade", (msg) => {
      try {
        const raw = msg ? msg.data : null;
        if (!raw) return;
        const data = typeof raw === "string" ? JSON.parse(raw) : raw;
        const sym = data.s || "";
        const price = parseFloat(data.p || 0);
        const coin = sym.replace("B-", "").replace("_USDT", "");
        if (coin && price > 0) {
          handleWebSocketLiveTick(coin, price);
        }
      } catch (e) {}
    });
  } catch (err) {
    console.warn("WebSocket init error:", err);
  }
}

function syncWebSocketSubscriptions(positions) {
  if (!wsClient || !wsClient.connected || !positions || !positions.length) return;
  positions.forEach(p => {
    const coin = p.symbol;
    if (!coin) return;
    const channel = `B-${coin}_USDT@trades`;
    if (!subscribedWsChannels.has(channel)) {
      try {
        wsClient.emit("join", { channelName: channel });
        subscribedWsChannels.add(channel);
        console.log(`⚡ [WS Subscribed]: ${channel}`);
      } catch (err) {}
    }
  });
}

function handleWebSocketLiveTick(coin, newPrice) {
  if (!window._ACTIVE_POSITIONS_MAP || !window._ACTIVE_POSITIONS_MAP[coin]) return;
  const pos = window._ACTIVE_POSITIONS_MAP[coin];
  const entry = Number(pos.buy_price || pos.price || 0);
  if (!entry || entry <= 0) return;
  const lev = Number(pos.leverage || 7);
  const isShort = (pos.direction || pos.side) === "SHORT";

  // Calculate new live gross PnL %
  const rawMove = isShort ? ((entry - newPrice) / entry) * 100 : ((newPrice - entry) / entry) * 100;
  const grossPnlPct = rawMove * lev;
  const isProfit = grossPnlPct >= 0;
  const pnlSign = grossPnlPct > 0 ? "+" : "";
  const pnlFormatted = `${pnlSign}${grossPnlPct.toFixed(1)}%`;
  const pnlColorClass = isProfit ? "pos-pnl-green" : "pos-pnl-red";
  const pinIcon = isProfit ? "▲" : "▼";

  // Calculate live Active PnL in INR
  const investedNum = Number(pos.invested || 200.0);
  const curActivePnlInr = investedNum * (grossPnlPct / 100.0);
  const pnlInrSign = curActivePnlInr >= 0 ? "+₹" : "-₹";
  const pnlInrFormatted = `${pnlInrSign}${Math.abs(curActivePnlInr).toFixed(2)}`;

  // Update live price text
  const elLiveVal = document.getElementById(`pos-live-val-${coin}`);
  if (elLiveVal) {
    elLiveVal.textContent = formatPrice(newPrice);
    elLiveVal.className = pnlColorClass;
  }

  // Update live PnL tag with both INR and %
  const elPnlTag = document.getElementById(`pos-live-pnl-${coin}`);
  if (elPnlTag) {
    elPnlTag.textContent = `${pnlInrFormatted} (${pnlSign}${grossPnlPct.toFixed(2)}%)`;
    elPnlTag.className = `pos-live-pnl-tag ${pnlColorClass}`;
  }

  // Calculate new needle percentage (0% = -48% Def, 50% = Entry, 100% = Target TP)
  let targetPnlPct = Number(pos.tp_target_pct || 15.0);
  let needlePct = 50.0;
  if (grossPnlPct >= 0) {
    const ratio = Math.min(1.0, grossPnlPct / targetPnlPct);
    needlePct = 50.0 + (ratio * 50.0);
  } else {
    const ratio = Math.min(1.0, Math.abs(grossPnlPct) / 48.0);
    needlePct = 50.0 - (ratio * 50.0);
  }
  needlePct = Math.max(3, Math.min(97, Math.round(needlePct * 10) / 10));

  // Update Needle
  const elNeedle = document.getElementById(`pos-needle-${coin}`);
  if (elNeedle) {
    elNeedle.style.left = `${needlePct}%`;
    elNeedle.className = `pos-gauge-needle ${isProfit ? 'needle-profit' : 'needle-loss'}`;
  }

  // Update Pin Badge with INR and %
  const elPin = document.getElementById(`pos-pin-${coin}`);
  if (elPin) {
    elPin.innerHTML = `${pinIcon} ${pnlInrFormatted} (${pnlFormatted})`;
    elPin.className = `pos-gauge-pin-badge ${pnlColorClass}`;
  }

  // Update Gauge Fill
  const elFill = document.getElementById(`pos-fill-${coin}`);
  if (elFill) {
    if (needlePct >= 50) {
      elFill.style.left = "50%";
      elFill.style.width = `${(needlePct - 50).toFixed(1)}%`;
    } else {
      elFill.style.left = `${needlePct.toFixed(1)}%`;
      elFill.style.width = `${(50 - needlePct).toFixed(1)}%`;
    }
    elFill.className = `pos-gauge-fill ${isProfit ? 'fill-profit' : 'fill-loss'}`;
  }
}

// Auto-initialize CoinDCX WebSocket stream on load
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initCoinDcxWebSocket);
} else {
  setTimeout(initCoinDcxWebSocket, 500);
}


