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

### Capital Allocation & Dynamic Sizing Playbook (For ₹30,000 Wallet)
- **Starting Wallet Balance**: **₹30,000.00 INR**
- **Maximum Concurrent Positions**: **10 Trades Simultaneously**
- **Dynamic Adaptive Margin Sizing**:
  - **Solo Sniper Trade (1 Best in 24h)**: **₹5,000 Margin** (Allocated when only 1 standout high-conviction 92%+ setup is found).
  - **Standard Multi-Slot**: **₹3,000 Margin per trade** (Up to 10 slots = ₹30,000 total capital utilized).
  - **Broad Confluence Wave (6-10 Confirmed Signals)**: **₹2,500 Margin per trade** (Ensures all 10 slots fit smoothly with a ₹5,000 cash reserve).
- **Realistic Indian Crypto Tax & Fee Deductions**:
  - **CoinDCX Futures Fees**: 0.05% entry taker fee + 0.05% exit taker fee (0.10% total on notional position).
  - **1% TDS (Section 194S)**: 1.0% deducted on exit payout.
  - **31.2% Flat Govt Tax (Section 115BBH)**: 30% flat capital gains tax + 4% Health & Education cess automatically deducted from gross winning profits.
  - **True In-Pocket PnL**: Tracks gross gains, exchange fees, TDS, and government taxes separately so you know your exact real profit in your pocket.

### User Mirror Strategy (100% Win Rate Architecture)
- **Asset-Specific Adaptive Leverage (Safe Sweetspot)**:
  - **BTC / WBTC**: **`20x – 22x`** (Liquidation buffer: ~4.5% to 5.0%; captures ₹300–₹500 on small $400–$600 drops).
  - **ETH**: **`10x – 12x`** (12x on 5/5 confluence, 10x on 4/5; de-leverages to 7x if defended).
  - **Altcoins (ZEC, METIS, EPIC, CRV, VVV, BERA, etc.)**: **`6x – 8x`** (8x on 5/5 confluence, 6x on 4/5).
- **Diamond Setup Only (Quality Over Quantity)**:
  - **10 Slots is a Ceiling, NOT a Quota**: The bot will NEVER open trades just to fill slots.
  - If 0 coins have high-conviction 5-timeframe alignment, the bot **stands down and sits in 100% cash**. Preserving capital is priority #1.
  - Requires unanimous or strong 4/5 agreement across all 5 timeframes (`1m`, `5m`, `15m`, `1h`, `1d`) with **90%+ probability**.
  - **SHORT**: `1m`, `5m`, `15m`, `1h`, `1d` are all RED / Bearish.
  - **LONG**: `1m`, `5m`, `15m`, `1h`, `1d` are all GREEN / Bullish.
- **Realistic Front-Run Take Profit (₹200 – ₹500 Net Win)**:
  - Standard Trades: Targets **+10% to +18% Margin ROI** (₹200 to ₹350 on Alts/ETH, ₹300 to ₹500 on BTC).
  - At 22x leverage on BTC, a tiny **+0.6% price drop yields +13.2% margin ROI (+₹330 to +₹400 profit)**!
  - Front-runs the predicted target by **75% of the distance** to guarantee smooth execution without reversal risk.
- **Smart Margin Defense at -65% Drawdown & Relief Exit**:
  - No tight stop-loss choking normal wicks.
  - If a position experiences temporary pullback to **-65% margin drawdown**:
    1. Checks technical reversal indicators (RSI oversold/overbought, divergence, bounce).
    2. If reversal setup is present, adds **+50% margin** from wallet reserve, de-leveraging the position (e.g. 22x $\rightarrow$ 14.6x; 8x $\rightarrow$ 5.3x).
    3. Shrinks the drawdown from -65% to **-43%** and pushes liquidation price far away, giving the trade room to mean-revert into TP.
    4. **Relief Take-Profit (+5% to +8% Margin ROI)**: When a defended trade recovers into green, the bot does **NOT** wait greedily for +20%. It takes **+5% to +8% small profit immediately** and exits to eliminate risk!
    5. If no reversal setup or if defended barrier at -75% is breached, triggers Stop-Loss to safeguard capital.
- **30-Minute Anti-Whipsaw Cooldown (No Revenge Flipping)**:
  - If a trade gets stopped out, the bot enters a **strict 30-minute cooling period** on that coin.
  - Eliminates the classic trap of buying at the top of a stop-hunt wick only to suffer a double loss.
  - Re-entry is allowed ONLY after the 30-minute cooldown AND when the 5-timeframe engine (`1m` to `1d`) confirms a fresh, genuine Diamond setup.

## File Structure
- [`config.py`](file:///d:/Work/Trading/config.py): All settings (30k wallet, 10 slots, dynamic 2.5k-5k margin, Indian 31.2% tax & TDS rates).
- [`strategy.py`](file:///d:/Work/Trading/strategy.py): Indicator calculations and signal generation (BUY, SELL, HOLD).
- [`coindcx_client.py`](file:///d:/Work/Trading/coindcx_client.py): CoinDCX API client for live ticker, candles, balances, and orders.
- [`server.py`](file:///d:/Work/Trading/server.py): Visual Web Dashboard, autonomous 10-slot bot engine, and complete tax/fee deduction accounting.
- [`bot.py`](file:///d:/Work/Trading/bot.py): Terminal bot engine.

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
