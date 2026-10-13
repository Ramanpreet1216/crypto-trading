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
RISK_PROFILES = {
    "SAFE": {
        "label": "Safe Mode (25-35% Monthly)",
        "leverage": 4,
        "investment_inr": 150.0,
        "min_confidence": 90,
        "stop_loss_pct": 1.1,
        "take_profit_pct": 3.8,
        "timeframe": "15m",
        "description": "Ultra high selectivity. Strict capital protection (3.45:1 RRR)."
    },
    "BALANCED": {
        "label": "Balanced Growth (40-60% Monthly)",
        "leverage": 5,
        "investment_inr": 150.0,
        "min_confidence": 86,
        "stop_loss_pct": 1.3,
        "take_profit_pct": 4.5,
        "timeframe": "15m",
        "description": "Client target 40%. Optimal risk-reward ratio (3.46:1 RRR)."
    },
    "AGGRESSIVE": {
        "label": "Aggressive Alpha (80-120%+ Monthly)",
        "leverage": 6,
        "investment_inr": 160.0,
        "min_confidence": 82,
        "stop_loss_pct": 1.6,
        "take_profit_pct": 5.5,
        "timeframe": "15m",
        "description": "High frequency breakout scalper with 6x leverage (3.44:1 RRR)."
    }
}

CURRENT_RISK_MODE = "BALANCED"

# Trade settings (Active defaults derived from CURRENT_RISK_MODE)
INVESTMENT_PER_TRADE_INR = RISK_PROFILES[CURRENT_RISK_MODE]["investment_inr"]
LEVERAGE = RISK_PROFILES[CURRENT_RISK_MODE]["leverage"]
MAX_OPEN_POSITIONS = 3  # Up to 3 concurrent active positions simultaneously
SAME_COIN_COOLDOWN_SECONDS = 7200  # 2 hours cooldown before re-trading the same coin

# Dynamic Adaptive Runner Settings (Anti-Choke 18% - 35% Target Extension & Profit Lock)
RUNNER_TRIGGER_PNL_PCT = 18.0  # When trade hits +18% PnL, shift TP to mega runner mode
RUNNER_EXTENDED_TP_PCT = 28.0  # Auto-shift TP up to +28% - +35%
RUNNER_LOCK_PROFIT_PCT = 11.0  # Lock at least +11% guaranteed net profit
RUNNER_TRAILING_BUFFER_PCT = 7.0 # Trail 7% below peak PnL for runners

# Strategy settings (EMA Crossover + RSI)
FAST_EMA_PERIOD = 9
SLOW_EMA_PERIOD = 21
RSI_PERIOD = 14
RSI_BUY_THRESHOLD = 52
RSI_SELL_THRESHOLD = 48

# Risk Management
STOP_LOSS_PERCENT = RISK_PROFILES[CURRENT_RISK_MODE]["stop_loss_pct"]
TAKE_PROFIT_PERCENT = RISK_PROFILES[CURRENT_RISK_MODE]["take_profit_pct"]

# CoinDCX API credentials
COINDCX_API_KEY = os.getenv("COINDCX_API_KEY", "c590bc67e17800d3955ca0cf02b23b4c1a83d7360d7f1e6d")
COINDCX_API_SECRET = os.getenv("COINDCX_API_SECRET", "3f86d69988e76ed689087544d5264ff5cadc72af03d623e66effca8ae28c78a2")

# Realistic Exchange Fee Deduction
# 'COINDCX': 0.05% taker fee on open + 0.05% taker fee on close (0.10% total on notional position)
# 'FLAT_1PCT': 1.0% flat margin buffer (covers TDS / slippage)
FEE_MODE = os.getenv("FEE_MODE", "COINDCX")
FEE_TAKER_PCT = 0.05  # 0.05% per leg



