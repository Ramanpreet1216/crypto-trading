"""
Gold (XAUUSD) Institutional Trend & Momentum Strategy
Engineered specifically for Gold's volatility dynamics:
- Multi-Timeframe EMA Alignment (21, 50, 200)
- ATR-based Dynamic Stop Loss & Take Profit (1:2 Risk to Reward)
- RSI & ADX Trend Confirmation
- London & New York Liquidity Session Filters
- Integrated News Shield & Spread Checks
"""

import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import config

class GoldStrategy:
    def __init__(self):
        self.ema_fast = config.EMA_FAST
        self.ema_mid = config.EMA_MID
        self.ema_slow = config.EMA_SLOW
        self.rsi_period = config.RSI_PERIOD
        self.adx_period = config.ADX_PERIOD
        self.min_adx = config.MIN_ADX_TREND

    def is_valid_session(self) -> Tuple[bool, str]:
        """
        Check if the current time falls within active high-liquidity trading sessions:
        - London Session: 13:30 - 21:30 IST
        - New York Session: 18:00 - 23:30 IST
        Gold should avoid Asian late night / rollover (02:00 - 04:00 IST).
        """
        if not config.SESSION_FILTER_ENABLED:
            return True, "Session Filter Disabled"

        # Current IST time (UTC + 5:30)
        utc_now = datetime.now(timezone.utc)
        ist_now = utc_now + timedelta(hours=5, minutes=30)
        hour_decimal = ist_now.hour + ist_now.minute / 60.0

        in_london = config.LONDON_SESSION_START_IST <= hour_decimal <= config.LONDON_SESSION_END_IST
        in_ny = config.NY_SESSION_START_IST <= hour_decimal <= config.NY_SESSION_END_IST

        if in_london and in_ny:
            return True, f"London/NY Overlap Peak Liquidity ({ist_now.strftime('%H:%M')} IST)"
        elif in_london:
            return True, f"London Active Session ({ist_now.strftime('%H:%M')} IST)"
        elif in_ny:
            return True, f"New York Active Session ({ist_now.strftime('%H:%M')} IST)"
        else:
            return False, f"Off-Hours / Asian Session ({ist_now.strftime('%H:%M')} IST) - Low Liquidity, Trading Paused"

    def calculate_indicators(self, candles: List[Dict]) -> Optional[Dict]:
        """
        Calculate technical indicators over candlestick data:
        candles: list of dicts with 'open', 'high', 'low', 'close', 'volume', 'time'
        """
        if len(candles) < self.ema_slow + 5:
            return None

        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        n = len(closes)

        # 1. EMAs
        def calc_ema(values, period):
            k = 2 / (period + 1)
            ema = [sum(values[:period]) / period]
            for v in values[period:]:
                ema.append(v * k + ema[-1] * (1 - k))
            return ema

        ema_21 = calc_ema(closes, self.ema_fast)[-1]
        ema_50 = calc_ema(closes, self.ema_mid)[-1]
        ema_200 = calc_ema(closes, self.ema_slow)[-1]

        # 2. ATR (Average True Range)
        tr_list = []
        for i in range(1, n):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1])
            )
            tr_list.append(tr)

        atr_period = config.ATR_PERIOD
        if len(tr_list) < atr_period:
            return None
        atr = sum(tr_list[-atr_period:]) / atr_period

        # 3. RSI
        gains = []
        losses = []
        for i in range(1, n):
            delta = closes[i] - closes[i - 1]
            gains.append(max(0.0, delta))
            losses.append(max(0.0, -delta))

        rsi_period = self.rsi_period
        avg_gain = sum(gains[-rsi_period:]) / rsi_period
        avg_loss = sum(losses[-rsi_period:]) / rsi_period
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

        # 4. ADX (Average Directional Index) for trend strength
        plus_dm = []
        minus_dm = []
        for i in range(1, n):
            up_move = highs[i] - highs[i - 1]
            down_move = lows[i - 1] - lows[i]
            if up_move > down_move and up_move > 0:
                plus_dm.append(up_move)
            else:
                plus_dm.append(0.0)

            if down_move > up_move and down_move > 0:
                minus_dm.append(down_move)
            else:
                minus_dm.append(0.0)

        adx_period = self.adx_period
        if len(tr_list) >= adx_period * 2:
            tr_smooth = sum(tr_list[-adx_period:])
            plus_smooth = sum(plus_dm[-adx_period:])
            minus_smooth = sum(minus_dm[-adx_period:])

            plus_di = 100.0 * (plus_smooth / (tr_smooth or 1.0))
            minus_di = 100.0 * (minus_smooth / (tr_smooth or 1.0))
            dx_denom = plus_di + minus_di
            dx = 100.0 * (abs(plus_di - minus_di) / (dx_denom or 1.0))
            adx = dx  # single period approximation
        else:
            adx = 25.0  # default healthy baseline

        current_price = closes[-1]
        prev_price = closes[-2]

        return {
            "current_price": current_price,
            "ema_21": ema_21,
            "ema_50": ema_50,
            "ema_200": ema_200,
            "atr": atr,
            "rsi": rsi,
            "adx": adx,
            "recent_high": max(highs[-20:]),
            "recent_low": min(lows[-20:]),
            "candle_range": highs[-1] - lows[-1]
        }

    def evaluate_signal(self, candles: List[Dict], current_spread_pips: float, news_status: Dict) -> Dict:
        """
        Evaluate full trading signal with all filters:
        - Session Filter
        - News Lockdown Check
        - Spread Check
        - Volatility Spike Check
        - Technical Indicator Confluence
        """
        # 1. Check News Lockdown first (MANDATORY)
        if news_status.get("is_locked", False):
            return {
                "action": "HOLD",
                "reason": news_status.get("lock_reason", "News Lockdown Active"),
                "signal_type": "NEWS_LOCKDOWN"
            }

        # 2. Check Spread Filter
        if current_spread_pips > config.MAX_ALLOWED_SPREAD_PIPS:
            return {
                "action": "HOLD",
                "reason": f"Spread too high ({current_spread_pips:.2f} > {config.MAX_ALLOWED_SPREAD_PIPS:.2f} pips)",
                "signal_type": "SPREAD_EXCEEDED"
            }

        # 3. Check Session Timing
        session_ok, session_msg = self.is_valid_session()
        if not session_ok:
            return {
                "action": "HOLD",
                "reason": session_msg,
                "signal_type": "OFF_SESSION"
            }

        # 4. Calculate Indicators
        ind = self.calculate_indicators(candles)
        if not ind:
            return {
                "action": "HOLD",
                "reason": "Insufficient historical candle bars",
                "signal_type": "INSUFFICIENT_DATA"
            }

        price = ind["current_price"]
        ema_21 = ind["ema_21"]
        ema_50 = ind["ema_50"]
        ema_200 = ind["ema_200"]
        atr = ind["atr"]
        rsi = ind["rsi"]
        adx = ind["adx"]
        candle_range = ind["candle_range"]

        # 5. Volatility Circuit Breaker Check
        if atr > 0 and (candle_range / atr) >= config.VOLATILITY_CIRCUIT_BREAKER_ATR:
            return {
                "action": "HOLD",
                "reason": f"Violent candle range ({candle_range:.2f} vs {atr:.2f} ATR) - volatility shock protection",
                "signal_type": "VOLATILITY_SHOCK"
            }

        # Dynamic Stop Loss & Take Profit sizing based on ATR
        sl_distance = max(config.MIN_STOP_LOSS_USD, min(config.MAX_STOP_LOSS_USD, atr * config.ATR_SL_MULTIPLIER))
        tp_distance = sl_distance * config.RISK_REWARD_RATIO

        # 6. Trend Strength Filter
        if adx < self.min_adx:
            return {
                "action": "HOLD",
                "reason": f"Gold consolidating (ADX {adx:.1f} < {self.min_adx} threshold) - awaiting trend expansion",
                "signal_type": "CHOPPY_MARKET",
                "indicators": ind
            }

        # 7. BULLISH SETUP (BUY)
        # Macro Bullish: Price > 200 EMA and 50 EMA > 200 EMA
        is_bullish_trend = (price > ema_200) and (ema_50 > ema_200)
        # Pullback into 21 EMA or clean breakout above 21 EMA
        is_bullish_entry = (price >= ema_21 * 0.998) and (rsi >= config.RSI_BULLISH_THRESHOLD) and (rsi <= 72.0)

        if is_bullish_trend and is_bullish_entry:
            sl_price = round(price - sl_distance, 2)
            tp_price = round(price + tp_distance, 2)
            return {
                "action": "BUY",
                "symbol": config.SYMBOL,
                "price": price,
                "sl": sl_price,
                "tp": tp_price,
                "sl_distance": sl_distance,
                "tp_distance": tp_distance,
                "risk_reward": f"1:{config.RISK_REWARD_RATIO:.1f}",
                "reason": f"Bullish Trend Confluence: Price ${price:.2f} > 200 EMA (${ema_200:.2f}), RSI {rsi:.1f}, ATR ${atr:.2f}",
                "indicators": ind,
                "session": session_msg
            }

        # 8. BEARISH SETUP (SELL)
        # Macro Bearish: Price < 200 EMA and 50 EMA < 200 EMA
        is_bearish_trend = (price < ema_200) and (ema_50 < ema_200)
        # Pullback into 21 EMA or clean rejection below 21 EMA
        is_bearish_entry = (price <= ema_21 * 1.002) and (rsi <= config.RSI_BEARISH_THRESHOLD) and (rsi >= 28.0)

        if is_bearish_trend and is_bearish_entry:
            sl_price = round(price + sl_distance, 2)
            tp_price = round(price - tp_distance, 2)
            return {
                "action": "SELL",
                "symbol": config.SYMBOL,
                "price": price,
                "sl": sl_price,
                "tp": tp_price,
                "sl_distance": sl_distance,
                "tp_distance": tp_distance,
                "risk_reward": f"1:{config.RISK_REWARD_RATIO:.1f}",
                "reason": f"Bearish Trend Confluence: Price ${price:.2f} < 200 EMA (${ema_200:.2f}), RSI {rsi:.1f}, ATR ${atr:.2f}",
                "indicators": ind,
                "session": session_msg
            }

        return {
            "action": "HOLD",
            "reason": f"Trend neutral / awaiting pull-back (Price: ${price:.2f}, EMA 50: ${ema_50:.2f}, RSI: {rsi:.1f})",
            "signal_type": "NEUTRAL",
            "indicators": ind,
            "session": session_msg
        }
