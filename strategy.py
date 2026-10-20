import pandas as pd
import numpy as np
from typing import Tuple, Optional, Dict, Any
import config


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes Turtle Trading Strategy indicators (Richard Dennis & William Eckhardt System 2):
    1. True Range (TR) and Volatility N (20-period EMA of True Range, as defined by Dennis)
    2. Donchian Breakout Channels:
       - 55-period High (Entry breakout level for Long)
       - 55-period Low (Entry breakdown level for Short)
    3. Donchian Trailing Exit Channels:
       - 20-period Low (Trailing exit level for Long)
       - 20-period High (Trailing exit level for Short)
    4. Auxiliary EMAs & RSI (Maintained for macro market filters)
    """
    df = df.copy()

    # Ensure high, low, close columns exist
    if "high" not in df.columns:
        df["high"] = df["close"]
    if "low" not in df.columns:
        df["low"] = df["close"]

    # --------------------------------------------------------------------------
    # 1. TURTLE VOLATILITY N (Wilder's 20-period True Range EMA)
    # Formula: TR = max(High - Low, |High - Close_prev|, |Low - Close_prev|)
    #          N  = (19 * N_prev + TR) / 20
    # --------------------------------------------------------------------------
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["true_range"] = tr

    atr_period = getattr(config, "TURTLE_ATR_PERIOD", 20)
    # Alpha = 1/20 implements Dennis & Eckhardt's exact (19*N_prev + TR)/20 formula
    df["n_volatility"] = tr.ewm(alpha=1.0 / atr_period, min_periods=atr_period, adjust=False).mean()

    # --------------------------------------------------------------------------
    # 2. TURTLE DONCHIAN BREAKOUT & EXIT CHANNELS
    # Shifted by 1 period so current evaluating bar does not look ahead at itself
    # --------------------------------------------------------------------------
    breakout_period = getattr(config, "TURTLE_BREAKOUT_PERIOD", 55)
    exit_period = getattr(config, "TURTLE_EXIT_PERIOD", 20)

    df["donchian_high"] = df["high"].rolling(window=breakout_period).max().shift(1)
    df["donchian_low"] = df["low"].rolling(window=breakout_period).min().shift(1)
    df["exit_low"] = df["low"].rolling(window=exit_period).min().shift(1)
    df["exit_high"] = df["high"].rolling(window=exit_period).max().shift(1)

    # --------------------------------------------------------------------------
    # 3. AUXILIARY INDICATORS (For macro regime filters)
    # --------------------------------------------------------------------------
    df["ema_fast"] = df["close"].ewm(span=getattr(config, "FAST_EMA_PERIOD", 9), adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=getattr(config, "SLOW_EMA_PERIOD", 21), adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    rsi_period = getattr(config, "RSI_PERIOD", 14)
    avg_gain = gain.ewm(alpha=1.0 / rsi_period, min_periods=rsi_period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / rsi_period, min_periods=rsi_period, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df["rsi"] = 100.0 - (100.0 / (1.0 + rs))

    return df


def calculate_turtle_position_size(
    deposit: float,
    current_price: float,
    n_volatility: float,
    risk_pct: float = 2.0
) -> Dict[str, float]:
    """
    Computes Turtle Volatility-Adjusted Position Sizing ('1 Unit').
    Thesis Formula:
        Size (Units) = (Deposit * (Risk% / 100)) / (2 * N)
        Invested Amount = Units * Current Price
    """
    if n_volatility <= 0 or current_price <= 0:
        return {"units": 0.0, "invested_inr": 0.0, "risk_inr": 0.0, "stop_distance": 0.0}

    risk_amount = deposit * (risk_pct / 100.0)
    stop_distance = 2.0 * n_volatility  # 2N stop distance
    units = risk_amount / stop_distance
    invested_amount = units * current_price

    return {
        "units": units,
        "invested_inr": invested_amount,
        "risk_inr": risk_amount,
        "stop_distance": stop_distance,
    }


def evaluate_signal(
    df: pd.DataFrame,
    current_position: Optional[Dict[str, Any]] = None
) -> Tuple[str, str, Dict[str, float]]:
    """
    Strict Turtle Trading Strategy Engine (System 2):
    
    1. ENTRY RULES:
       - LONG: Price breaks and closes above 55-bar Donchian High.
       - Initial Stop-Loss placed at 2N (2 x ATR) below entry.
       
    2. EXIT RULES:
       - 2N Volatility Stop-Loss: Triggers if price drops below Entry - 2N.
       - 20-bar Low Channel Exit: Triggers if price drops below 20-bar Donchian Low.
       
    Returns:
        (signal, reason, metrics)
        signal: 'BUY', 'SELL', or 'HOLD'
    """
    required_candles = max(
        getattr(config, "TURTLE_BREAKOUT_PERIOD", 55),
        getattr(config, "TURTLE_ATR_PERIOD", 20)
    ) + 2

    if len(df) < required_candles:
        return "HOLD", f"Insufficient candles for Turtle analysis (needs {required_candles}, got {len(df)})", {}

    df = calculate_indicators(df)
    latest = df.iloc[-1]
    previous = df.iloc[-2]

    current_price = float(latest["close"])
    n_val = float(latest["n_volatility"]) if not np.isnan(latest["n_volatility"]) else (current_price * 0.02)
    donchian_high = float(latest["donchian_high"]) if not np.isnan(latest["donchian_high"]) else current_price
    donchian_low = float(latest["donchian_low"]) if not np.isnan(latest["donchian_low"]) else current_price
    exit_low = float(latest["exit_low"]) if not np.isnan(latest["exit_low"]) else (current_price * 0.95)
    exit_high = float(latest["exit_high"]) if not np.isnan(latest["exit_high"]) else (current_price * 1.05)

    stop_multiple = getattr(config, "TURTLE_STOP_MULTIPLE", 2.0)
    risk_reward_ratio = getattr(config, "RISK_REWARD_RATIO", 2.0)
    turtle_stop_price = current_price - (stop_multiple * n_val)
    turtle_tp_price, _ = calculate_trade_targets(current_price, "LONG", turtle_stop_price, risk_reward_ratio=risk_reward_ratio)

    metrics = {
        "price": current_price,
        "n_volatility": round(n_val, 4),
        "donchian_high": round(donchian_high, 4),
        "donchian_low": round(donchian_low, 4),
        "exit_low": round(exit_low, 4),
        "exit_high": round(exit_high, 4),
        "turtle_stop_loss": round(turtle_stop_price, 4),
        "turtle_take_profit": round(turtle_tp_price, 4),
        "risk_reward_ratio": risk_reward_ratio,
        "ema_fast": float(latest["ema_fast"]),
        "ema_slow": float(latest["ema_slow"]),
        "rsi": float(latest["rsi"]),
    }

    # --------------------------------------------------------------------------
    # 1. POSITION MANAGEMENT (If already in an active Turtle 1:2 trade)
    # --------------------------------------------------------------------------
    if current_position is not None:
        buy_price = float(current_position["buy_price"])
        pnl_pct = ((current_price - buy_price) / buy_price) * 100.0

        # Turtle 2N Dynamic Volatility Stop Loss check (1R Risk Invalidation)
        pos_stop_loss = current_position.get("stop_loss")
        if pos_stop_loss is None or pos_stop_loss <= 0:
            pos_stop_loss = buy_price - (stop_multiple * n_val)

        if current_price <= pos_stop_loss:
            return "SELL", f"1:2 Stop Loss hit (-1R)! Price ({current_price:,.2f}) <= SL ({pos_stop_loss:,.2f}) | PnL: {pnl_pct:+.2f}%", metrics

        # Asymmetric 1:2 Take Profit Target check (+2R Reward Target)
        pos_target = current_position.get("target")
        if pos_target and current_price >= float(pos_target):
            return "SELL", f"1:2 Take Profit target reached (+2R)! Price ({current_price:,.2f}) >= Target ({float(pos_target):,.2f}) | PnL: {pnl_pct:+.2f}%", metrics

        # Turtle 20-period Donchian Low Trailing Channel Exit check (Structural shift)
        if current_price < exit_low:
            return "SELL", f"Turtle 20-bar Low Channel Exit triggered! Price ({current_price:,.2f}) < Exit Floor ({exit_low:,.2f}) | PnL: {pnl_pct:+.2f}%", metrics

        return "HOLD", f"Holding 1:2 trend (PnL: {pnl_pct:+.2f}%, Target +2R: {pos_target or turtle_tp_price:,.2f}, 1R SL: {pos_stop_loss:,.2f})", metrics

    # --------------------------------------------------------------------------
    # 2. ENTRY BREAKOUT TRIGGER (No active position)
    # --------------------------------------------------------------------------
    # Bullish Breakout: Current Close pierces above the 55-bar Donchian High
    is_breakout = current_price > donchian_high

    if is_breakout:
        reason = f"Turtle 1:2 Breakout Entry! Close ({current_price:,.2f}) > 55-bar High ({donchian_high:,.2f}) | 1R SL: {turtle_stop_price:,.2f}, +2R TP: {turtle_tp_price:,.2f} (N: {n_val:,.2f})"
        return "BUY", reason, metrics

    return "HOLD", f"Waiting for 1:2 Turtle Breakout (55-High: {donchian_high:,.2f}, 55-Low: {donchian_low:,.2f}, N: {n_val:,.2f})", metrics


def calculate_trade_targets(
    entry_price: float,
    signal_type: str,
    stop_loss_price: float,
    risk_reward_ratio: float = 2.0
) -> Tuple[float, float]:
    """
    Enforces a strict 1:2 Risk-to-Reward Ratio (Reward = 2 x Risk).
    LONG:  Risk = Entry - StopLoss -> TakeProfit = Entry + (Risk * 2)
    SHORT: Risk = StopLoss - Entry -> TakeProfit = Entry - (Risk * 2)
    """
    signal_type = signal_type.upper()
    if signal_type in ["LONG", "BUY"]:
        risk_distance = max(entry_price * 0.005, entry_price - stop_loss_price)
        take_profit_price = entry_price + (risk_distance * risk_reward_ratio)
    elif signal_type in ["SHORT", "SELL"]:
        risk_distance = max(entry_price * 0.005, stop_loss_price - entry_price)
        take_profit_price = entry_price - (risk_distance * risk_reward_ratio)
    else:
        take_profit_price = entry_price * 1.04
        stop_loss_price = entry_price * 0.98

    return round(take_profit_price, 4), round(stop_loss_price, 4)

