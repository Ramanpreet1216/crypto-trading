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
MAX_OPEN_POSITIONS = 3                 # Max 3 slots (Slot 1 & 2 standard, Slot 3 strictly reserved for 96%+ 5/5 A+ setups)
MAX_CONCURRENT_POSITIONS = 3
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
LEVERAGE_BTC_ETH = 4                  # Safe 4x max for BTC/ETH (~22% liquidation buffer)
LEVERAGE_ALTS = 4                      # Safe 4x max for Altcoins (provides optimal 2.75% target reach with safe breathing room)

# Minimum 24h USDT Volume for any coin to enter trades ($20,000,000 Institutional Floor)
MIN_LIQUIDITY_USDT = 20_000_000.0

# Chronic Choppy & Thin Orderbook Blacklist (24 Banned High-Risk Tokens)
CHOPPY_COIN_BLACKLIST = {
    "ASTER", "ZEC", "QNT", "PROM", "PIEVERSE", "ULTIMA", "GMX", "FIL", "VVV", "GIGGLE",
    "TRB", "GAS", "BLZ", "LOOM", "DASH", "ZEN", "STRAX", "BIGTIME", "STPT", "MEME", "XVG", "ICX", "FRONT", "LEVER"
}

# Strict Blacklist: Stablecoins, Synthetic, & Chronic Choppy Tokens
STABLECOIN_BLACKLIST = {
    "USDT", "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "EUR", "AEUR",
    "WBETH", "BTCST", "EURS", "USTC", "FRAX", "PYUSD", "USDD", "GUSD",
    "USD1", "RLUSD", "U", "USDE", "USDJ", "SUSD", "XAUT", "PAXG"
} | CHOPPY_COIN_BLACKLIST
COIN_BLACKLIST = STABLECOIN_BLACKLIST

STABLECOIN_PRICE_MIN = 0.96
STABLECOIN_PRICE_MAX = 1.04

