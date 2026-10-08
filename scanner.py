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

    usdt_pairs = [t for t in tickers if t.get("symbol", "").endswith("USDT") and t.get("priceChangePercent")]
    if not usdt_pairs:
        return []

    # Gather top candidates: 4 top gainers, 4 top losers, 4 highest volume (cloud lightweight)
    usdt_pairs_sorted_gain = sorted(usdt_pairs, key=lambda x: float(x.get("priceChangePercent", 0)), reverse=True)
    usdt_pairs_sorted_vol = sorted(usdt_pairs, key=lambda x: float(x.get("quoteVolume", 0)), reverse=True)
    usdt_pairs_sorted_loss = sorted(usdt_pairs, key=lambda x: float(x.get("priceChangePercent", 0)))

    candidate_symbols = []
    seen = set()

    for pool in [usdt_pairs_sorted_gain[:4], usdt_pairs_sorted_loss[:4], usdt_pairs_sorted_vol[:4]]:
        for item in pool:
            sym = item.get("symbol", "").replace("USDT", "")
            if sym.isascii() and sym.isalnum() and sym not in seen:
                seen.add(sym)
                candidate_symbols.append((sym, float(item.get("priceChangePercent", 0)), float(item.get("quoteVolume", 0))))

    client = CoinDCXClient()

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

            dir_match = pred.get("direction", "")
            prob = pred.get("probability", 50)

            if prob < min_confidence:
                return None
            if direction != "ALL" and dir_match != direction.upper():
                return None

            return {
                "coin": coin,
                "symbol": f"{coin}USDT",
                "contract": f"{coin}USDT.P",
                "direction": dir_match,
                "probability": prob,
                "confidence_tier": pred.get("confidence_tier", "HIGH"),
                "signal_type": pred.get("signal_type", "MOMENTUM SETUP"),
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

    # Lightweight parallel evaluation with 3 workers (cloud friendly)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
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
