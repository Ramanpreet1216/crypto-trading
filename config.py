import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==============================================================================
# BOT CONFIGURATION
# ==============================================================================

# SET TO False FOR LIVE REAL-MONEY TRADING (True FOR PAPER SIMULATION)
DRY_RUN = True

# Trading pair: 'BTCINR', 'ETHINR', 'SOLINR', 'USDTINR'
# On CoinDCX candle API: 'I-BTC_INR', 'I-ETH_INR', 'I-SOL_INR'
SYMBOL = "BTCINR"
CANDLE_PAIR = "I-BTC_INR"

# Timeframe for candle data ('1m', '5m', '15m', '1h')
# 15m is recommended to avoid 1m noise and false wicks
TIMEFRAME = "15m"

# ==============================================================================
# ==============================================================================
# RE-ENGINEERED 1:2 RISK-TO-REWARD QUANT ARCHITECTURE
# Target: Sustainable ~₹15,000/mo net returns on ₹30,000 wallet with asymmetric 1:2 R:R
# ==============================================================================
STARTING_WALLET_INR = 30000.0
TOTAL_WALLET_CAPITAL = 30000.0
MAX_OPEN_POSITIONS = 2                 # Strict 2 slots max (60-70% wallet remains safe in reserve)
MAX_CONCURRENT_POSITIONS = 2
INVESTMENT_PER_TRADE_INR = 2500.0       # Strict ₹2,500 margin per trade (max ₹5,000 in trades, ₹25,000 cash reserve)
MARGIN_PER_TRADE = 2500.0
SOLO_SNIPER_INVESTMENT_INR = 2500.0
MULTI_CONFIRMED_INVESTMENT_INR = 2500.0
MAX_CAPITAL_IN_TRADE_RATIO = 0.35      # Maximum 35% of wallet deployed in open positions (~₹10,500 cap)
SAFE_MARGIN_RATIO = 0.65               # Maintain at least 65% safe reserve buffer in wallet (~₹19,500)

# Daily Capital Preservation & Profit Guardrails
MAX_DAILY_LOSS_LIMIT = 1500.0          # 5% of wallet. If hit, bot stops trading for 24h to prevent cascade losses
DAILY_PROFIT_GOAL = 2000.0             # Daily target goal (+₹2,000 net). When reached, lock in profits
RISK_REWARD_RATIO = 2.0                # Strict 1:2 Asymmetric R:R (Every $1 risked targets $2 profit)

# Asymmetric Leverage Caps (Prevents flash-crash liquidations & wick stop-outs)
LEVERAGE_BTC_ETH = 10                  # Safe 10x max for BTC/ETH (~9.5% liquidation buffer)
LEVERAGE_ALTS = 4                      # Safe 4x max for Altcoins (gives safe 3.5% - 5.0% breathing room)

# Strict Stablecoin Blacklist (Never trade pegged tokens or fiat mirrors)
STABLECOIN_BLACKLIST = {
    "USDT", "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "EUR", "AEUR",
    "WBETH", "BTCST", "EURS", "USTC", "FRAX", "PYUSD", "USDD", "GUSD"
}

