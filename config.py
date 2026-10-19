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
DRY_RUN = True  # Paper simulation mode by default for safety

# Trading pair: 'BTCINR', 'ETHINR', 'SOLINR', 'USDTINR'
# On CoinDCX candle API: 'I-BTC_INR', 'I-ETH_INR', 'I-SOL_INR'
SYMBOL = "BTCINR"
CANDLE_PAIR = "I-BTC_INR"

# Timeframe for candle data ('1m', '5m', '15m', '1h')
# 15m is recommended to avoid 1m noise and false wicks
TIMEFRAME = "15m"

# ==============================================================================
# ==============================================================================
# RISK & PROFIT TARGET PROFILES
# ==============================================================================
STARTING_WALLET_INR = 30000.0
MAX_OPEN_POSITIONS = 5
ALLOWED_COINS = ['BTC', 'ETH', 'SOL', 'NEAR', 'SUI', 'DOGE', 'AVAX', 'LINK', 'XRP', 'ADA', 'APT']  # Up to 5 concurrent active positions maximum
INVESTMENT_PER_TRADE_INR = 6000.0
MAX_LOSS_PER_TRADE_INR = 950.0        # -14.0% margin ROI stop-loss cut (gives 2.0% spot room on 7x)
TARGET_PROFIT_PER_TRADE_INR = 1320.0  # +22.0% margin ROI target profit (+₹900-₹1,000 net in pocket)
HARD_STOP_LOSS_MARGIN_PCT = -14.0     # Disciplined -14% ROI stop-loss (healthy 2% breathing room)
SOLO_SNIPER_INVESTMENT_INR = 6000.0   # ₹6,000 per trade
MULTI_CONFIRMED_INVESTMENT_INR = 6000.0  # ₹6,000 per trade
MAX_CAPITAL_IN_TRADE_RATIO = 1.0      # Allow all 5 slots * ₹6,000 = ₹30,000 deployed
SAFE_MARGIN_RATIO = 0.0               # No artificial reservation blocking trade slots

