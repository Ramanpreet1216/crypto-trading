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
        "leverage": 5,
        "investment_inr": 150.0,
        "min_confidence": 90,
        "stop_loss_pct": 1.5,
        "take_profit_pct": 3.0,
        "timeframe": "15m",
        "description": "Ultra high selectivity. Strict capital protection."
    },
    "BALANCED": {
        "label": "Balanced Growth (40-60% Monthly)",
        "leverage": 7,
        "investment_inr": 160.0,
        "min_confidence": 85,
        "stop_loss_pct": 2.0,
        "take_profit_pct": 4.5,
        "timeframe": "15m",
        "description": "Client target 40%. Optimal risk-reward ratio."
    },
    "AGGRESSIVE": {
        "label": "Aggressive Alpha (80-120%+ Monthly)",
        "leverage": 10,
        "investment_inr": 200.0,
        "min_confidence": 78,
        "stop_loss_pct": 2.5,
        "take_profit_pct": 6.0,
        "timeframe": "15m",
        "description": "High frequency breakout scalper with 10x leverage."
    }
}

CURRENT_RISK_MODE = "BALANCED"

# Trade settings (Active defaults derived from CURRENT_RISK_MODE)
INVESTMENT_PER_TRADE_INR = RISK_PROFILES[CURRENT_RISK_MODE]["investment_inr"]
LEVERAGE = RISK_PROFILES[CURRENT_RISK_MODE]["leverage"]
MAX_OPEN_POSITIONS = 1

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