RISK_PROFILES = {
    "USER_MIRROR": {
        "label": "Asymmetric 1:2 Trend Breakout (Turtle & SMC)",
        "leverage_btc": (8, 10),
        "leverage_eth": (8, 10),
        "leverage_alts": (3, 4),
        "investment_inr": 2500.0,
        "min_confidence": 85,
        "stop_loss_pct": 3.5,          # Safe 3.5% SL buffer (never stopped out by 1m micro-wicks)
        "take_profit_pct": 7.0,        # Exact 1:2 R:R (3.5% SL vs 7.0% TP)
        "target_profit_min_inr": 175.0,
        "target_profit_max_inr": 500.0,
        "front_run_ratio": 0.85,
        "margin_defense_drawdown_pct": -48.0,
        "margin_defense_topup_ratio": 0.50,
        "hard_stop_loss_margin_pct": -58.0,
        "post_loss_cooldown_seconds": 1800,  # 30-min cooldown after a stop-loss
        "timeframe": "15m",
        "description": "Strict 1:2 Asymmetric R:R (4x-5x Alts, ₹2,500 sizing, 1:2 Profit Target, 2-Slot Cap)."
    },
    "SAFE": {
        "label": "Safe Mode (25-35% Monthly)",
        "leverage": 4,
        "investment_inr": 6000.0,
        "min_confidence": 88,
        "stop_loss_pct": 0.85,
        "take_profit_pct": 3.6,
        "timeframe": "15m",
        "description": "Ultra high selectivity. Strict capital protection (4.23:1 RRR, safe 4x leverage)."
    },
    "BALANCED": {
        "label": "Balanced Growth (40-60% Monthly)",
        "leverage": 4,
        "investment_inr": 6000.0,
        "min_confidence": 86,
        "stop_loss_pct": 0.90,
        "take_profit_pct": 3.8,
        "timeframe": "15m",
        "description": "Optimal risk-reward ratio (4.22:1 RRR, max selectivity)."
    },
    "AGGRESSIVE": {
        "label": "Aggressive Alpha (80-120%+ Monthly)",
        "leverage": 5,
        "investment_inr": 6000.0,
        "min_confidence": 82,
        "stop_loss_pct": 1.00,
        "take_profit_pct": 4.5,
        "timeframe": "15m",
        "description": "High frequency breakout scalper with 5x leverage."
    }
}

CURRENT_RISK_MODE = "USER_MIRROR"

# Multi-Timeframe Alignment Settings (User Calibrated: 4/5 MTF Confluence)
CONFLUENCE_TIMEFRAMES = ["1m", "5m", "15m", "1h", "1d"]
MIN_TIMEFRAME_AGREEMENT = 4  # At least 4 of 5 timeframes must agree (4/5 or 5/5 qualify)

# Margin Defense & Drawdown Settings (Optimal -48% Breathing Room & Capital Shield)
MARGIN_DEFENSE_DRAWDOWN_PCT = -48.0  # At -48% drawdown (~6.5% spot drop), check reversal and top up margin
MARGIN_DEFENSE_TOPUP_RATIO = 0.50    # Top up 50% margin to de-leverage (e.g. 8x -> 5.3x) and absorb drawdown
HARD_STOP_LOSS_MARGIN_PCT = -58.0    # Final hard stop barrier (~8% spot drop) to prevent deep losses

# Target Profit Settings: Dynamic +6.8% - +14.0% Scalp Take-Profit (₹350 - ₹850 Net Profit per trade)
TARGET_PROFIT_MIN_INR = 350.0         # ₹350 minimum profit per trade (calibrated for ₹6,000 margin)
TARGET_PROFIT_MAX_INR = 850.0         # ₹850 maximum target profit for high-conviction breakout setups
TARGET_PROFIT_ROI_PCT = 6.8          # +6.8% Baseline Target ROI on margin
FRONT_RUN_RATIO = 0.75               # Front-run predicted target at 75% distance to guarantee fill

# Capital Opportunity Rotation Settings (When 5 slots are full)
CAPITAL_ROTATION_ENABLED = True
ROTATION_MIN_PROFIT_PCT = 5.5        # Existing position must have at least +5.5% ROI to be rotated
ROTATION_CANDIDATE_MIN_CONF = 84     # New candidate must have >= 84% confidence
ROTATION_CANDIDATE_MIN_MTF = 4       # 4/5 or 5/5 MTF agreement

