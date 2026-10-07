import pandas as pd
from typing import Tuple, Optional, Dict, Any
import config


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes technical indicators:
    - Fast Exponential Moving Average (EMA 9)
    - Slow Exponential Moving Average (EMA 21)
    - Relative Strength Index (RSI 14)
    """
    df = df.copy()

    # EMAs
    df["ema_fast"] = df["close"].ewm(span=config.FAST_EMA_PERIOD, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=config.SLOW_EMA_PERIOD, adjust=False).mean()

    # RSI
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    # Wilder's smoothing for RSI
    avg_gain = gain.ewm(alpha=1.0 / config.RSI_PERIOD, min_periods=config.RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / config.RSI_PERIOD, min_periods=config.RSI_PERIOD, adjust=False).mean()

    rs = avg_gain / (avg_loss + 1e-9)
    df["rsi"] = 100.0 - (100.0 / (1.0 + rs))

    return df


def evaluate_signal(
    df: pd.DataFrame,
    current_position: Optional[Dict[str, Any]] = None
) -> Tuple[str, str, Dict[str, float]]:
    """
    Evaluates current market indicators against strategy rules.

    Returns:
        (signal, reason, latest_metrics)
        signal: 'BUY', 'SELL', or 'HOLD'
    """
    if len(df) < max(config.SLOW_EMA_PERIOD, config.RSI_PERIOD) + 2:
        return "HOLD", "Insufficient candles for indicators", {}

    df = calculate_indicators(df)

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    metrics = {
        "price": float(latest["close"]),
        "ema_fast": float(latest["ema_fast"]),
        "ema_slow": float(latest["ema_slow"]),
        "rsi": float(latest["rsi"]),
    }

    current_price = metrics["price"]

    # 1. RISK MANAGEMENT CHECKS (If in an active position)
    if current_position is not None:
        buy_price = current_position["buy_price"]
        pnl_pct = ((current_price - buy_price) / buy_price) * 100.0

        # Check Stop Loss
        if pnl_pct <= -config.STOP_LOSS_PERCENT:
            return "SELL", f"Stop Loss triggered! Loss: {pnl_pct:.2f}%", metrics

        # Check Take Profit
        if pnl_pct >= config.TAKE_PROFIT_PERCENT:
            return "SELL", f"Take Profit target reached! Gain: +{pnl_pct:.2f}%", metrics

        # Check Bearish Crossover (EMA Fast crosses below EMA Slow)
        if (previous["ema_fast"] >= previous["ema_slow"]) and (latest["ema_fast"] < latest["ema_slow"]):
            return "SELL", f"Bearish EMA crossover (Fast < Slow, RSI: {latest['rsi']:.1f})", metrics

        return "HOLD", f"Holding position (Current PnL: {pnl_pct:+.2f}%)", metrics

    # 2. ENTRY SIGNAL CHECKS (If not currently in a position)
    # Fast EMA crosses above Slow EMA + RSI confirms bullish momentum
    is_bullish_cross = (previous["ema_fast"] <= previous["ema_slow"]) and (latest["ema_fast"] > latest["ema_slow"])
    is_above_trend = latest["ema_fast"] > latest["ema_slow"]
    rsi_bullish = latest["rsi"] > config.RSI_BUY_THRESHOLD

    if is_bullish_cross and rsi_bullish:
        return "BUY", f"Golden EMA Crossover + Strong RSI ({latest['rsi']:.1f})", metrics

    # Also catch existing strong uptrend if RSI just broke above threshold
    if is_above_trend and (previous["rsi"] <= config.RSI_BUY_THRESHOLD) and rsi_bullish:
        return "BUY", f"RSI momentum breakout ({latest['rsi']:.1f}) with Fast EMA > Slow EMA", metrics

    return "HOLD", f"Waiting for setup (EMA Diff: {metrics['ema_fast'] - metrics['ema_slow']:+.2f}, RSI: {metrics['rsi']:.1f})", metrics
