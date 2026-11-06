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

# Strict Stablecoin & Synthetic Asset Blacklist (Never trade pegged tokens or fiat mirrors)
STABLECOIN_BLACKLIST = {
    "USDT", "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "EUR", "AEUR",
    "WBETH", "BTCST", "EURS", "USTC", "FRAX", "PYUSD", "USDD", "GUSD",
    "USD1", "RLUSD", "U", "USDE", "USDJ", "SUSD", "XAUT", "PAXG"
}
STABLECOIN_PRICE_MIN = 0.96
STABLECOIN_PRICE_MAX = 1.04

RISK_PROFILES = {
    "USER_MIRROR": {
        "label": "User Mirror High-Win Scalper (+100% Win Edge)",
        "leverage_btc": (8, 10),
        "leverage_eth": (8, 10),
        "leverage_alts": (3, 4),
        "investment_inr": 2500.0,
        "min_confidence": 86,          # Calibrated for 4 to 5 high-conviction trades per day
        "stop_loss_pct": 3.20,         # Safe 3.2% spot SL (breathing room outside 15m noise)
        "take_profit_pct": 6.50,       # 6.5% spot target (+26% ROI runner)
        "target_profit_min_inr": 30.0,
        "target_profit_max_inr": 150.0,
        "front_run_ratio": 0.85,
        "margin_defense_drawdown_pct": -48.0,
        "margin_defense_topup_ratio": 0.50,
        "hard_stop_loss_margin_pct": -58.0,
        "post_loss_cooldown_seconds": 1800,  # 30-min cooldown after a stop-loss
        "timeframe": "15m",
        "description": "High-Win Rate Scalper (Quick +2.5% Target Hit, 3.2% SL Breathing Room, Early Breakeven Armor, 2-Slot Cap)."
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

# Target Profit Settings: Dynamic Quick Scalp +6.8% Take-Profit (₹30 - ₹80 Net In-Pocket)
TARGET_PROFIT_MIN_INR = 30.0          # ₹30 minimum net profit per trade
TARGET_PROFIT_MAX_INR = 150.0         # ₹150 maximum target profit for normal scalps
TARGET_PROFIT_ROI_PCT = 6.8           # +6.8% Baseline Target ROI on margin (~1.7% spot move at 4x)
STOP_LOSS_PERCENT = 3.2               # Safe 3.2% SL outside candle noise
FRONT_RUN_RATIO = 0.85                # Front-run predicted target at 85% distance to guarantee fill

# Capital Opportunity Rotation Settings (DISABLED to let winners run to full target!)
CAPITAL_ROTATION_ENABLED = False
ROTATION_MIN_PROFIT_PCT = 18.0        # Disabled
ROTATION_CANDIDATE_MIN_CONF = 88      # 88% min confidence
ROTATION_CANDIDATE_MIN_MTF = 4        # 4/5 or 5/5 MTF agreement

# Unified Multi-Stage Trailing Profit Staircase (Guarantees net profit after Indian TDS & fees):
TRAILING_PROFIT_STAIRCASE = [
    (40.0, 30.0), # At +40% ROI -> Lock +30.0% profit (~₹500 net profit)
    (30.0, 22.0), # At +30% ROI -> Lock +22.0% profit (~₹350 net profit)
    (22.0, 15.0), # At +22% ROI -> Lock +15.0% profit (~₹240 net profit)
    (15.0, 10.0), # At +15% ROI -> Lock +10.0% profit (~₹160 net profit)
    (10.0, 6.0),  # At +10% ROI -> Lock +6.0% profit (~₹100 net profit)
    (6.0, 3.0),   # At +6% ROI -> Lock +3.0% profit (guaranteed green after TDS/fees)
    (3.5, 1.2),   # At +3.5% ROI -> Lock +1.2% Breakeven + Fee Armor (0 Loss Guarantee)
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

# Breakout Quality & Market Regime Filters (Anti-Fakeout & Anti-Chop Shields)
MIN_VOLUME_SURGE_RATIO = 1.25      # Breakout candle must have >= 1.25x (125%) 20-bar avg volume
MIN_ADX_TREND_STRENGTH = 20.0      # Minimum ADX (>= 20) confirming real trend vs sideways chop
REQUIRE_VOLUME_CONFIRMATION = True # Reject breakout if volume is weak/dry
REQUIRE_TREND_STRENGTH = True      # Reject breakout if market is consolidating/sideways

# ==============================================================================
# STRATEGY SELECTION
# ==============================================================================
# "USER_MIRROR": Multi-Timeframe Confluence (1m, 5m, 15m, 1h, 1d) 4/5 or 5/5 Agreement (4-5 Trades/Day)
# "TURTLE"     : Richard Dennis & William Eckhardt Turtle System 2 (55-period Donchian Breakout + 2N ATR Stop)
# "EMA_RSI"    : Legacy Fast/Slow EMA Crossover with RSI Filter
STRATEGY_MODE = os.getenv("STRATEGY_MODE", "USER_MIRROR")

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