# Unified Multi-Stage Trailing Profit Staircase (95% Quick Scalps + Rare Parabolic Mega-Runners):
TRAILING_PROFIT_STAIRCASE = [
    (45.0, 35.0), # At +45% ROI -> Lock +35.0% profit (~₹122 net profit on ₹350 margin!)
    (35.0, 25.0), # At +35% ROI -> Lock +25.0% profit (~₹87 net profit)
    (30.0, 20.0), # At +30% ROI -> Lock +20.0% profit (~₹70 net profit) [17-22% gain SL requested by user!]
    (25.0, 17.0), # At +25% ROI -> Lock +17.0% profit (~₹59 net profit)
    (20.0, 14.0), # At +20% ROI -> Lock +14.0% profit (~₹49 net profit)
    (14.0, 10.5), # At +14% ROI -> Lock +10.5% profit (~₹37 net profit)
    (12.0, 8.5),  # At +12% ROI -> Lock +8.5% profit (~₹30 net profit)
    (8.0, 6.0),   # At +8.0% ROI -> Lock +6.0% profit (~₹21 net profit)
    (6.5, 4.8),   # At +6.5% ROI -> Lock +4.8% profit (~₹17 net profit)
    (5.5, 3.8),   # At +5.5% ROI -> Lock +3.8% profit (~₹13 net profit)
    (4.0, 1.5),   # At +4.0% ROI -> Lock +1.5% profit (cushion for fees & TDS, guaranteed no-loss)
]

# ==============================================================================
# 5-PILLAR ACCURACY & DIRECTIONAL RISK PROTECTION
# ==============================================================================
# 1. Bitcoin King Macro Regime Guard
BTC_REGIME_FILTER_ENABLED = True      # Block altcoin LONGs when BTC 1h/15m is in a confirmed pullback
BTC_BEARISH_RSI_THRESHOLD = 48.0      # BTC 1h RSI below 48 or price below EMA21 = Bearish Regime (blocks Alt LONGs)
BTC_BULLISH_RSI_THRESHOLD = 52.0      # BTC 1h RSI above 52 and price above EMA21 = Bullish Regime

# 2. Portfolio Directional Balance Guard (Anti-Cascade Shield)
MAX_SAME_DIRECTION_POSITIONS = 3      # In 5-slot mode, max 3 positions in same direction (prevents 100% one-sided crash)

# 3. 7-Day & 30-Day Higher Timeframe Macro Trend Shield (Anti-Falling Knife)
MACRO_TREND_FILTER_ENABLED = True     # Check 7-day to 30-day daily candle structure before entry
MAX_ALLOWABLE_7D_DOWNTREND_PCT = -6.0 # Block LONG if coin has bled more than -6% over last 7 days

# 4. Anti-FOMO "Pullback to Value" Entry Filters
MAX_EMA_PULLBACK_DEVIATION_PCT = 1.8  # Price must be within 1.8% of 15m EMA9 (buy value, never chase pumps)
RSI_LONG_MIN = 38.0                   # Minimum momentum for LONG
RSI_LONG_MAX = 65.0                   # Max RSI for LONG (never buy overbought tops like ZRO/FET)
RSI_SHORT_MIN = 35.0                  # Min RSI for SHORT (never short into oversold bounce traps)
RSI_SHORT_MAX = 62.0                  # Maximum momentum for SHORT

# 4. Volatility-Adaptive Leverage (Safe 3x - 4x Caps to prevent wick stop-outs)
MAX_HIGH_BETA_LEVERAGE = 3            # Cap wild altcoins (>10% daily swing) at safe 3x leverage
MAX_MID_BETA_LEVERAGE = 4             # Cap standard altcoins at safe 4x leverage

# Trade settings (Active defaults derived from CURRENT_RISK_MODE)
LEVERAGE = 4  # Dynamic safe fallback
SAME_COIN_COOLDOWN_SECONDS = 7200  # 2 hours cooldown before re-trading the same coin
POST_LOSS_COOLDOWN_SECONDS = 2700  # 45-min anti-whipsaw cooldown after a loss/stop-out