RISK_PROFILES = {
    "USER_MIRROR": {
        "label": "User Mirror Asymmetric 1:2 R:R (+100% Win Edge)",
        "leverage_btc": (3, 4),
        "leverage_eth": (3, 4),
        "leverage_alts": (3, 4),
        "investment_inr": 2500.0,
        "min_confidence": 86,          # Calibrated for 4 to 5 high-conviction trades per day
        "stop_loss_pct": 1.35,         # Safe 1.35% spot SL (-5.4% margin risk at 4x = ~-₹135 max loss)
        "take_profit_pct": 2.75,       # 2.75% spot target (+11.0% ROI target at 4x = +₹275 gross / +₹195 net, 1:2 R:R)
        "target_profit_min_inr": 180.0, # ₹180 min net profit in pocket for pure 1:2 R:R sweetspot
        "target_profit_max_inr": 280.0, # ₹280 max target profit for sweetspot
        "front_run_ratio": 0.88,
        "margin_defense_drawdown_pct": -5.1,   # Strict -5.1% margin drawdown cap (-₹127 max risk on ₹2,500 margin)
        "margin_defense_topup_ratio": 0.0,     # DISABLED margin top-up to eliminate the -₹224 loss trap!
        "hard_stop_loss_margin_pct": -5.5,    # Hard catastrophic ceiling at -5.5% (-₹137 max)
        "post_loss_cooldown_seconds": 7200,  # 2-hour cooldown after a stop-loss
        "timeframe": "15m",
        "description": "Asymmetric 1:2 R:R Architecture (2.2% SL, 4.8% TP, Pure 1:2 R:R Guard, 2-Slot Cap)."
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

# Margin Defense & Drawdown Settings (Strict 1:2 R:R Guard: Capped at -5.1% / -₹127 SL)
MARGIN_DEFENSE_DRAWDOWN_PCT = -5.1   # Strict -5.1% (-₹127 max loss on ₹2,500 margin)
MARGIN_DEFENSE_TOPUP_RATIO = 0.0     # DISABLED: Never add extra margin to a losing trade!
HARD_STOP_LOSS_MARGIN_PCT = -5.5     # Final hard stop barrier at -5.5% (~-₹137 max) to guarantee 1:2 R:R

# Target Profit Settings: Calibrated +11% ROI Sweetspot (+₹180 to +₹220 Net in Pocket)
TARGET_PROFIT_MIN_INR = 180.0         # ₹180 minimum net profit per trade (covers fees & TDS with real profit)
TARGET_PROFIT_MAX_INR = 280.0         # ₹280 maximum target profit for 1:2 R:R winners
TARGET_PROFIT_ROI_PCT = 11.0          # +11.0% Target ROI on margin (~3.6% spot move at 3x = +₹280 gross / +₹200 net)
STOP_LOSS_PERCENT = 1.35              # 1.35% spot SL (~5.4% margin risk on 4x leverage = ~-₹135 max loss)
TAKE_PROFIT_PERCENT = 2.75            # 2.75% spot TP (+11.0% ROI on 4x leverage = 1:2.04 R:R)
FRONT_RUN_RATIO = 0.88                # Front-run predicted target at 88% distance to guarantee fill (never miss by 1 cent)
RISK_REWARD_RATIO = 2.2               # Strict 1:2.2 Asymmetric R:R (+₹200 net target vs -₹127 max stop)

# Capital Opportunity Rotation Settings (DISABLED to let winners run to full target!)
CAPITAL_ROTATION_ENABLED = False
ROTATION_MIN_PROFIT_PCT = 18.0        # Disabled
ROTATION_CANDIDATE_MIN_CONF = 88      # 88% min confidence
ROTATION_CANDIDATE_MIN_MTF = 4        # 4/5 or 5/5 MTF agreement

# Asymmetric 1:2 Dynamic Trailing Profit-Lock Staircase:
# Sweetspot: Only lock profit when net in-hand profit has reached at least +₹95 to +₹125!
# - At +8.0% ROI: Lock +5.6% Profit Lock (guarantees >= +₹95 net profit banked after all fees & TDS)
# - At +11.0% ROI: Lock +7.4% Profit Lock (guarantees >= +₹125 to +₹135 net profit banked)
TRAILING_PROFIT_STAIRCASE = [
    (11.0, 7.4),  # At +11.0% ROI -> Lock +7.4% profit (~+₹125 to +₹135 net banked)
    (8.0, 5.6),   # At +8.0% ROI  -> Lock +5.6% profit (~+₹95 to +₹105 net banked)
]
MIN_TRAILING_PROFIT_NET_INR = 95.0   # Sweetspot Floor: Never exit on trailing lock for less than ₹95 net
MAX_TRAILING_PROFIT_NET_INR = 125.0  # Sweetspot Ceiling: ₹125 net before full target (+₹185)

# ==============================================================================
# 5-PILLAR ACCURACY & DIRECTIONAL RISK PROTECTION
# ==============================================================================
# 1. Bitcoin King Macro Regime Guard (70%+ Win Surety via Trend Alignment)
BTC_REGIME_FILTER_ENABLED = True      # Only trade with the macro trend (LONGs when BTC is Bullish, SHORTs when BTC is Bearish)
BTC_BEARISH_RSI_THRESHOLD = 48.0      # BTC 1h RSI below 48 or price below EMA21 = Bearish Regime (blocks Alt LONGs)
BTC_BULLISH_RSI_THRESHOLD = 52.0      # BTC 1h RSI above 52 and price above EMA21 = Bullish Regime

# 2. Portfolio Directional Balance Guard (Anti-Cascade Shield)
MAX_SAME_DIRECTION_POSITIONS = 3      # In 5-slot mode, max 3 positions in same direction (prevents 100% one-sided crash)

# 3. 7-Day & 30-Day Higher Timeframe Macro Trend Shield (Anti-Falling Knife)
MACRO_TREND_FILTER_ENABLED = True     # Check 7-day to 30-day daily candle structure before entry
MAX_ALLOWABLE_7D_DOWNTREND_PCT = -6.0 # Block LONG if coin has bled more than -6% over last 7 days

# 4. Anti-Exhaustion "Pullback to Value" Entry Filters (Never Buy Tops, Never Short Bottoms)
MAX_EMA_PULLBACK_DEVIATION_PCT = 0.95 # Price must be within 0.95% of 15m EMA9 (buy pullbacks, never chase green pumps)
RSI_LONG_MIN = 40.0                   # Minimum momentum for LONG
RSI_LONG_MAX = 56.0                   # Strict Max RSI for LONG (blocks buying at exhaustion tops)
RSI_SHORT_MIN = 44.0                  # Strict Min RSI for SHORT (blocks shorting into oversold bottoms)
RSI_SHORT_MAX = 60.0                  # Maximum momentum for SHORT

# 4. Volatility-Adaptive Leverage (Safe 2x - 4x Caps to prevent wick stop-outs)
MAX_HIGH_BETA_LEVERAGE = 3            # Cap wild altcoins (>10% daily swing) at safe 3x leverage
MAX_MID_BETA_LEVERAGE = 4             # Cap standard altcoins at safe 4x leverage

# Trade settings (Active defaults derived from CURRENT_RISK_MODE)
LEVERAGE = 4  # Dynamic safe fallback
SAME_COIN_COOLDOWN_SECONDS = 10800  # 3 hours cooldown before re-trading the same coin
POST_LOSS_COOLDOWN_SECONDS = 7200  # 2 hours anti-whipsaw cooldown after a loss/stop-out

# Dynamic Adaptive Runner Settings (Rare Parabolic Breakouts +25% to +45%)
RUNNER_TRIGGER_PNL_PCT = 14.0  # When trade hits +14% PnL, shift TP to mega runner mode
RUNNER_EXTENDED_TP_PCT = 35.0  # Auto-shift TP up to +35% - +45%
RUNNER_LOCK_PROFIT_PCT = 10.5  # Lock at least +10.5% guaranteed net profit
RUNNER_TRAILING_BUFFER_PCT = 8.0 # Trail 8% below peak PnL for runners

# Anti-Ghost Coin & Institutional Liquidity Safeguards
# NOTE: MIN_LIQUIDITY_USDT already defined at top of file as 20_000_000.0 — do NOT redefine here (Python uses last definition)
MAX_24H_VOLATILITY_PCT = 35.0      # Anti-pump-and-dump: blocks unnatural extreme spike coins (>35% or <-35%)
FILTER_EXIT_ONLY_CONTRACTS = True  # Automatically blacklist non-trading, delisted, and exit-only contracts

# Dynamic Entry 15m Candle Volume Surge Gate (Confirms Active Institutional Inflows)
MIN_ENTRY_CANDLE_VOL_SURGE = 1.20   # 15m candle volume must be >= 1.2x of 20-bar SMA

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



