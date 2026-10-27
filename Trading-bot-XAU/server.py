"""
Trading-bot-XAU Server & Autonomous Trading Engine.
Combines:
- Real-time Gold (XAUUSD) Data Feed
- Automated ForexFactory High-Impact Economic News Shield
- Institutional Trend & Liquidity Sweep Strategy
- Auto-Breakeven, Trailing Stop & Risk Defense
- Interactive TradingView Live Candlestick Chart (OANDA:XAUUSD)
- 1-Click Manual Execution Bar (BUY / SELL with auto SL/TP)
- High-Performance Web Dashboard UI & REST APIs
"""

import time
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask, jsonify, request, render_template_string

import config
from news_filter import NewsShield
from data_feed import GoldDataProvider
from gold_strategy import GoldStrategy
from trade_engine import TradeEngine

app = Flask(__name__)

# Initialize components
news_shield = NewsShield(
    pre_news_minutes=config.PRE_NEWS_MINUTES,
    post_news_minutes=config.POST_NEWS_MINUTES,
    filter_impacts=config.NEWS_IMPACTS,
    filter_currencies=config.NEWS_CURRENCIES,
    max_spread_pips=config.MAX_ALLOWED_SPREAD_PIPS,
    atr_spike_threshold=config.VOLATILITY_CIRCUIT_BREAKER_ATR
)

data_feed = GoldDataProvider()
strategy = GoldStrategy()
engine = TradeEngine()

# State cache
latest_state = {
    "price": 0.0,
    "bid": 0.0,
    "ask": 0.0,
    "spread_pips": 0.0,
    "source": "Initializing...",
    "news_status": {},
    "last_signal": {},
    "session_status": "",
    "updated_at": ""
}

bot_running = True

def trading_worker():
    """Autonomous Gold trading loop running in background."""
    global latest_state
    print("[Gold Engine] Trading loop started. Monitoring XAUUSD & US Economic Calendar...")
    
    while bot_running:
        try:
            # 1. Fetch live Gold ticker
            ticker = data_feed.get_live_ticker()
            current_price = ticker.get("mid", 0.0)
            spread_pips = ticker.get("spread_pips", 0.0)

            # 2. Evaluate Economic News Status
            news_status = news_shield.evaluate_news_status()

            # 3. Update active positions (Breakeven, Trailing Stop, TP/SL, Pre-News defense)
            if current_price > 0:
                closed_trades = engine.update_positions(current_price, news_status)
                for ct in closed_trades:
                    print(f"[Gold Engine] Position closed: {ct['id']} | PnL: ${ct['pnl']} | Reason: {ct['close_reason']}")

            # 4. Check trading session
            session_ok, session_msg = strategy.is_valid_session()

            # 5. Fetch candles & evaluate strategy
            candles = data_feed.get_candles(timeframe="15m", limit=120)
            signal = {"action": "HOLD", "reason": "Initializing candles..."}
            if len(candles) >= 50:
                signal = strategy.evaluate_signal(candles, spread_pips, news_status)

            # 6. Execute autonomous signal if actionable
            if signal.get("action") in ("BUY", "SELL"):
                opened, msg = engine.open_position(signal)
                if opened:
                    print(f"[Gold Engine] ⭐ AUTONOMOUS TRADE EXECUTED: {msg}")

            # Update cache
            utc_now = datetime.now(timezone.utc)
            ist_now = utc_now + timedelta(hours=5, minutes=30)
            latest_state = {
                "price": current_price,
                "bid": ticker.get("bid", 0.0),
                "ask": ticker.get("ask", 0.0),
                "spread_pips": spread_pips,
                "spread_usd": ticker.get("spread_usd", 0.0),
                "source": ticker.get("source", "Live"),
                "news_status": news_status,
                "last_signal": signal,
                "session_status": session_msg,
                "updated_at": ist_now.strftime("%d %b %Y, %H:%M:%S IST")
            }

        except Exception as e:
            print(f"[Gold Engine] Error in trading loop: {e}")

        time.sleep(10)