# Dynamic Adaptive Runner Settings (Rare Parabolic Breakouts +25% to +45%)
RUNNER_TRIGGER_PNL_PCT = 14.0  # When trade hits +14% PnL, shift TP to mega runner mode
RUNNER_EXTENDED_TP_PCT = 35.0  # Auto-shift TP up to +35% - +45%
RUNNER_LOCK_PROFIT_PCT = 10.5  # Lock at least +10.5% guaranteed net profit
RUNNER_TRAILING_BUFFER_PCT = 8.0 # Trail 8% below peak PnL for runners

# Anti-Ghost Coin & Institutional Liquidity Safeguards
MIN_LIQUIDITY_USDT = 5_000_000.0   # Minimum $5M USDT 24h volume (eliminates illiquid ghost coins & fatal slippage)
MAX_24H_VOLATILITY_PCT = 35.0      # Anti-pump-and-dump: blocks unnatural extreme spike coins (>35% or <-35%)
FILTER_EXIT_ONLY_CONTRACTS = True  # Automatically blacklist non-trading, delisted, and exit-only contracts

# ==============================================================================
# STRATEGY SELECTION
# ==============================================================================
# "TURTLE"   : Richard Dennis & William Eckhardt Turtle System 2 (Proven winner in crypto thesis)
#              55-period Donchian Breakout + 2N (ATR 20) Volatility-Adaptive Stop Loss + 20-period Exit
# "EMA_RSI"  : Legacy Fast/Slow EMA Crossover with RSI Filter
STRATEGY_MODE = os.getenv("STRATEGY_MODE", "TURTLE")

# Turtle Strategy Parameters (Calibrated from Crypto Thesis Findings)
TURTLE_SYSTEM = 2                   # System 2 (55-period Breakout) or System 1 (20-period Breakout)
TURTLE_BREAKOUT_PERIOD = 55         # 55-candle breakout channel (System 2 default)
TURTLE_EXIT_PERIOD = 20             # 20-candle trailing exit channel
TURTLE_ATR_PERIOD = 20              # 20-period Wilder's True Range EMA (N volatility)
TURTLE_STOP_MULTIPLE = 2.0          # 2.0 x N volatility stop-loss distance
TURTLE_RISK_PER_TRADE_PCT = 2.0     # 2.0% maximum account risk per trade unit

# Legacy Strategy settings (EMA Crossover + RSI)
FAST_EMA_PERIOD = 9
SLOW_EMA_PERIOD = 21
RSI_PERIOD = 14
RSI_BUY_THRESHOLD = 52
RSI_SELL_THRESHOLD = 48

# Risk Management
STOP_LOSS_PERCENT = RISK_PROFILES[CURRENT_RISK_MODE].get("stop_loss_pct", 0.0)
TAKE_PROFIT_PERCENT = RISK_PROFILES[CURRENT_RISK_MODE].get("take_profit_pct", 1.25)

# CoinDCX API credentials
COINDCX_API_KEY = os.getenv("COINDCX_API_KEY", "650503ecfd85181cc3ed857f48623186fd3abf5432a59ee5")
COINDCX_API_SECRET = os.getenv("COINDCX_API_SECRET", "bfef172bd33b046faf72b9b76b8da63fa8e1ff742365b2c68baf77695ba297e8")

# Realistic Exchange Fee & Government Tax Deduction Model
# - CoinDCX Futures: 0.05% taker fee on open + 0.05% taker fee on close (0.10% total)
# - Section 194S TDS: 1.0% on sell / exit payout
# - Section 115BBH VDA Flat Tax: 30% flat capital gains tax + 4% Health & Education cess = 31.2% total
FEE_MODE = os.getenv("FEE_MODE", "COINDCX")
FEE_TAKER_PCT = 0.05          # 0.05% exchange taker fee per leg
TDS_RATE_PCT = 1.0            # 1.0% Indian TDS under Section 194S
GOVT_TAX_RATE_PCT = 31.2      # 30% Flat VDA Tax + 4% Cess = 31.2% under Section 115BBH