RISK_PROFILES = {
    "USER_MIRROR": {
        "label": "User Mirror Sniper (High-Velocity 4/5 MTF Scalper)",
        "leverage_btc": (20, 22),
        "leverage_eth": (10, 12),
        "leverage_alts": (6, 8),
        "investment_inr": 6000.0,
        "min_confidence": 84,
        "stop_loss_pct": 0.0,
        "take_profit_pct": 2.80,
        "target_profit_min_inr": 900.0,
        "target_profit_max_inr": 1400.0,
        "front_run_ratio": 0.75,
        "margin_defense_drawdown_pct": -48.0,
        "margin_defense_topup_ratio": 0.50,
        "hard_stop_loss_margin_pct": -14.0,
        "post_loss_cooldown_seconds": 1800,  # 30-min cooldown after a stop-loss
        "timeframe": "15m",
        "description": "Disciplined Scalper (6x-8x Alts, ₹6,000 sizing, +22% Dynamic TP, -14% SL Breathing Room, 4/5 MTF Alpha Rotation)."
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

# Margin Defense & Drawdown Settings
MARGIN_DEFENSE_DRAWDOWN_PCT = -48.0  # At -48% drawdown (~6.5% spot drop), check reversal and top up margin
MARGIN_DEFENSE_TOPUP_RATIO = 0.50    # Top up 50% margin to de-leverage (e.g. 8x -> 5.3x) and absorb drawdown
HARD_STOP_LOSS_MARGIN_PCT = -14.0    # Disciplined -14.0% margin ROI stop-loss (-₹950 max cut on ₹6,000 margin)

# Target Profit Settings: Dynamic +18% - +25% Take-Profit (+₹900 - +₹1,400 Net Profit per trade on ₹6,000 margin)
TARGET_PROFIT_MIN_INR = 900.0        # Minimum net profit target per trade (calibrated for ₹6,000 margin)
TARGET_PROFIT_MAX_INR = 1400.0       # Maximum target profit for high-conviction breakout setups
TARGET_PROFIT_ROI_PCT = 22.0         # +22.0% Baseline Target ROI on margin (Healthy positive RRR)
FRONT_RUN_RATIO = 0.75               # Front-run predicted target at 75% distance to guarantee fill

# Capital Opportunity Rotation Settings (When 5 slots are full)
CAPITAL_ROTATION_ENABLED = True
ROTATION_MIN_PROFIT_PCT = 8.0        # Existing position must have at least +8.0% ROI to be rotated
ROTATION_CANDIDATE_MIN_CONF = 84     # New candidate must have >= 84% confidence
ROTATION_CANDIDATE_MIN_MTF = 4       # 4/5 or 5/5 MTF agreement

# Unified Multi-Stage Trailing Profit Staircase (Guaranteed Positive Net Yield after all Fees & TDS):
TRAILING_PROFIT_STAIRCASE = [
    (45.0, 35.0), # At +45% ROI -> Lock +35.0% profit
    (35.0, 26.0), # At +35% ROI -> Lock +26.0% profit
    (30.0, 22.0), # At +30% ROI -> Lock +22.0% profit
    (25.0, 18.0), # At +25% ROI -> Lock +18.0% profit
    (20.0, 14.0), # At +20% ROI -> Lock +14.0% profit (+₹840 gross -> +₹550 net)
    (15.0, 10.0), # At +15% ROI -> Lock +10.0% profit (+₹600 gross -> +₹380 net)
    (10.0, 6.0),  # At +10% ROI -> Lock +6.0% profit (+₹360 gross -> +₹210 net, guaranteed profit after fees & TDS!)
]

# ==============================================================================
# 5-PILLAR ACCURACY & DIRECTIONAL RISK PROTECTION
# ==============================================================================
# 1. Bitcoin King Macro Regime Guard
BTC_REGIME_FILTER_ENABLED = True      # Block altcoin LONGs when BTC 1h/15m is in a confirmed pullback
BTC_BEARISH_RSI_THRESHOLD = 48.0      # BTC 1h RSI below 48 or price below EMA21 = Bearish Regime (blocks Alt LONGs)
BTC_BULLISH_RSI_THRESHOLD = 52.0      # BTC 1h RSI above 52 and price above EMA21 = Bullish Regime

# 2. Portfolio Directional Balance Guard (Anti-Cascade Shield)
MAX_SAME_DIRECTION_POSITIONS = 4      # Allow up to 4 positions in the dominant trend direction (rides multi-coin downtrends/uptrends)

# 3. 7-Day & 30-Day Higher Timeframe Macro Trend Shield (Anti-Falling Knife)
MACRO_TREND_FILTER_ENABLED = True     # Check 7-day to 30-day daily candle structure before entry
MAX_ALLOWABLE_7D_DOWNTREND_PCT = -16.0 # Block LONG if coin has bled more than -16% over last 7 days (prevents real falling knives like -25% dumps)

# 4. Anti-FOMO "Pullback to Value" Entry Filters
MAX_EMA_PULLBACK_DEVIATION_PCT = 1.8  # Price must be within 1.8% of 15m EMA9 (buy value, never chase pumps)
RSI_LONG_MIN = 38.0                   # Minimum momentum for LONG
RSI_LONG_MAX = 65.0                   # Max RSI for LONG (never buy overbought tops like ZRO/FET)
RSI_SHORT_MIN = 35.0                  # Min RSI for SHORT (never short into oversold bounce traps)
RSI_SHORT_MAX = 62.0                  # Maximum momentum for SHORT

# 4. Volatility-Adaptive Leverage (ATR / Beta Scaling)
MAX_HIGH_BETA_LEVERAGE = 5            # Cap wild altcoins (>10% daily swing) at 5x leverage
MAX_MID_BETA_LEVERAGE = 7             # Cap standard altcoins at 7x leverage

# Trade settings (Active defaults derived from CURRENT_RISK_MODE)
LEVERAGE = 8  # Dynamic fallback
SAME_COIN_COOLDOWN_SECONDS = 7200  # 2 hours cooldown before re-trading the same coin
POST_LOSS_COOLDOWN_SECONDS = 1800  # 30-min anti-whipsaw cooldown after a loss/stop-out

# Dynamic Adaptive Runner Settings (Rare Parabolic Breakouts +25% to +45%)
RUNNER_TRIGGER_PNL_PCT = 14.0  # When trade hits +14% PnL, shift TP to mega runner mode
RUNNER_EXTENDED_TP_PCT = 35.0  # Auto-shift TP up to +35% - +45%
RUNNER_LOCK_PROFIT_PCT = 10.5  # Lock at least +10.5% guaranteed net profit
RUNNER_TRAILING_BUFFER_PCT = 8.0 # Trail 8% below peak PnL for runners

# Anti-Ghost Coin & Institutional Liquidity Safeguards
MIN_LIQUIDITY_USDT = 3_000_000.0   # Minimum $3M USDT 24h volume (eliminates illiquid ghost coins & fatal slippage)
MAX_24H_VOLATILITY_PCT = 35.0      # Anti-pump-and-dump: blocks unnatural extreme spike coins (>35% or <-35%)
FILTER_EXIT_ONLY_CONTRACTS = True  # Automatically blacklist non-trading, delisted, and exit-only contracts

# Strategy settings (EMA Crossover + RSI)
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



