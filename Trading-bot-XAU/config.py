"""
Configuration for Trading-bot-XAU (Gold / XAUUSD Automated Trading Engine)
Targeted for Institutional-Grade Gold Trend & Volatility Trading with Comprehensive News & Slippage Protection.
"""

import os

# --- CORE INSTRUMENT SPECIFICATION ---
SYMBOL = "XAUUSD"                 # Gold vs US Dollar
CONTRACT_SIZE = 100               # Standard 1 Lot XAUUSD = 100 Troy Ounces
PIP_SIZE = 0.01                   # 1 Cent ($0.01) is 1 Pip / Point in Gold quote
CURRENCY = "USD"

# --- ACCOUNT & RISK LIMITS ---
INITIAL_BALANCE = 5000.0          # Starting Demo/Paper Capital ($ USD)
RISK_PER_TRADE_PERCENT = 1.0      # Conservative 1% risk per trade ($50 on $5,000)
MAX_OPEN_POSITIONS = 1            # Only 1 trade open at a time (prevent overexposure)
MAX_DAILY_DRAWDOWN_PERCENT = 3.0  # Daily circuit breaker: stop all trades if down 3% today
MAX_TOTAL_DRAWDOWN_PERCENT = 8.0  # Max allowable drawdown before emergency stop

# --- RISK REWARD & EXECUTION ---
RISK_REWARD_RATIO = 2.0           # 1:2 Minimum Risk to Reward
ATR_PERIOD = 14                   # Average True Range period
ATR_SL_MULTIPLIER = 1.5           # Stop Loss = 1.5x ATR (e.g. $4.50 on Gold)
ATR_TP_MULTIPLIER = 3.0           # Take Profit = 3.0x ATR (e.g. $9.00 on Gold, 1:2 R:R)
MIN_STOP_LOSS_USD = 3.0           # Minimum $3.00 stop loss buffer to survive micro-wicks
MAX_STOP_LOSS_USD = 12.0          # Maximum $12.00 stop loss

# --- ADVANCED PROTECTION: TRAILING STOP & BREAKEVEN ---
BREAKEVEN_TRIGGER_R = 1.2         # Move SL to Entry + Spread once price hits +1.2R profit
TRAILING_STOP_ENABLED = True      # Trail stop behind price
TRAILING_STOP_TRIGGER_R = 1.5     # Activate trailing stop once price reaches +1.5R profit
TRAILING_STOP_DISTANCE_ATR = 1.2  # Keep trailing stop 1.2x ATR behind the high/low

# --- SPREAD & SLIPPAGE DEFENSE ---
MAX_ALLOWED_SPREAD_PIPS = 3.5     # $0.35 on Gold (normal spread is 0.15 - 0.25). >0.35 = wide!
MAX_SLIPPAGE_PIPS = 2.0           # Maximum 20 cents slippage permitted
VOLATILITY_CIRCUIT_BREAKER_ATR = 2.5 # Freeze if a 1-min candle is > 2.5x ATR (violent shock)

# --- NEWS SHIELD DEFENSE (High-Impact US Economic News Protection) ---
NEWS_FILTER_ENABLED = True        # Automatically pause during high-impact US news
PRE_NEWS_MINUTES = 30             # Stop new trades 30 minutes BEFORE news release
POST_NEWS_MINUTES = 30            # Remain paused for 30 minutes AFTER news release
NEWS_IMPACTS = ("High", "Medium") # Filter Red and Orange folder events
NEWS_CURRENCIES = ("USD",)        # Gold is denominated in USD
AUTO_BREAKEVEN_BEFORE_NEWS = True # Move existing profitable open trades to breakeven before news

# --- LIQUIDITY SESSION FILTERS (in IST hours) ---
# Gold trades best during London & New York session overlap. Avoid Asian rollover (02:00-04:00 IST)
SESSION_FILTER_ENABLED = True
LONDON_SESSION_START_IST = 13.5   # 13:30 IST (08:00 GMT)
LONDON_SESSION_END_IST = 21.5     # 21:30 IST (16:00 GMT)
NY_SESSION_START_IST = 18.0       # 18:00 IST (12:30 GMT)
NY_SESSION_END_IST = 23.5         # 23:30 IST (18:00 GMT)

# --- TECHNICAL STRATEGY PARAMETERS ---
EMA_FAST = 21
EMA_MID = 50
EMA_SLOW = 200
RSI_PERIOD = 14
RSI_BULLISH_THRESHOLD = 52.0
RSI_BEARISH_THRESHOLD = 48.0
ADX_PERIOD = 14
MIN_ADX_TREND = 20.0

# --- PLATFORM CONNECTIONS ---
EXECUTION_MODE = "PAPER"          # "PAPER" (Internal simulation) or "MT5" (Live/Demo MetaTrader 5)
MT5_LOGIN = 0                     # Set your MT5 demo account number
MT5_PASSWORD = ""                 # Set your MT5 demo password
MT5_SERVER = ""                   # Set your MT5 broker server (e.g. "Exness-MT5Trial", "ICMarkets-Demo")

# Web Server Dashboard Port
PORT = 5005
