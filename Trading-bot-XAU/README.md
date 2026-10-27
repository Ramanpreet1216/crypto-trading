# Trading-bot-XAU (Institutional Gold / XAUUSD Trading System)

Autonomous trading bot and MT5 Expert Advisor engineered specifically for **Gold (XAU/USD)** volatility with institutional-grade news defense, dynamic spread filtering, auto-breakeven, and trailing stops.

---

## 🛡️ How We Stay Safe From Violent US Economic News Spikes (NFP, CPI, Fed Rates)

Gold moves violently ($20–$50 in 60 seconds) during major macroeconomic announcements. Here is the **5-layer protective shield** implemented in this bot:

### 1. Automated ForexFactory Economic Calendar Shield (`news_filter.py`)
- Automatically pulls high-impact US economic events (CPI, Non-Farm Payrolls, FOMC Interest Rates, PPI, GDP, Jackson Hole, Powell speeches).
- **Pre-News Lockdown (30 Minutes Before)**: Disallows opening any new trades 30 minutes before release.
- **Post-News Settling (30 Minutes After)**: Remains locked down for 30 minutes until extreme spread widening and erratic two-way wicks subside.
- **Defensive Breakeven (0 Risk)**: If an active trade is already open and in profit (+0.5R or more), the bot **automatically slides the Stop Loss to Breakeven** before the news hits. If a violent wick occurs, you exit at $0 risk without losing a penny.

### 2. Real-Time Spread Spike Circuit Breaker
- In events of unannounced breaking news (geopolitics, emergency rate cuts, flash crash), spreads instantly balloon from 15–25¢ to $2.00–$5.00.
- If spread exceeds `MAX_ALLOWED_SPREAD_PIPS` (3.5 pips / $0.35), the bot immediately **rejects all order execution**.

### 3. ATR Volatility Circuit Breaker
- If any 1-minute or 5-minute candle range exceeds 2.5× the 14-period Average True Range (ATR), the bot freezes trading for 15 minutes to avoid chasing wild spikes.

### 4. High-Liquidity Trading Session Filter
- Gold experiences erratic fakeouts during low-liquidity rollover (02:00–04:00 IST).
- The bot restricts entries exclusively to:
  - **London Session**: 13:30 – 21:30 IST (08:00 – 16:00 GMT)
  - **New York Session**: 18:00 – 23:30 IST (12:30 – 18:00 GMT)

### 5. Institutional Lot Sizing & 1:2 R:R Ratio
- Fixed 1% risk per trade.
- Lot size is mathematically scaled based on ATR stop-loss distance ($3.00 minimum buffer to absorb normal market breathing room).
- Minimum 1:2 Risk to Reward (e.g. risking $4.00 to target $8.00).

---

## 📁 System Architecture

```
d:\raman\Trading-final\Trading\Trading-bot-XAU/
├── config.py                 # Risk parameters, session hours, news filter toggles
├── news_filter.py            # ForexFactory live calendar scraper & lockdown engine
├── data_feed.py              # Real-time Gold spot (PAXG / LBMA) & MT5 quote feed
├── gold_strategy.py          # Institutional EMA (21/50/200), ATR, RSI & ADX confluence
├── trade_engine.py           # Lot sizing, Trailing Stop, Auto-Breakeven, PnL math
├── server.py                 # High-performance Flask dashboard running on port 5005
├── xau_trades.json           # Persistent balance and trade history
└── mql5_expert_advisor/
    └── GoldSniper_EA.mq5     # Production-ready MQL5 EA for MetaTrader 5
```

---

## 🚀 How to Run the Bot Dashboard

1. Launch the server:
   ```powershell
   python server.py
   ```
2. Open your web browser:
   ```
   http://localhost:5005
   ```
3. The dashboard displays:
   - Live Gold (XAUUSD) Spot Price & Current Spread
   - **Live News Radar Banner** (e.g., `🟢 SHIELD ALL CLEAR` vs `🚨 PRE-NEWS LOCKDOWN`)
   - Next upcoming US economic event with countdown in minutes
   - Active open positions with live floating PnL & Breakeven status
   - One-Click **Emergency Killswitch**

---

## 📊 How to Use in MetaTrader 5 (MT5)

1. Open MetaTrader 5.
2. Press `F4` to open **MetaEditor**.
3. Copy `mql5_expert_advisor/GoldSniper_EA.mq5` into `MQL5/Experts/` folder.
4. Click **Compile** (`F7`).
5. In MT5, attach `GoldSniper_EA` to the `XAUUSD` M15 chart with **Algo Trading** enabled.