# Start background thread
worker_thread = threading.Thread(target=trading_worker, daemon=True)
worker_thread.start()


# --- DASHBOARD TEMPLATE ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Gold (XAU/USD) Autonomous Terminal | Live Chart & News Shield</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0d14;
            --bg-card: rgba(18, 24, 38, 0.78);
            --border-glass: rgba(255, 255, 255, 0.08);
            --gold-primary: #ffd700;
            --gold-glow: rgba(255, 215, 0, 0.35);
            --green: #10b981;
            --red: #ef4444;
            --text-main: #f1f5f9;
            --text-dim: #94a3b8;
            --font-main: 'Plus Jakarta Sans', sans-serif;
            --font-mono: 'JetBrains Mono', monospace;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: radial-gradient(circle at 50% 0%, #171f33 0%, #080b11 100%);
            color: var(--text-main);
            font-family: var(--font-main);
            min-height: 100vh;
            padding: 20px;
        }

        .container { max-width: 1440px; margin: 0 auto; }

        /* Top Header */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 18px 24px;
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-glass);
            border-radius: 18px;
            margin-bottom: 20px;
            box-shadow: 0 12px 32px rgba(0,0,0,0.4);
        }

        .brand { display: flex; align-items: center; gap: 16px; }

        .gold-icon {
            width: 46px;
            height: 46px;
            background: linear-gradient(135deg, #ffd700, #b8860b);
            border-radius: 12px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 22px;
            box-shadow: 0 0 24px var(--gold-glow);
        }

        .title-h1 { font-size: 20px; font-weight: 800; letter-spacing: -0.5px; }
        .subtitle { font-size: 13px; color: var(--text-dim); margin-top: 3px; }

        .header-stats { display: flex; align-items: center; gap: 16px; }

        .badge {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 14px;
            border-radius: 30px;
            font-size: 13px;
            font-weight: 600;
        }

        .badge-safe { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
        .badge-danger { background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); animation: pulse 1.8s infinite; }

        @keyframes pulse {
            0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(239, 68, 68, 0.4); }
            70% { transform: scale(1.02); box-shadow: 0 0 0 10px rgba(239, 68, 68, 0); }
            100% { transform: scale(1); }
        }

        /* News Radar Banner */
        .news-radar {
            padding: 16px 22px;
            background: rgba(30, 41, 59, 0.65);
            backdrop-filter: blur(12px);
            border: 1px solid var(--border-glass);
            border-radius: 16px;
            margin-bottom: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .news-radar.locked {
            background: rgba(239, 68, 68, 0.15);
            border-color: rgba(239, 68, 68, 0.4);
        }

        .news-info { display: flex; align-items: center; gap: 14px; }
        .news-icon { font-size: 26px; }
        .news-text-title { font-size: 15px; font-weight: 700; }
        .news-text-sub { font-size: 13px; color: var(--text-dim); margin-top: 3px; }

        /* Metric Grid */
        .metric-grid {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 18px;
            margin-bottom: 20px;
        }

        .card {
            background: var(--bg-card);
            backdrop-filter: blur(16px);
            border: 1px solid var(--border-glass);
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.3);
            position: relative;
        }

        .card-label {
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            color: var(--text-dim);
            margin-bottom: 8px;
        }

        .card-value {
            font-family: var(--font-mono);
            font-size: 26px;
            font-weight: 700;
            color: #fff;
        }

        .card-sub { font-size: 12px; color: var(--text-dim); margin-top: 6px; }

        /* Manual Trading Control Bar */
        .manual-bar {
            background: var(--bg-card);
            border: 1px solid var(--border-glass);
            border-radius: 16px;
            padding: 16px 22px;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 16px;
        }

        .manual-left { display: flex; align-items: center; gap: 16px; }
        .manual-title { font-size: 15px; font-weight: 700; }
        .lot-selector { display: flex; align-items: center; gap: 8px; }
        .lot-input {
            background: rgba(0,0,0,0.3);
            border: 1px solid var(--border-glass);
            color: #ffd700;
            font-family: var(--font-mono);
            font-weight: 700;
            font-size: 15px;
            padding: 8px 12px;
            border-radius: 8px;
            width: 90px;
            text-align: center;
        }

        .btn-lot {
            background: rgba(255,255,255,0.06);
            border: 1px solid var(--border-glass);
            color: var(--text-main);
            padding: 6px 12px;
            border-radius: 6px;
            font-size: 12px;
            cursor: pointer;
            font-weight: 600;
        }
        .btn-lot:hover { background: rgba(255,255,255,0.15); }

        .manual-actions { display: flex; align-items: center; gap: 12px; }
        .btn-buy {
            background: linear-gradient(135deg, #10b981, #059669);
            color: #fff;
            border: none;
            padding: 10px 22px;
            border-radius: 10px;
            font-weight: 700;
            font-size: 14px;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(16, 185, 129, 0.4);
            transition: all 0.2s;
        }
        .btn-buy:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(16, 185, 129, 0.6); }

        .btn-sell {
            background: linear-gradient(135deg, #ef4444, #dc2626);
            color: #fff;
            border: none;
            padding: 10px 22px;
            border-radius: 10px;
            font-weight: 700;
            font-size: 14px;
            cursor: pointer;
            box-shadow: 0 4px 14px rgba(239, 68, 68, 0.4);
            transition: all 0.2s;
        }
        .btn-sell:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(239, 68, 68, 0.6); }

        /* TradingView Chart Container */
        .chart-card {
            background: var(--bg-card);
            border: 1px solid var(--border-glass);
            border-radius: 16px;
            padding: 18px;
            margin-bottom: 20px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        }

        .chart-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }

        /* Main Workspace Split */
        .workspace {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }

        .panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 10px;
            border-bottom: 1px solid var(--border-glass);
        }

        .panel-title { font-size: 16px; font-weight: 700; }

        /* Table */
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { text-align: left; padding: 10px; color: var(--text-dim); font-size: 11px; text-transform: uppercase; }
        td { padding: 12px 10px; border-top: 1px solid var(--border-glass); }

        .btn {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid var(--border-glass);
            color: #fff;
            padding: 7px 14px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn:hover { background: rgba(255, 255, 255, 0.16); }
        .btn-danger { background: rgba(239, 68, 68, 0.2); border-color: rgba(239, 68, 68, 0.4); color: #f87171; }
        .btn-danger:hover { background: rgba(239, 68, 68, 0.35); }

        .pnl-green { color: var(--green); font-weight: 700; font-family: var(--font-mono); }
        .pnl-red { color: var(--red); font-weight: 700; font-family: var(--font-mono); }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="brand">
                <div class="gold-icon">🪙</div>
                <div>
                    <div class="title-h1">Trading-bot-XAU &bull; Gold Institutional Terminal</div>
                    <div class="subtitle" id="last-updated">Real-time Gold & ForexFactory News Shield</div>
                </div>
            </div>
            <div class="header-stats">
                <div id="session-badge" class="badge badge-safe">London Active Session</div>
                <div id="news-badge" class="badge badge-safe">🟢 SHIELD ALL CLEAR</div>
                <button class="btn btn-danger" onclick="emergencyClose()">🚨 EMERGENCY KILLSWITCH</button>
            </div>
        </header>

        <!-- News Radar Banner -->
        <div id="news-radar-box" class="news-radar">
            <div class="news-info">
                <div class="news-icon" id="news-icon">🛡️</div>
                <div>
                    <div class="news-text-title" id="news-headline">US Economic News Shield Active</div>
                    <div class="news-text-sub" id="news-details">Monitoring Non-Farm Payrolls (NFP), CPI, FOMC Fed Rates & PPI</div>
                </div>
            </div>
            <div>
                <span style="font-size: 13px; color: var(--text-dim); margin-right: 8px;">Next US Event:</span>
                <span id="next-event-tag" style="font-family: var(--font-mono); font-weight: 700; color: #ffd700;">Scanning...</span>
            </div>
        </div>

        <!-- 1-Click Manual Execution Bar -->
        <div class="manual-bar">
            <div class="manual-left">
                <div class="manual-title">⚡ 1-Click Trade Execution (Manual Override)</div>
                <div class="lot-selector">
                    <span style="font-size: 12px; color: var(--text-dim);">Lot Size:</span>
                    <input type="number" id="manual-lots" class="lot-input" value="0.05" step="0.01" min="0.01" max="5.0" oninput="updateMarginEstimates()">
                    <button class="btn-lot" onclick="setLots(0.01)">0.01 Micro</button>
                    <button class="btn-lot" onclick="setLots(0.05)">0.05 Safe</button>
                    <button class="btn-lot" onclick="setLots(0.10)">0.10 Mini</button>
                </div>
                <div id="margin-calc" style="font-size: 12px; color: var(--text-dim);">
                    Margin Req: <span id="margin-usd" style="color: #ffd700; font-weight: 700;">~$20 USD</span> (~₹1,750 INR)
                </div>
            </div>
            <div class="manual-actions">
                <button class="btn-buy" onclick="executeManual('BUY')">🟢 BUY MARKET (Auto SL/TP)</button>
                <button class="btn-sell" onclick="executeManual('SELL')">🔴 SELL MARKET (Auto SL/TP)</button>
            </div>
        </div>

        <!-- Metric Grid -->
        <div class="metric-grid">
            <div class="card">
                <div class="card-label">Spot Gold (XAU/USD)</div>
                <div class="card-value" id="gold-price" style="color: #ffd700;">$0.00</div>
                <div class="card-sub" id="spread-info">Spread: 0.0 pips ($0.00)</div>
            </div>
            <div class="card">
                <div class="card-label">Account Balance / Equity</div>
                <div class="card-value" id="balance-equity">$5,000.00</div>
                <div class="card-sub" id="floating-pnl">Floating PnL: $0.00</div>
            </div>
            <div class="card">
                <div class="card-label">Live Win Rate & Ratio</div>
                <div class="card-value" id="win-rate">0.0%</div>
                <div class="card-sub" id="win-loss-count">0 Wins / 0 Losses</div>
            </div>
            <div class="card">
                <div class="card-label">Net Profit / Profit Factor</div>
                <div class="card-value" id="net-pnl">$0.00</div>
                <div class="card-sub" id="profit-factor">Profit Factor: 0.00</div>
            </div>
        </div>

        <!-- Live Candlestick Chart (TradingView Interactive) -->
        <div class="chart-card">
            <div class="chart-header">
                <div style="font-size: 16px; font-weight: 700;">📈 Live Gold (XAU/USD) Candlestick Chart & Technicals</div>
                <div style="font-size: 12px; color: var(--text-dim);">Interactive TradingView M15 Candles &bull; Real-time Feed</div>
            </div>
            <div style="height: 480px; width: 100%; border-radius: 12px; overflow: hidden;">
                <!-- TradingView Widget BEGIN -->
                <div class="tradingview-widget-container" style="height:100%; width:100%;">
                    <div id="tradingview_chart" style="height:100%; width:100%;"></div>
                    <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
                    <script type="text/javascript">
                    new TradingView.widget({
                        "autosize": true,
                        "symbol": "OANDA:XAUUSD",
                        "interval": "15",
                        "timezone": "Asia/Kolkata",
                        "theme": "dark",
                        "style": "1",
                        "locale": "en",
                        "toolbar_bg": "#0a0d14",
                        "enable_publishing": false,
                        "allow_symbol_change": true,
                        "container_id": "tradingview_chart"
                    });
                    </script>
                </div>
                <!-- TradingView Widget END -->
            </div>
        </div>

        <!-- Main Workspace -->
        <div class="workspace">
            <!-- Active Positions Panel -->
            <div class="card">
                <div class="panel-header">
                    <div class="panel-title">⚡ Active Open Positions (XAU/USD)</div>
                    <button class="btn" onclick="fetchStatus()">Refresh</button>
                </div>
                <table id="positions-table">
                    <thead>
                        <tr>
                            <th>Side</th>
                            <th>Lots</th>
                            <th>Entry</th>
                            <th>Current</th>
                            <th>Stop Loss</th>
                            <th>Take Profit</th>
                            <th>Defense</th>
                            <th>PnL (USD)</th>
                        </tr>
                    </thead>
                    <tbody id="positions-body">
                        <tr><td colspan="8" style="text-align: center; color: var(--text-dim); padding: 24px;">No active open positions. Scanning Gold liquidity zones...</td></tr>
                    </tbody>
                </table>
            </div>

            <!-- Signal & Session Radar Panel -->
            <div class="card">
                <div class="panel-header">
                    <div class="panel-title">🎯 Algorithmic Confluence</div>
                </div>
                <div style="margin-bottom: 16px;">
                    <div style="font-size: 13px; color: var(--text-dim); margin-bottom: 6px;">Current Signal:</div>
                    <div id="signal-badge" style="font-size: 17px; font-weight: 700; font-family: var(--font-mono);">AWAITING SIGNAL</div>
                    <div id="signal-reason" style="font-size: 12px; color: var(--text-dim); margin-top: 6px; line-height: 1.5;"></div>
                </div>
                <div style="border-top: 1px solid var(--border-glass); padding-top: 14px;">
                    <div style="font-size: 13px; font-weight: 600; margin-bottom: 8px;">Upcoming US Economic Events (24h):</div>
                    <ul id="events-list" style="list-style: none; font-size: 12px; color: var(--text-dim);">
                        <li>Loading economic calendar...</li>
                    </ul>
                </div>
            </div>
        </div>
    </div>

    <script>
        function setLots(val) {
            document.getElementById('manual-lots').value = val;
            updateMarginEstimates();
        }

        function updateMarginEstimates() {
            const lots = parseFloat(document.getElementById('manual-lots').value) || 0.01;
            // 0.01 lot = 1 oz. At 1:100 leverage, 1 oz at $4090 requires ~$40.90 margin
            const estMarginUSD = Math.round(lots * 400); 
            const estMarginINR = Math.round(estMarginUSD * 87.5);
            document.getElementById('margin-usd').textContent = `~$${estMarginUSD} USD (~₹${estMarginINR.toLocaleString('en-IN')} INR)`;
        }

        async function executeManual(side) {
            const lots = parseFloat(document.getElementById('manual-lots').value) || 0.05;
            if (!confirm(`Are you sure you want to execute MANUAL ${side} of ${lots} Lots on Gold (XAUUSD)?`)) return;

            try {
                const res = await fetch('/api/manual_trade', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ side: side, lots: lots })
                });
                const data = await res.json();
                if (data.success) {
                    alert('Order Placed Successfully: ' + data.message);
                } else {
                    alert('Order Failed: ' + data.message);
                }
                fetchStatus();
            } catch (e) {
                alert('Execution error: ' + e);
            }
        }

        async function fetchStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();

                // 1. Price & Spread
                document.getElementById('gold-price').textContent = '$' + data.ticker.price.toFixed(2);
                document.getElementById('spread-info').textContent = `Spread: ${data.ticker.spread_pips} pips ($${data.ticker.spread_usd})`;
                document.getElementById('last-updated').textContent = `Last update: ${data.updated_at} | Data Source: ${data.ticker.source}`;

                // 2. News Shield Status
                const news = data.news_status;
                const radarBox = document.getElementById('news-radar-box');
                const newsBadge = document.getElementById('news-badge');
                const nextTag = document.getElementById('next-event-tag');

                if (news.is_locked) {
                    radarBox.className = 'news-radar locked';
                    newsBadge.className = 'badge badge-danger';
                    newsBadge.textContent = '🚨 NEWS LOCKDOWN';
                    document.getElementById('news-icon').textContent = '⚠️';
                    document.getElementById('news-headline').textContent = news.lock_reason;
                } else {
                    radarBox.className = 'news-radar';
                    newsBadge.className = 'badge badge-safe';
                    newsBadge.textContent = '🟢 SHIELD ALL CLEAR';
                    document.getElementById('news-icon').textContent = '🛡️';
                    document.getElementById('news-headline').textContent = 'US Economic News Shield Active (Safe to Trade)';
                }

                if (news.next_event) {
                    nextTag.textContent = `[${news.next_event.country}] ${news.next_event.title} in ${news.minutes_to_next}m`;
                } else {
                    nextTag.textContent = 'None in next 24 hours';
                }

                // 3. Metrics
                const metrics = data.metrics;
                document.getElementById('balance-equity').textContent = '$' + metrics.balance.toFixed(2);
                document.getElementById('floating-pnl').textContent = `Equity: $${metrics.equity.toFixed(2)}`;
                document.getElementById('win-rate').textContent = metrics.win_rate + '%';
                document.getElementById('win-loss-count').textContent = `${metrics.wins}W / ${metrics.losses}L (${metrics.total_trades} total)`;
                
                const netEl = document.getElementById('net-pnl');
                netEl.textContent = (metrics.net_profit >= 0 ? '+$' : '-$') + Math.abs(metrics.net_profit).toFixed(2);
                netEl.style.color = metrics.net_profit >= 0 ? '#10b981' : '#ef4444';
                document.getElementById('profit-factor').textContent = `Profit Factor: ${metrics.profit_factor}`;

                // 4. Session
                document.getElementById('session-badge').textContent = data.session_status;

                // 5. Signal
                const sig = data.last_signal;
                const sigEl = document.getElementById('signal-badge');
                sigEl.textContent = sig.action || 'HOLD';
                if (sig.action === 'BUY') sigEl.style.color = '#10b981';
                else if (sig.action === 'SELL') sigEl.style.color = '#ef4444';
                else sigEl.style.color = '#94a3b8';
                document.getElementById('signal-reason').textContent = sig.reason || '';

                // 6. Active Positions
                const pBody = document.getElementById('positions-body');
                if (data.positions.length === 0) {
                    pBody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-dim); padding: 24px;">No active open positions. Scanning Gold liquidity zones...</td></tr>';
                } else {
                    pBody.innerHTML = data.positions.map(p => `
                        <tr>
                            <td style="font-weight: 700; color: ${p.side === 'BUY' ? '#10b981' : '#ef4444'}">${p.side}</td>
                            <td>${p.lots} lots</td>
                            <td>$${p.entry_price.toFixed(2)}</td>
                            <td>$${p.current_price.toFixed(2)}</td>
                            <td>$${p.sl.toFixed(2)}</td>
                            <td>$${p.tp.toFixed(2)}</td>
                            <td>${p.is_breakeven ? '🛡️ Breakeven' : (p.trailing_active ? '⚡ Trailing' : 'Initial SL')}</td>
                            <td class="${p.pnl >= 0 ? 'pnl-green' : 'pnl-red'}">${p.pnl >= 0 ? '+$' : '-$'}${Math.abs(p.pnl).toFixed(2)}</td>
                        </tr>
                    `).join('');
                }

                // 7. Upcoming Events
                const evList = document.getElementById('events-list');
                if (news.upcoming_events && news.upcoming_events.length > 0) {
                    evList.innerHTML = news.upcoming_events.slice(0, 5).map(e => `
                        <li style="margin-bottom: 8px; display: flex; justify-content: space-between;">
                            <span>${e.title}</span>
                            <span style="color: #ffd700; font-family: var(--font-mono);">${e.minutes_away}m away</span>
                        </li>
                    `).join('');
                } else {
                    evList.innerHTML = '<li>No major events in next 24h</li>';
                }

            } catch (e) {
                console.error("Fetch error:", e);
            }
        }

        async function emergencyClose() {
            if (confirm("Are you sure you want to trigger Emergency Close for all open Gold positions?")) {
                await fetch('/api/close_all', { method: 'POST' });
                fetchStatus();
            }
        }

        updateMarginEstimates();
        fetchStatus();
        setInterval(fetchStatus, 4000);
    </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/status")
