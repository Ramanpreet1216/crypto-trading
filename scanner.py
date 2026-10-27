import sys
import requests
import pandas as pd
import numpy as np

# Ensure UTF-8 output on Windows terminal
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import time
import concurrent.futures
from typing import List, Dict, Any, Optional
import config

PUBLIC_URL = "https://public.coindcx.com"
API_URL = "https://api.coindcx.com"

# In-memory ticker cache (refreshed every 30 seconds to prevent cloud CPU starvation)
_TICKER_CACHE = {
    "data": [],
    "timestamp": 0
}

PUBLIC_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json"
}


def _fetch_all_raw_tickers():
    """Fetches raw 24hr tickers with 30-second caching using CoinDCX official public API."""
    global _TICKER_CACHE
    now = time.time()
    if _TICKER_CACHE["data"] and (now - _TICKER_CACHE["timestamp"]) < 30.0:
        return _TICKER_CACHE["data"]

    # 1. Primary: CoinDCX Official Public Ticker (Fast, never blocked in India / cloud)
    try:
        raw = requests.get(f"{PUBLIC_URL}/exchange/ticker", headers=PUBLIC_HEADERS, timeout=3.5).json()
        if isinstance(raw, list) and len(raw) > 0:
            converted = []
            for t in raw:
                m = t.get("market", "")
                if m.endswith("USDT"):
                    try:
                        lp = float(t.get("last_price", 0) or 0)
                        vol = float(t.get("volume", 0) or 0)
                        converted.append({
                            "symbol": m,
                            "lastPrice": lp,
                            "priceChangePercent": float(t.get("change_24_hour", 0) or 0),
                            "highPrice": float(t.get("high", 0) or 0),
                            "lowPrice": float(t.get("low", 0) or 0),
                            "volume": vol,
                            "quoteVolume": round(vol * lp, 2)
                        })
                    except (ValueError, TypeError):
                        continue
            if converted:
                _TICKER_CACHE["data"] = converted
                _TICKER_CACHE["timestamp"] = now
                return converted
    except Exception as e:
        print(f"[CoinDCX Ticker API Notice]: {e}")

    # 2. Secondary fallback: Binance Futures Ticker with browser headers
    try:
        tickers = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", headers=PUBLIC_HEADERS, timeout=2.5).json()
        if isinstance(tickers, list) and len(tickers) > 0:
            _TICKER_CACHE["data"] = tickers
            _TICKER_CACHE["timestamp"] = now
            return tickers
    except Exception as e:
        pass

    return _TICKER_CACHE["data"]


