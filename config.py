import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ==============================================================================
# BOT CONFIGURATION
# ==============================================================================

# SET TO True FOR PAPER/SIMULATED TRADING (SAFETY HALT)
DRY_RUN = True

# Trading pair: 'BTCINR', 'ETHINR', 'SOLINR', 'USDTINR'
# On CoinDCX candle API: 'I-BTC_INR', 'I-ETH_INR', 'I-SOL_INR'
SYMBOL = "BTCINR"
CANDLE_PAIR = "I-BTC_INR"

# Timeframe for candle data ('1m', '5m', '15m', '1h')
# 15m is recommended to avoid 1m noise and false wicks
TIMEFRAME = "15m"

# ==============================================================================
# RISK & PROFIT TARGET PROFILES
# ==============================================================================
STARTING_WALLET_INR = 30000.0
MAX_OPEN_POSITIONS = 10  # Up to 10 concurrent active positions simultaneously
INVESTMENT_PER_TRADE_INR = 3000.0  # Base ₹3,000 margin per trade (10 trades = ₹30,000)
SOLO_SNIPER_INVESTMENT_INR = 5000.0  # ₹5,000 for solo high-conviction setup in 24h
MULTI_CONFIRMED_INVESTMENT_INR = 2500.0  # ₹2,500 when broad wave of confirmed trades detected

RISK_PROFILES = {
    "USER_MIRROR": {
        "label": "User Mirror Sniper (100% Win Rate Replication)",
        "leverage_btc": (20, 22),
        "leverage_eth": (10, 12),
        "leverage_alts": (6, 8),
        "investment_inr": 3000.0,
        "min_confidence": 80,
        "stop_loss_pct": 0.0,
        "take_profit_pct": 1.25,
        "target_profit_min_inr": 200.0,
        "target_profit_max_inr": 500.0,
        "front_run_ratio": 0.75,
        "margin_defense_drawdown_pct": -65.0,
        "margin_defense_topup_ratio": 0.50,
        "hard_stop_loss_margin_pct": -75.0,
        "post_loss_cooldown_seconds": 1800,  # 30-min cooldown after a stop-loss to avoid double whipsaws
        "timeframe": "15m",
        "description": "Adaptive 6x-22x safe leverage, 5-timeframe confluence, 10-15% margin TP, and 30-min anti-whipsaw cooldown."
    },
    "SAFE": {
        "label": "Safe Mode (25-35% Monthly)",
        "leverage": 4,
        "investment_inr": 3000.0,
        "min_confidence": 90,
        "stop_loss_pct": 0.85,
        "take_profit_pct": 3.6,
        "timeframe": "15m",
        "description": "Ultra high selectivity. Strict capital protection (4.23:1 RRR, safe 4x leverage)."
    },
    "BALANCED": {
        "label": "Balanced Growth (40-60% Monthly)",
        "leverage": 4,
        "investment_inr": 3000.0,
        "min_confidence": 86,
        "stop_loss_pct": 0.90,
        "take_profit_pct": 3.8,
        "timeframe": "15m",
        "description": "Optimal risk-reward ratio (4.22:1 RRR, max selectivity)."
    },
    "AGGRESSIVE": {
        "label": "Aggressive Alpha (80-120%+ Monthly)",
        "leverage": 5,
        "investment_inr": 3000.0,
        "min_confidence": 82,
        "stop_loss_pct": 1.00,
        "take_profit_pct": 4.5,
        "timeframe": "15m",
        "description": "High frequency breakout scalper with 5x leverage."
    }
}

CURRENT_RISK_MODE = "USER_MIRROR"

# Multi-Timeframe Alignment Settings
CONFLUENCE_TIMEFRAMES = ["1m", "5m", "15m", "1h", "1d"]
MIN_TIMEFRAME_AGREEMENT = 3  # At least 3 of 5 timeframes must agree (3/5, 4/5, 5/5 qualify)

# Margin Defense & Drawdown Settings
MARGIN_DEFENSE_DRAWDOWN_PCT = -65.0  # At -65% drawdown, check reversal potential and add 50% margin
MARGIN_DEFENSE_TOPUP_RATIO = 0.50    # Top up 50% margin to de-leverage (e.g. 8x -> 5.3x) and absorb drawdown
HARD_STOP_LOSS_MARGIN_PCT = -75.0    # Final protection if defense fails or no reversal setup detected

# Target Profit Settings
TARGET_PROFIT_MIN_INR = 200.0        # ₹200 minimum profit per trade (bank early in altcoins/ETH)
TARGET_PROFIT_MAX_INR = 500.0        # ₹500 maximum profit per trade (ideal on BTC)
FRONT_RUN_RATIO = 0.75               # Front-run predicted target at 75% distance to guarantee fill

# Trade settings (Active defaults derived from CURRENT_RISK_MODE)
LEVERAGE = 8  # Dynamic fallback
SAME_COIN_COOLDOWN_SECONDS = 7200  # 2 hours cooldown before re-trading the same coin
POST_LOSS_COOLDOWN_SECONDS = 1800  # 30-min anti-whipsaw cooldown after a loss/stop-out

# Dynamic Adaptive Runner Settings (Anti-Choke 18% - 35% Target Extension & Profit Lock)
RUNNER_TRIGGER_PNL_PCT = 18.0  # When trade hits +18% PnL, shift TP to mega runner mode
RUNNER_EXTENDED_TP_PCT = 28.0  # Auto-shift TP up to +28% - +35%
RUNNER_LOCK_PROFIT_PCT = 11.0  # Lock at least +11% guaranteed net profit
RUNNER_TRAILING_BUFFER_PCT = 7.0 # Trail 7% below peak PnL for runners

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
COINDCX_API_KEY = os.getenv("COINDCX_API_KEY", "c590bc67e17800d3955ca0cf02b23b4c1a83d7360d7f1e6d")
COINDCX_API_SECRET = os.getenv("COINDCX_API_SECRET", "3f86d69988e76ed689087544d5264ff5cadc72af03d623e66effca8ae28c78a2")

# Realistic Exchange Fee & Government Tax Deduction Model
# - CoinDCX Futures: 0.05% taker fee on open + 0.05% taker fee on close (0.10% total)
# - Section 194S TDS: 1.0% on sell / exit payout
# - Section 115BBH VDA Flat Tax: 30% flat capital gains tax + 4% Health & Education cess = 31.2% total
FEE_MODE = os.getenv("FEE_MODE", "COINDCX")
FEE_TAKER_PCT = 0.05          # 0.05% exchange taker fee per leg
TDS_RATE_PCT = 1.0            # 1.0% Indian TDS under Section 194S
GOVT_TAX_RATE_PCT = 31.2      # 30% Flat VDA Tax + 4% Cess = 31.2% under Section 115BBH