def api_status():
    metrics = engine.get_performance_metrics()
    return jsonify({
        "ticker": {
            "price": latest_state["price"],
            "bid": latest_state["bid"],
            "ask": latest_state["ask"],
            "spread_pips": latest_state["spread_pips"],
            "spread_usd": latest_state["spread_usd"],
            "source": latest_state["source"]
        },
        "news_status": latest_state["news_status"],
        "session_status": latest_state["session_status"],
        "last_signal": latest_state["last_signal"],
        "positions": engine.positions,
        "metrics": metrics,
        "updated_at": latest_state["updated_at"]
    })

@app.route("/api/manual_trade", methods=["POST"])
def api_manual_trade():
    """Execute a manual BUY or SELL trade with auto-calculated Stop Loss & Take Profit."""
    data = request.json or {}
    side = data.get("side", "BUY").upper()
    lots = float(data.get("lots", 0.05))
    current_price = latest_state["price"]
    
    if current_price <= 0:
        return jsonify({"success": False, "message": "Live Gold price feed unavailable"}), 400

    # Auto-calculate institutional 1:2 R:R SL and TP ($4.50 SL buffer, $9.00 TP)
    sl_dist = 4.50
    tp_dist = 9.00
    if side == "BUY":
        sl = round(current_price - sl_dist, 2)
        tp = round(current_price + tp_dist, 2)
    else:
        sl = round(current_price + sl_dist, 2)
        tp = round(current_price - tp_dist, 2)

    sig = {
        "action": side,
        "price": current_price,
        "sl": sl,
        "tp": tp,
        "lots": lots,
        "reason": f"Manual {side} execution via Web Terminal ({lots} Lots)"
    }
    opened, msg = engine.open_position(sig)
    return jsonify({"success": opened, "message": msg})

@app.route("/api/close_all", methods=["POST"])
def api_close_all():
    closed = []
    now_ts = time.time()
    for pos in engine.positions:
        pos["exit_price"] = latest_state["price"]
        pos["close_time"] = now_ts
        pos["close_reason"] = "Manual Emergency Killswitch Triggered"
        pos["final_pnl"] = pos["pnl"]
        engine.balance = round(engine.balance + pos["pnl"], 2)
        engine.closed_trades.append(pos)
        closed.append(pos)
    engine.positions = []
    engine.equity = engine.balance
    engine.save_state()
    return jsonify({"status": "success", "closed_positions": len(closed)})

@app.route("/api/reset", methods=["POST"])
def api_reset():
    engine.balance = config.INITIAL_BALANCE
    engine.equity = config.INITIAL_BALANCE
    engine.positions = []
    engine.closed_trades = []
    engine.save_state()
    return jsonify({"status": "reset", "balance": engine.balance})

if __name__ == "__main__":
    print(f"[Trading-bot-XAU] Starting Web Terminal at http://localhost:{config.PORT}")
    app.run(host="0.0.0.0", port=config.PORT, debug=False)
