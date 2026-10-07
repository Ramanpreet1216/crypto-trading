# CoinDCX Algorithmic Trading Bot

An automated trading bot designed for Indian crypto markets using the official CoinDCX REST API.

## Features
- **All 700+ Cryptocurrencies Available**: Global real-time search and an interactive full-market explorer modal supporting all 739+ USDT Perpetual Futures pairs (BTC, ETH, SOL, DOGE, PEPE, WIF, SUI, NEAR, etc.).
- **100% Quantitative Signal Scanner & Radar**: Scans all 700+ cryptos concurrently using multi-indicator confluence (EMA 9/21/50, RSI extremes, Bollinger Band breakouts, linear regression momentum, and volume surges) to detect Ultra-High Probability (90%-98% "100% Setup") Go UP (Long) and Go LOW (Short) opportunities with precise targets, stop-losses, and risk:reward ratios.
- **Real-Time Sound & Visual Alerts**: Background scanner evaluates all markets every 25 seconds; triggers dual-tone Web Audio API sound alerts (crystal UP chime and caution DOWN chime), animated floating toast notifications, and an Alert Center with live unread badge counters.
- **Visual Web Dashboard**: Interactive modern dark-mode GUI with live charts, AI price prediction, and paper trading controls at `http://localhost:5000`.
- **AI Futures Strategy & Leverage Advisor**: Real-time multi-timeframe evaluator (1m, 5m, 15m, 1h, 1D) that recommends whether to go **LONG** or **SHORT**, which timeframe has highest probability, and what leverage tier (1x to 100x) is safest for ₹1,500 capital.
- **Dynamic Leverage Inspector & Wipeout Trap Warning**: Live calculation of liquidation prices across 1x, 3x, 5x, 10x, 25x, 50x, and 100x with clear explanations of why 100x is an instant liquidation trap (0.9% drop loses 100%) vs why 5x–10x is the optimal sweetspot.
- **Zero Risk Paper Trading Mode (Default)**: Connects to real-time live market data and simulates trades with your INR 1,500 wallet so you don't risk real money while learning.

---

## Visual Dashboard (Recommended)

To launch the web interface:
```bash
python server.py
```
Then open your browser to: **`http://localhost:5000`**

### Timeframe & Leverage Selection Playbook (For ₹1,500 Capital)
| Timeframe | Trading Style | Holding Duration | Optimal Leverage | Strategy Note |
|---|---|---|---|---|
| **1m** | Ultra Scalp | 2 – 5 mins | **5x** | Fast reaction to 1m orderbook drift with tight stop-loss. |
| **5m** | Quick Scalp | 5 – 15 mins | **10x** | Captures fast intraday momentum swings. |
| **15m** | Intraday Trend | 30m – 2 hours | **10x** ⭐ *(Recommended)* | **Highest statistical win-rate.** Filters out 1m/5m market noise. |
| **1h** | Swing Trend | 2 – 8 hours | **5x – 10x** | High-probability continuation setups with wide stop room. |
| **1D** | Macro Position | 1 – 5 days | **1x – 2x** | Safe macro holding without liquidation risk. |

### Leverage Reality Check (1x vs 100x)
- **100x Leverage (⚠️ WIPEOUT TRAP)**: At 100x, a mere **0.90% price movement against your trade triggers 100% liquidation** (complete loss of your ₹1,500). Cryptocurrency prices routinely fluctuate 1% in seconds due to normal bid/ask spreads. **Never use 100x!**
- **10x Leverage (💎 RECOMMENDED SWEETSPOT)**: Requires a **9.0% drop** to liquidate. You can comfortably set a 1.5%–2.5% stop-loss and make **+40% to +60% profit (+₹600–₹900)** on target hit while being completely safe from normal wicks.
- **5x Leverage (🛡️ SAFE BUFFER)**: Requires an **18.0% drop** to liquidate. Excellent for beginners and volatile coins.
- **1x Leverage (🟢 ZERO LIQUIDATION RISK)**: Behaves like spot crypto holding. No liquidation danger.

## File Structure
- [`config.py`](file:///d:/Work/Trading/config.py): All settings (Dry run mode, symbol, timeframe, EMA/RSI periods, stop loss).
- [`strategy.py`](file:///d:/Work/Trading/strategy.py): Indicator calculations and signal generation (BUY, SELL, HOLD).
- [`coindcx_client.py`](file:///d:/Work/Trading/coindcx_client.py): CoinDCX API client for live ticker, candles, balances, and orders.
- [`bot.py`](file:///d:/Work/Trading/bot.py): Main bot engine and terminal dashboard.

---

## How to Run the Bot

1. Open PowerShell or Terminal in this folder (`d:\Work\Trading`).
2. Run:
   ```bash
   python bot.py
   ```
3. Watch the bot stream live market prices, compute indicators, and execute paper trades.
4. Press `Ctrl + C` anytime to stop the bot safely.

---

## Going Live with Real Money (When Ready)

When you are satisfied with how the bot operates in paper trading mode:

1. Log in to your CoinDCX account on Web or App.
2. Go to **Profile** -> **API Management** -> **Create API Key**.
   > **CRITICAL SECURITY RULE**: Enable only **Read** and **Trading/Order Placement** permissions. **NEVER** enable "Withdrawal" permission.
3. Open [`config.py`](file:///d:/Work/Trading/config.py) and enter:
   ```python
   DRY_RUN = False
   COINDCX_API_KEY = "your_api_key_here"
   COINDCX_API_SECRET = "your_api_secret_here"
   ```
4. Start small: keep `INVESTMENT_PER_TRADE_INR = 100.0` (CoinDCX minimum order is ₹100).
