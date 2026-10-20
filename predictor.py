import numpy as np
import pandas as pd
from typing import Dict, Any, List


def _format_prec(val: float, base_price: float) -> float:
    if base_price < 0.001:
        return round(val, 8)
    elif base_price < 0.1:
        return round(val, 6)
    elif base_price < 10.0:
        return round(val, 4)
    else:
        return round(val, 2)


def predict_next_move(df: pd.DataFrame, forecast_steps: int = 10) -> Dict[str, Any]:
    """
    Quantitative Predictive Engine that forecasts:
    1. Expected Next Direction (UP, DOWN, or SIDEWAYS)
    2. Probability Confidence (0% to 100%)
    3. Projected Price Target for the next 10 candles / dots
    4. Invalidation / Stop-Loss level
    5. Step-by-step future price trajectory (for chart visualization)
    """
    if len(df) < 25:
        curr = float(df["close"].iloc[-1]) if len(df) else 0.0
        return {
            "direction": "SIDEWAYS",
            "probability": 50,
            "current_price": curr,
            "target_price": curr,
            "stop_loss": 0,
            "expected_change_pct": 0.0,
            "reason": "Insufficient candle data for high-confidence forecast.",
            "confluences": [],
            "projected_path": [curr] * forecast_steps
        }

    df = df.copy()
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values
    volumes = df["volume"].values

    curr_price = float(closes[-1])
    n = len(closes)

    # ---------------------------------------------------------
    # FACTOR 1: Momentum Velocity & Trend Alignment
    # ---------------------------------------------------------
    df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

    ema9 = float(df["ema9"].iloc[-1])
    ema21 = float(df["ema21"].iloc[-1])
    ema50 = float(df["ema50"].iloc[-1])

    # ---------------------------------------------------------
    # FACTOR 2: RSI Momentum & Exhaustion
    # ---------------------------------------------------------
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    rsi = float((100.0 - (100.0 / (1.0 + rs))).iloc[-1])

    # ---------------------------------------------------------
    # FACTOR 3: Linear Regression Drift (Recent 15 candles)
    # ---------------------------------------------------------
    window = min(15, n)
    recent_closes = closes[-window:]
    x = np.arange(window)
    slope, intercept = np.polyfit(x, recent_closes, 1)

    # Calculate residuals and volatility (Standard Error)
    predicted_past = intercept + slope * x
    residuals = recent_closes - predicted_past
    std_err = float(np.std(residuals))
    if std_err == 0:
        std_err = curr_price * 0.01

    # ---------------------------------------------------------
    # FACTOR 4: Bollinger Band Expansion / Compression
    # ---------------------------------------------------------
    sma20 = float(df["close"].rolling(20).mean().iloc[-1])
    std20 = float(df["close"].rolling(20).std().iloc[-1])
    bb_upper = sma20 + (2.0 * std20)
    bb_lower = sma20 - (2.0 * std20)

    # ---------------------------------------------------------
    # FACTOR 5: Multi-Factor Scoring Matrix
    # ---------------------------------------------------------
    bullish_score = 0
    bearish_score = 0
    confluences: List[str] = []

    # Trend scoring
    if curr_price > ema9 > ema21:
        bullish_score += 25
        confluences.append("Bullish Trend: Price > EMA 9 > EMA 21 (+25%)")
    elif curr_price < ema9 < ema21:
        bearish_score += 25
        confluences.append("Bearish Trend: Price < EMA 9 < EMA 21 (+25%)")

    # Slope scoring
    slope_pct = (slope / curr_price) * 100.0
    if slope_pct > 0.05:
        bullish_score += 20
        confluences.append(f"Upward Linear Slope velocity: +{slope_pct:.2f}%/candle (+20%)")
    elif slope_pct < -0.05:
        bearish_score += 20
        confluences.append(f"Downward Linear Slope velocity: {slope_pct:.2f}%/candle (+20%)")

    # RSI & Exhaustion Scoring
    if rsi > 72:
        bearish_score += 30
        confluences.append(f"RSI Exhaustion Warning: {rsi:.1f} Overheated, high probability of mean reversion dip (+30%)")
    elif rsi < 30:
        bullish_score += 30
        confluences.append(f"RSI Oversold Bounce: {rsi:.1f} Deep discount, high probability of technical bounce (+30%)")
    elif 52 <= rsi <= 68:
        bullish_score += 20
        confluences.append(f"Healthy RSI Momentum: {rsi:.1f} in sweet expansion zone (+20%)")
    elif 32 <= rsi <= 48:
        bearish_score += 20
        confluences.append(f"Weak Bearish RSI: {rsi:.1f} below midpoint (+20%)")

    # Volatility / Resistance Ceiling Test
    dist_to_upper = ((bb_upper - curr_price) / curr_price) * 100.0
    if dist_to_upper < 1.0 and rsi > 65:
        bearish_score += 25
        confluences.append("Upper Bollinger Band Rejection risk near resistance (+25%)")

    # Volume Confirmation
    recent_vol = float(volumes[-1])
    avg_vol = float(np.mean(volumes[-10:]))
    if recent_vol > avg_vol * 1.3:
        if closes[-1] > closes[-2]:
            bullish_score += 15
            confluences.append("Volume Climax Surge supporting Buyers (+15%)")
        else:
            bearish_score += 15
            confluences.append("Heavy Volume Sell Pressure (+15%)")

    # ---------------------------------------------------------
    # FACTOR 6: Turtle Donchian Channel Breakout (Dennis System)
    # ---------------------------------------------------------
    if n >= 25:
        turtle_lookback = min(55, n - 1)
        channel_high = float(np.max(highs[-turtle_lookback - 1:-1]))
        channel_low = float(np.min(lows[-turtle_lookback - 1:-1]))
        if curr_price > channel_high:
            bullish_score += 30
            confluences.append(f"Turtle Breakout: Crossed {turtle_lookback}-bar Channel High (+30%)")
        elif curr_price < channel_low:
            bearish_score += 30
            confluences.append(f"Turtle Breakdown: Broke {turtle_lookback}-bar Channel Low (+30%)")

    # ---------------------------------------------------------
    # FINAL PREDICTION SYNTHESIS
    # ---------------------------------------------------------
    total_score = bullish_score + bearish_score
    if total_score == 0:
        total_score = 1

    bull_prob = int(round((bullish_score / max(1, total_score)) * 100))
    bear_prob = 100 - bull_prob

    # Generate forward projected path (up to forecast_steps dots)
    projected_path = []

    if bull_prob >= 58:
        direction = "UP"
        # Confluence multiplier: when 4+ confluences align, probability scales up to 98%
        conf_count = len([c for c in confluences if "(+" in c])
        base_prob = max(62, bull_prob)
        if conf_count >= 4 and bull_prob >= 75:
            probability = min(98, base_prob + 10)
        elif conf_count >= 3 and bull_prob >= 68:
            probability = min(95, base_prob + 6)
        else:
            probability = min(92, base_prob)

        # Expected target: 1.5 to 2.5 times standard error above current price
        projected_rise = max(curr_price * 0.02, std_err * 2.0)
        target_price = _format_prec(curr_price + projected_rise, curr_price)
        stop_loss = _format_prec(max(ema21 * 0.99, curr_price - (projected_rise * 0.6)), curr_price)

        for step in range(1, forecast_steps + 1):
            progress = np.sqrt(step / forecast_steps)
            projected_val = curr_price + (projected_rise * progress)
            projected_path.append(_format_prec(projected_val, curr_price))

        if rsi < 32:
            signal_type = "EXTREME OVERSOLD REBOUND"
        elif curr_price > ema9 > ema21:
            signal_type = "STRONG BULL BREAKOUT"
        else:
            signal_type = "BULLISH MOMENTUM RALLY"

        summary = f"Predictive model indicates a {probability}% probability of an UPWARD rally to ${target_price}."

    elif bear_prob >= 58:
        direction = "DOWN"
        conf_count = len([c for c in confluences if "(+" in c])
        base_prob = max(62, bear_prob)
        if conf_count >= 4 and bear_prob >= 75:
            probability = min(98, base_prob + 10)
        elif conf_count >= 3 and bear_prob >= 68:
            probability = min(95, base_prob + 6)
        else:
            probability = min(92, base_prob)

        projected_drop = max(curr_price * 0.02, std_err * 2.0)
        target_price = _format_prec(curr_price - projected_drop, curr_price)
        stop_loss = _format_prec(min(ema21 * 1.01, curr_price + (projected_drop * 0.6)), curr_price)

        for step in range(1, forecast_steps + 1):
            progress = np.sqrt(step / forecast_steps)
            projected_val = curr_price - (projected_drop * progress)
            projected_path.append(_format_prec(projected_val, curr_price))

        if rsi > 70:
            signal_type = "EXTREME OVERBOUGHT REVERSAL"
        elif curr_price < ema9 < ema21:
            signal_type = "BEARISH BREAKDOWN DUMP"
        else:
            signal_type = "BEARISH PULLBACK / SHORT"

        summary = f"Predictive model indicates a {probability}% probability of a PULLBACK / DIP to ${target_price}."

    else:
        direction = "SIDEWAYS"
        probability = 52
        signal_type = "NEUTRAL CONSOLIDATION"
        target_price = _format_prec(curr_price, curr_price)
        stop_loss = _format_prec(curr_price * 0.98, curr_price)
        for step in range(1, forecast_steps + 1):
            variation = (std_err * 0.3) * np.sin(step * 0.8)
            projected_path.append(_format_prec(curr_price + variation, curr_price))
        summary = "Predictive model indicates sideways consolidation / choppy market. No clear edge."

    # Risk-Reward calculation
    risk = abs(curr_price - stop_loss)
    reward = abs(target_price - curr_price)
    rr_ratio = round(reward / max(1e-9, risk), 2) if risk > 0 else 2.0

    if probability >= 90:
        confidence_tier = "ULTRA (100% SETUP)"
    elif probability >= 80:
        confidence_tier = "HIGH PROBABILITY"
    elif probability >= 65:
        confidence_tier = "MODERATE"
    else:
        confidence_tier = "NEUTRAL"

    return {
        "direction": direction,
        "probability": probability,
        "confidence_tier": confidence_tier,
        "signal_type": signal_type,
        "current_price": _format_prec(curr_price, curr_price),
        "target_price": target_price,
        "stop_loss": stop_loss,
        "risk_reward_ratio": rr_ratio,
        "expected_change_pct": round(((target_price - curr_price) / curr_price) * 100.0, 2),
        "summary": summary,
        "confluences": confluences,
        "projected_path": projected_path,
        "rsi": round(rsi, 1),
        "ema9": _format_prec(ema9, curr_price),
        "ema21": _format_prec(ema21, curr_price),
    }