def get_all_cryptos(search: str = "", sort_by: str = "volume", limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Returns all available cryptocurrency pairs (over 700+ coins).
    Supports instant search filtering and sorting by volume, gainers, losers, or price.
    """
    tickers = _fetch_all_raw_tickers()
    if not tickers:
        return []

    results = []
    search_q = (search or "").strip().upper()

    for t in tickers:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        coin = sym[:-4]
        if not coin.isascii() or not coin.isalnum():
            continue

        if search_q and search_q not in coin:
            continue

        try:
            price = float(t.get("lastPrice", 0))
            chg = float(t.get("priceChangePercent", 0))
            vol_coin = float(t.get("volume", 0))
            vol_usdt = float(t.get("quoteVolume", 0))
            high_24h = float(t.get("highPrice", 0))
            low_24h = float(t.get("lowPrice", 0))

            results.append({
                "coin": coin,
                "symbol": sym,
                "contract": f"{coin}USDT.P",
                "price": price,
                "change_24h": round(chg, 2),
                "high_24h": high_24h,
                "low_24h": low_24h,
                "volume_coin": vol_coin,
                "volume_usdt": round(vol_usdt, 2),
                "momentum": "UP" if chg > 0 else "DOWN"
            })
        except (ValueError, TypeError):
            continue

    # Sorting
    if sort_by == "gainers":
        results.sort(key=lambda x: x["change_24h"], reverse=True)
    elif sort_by == "losers":
        results.sort(key=lambda x: x["change_24h"])
    elif sort_by == "price_desc":
        results.sort(key=lambda x: x["price"], reverse=True)
    elif sort_by == "name":
        results.sort(key=lambda x: x["coin"])
    else: # default: volume
        results.sort(key=lambda x: x["volume_usdt"], reverse=True)

    return results[:limit]


def get_top_gainers(limit: int = 8):
    """Fetches top gaining USDT-M Perpetual Futures pairs."""
    all_coins = get_all_cryptos(sort_by="gainers", limit=limit)
    return [{
        "coin": c["coin"],
        "market": c["symbol"],
        "contract": c["contract"],
        "last_price": c["price"],
        "change_float": c["change_24h"],
        "volume": c["volume_coin"]
    } for c in all_coins]


_RADAR_CACHE = {
    "data": None,
    "timestamp": 0
}

_SIGNALS_CACHE = {}
_ANALYZE_CACHE = {}


def get_market_radar(limit: int = 10):
    """Fetches top Bullish (gainers) and top Bearish (losers) Perpetual Futures on CoinDCX with 45s cache."""
    global _RADAR_CACHE
    now = time.time()
    if _RADAR_CACHE["data"] and (now - _RADAR_CACHE["timestamp"]) < 45.0:
        return _RADAR_CACHE["data"]

    gainers = get_all_cryptos(sort_by="gainers", limit=limit)
    losers = get_all_cryptos(sort_by="losers", limit=limit)

    res = {
        "bullish": [{
            "coin": c["coin"],
            "market": c["symbol"],
            "contract": c["contract"],
            "price": c["price"],
            "change": c["change_24h"]
        } for c in gainers],
        "bearish": [{
            "coin": c["coin"],
            "market": c["symbol"],
            "contract": c["contract"],
            "price": c["price"],
            "change": c["change_24h"]
        } for c in losers]
    }
    _RADAR_CACHE["data"] = res
    _RADAR_CACHE["timestamp"] = now
    return res


_BTC_REGIME_CACHE = {
    "regime": "NEUTRAL",
    "rsi": 50.0,
    "timestamp": 0
}

def get_btc_macro_regime(client=None) -> Dict[str, Any]:
    """
    Evaluates Bitcoin (BTC) 1h & 15m trend, EMA21, and RSI to determine macro market regime.
    Protects altcoins from taking wrong-way LONGs when Bitcoin is dumping.
    """
    global _BTC_REGIME_CACHE
    now = time.time()
    if _BTC_REGIME_CACHE["timestamp"] and (now - _BTC_REGIME_CACHE["timestamp"]) < 45.0:
        return _BTC_REGIME_CACHE

    if not getattr(config, "BTC_REGIME_FILTER_ENABLED", True):
        return {"regime": "NEUTRAL", "rsi": 50.0, "timestamp": now}

    try:
        from coindcx_client import CoinDCXClient
        from strategy import calculate_indicators
        c = client or CoinDCXClient()
        df = c.get_candles(pair="B-BTC_USDT", interval="1h", limit=25)
        if df is not None and len(df) >= 15:
            ind = calculate_indicators(df)
            last = ind.iloc[-1]
            close = float(last["close"])
            ema21 = float(last["ema_slow"])
            rsi = float(last["rsi"])

            bearish_rsi = getattr(config, "BTC_BEARISH_RSI_THRESHOLD", 48.0)
            bullish_rsi = getattr(config, "BTC_BULLISH_RSI_THRESHOLD", 52.0)

            if close > ema21 and rsi >= bullish_rsi:
                regime = "BULLISH" # Altcoin LONGs favored
            elif close < ema21 or rsi <= bearish_rsi:
                regime = "BEARISH" # Block Altcoin LONGs, prioritize SHORTS
            else:
                regime = "NEUTRAL"

            res = {
                "regime": regime,
                "rsi": round(rsi, 1),
                "close": close,
                "ema21": round(ema21, 2),
                "timestamp": now
            }
            _BTC_REGIME_CACHE = res
            return res
    except Exception as e:
        print(f"[BTC Macro Guard Notice]: {e}")

    return {"regime": "NEUTRAL", "rsi": 50.0, "timestamp": now}


_MACRO_TREND_CACHE: Dict[str, Any] = {}

def check_macro_daily_trend(coin: str, client=None) -> Dict[str, Any]:
    """
    Evaluates 7-day to 30-day macro trend from daily (1d) candles to prevent buying
    multi-week falling knives (like FET -18% or ZRO -7% on Render).
    """
    global _MACRO_TREND_CACHE
    now = time.time()
    clean_coin = coin.upper().replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "").replace("USDT", "")

    if clean_coin in _MACRO_TREND_CACHE:
        entry = _MACRO_TREND_CACHE[clean_coin]
        if (now - entry.get("timestamp", 0)) < 300.0:  # 5 min cache
            return entry

    res = {
        "trend": "NEUTRAL",
        "ret_7d": 0.0,
        "ret_14d": 0.0,
        "price_above_ema": True,
        "is_falling_knife": False,
        "is_parabolic_pump": False,
        "timestamp": now
    }

    if not getattr(config, "MACRO_TREND_FILTER_ENABLED", True):
        return res

    try:
        from coindcx_client import CoinDCXClient
        c = client or CoinDCXClient()
        candles = c.get_futures_candles(clean_coin, interval="1d", limit=20)
        if candles and len(candles) >= 8:
            cur_p = float(candles[0].get("close", 0))
            idx_7d = min(len(candles) - 1, 6)
            idx_14d = min(len(candles) - 1, 13)
            p_7d = float(candles[idx_7d].get("close", cur_p))
            p_14d = float(candles[idx_14d].get("close", cur_p))

            ret_7d = round(((cur_p - p_7d) / max(1e-6, p_7d)) * 100.0, 2)
            ret_14d = round(((cur_p - p_14d) / max(1e-6, p_14d)) * 100.0, 2)

            closes = [float(cd.get("close", 0)) for cd in candles[:10] if float(cd.get("close", 0)) > 0]
            avg_10d = sum(closes) / max(1, len(closes))
            price_above_ema = cur_p >= avg_10d

            max_drop = getattr(config, "MAX_ALLOWABLE_7D_DOWNTREND_PCT", -6.0)
            is_falling_knife = (ret_7d <= max_drop) or (ret_14d <= (max_drop * 1.5) and not price_above_ema)
            is_parabolic_pump = ret_7d >= 18.0

            if is_falling_knife:
                trend = "DOWNTREND"
            elif price_above_ema and ret_7d > 1.0:
                trend = "UPTREND"
            else:
                trend = "NEUTRAL"

            res = {
                "trend": trend,
                "ret_7d": ret_7d,
                "ret_14d": ret_14d,
                "price_above_ema": price_above_ema,
                "is_falling_knife": is_falling_knife,
                "is_parabolic_pump": is_parabolic_pump,
                "timestamp": now
            }
            _MACRO_TREND_CACHE[clean_coin] = res
            return res
    except Exception as e:
        print(f"[Macro Trend Guard Notice for {clean_coin}]: {e}")

    return res



def scan_all_crypto_signals(min_confidence: int = 70, direction: str = "ALL", limit: int = 35) -> List[Dict[str, Any]]:
    """
    High-Performance Multi-Crypto Quantitative Scanner with 90s in-memory caching.
    """
    global _SIGNALS_CACHE
    now = time.time()
    cache_key = (min_confidence, direction, limit)
    cached = _SIGNALS_CACHE.get(cache_key)
    if cached and (now - cached["timestamp"]) < 90.0:
        return cached["data"]

    from coindcx_client import CoinDCXClient
    import predictor

    tickers = _fetch_all_raw_tickers()
    if not tickers:
        return []

    # 1. EXIT-ONLY / DELISTING FILTER:
    # Completely blocks contracts that are in 'SETTLING', 'DELIVERING', or non-trading status on futures.
    exit_only_set = set()
    if getattr(config, "FILTER_EXIT_ONLY_CONTRACTS", True):
        try:
            r_info = requests.get("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=3).json()
            exit_only_set = {
                s["symbol"].replace("USDT", "") 
                for s in r_info.get("symbols", []) 
                if s.get("status") != "TRADING"
            }
        except Exception:
            exit_only_set = set()

    # 2. INSTITUTIONAL LIQUIDITY & ANTI-GHOST FILTER:
    # Requires minimum $5,000,000 USDT 24h volume.
    # Excludes stablecoins, fiat mirrors, and extreme unnatural pump-and-dump spikes (>35% or <-35%).
    min_vol = getattr(config, "MIN_LIQUIDITY_USDT", 5_000_000.0)
    max_volatility = getattr(config, "MAX_24H_VOLATILITY_PCT", 35.0)
    stable_blacklist = set(getattr(config, "STABLECOIN_BLACKLIST", {
        "USDT", "USDC", "FDUSD", "TUSD", "BUSD", "DAI", "USDP", "EUR", "AEUR"
    }))
    peg_min = getattr(config, "STABLECOIN_PRICE_MIN", 0.96)
    peg_max = getattr(config, "STABLECOIN_PRICE_MAX", 1.04)

    def is_peg_or_stable(t_item: dict) -> bool:
        sym = t_item.get("symbol", "").replace("USDT", "")
        if sym in stable_blacklist:
            return True
        try:
            lp = float(t_item.get("lastPrice", 0) or 0)
            if peg_min <= lp <= peg_max:
                return True
        except (ValueError, TypeError):
            pass
        return False

    usdt_pairs = [
        t for t in tickers 
        if t.get("symbol", "").endswith("USDT") 
        and t.get("priceChangePercent")
        and float(t.get("quoteVolume", 0) or 0) >= min_vol
        and abs(float(t.get("priceChangePercent", 0))) <= max_volatility
        and t.get("symbol", "").replace("USDT", "") not in exit_only_set
        and not is_peg_or_stable(t)
    ]
    if not usdt_pairs:
        # Fallback to top volume liquid pairs if volume was unusually high
        usdt_pairs = [
            t for t in tickers 
            if t.get("symbol", "").endswith("USDT") 
            and t.get("priceChangePercent")
            and t.get("symbol", "").replace("USDT", "") not in exit_only_set
            and not is_peg_or_stable(t)
        ]
        usdt_pairs = sorted(usdt_pairs, key=lambda x: float(x.get("quoteVolume", 0) or 0), reverse=True)[:35]
        if not usdt_pairs:
            return []

    # Gather top liquid candidates: top gainers, top volume, top dip/short candidates
    usdt_pairs_sorted_gain = sorted(usdt_pairs, key=lambda x: float(x.get("priceChangePercent", 0)), reverse=True)
    usdt_pairs_sorted_vol = sorted(usdt_pairs, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
    usdt_pairs_sorted_loss = sorted(usdt_pairs, key=lambda x: float(x.get("priceChangePercent", 0)))

    candidate_symbols = []
    seen = set()

    for pool in [usdt_pairs_sorted_gain[:15], usdt_pairs_sorted_vol[:20], usdt_pairs_sorted_loss[:15]]:
            sym = item.get("symbol", "").replace("USDT", "")
            if sym.isascii() and sym.isalnum() and sym not in seen and not is_peg_or_stable(item):
                seen.add(sym)
                candidate_symbols.append((sym, float(item.get("priceChangePercent", 0)), float(item.get("quoteVolume", 0))))

    client = CoinDCXClient()

    def evaluate_coin_multi_timeframe(coin_sym: str, chg_24h: float, c_1h: list) -> Dict[str, Any]:
        """
        True multi-timeframe evaluator across 1d, 1h, 15m, 5m, 1m with consensus, anti-wick gate & safe leverage.
        """
        # 1. Daily Trend (1d)
        c_1d = "GREEN" if chg_24h > 0 else "RED"

        # 2. 1-Hour Trend (1h)
        if len(c_1h) >= 2:
            latest_1h = c_1h[0]
            c_1h_trend = "GREEN" if latest_1h["close"] >= latest_1h["open"] else "RED"
        else:
            c_1h_trend = c_1d

        # 3. 15-Minute Trend (15m)
        try:
            c_15m_data = client.get_futures_candles(coin_sym, interval="15m", limit=5)
            if c_15m_data and len(c_15m_data) >= 2:
                l15 = c_15m_data[0]
                c_15m = "GREEN" if l15["close"] >= l15["open"] else "RED"
            else:
                c_15m = c_1h_trend
        except Exception:
            c_15m = c_1h_trend

        # 4. 5-Minute Momentum (5m)
        try:
            c_5m_data = client.get_futures_candles(coin_sym, interval="5m", limit=5)
            if c_5m_data and len(c_5m_data) >= 2:
                l5 = c_5m_data[0]
                c_5m = "GREEN" if l5["close"] >= l5["open"] else "RED"
            else:
                c_5m = c_15m
        except Exception:
            c_5m = c_15m

        # 5. 1-Minute Timing & Anti-Trap Pullback Gate (1m)
        try:
            c_1m_data = client.get_futures_candles(coin_sym, interval="1m", limit=5)
            if c_1m_data and len(c_1m_data) >= 2:
                l1 = c_1m_data[0]
                c_1m = "GREEN" if l1["close"] >= l1["open"] else "RED"
            else:
                c_1m = c_5m
        except Exception:
            c_1m = c_5m

        tf_results = {"1m": c_1m, "5m": c_5m, "15m": c_15m, "1h": c_1h_trend, "1d": c_1d}
        greens = sum(1 for v in tf_results.values() if v == "GREEN")
        reds = sum(1 for v in tf_results.values() if v == "RED")

        # Require strict confluence: at least 4 out of 5 timeframes must agree!
        if greens >= 4:
            consensus = "UP"
            agreement = greens
        elif reds >= 4:
            consensus = "DOWN"
            agreement = reds
        else:
            consensus = "MIXED"
            agreement = max(greens, reds)

        c_up = coin_sym.upper()
        if c_up in ["BTC", "WBTC"]:
            lev = 10 if agreement >= 4 else 8
        elif c_up == "ETH":
            lev = 8 if agreement >= 4 else 6
        elif abs(chg_24h) >= 10.0:  # High-Beta volatile altcoin -> Safe 3x leverage
            lev = getattr(config, "MAX_HIGH_BETA_LEVERAGE", 3)
        else: # Standard altcoin -> Safe 4x leverage
            lev = getattr(config, "MAX_MID_BETA_LEVERAGE", 4)

        boost = 10 if agreement == 5 else (6 if agreement == 4 else 0)

        return {
            "consensus": consensus,
            "agreement": agreement,
            "timeframes": tf_results,
            "adaptive_leverage": lev,
            "confidence_boost": boost
        }

    def _eval_coin(coin_tuple):
        coin, chg_24h, vol_usdt = coin_tuple
        try:
            candles = client.get_futures_candles(coin, interval="1h", limit=25)
            if not candles or len(candles) < 15:
                return None
            df = pd.DataFrame(candles[::-1])
            pred = predictor.predict_next_move(df, forecast_steps=10)
            if not pred or pred.get("direction") == "SIDEWAYS":
                return None

            mtf = evaluate_coin_multi_timeframe(coin, chg_24h, candles)
            if mtf["consensus"] == "MIXED" or mtf["agreement"] < 4:
                return None

            dir_match = mtf["consensus"]

            # Bitcoin King Macro Regime Guard:
            btc_macro = get_btc_macro_regime(client)
            if btc_macro.get("regime") == "BEARISH" and dir_match == "UP" and coin not in ["BTC", "WBTC"]:
                # If Bitcoin is bearish, block altcoin LONGs unless 5/5 unanimous MTF consensus!
                if mtf.get("agreement", 0) < 5:
                    return None

            # Macro Higher-Timeframe Trend Shield (Anti-Falling Knife):
            macro_trend = check_macro_daily_trend(coin, client)
            if dir_match == "UP" and macro_trend.get("is_falling_knife", False):
                # Block LONG on multi-week dumping coins (prevents FET -18% / ZRO -7% trapped trades)
                return None
            if dir_match == "DOWN" and macro_trend.get("is_parabolic_pump", False):
                # Block SHORT on parabolic momentum leaders
                return None

            raw_prob = pred.get("probability", 50)
            prob = min(96, raw_prob + mtf.get("confidence_boost", 2))

            effective_min_conf = int(min_confidence or 86)
            if prob < effective_min_conf:
                return None
            if direction != "ALL" and dir_match != direction.upper():
                return None

            adaptive_lev = mtf.get("adaptive_leverage", 8)
            agreement_str = f"{mtf.get('agreement', 3)}/5 {dir_match}"

            return {
                "coin": coin,
                "symbol": f"{coin}USDT",
                "contract": f"{coin}USDT.P",
                "direction": dir_match,
                "probability": prob,
                "adaptive_leverage": adaptive_lev,
                "mtf_agreement": agreement_str,
                "mtf_timeframes": mtf.get("timeframes", {}),
                "confidence_tier": "A+" if mtf.get("agreement") == 5 else ("A" if mtf.get("agreement") == 4 else "HIGH"),
                "signal_type": f"{mtf.get('agreement', 3)}/5 MTF {dir_match}",
                "current_price": pred.get("current_price"),
                "target_price": pred.get("target_price"),
                "stop_loss": pred.get("stop_loss"),
                "risk_reward_ratio": pred.get("risk_reward_ratio", 2.0),
                "expected_change_pct": pred.get("expected_change_pct", 0.0),
                "rsi": pred.get("rsi", 50),
                "change_24h": round(chg_24h, 2),
                "volume_usdt": round(vol_usdt, 0),
                "confluences": pred.get("confluences", [])[:4],
                "summary": pred.get("summary", ""),
                "timestamp": int(time.time() * 1000)
            }
        except Exception:
            return None

    # Lightweight parallel evaluation with 4 workers
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        scan_results = [r for r in executor.map(_eval_coin, candidate_symbols) if r is not None]

    scan_results.sort(key=lambda x: (x["probability"], abs(x["expected_change_pct"])), reverse=True)
    final_res = scan_results[:limit]
    _SIGNALS_CACHE[cache_key] = {"data": final_res, "timestamp": now}
    return final_res


from coindcx_client import CoinDCXClient

def analyze_coin(symbol_or_pair: str, interval: str = "1h", limit: int = 60):
    """
    Analyzes true Perpetual Futures chart data, funding rate, mark price, and indicators.
    Cached for 8 seconds to prevent redundant processing.
    """
    global _ANALYZE_CACHE
    now = time.time()
    cache_key = (symbol_or_pair.upper(), str(interval).lower(), int(limit))
    cached = _ANALYZE_CACHE.get(cache_key)
    if cached and (now - cached["timestamp"]) < 8.0:
        return cached["data"]

    clean_sym = symbol_or_pair.upper().replace("-", "").replace("_", "").replace("USDT", "").replace("B", "", 1) if symbol_or_pair.startswith("B-") else symbol_or_pair.upper().replace("-", "").replace("_", "").replace("USDT", "")
    pair_name = f"B-{clean_sym}_USDT"

    client = CoinDCXClient()
    df = client.get_candles(pair=pair_name, interval=interval, limit=limit)
    if df is None or len(df) == 0:
        return None

    futures_stats = client.get_futures_stats(clean_sym)

    try:
        # Indicators
        df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
        df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

        # RSI
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()
        rs = avg_gain / (avg_loss + 1e-9)
        df["rsi"] = 100.0 - (100.0 / (1.0 + rs))

        curr = df.iloc[-1]
        price = curr["close"]
        ema9 = curr["ema9"]
        ema21 = curr["ema21"]
        ema50 = curr["ema50"]
        rsi = curr["rsi"]

        # Support & Resistance (recent 30 candles)
        recent_window = df.tail(30)
        resistance = recent_window["high"].max()
        support = recent_window["low"].min()

        # Prediction Logic for Futures
        if rsi > 75:
            trend = "EXTREME OVERBOUGHT (FUTURES PULLBACK WARNING)"
            suggestion = "Caution: Price has surged heavily. High risk of long squeeze / liquidation dump. Avoid chasing long; look for dip entries."
        elif rsi > 55 and ema9 > ema21:
            trend = "STRONG BULLISH MOMENTUM (UP / LONG)"
            suggestion = "Upward continuation likely. Look for long entries on pullbacks near EMA 9/21 with tight Stop-Loss."
        elif rsi < 30:
            trend = "OVERSOLD (POTENTIAL SHORT SQUEEZE BOUNCE)"
            suggestion = "Heavily discounted. Watch for reversal signals before buying long."
        elif ema9 < ema21:
            trend = "BEARISH DOWNTREND (SHORT FAVORABLE)"
            suggestion = "Sellers in control. In futures, shorting rallies or remaining in cash is safer."
        else:
            trend = "CONSOLIDATION / NEUTRAL RANGE"
            suggestion = "Ranging sideways. Wait for breakout above resistance or bounce off support."

        result = {
            "pair": pair_name,
            "coin": clean_sym,
            "contract": futures_stats.get("contract", f"{clean_sym}USDT.P"),
            "interval": interval,
            "price": price,
            "mark_price": futures_stats.get("mark_price", price),
            "funding_rate": futures_stats.get("funding_rate", 0.01),
            "high_24h": futures_stats.get("high_24h", resistance),
            "low_24h": futures_stats.get("low_24h", support),
            "change_24h": futures_stats.get("change_24h", 0.0),
            "ema9": ema9,
            "ema21": ema21,
            "ema50": ema50,
            "rsi": rsi,
            "support": support,
            "resistance": resistance,
            "trend": trend,
            "suggestion": suggestion,
        }
        _ANALYZE_CACHE[cache_key] = {"data": result, "timestamp": now}
        return result
    except Exception as e:
        print(f"[Error analyzing {clean_sym}]: {e}")
        return None


def print_analysis(res: dict):
    if not res:
        print("Could not retrieve chart data for this coin.")
        return

    print("\n" + "=" * 68)
    print(f"  CHART ANALYSIS & PREDICTION: {res['coin']} (Timeframe: {res['interval']})")
    print("=" * 68)
    print(f" Current Price    : ${res['price']:,.4f}" if "USDT" in res["pair"] else f" Current Price    : INR {res['price']:,.2f}")
    print(f" 24h Resistance   : {res['resistance']:,.4f} (Ceiling / Target)")
    print(f" Recent Support   : {res['support']:,.4f} (Floor / Stop-Loss zone)")
    print("-" * 68)
    print(f" Technical Trend  : {res['trend']}")
    print(f" RSI Indicator    : {res['rsi']:.1f}  " + ("(Overheated > 70)" if res['rsi'] > 70 else "(Healthy Momentum)" if res['rsi'] > 50 else "(Weak/Oversold)"))
    print(f" Moving Averages  : EMA(9): {res['ema9']:.4f} | EMA(21): {res['ema21']:.4f} | EMA(50): {res['ema50']:.4f}")
    print("-" * 68)
    print(f" Price Outlook    : {res['suggestion']}")
    print("=" * 68 + "\n")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_coin = sys.argv[1]
        res = analyze_coin(target_coin)
        print_analysis(res)
    else:
        print("\nScanning Top Growing Crypto Futures on CoinDCX...")
        gainers = get_top_gainers(limit=6)
        print(f"{'Coin':<12} {'Price (USDT)':<15} {'24h Change':<12}")
        print("-" * 42)
        for g in gainers:
            print(f"{g['market']:<12} ${float(g['last_price']):<14.4f} +{g['change_float']:.2f}%")
        
        print("\nTip: Run 'python scanner.py <COIN>' (e.g. python scanner.py CRV) for deep chart analysis!")
