import time
import json
import hmac
import hashlib
import requests
import pandas as pd
from typing import Optional, Dict, Any
import config


class CoinDCXClient:
    """
    Client for CoinDCX Public & Private REST API.
    Supports live market data fetching, paper trading, and real order execution.
    """

    PUBLIC_URL = "https://public.coindcx.com"
    API_URL = "https://api.coindcx.com"

    def __init__(self, api_key: str = "", api_secret: str = ""):
        self.api_key = api_key or config.COINDCX_API_KEY
        self.api_secret = api_secret or config.COINDCX_API_SECRET

    def _get_headers(self, json_body: str) -> Dict[str, str]:
        """Generate HMAC SHA256 signature for private endpoints."""
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            json_body.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-AUTH-APIKEY": self.api_key,
            "X-AUTH-SIGNATURE": signature,
        }

    def get_current_price(self, symbol: str = config.SYMBOL) -> Optional[float]:
        """Fetch current market price for symbol (e.g., BTCINR)."""
        try:
            url = f"{self.API_URL}/exchange/ticker"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                tickers = response.json()
                for ticker in tickers:
                    if ticker.get("market") == symbol:
                        return float(ticker.get("last_price", 0))
        except Exception as e:
            print(f"[Error] Failed to fetch current price: {e}")
        return None

    def get_candles(self, pair: str = config.CANDLE_PAIR, interval: str = config.TIMEFRAME, limit: int = 50) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV candles from CoinDCX.
        Supports: '1m', '5m' (auto-resampled), '15m', '1h', '1d' (case-insensitive).
        Returns a pandas DataFrame sorted in chronological order (oldest to newest).
        """
        raw_candles = self.get_raw_candles(pair=pair, interval=interval, limit=limit)
        if not raw_candles:
            return None
        try:
            # Data comes newest first; reverse to oldest first
            df = pd.DataFrame(raw_candles[::-1])
            df["time"] = pd.to_datetime(df["time"], unit="ms")
            numeric_cols = ["open", "high", "low", "close", "volume"]
            df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric)
            return df
        except Exception as e:
            print(f"[Error] Failed to format candles DataFrame: {e}")
            return None

    def get_futures_candles(self, pair: str, interval: str = "1h", limit: int = 50) -> list:
        """
        Fetches true USDT-M Perpetual Futures Candlesticks.
        CoinDCX routes all B- futures instruments directly to USDT-M Perpetual Contracts.
        Returns a list of candle dictionaries (newest first).
        """
        clean = pair.upper().replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "").replace("USDT", "")
        futures_symbol = f"{clean}USDT"
        
        tf = (interval or "1h").strip().lower()
        if tf in ["d", "1day"]:
            tf = "1d"
        elif tf in ["15min"]:
            tf = "15m"
        elif tf in ["5min"]:
            tf = "5m"
        elif tf in ["1min"]:
            tf = "1m"
        elif tf not in ["1m", "5m", "15m", "1h", "1d"]:
            tf = "1h"

        # 1. Primary: CoinDCX Official Public Candles
        try:
            url = f"{self.PUBLIC_URL}/market_data/candles"
            params = {"pair": f"B-{clean}_USDT", "interval": tf, "limit": limit}
            res = requests.get(url, params=params, timeout=4)
            if res.status_code == 200:
                raw = res.json()
                if isinstance(raw, list) and len(raw) > 0:
                    candles = []
                    for c in raw:
                        candles.append({
                            "open": float(c.get("open", 0)),
                            "high": float(c.get("high", 0)),
                            "low": float(c.get("low", 0)),
                            "close": float(c.get("close", 0)),
                            "volume": float(c.get("volume", 0)),
                            "time": int(c.get("time", 0))
                        })
                    return candles
        except Exception:
            pass

        # 2. Secondary fallback: Binance Futures
        try:
            url = "https://fapi.binance.com/fapi/v1/klines"
            params = {"symbol": futures_symbol, "interval": tf, "limit": limit}
            res = requests.get(url, params=params, timeout=3)
            if res.status_code == 200:
                raw = res.json()
                candles = []
                for c in reversed(raw): # newest first
                    candles.append({
                        "open": float(c[1]),
                        "high": float(c[2]),
                        "low": float(c[3]),
                        "close": float(c[4]),
                        "volume": float(c[5]),
                        "time": int(c[0])
                    })
                return candles
        except Exception:
            pass

        # Fallback to CoinDCX spot candles
        return self.get_spot_raw_candles(pair=f"B-{clean}_USDT", interval=tf, limit=limit)

    def get_futures_stats(self, symbol_or_pair: str) -> dict:
        """
        Fetches live Futures statistics: Mark Price, Index Price, Funding Rate, 24h High, 24h Low.
        """
        clean = symbol_or_pair.upper().replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "").replace("USDT", "")
        futures_symbol = f"{clean}USDT"
        try:
            r_p = requests.get(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={futures_symbol}", timeout=4).json()
            r_t = requests.get(f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={futures_symbol}", timeout=4).json()
            return {
                "symbol": futures_symbol,
                "contract": f"{clean}USDT.P (Perpetual)",
                "mark_price": float(r_p.get("markPrice", 0)),
                "index_price": float(r_p.get("indexPrice", 0)),
                "funding_rate": round(float(r_p.get("lastFundingRate", 0)) * 100, 4),
                "next_funding_time": int(r_p.get("nextFundingTime", 0)),
                "high_24h": float(r_t.get("highPrice", 0)),
                "low_24h": float(r_t.get("lowPrice", 0)),
                "change_24h": round(float(r_t.get("priceChangePercent", 0)), 2),
                "volume_24h": float(r_t.get("volume", 0)),
            }
        except Exception:
            pass

        # CoinDCX Public Ticker Fallback
        try:
            raw = requests.get(f"{self.PUBLIC_URL}/exchange/ticker", timeout=3).json()
            for t in raw:
                if t.get("market") == futures_symbol:
                    lp = float(t.get("last_price", 0) or 0)
                    return {
                        "symbol": futures_symbol,
                        "contract": f"{clean}USDT.P (Perpetual)",
                        "mark_price": lp,
                        "index_price": lp,
                        "funding_rate": 0.01,
                        "next_funding_time": int(time.time() * 1000) + 3600000,
                        "high_24h": float(t.get("high", 0) or lp),
                        "low_24h": float(t.get("low", 0) or lp),
                        "change_24h": round(float(t.get("change_24_hour", 0) or 0), 2),
                        "volume_24h": float(t.get("volume", 0) or 0),
                    }
        except Exception:
            pass

        return {
            "symbol": futures_symbol,
            "contract": f"{clean}USDT.P (Perpetual)",
            "mark_price": 0.0,
            "index_price": 0.0,
            "funding_rate": 0.01,
            "next_funding_time": 0,
            "high_24h": 0.0,
            "low_24h": 0.0,
            "change_24h": 0.0,
            "volume_24h": 0.0,
        }

    def get_raw_candles(self, pair: str, interval: str = "1h", limit: int = 50) -> list:
        """
        Primary candle fetcher: Uses Perpetual Futures data with Spot fallback.
        """
        return self.get_futures_candles(pair=pair, interval=interval, limit=limit)

    def get_spot_raw_candles(self, pair: str, interval: str = "1h", limit: int = 50) -> list:
        """
        Fetches raw spot candle dictionaries from CoinDCX.
        Handles 5m resampling.
        """
        tf = (interval or "1h").strip().lower()

        # Handle 5m by fetching 1m and resampling
        if tf in ["5m", "5min"]:
            try:
                fetch_limit = min(300, max(50, limit * 5))
                url = f"{self.PUBLIC_URL}/market_data/candles"
                res = requests.get(url, params={"pair": pair, "interval": "1m", "limit": fetch_limit}, timeout=10)
                if res.status_code == 200 and res.json():
                    raw = res.json()[::-1] # oldest first
                    df = pd.DataFrame(raw)
                    df["time_dt"] = pd.to_datetime(df["time"], unit="ms")
                    df = df.set_index("time_dt")
                    for col in ["open", "high", "low", "close", "volume"]:
                        df[col] = pd.to_numeric(df[col])

                    resampled = df.resample("5min").agg({
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum"
                    }).dropna().reset_index()

                    resampled["time"] = [int(t.timestamp() * 1000) for t in resampled["time_dt"]]
                    resampled = resampled.drop(columns=["time_dt"])
                    result = resampled[["open", "high", "low", "close", "volume", "time"]].tail(limit).to_dict(orient="records")
                    return result[::-1]
            except Exception as e:
                print(f"[Error resampling 5m candles]: {e}")
            api_tf = "1m"
        elif tf in ["1d", "1day", "d"]:
            api_tf = "1d"
        elif tf in ["15m", "15min"]:
            api_tf = "15m"
        elif tf in ["1m", "1min", "m"]:
            api_tf = "1m"
        else:
            api_tf = "1h"

        try:
            url = f"{self.PUBLIC_URL}/market_data/candles"
            params = {"pair": pair, "interval": api_tf, "limit": limit}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"[Error fetching spot candles]: {e}")
        return []

    def get_futures_wallets(self) -> list:
        """Fetch Futures (Derivatives) Wallets from CoinDCX."""
        if not self.api_key or not self.api_secret:
            return [{"currency_short_name": "INR", "balance": 1154.53}]
        try:
            url = f"{self.API_URL}/exchange/v1/derivatives/futures/wallets"
            timestamp = int(round(time.time() * 1000))
            body = {"timestamp": timestamp}
            json_body = json.dumps(body, separators=(",", ":"))
            headers = self._get_headers(json_body)
            response = requests.get(url, data=json_body, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"[Warning] Failed to fetch futures wallets: {response.status_code} {response.text}")
        except Exception as e:
            print(f"[Error] get_futures_wallets error: {e}")
        return []

    def get_futures_cross_margin(self, currency: str = "INR") -> dict:
        """Fetch Futures Cross Margin Details from CoinDCX."""
        if not self.api_key or not self.api_secret:
            return {"total_wallet_balance": 1154.53, "available_balance_cross": 1154.53}
        try:
            url = f"{self.API_URL}/exchange/v1/derivatives/futures/positions/cross_margin_details"
            timestamp = int(round(time.time() * 1000))
            body = {"timestamp": timestamp, "currency_short_name": currency}
            json_body = json.dumps(body, separators=(",", ":"))
            headers = self._get_headers(json_body)
            response = requests.get(url, data=json_body, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"[Error] get_futures_cross_margin error: {e}")
        return {}

    def get_futures_positions(self) -> list:
        """Fetch active CoinDCX Futures Positions."""
        if not self.api_key or not self.api_secret:
            return []
        try:
            url = f"{self.API_URL}/exchange/v1/derivatives/futures/positions"
            timestamp = int(round(time.time() * 1000))
            body = {"timestamp": timestamp}
            json_body = json.dumps(body, separators=(",", ":"))
            headers = self._get_headers(json_body)
            response = requests.post(url, data=json_body, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"[Error] get_futures_positions error: {e}")
        return []

    def get_account_balances(self) -> Dict[str, Any]:
        """
        Fetch both Futures and Spot wallet balances.
        Prioritizes the Futures Wallet INR (e.g. ₹1,154.53) for derivatives trading.
        """
        if not self.api_key or not self.api_secret:
            return {
                "INR": 1154.53,
                "FUTURES_INR": 1154.53,
                "SPOT_INR": 553.01,
                "PAPER_MODE": True
            }

        balances = {}
        futures_inr = 0.0
        spot_inr = 0.0

        # 1. Fetch Futures Wallet (Total INR 1,154.53)
        try:
            f_wallets = self.get_futures_wallets()
            for w in f_wallets:
                curr = w.get("currency_short_name", "")
                bal = float(w.get("balance", 0))
                locked = float(w.get("locked_balance", 0))
                total_futures = round(bal + locked, 2)
                if curr == "INR":
                    futures_inr = total_futures
                    balances["FUTURES_INR"] = total_futures
                    balances["FUTURES_AVAILABLE_INR"] = round(bal, 2)
                    balances["FUTURES_LOCKED_INR"] = round(locked, 2)
                elif total_futures > 0:
                    balances[f"FUTURES_{curr}"] = total_futures
        except Exception as e:
            print(f"[Error fetching futures wallets]: {e}")

        # 2. Fetch Spot Wallet (INR 553.01)
        try:
            url = f"{self.API_URL}/exchange/v1/users/balances"
            timestamp = int(round(time.time() * 1000))
            body = {"timestamp": timestamp}
            json_body = json.dumps(body, separators=(",", ":"))
            headers = self._get_headers(json_body)

            response = requests.post(url, data=json_body, headers=headers, timeout=10)
            if response.status_code == 200:
                for item in response.json():
                    currency = item.get("currency")
                    balance = float(item.get("balance", 0))
                    if currency == "INR":
                        spot_inr = balance
                        balances["SPOT_INR"] = balance
                    elif balance > 0:
                        balances[currency] = balance
        except Exception as e:
            print(f"[Error fetching spot balances]: {e}")

        # Set primary trading INR balance to Futures INR if available, else Spot INR
        balances["INR"] = futures_inr if futures_inr > 0 else spot_inr
        balances["FUTURES_INR"] = futures_inr
        balances["SPOT_INR"] = spot_inr
        balances["TOTAL_INR"] = futures_inr + spot_inr
        balances["PAPER_MODE"] = False
        return balances

    def place_futures_order(self, side: str, pair: str, quantity: float, leverage: int = 10, order_type: str = "market_order", price: Optional[float] = None) -> Dict[str, Any]:
        """
        Place real or simulated futures order on CoinDCX Derivatives.
        pair format: 'B-BTC_USDT' or 'B-SOON_USDT'.
        """
        clean_pair = pair if pair.startswith("B-") else f"B-{pair}"
        if not clean_pair.endswith("_USDT") and not clean_pair.endswith("_INR"):
            clean_pair = f"{clean_pair}_USDT"

        if config.DRY_RUN:
            return {
                "status": "success",
                "simulated": True,
                "market": "futures",
                "side": side.lower(),
                "pair": clean_pair,
                "quantity": quantity,
                "leverage": leverage,
                "order_type": order_type,
                "price": price,
                "timestamp": time.time(),
            }

        if not self.api_key or not self.api_secret:
            raise ValueError("API Key and Secret required for live futures trading!")

        url = f"{self.API_URL}/exchange/v1/derivatives/futures/orders/create"
        timestamp = int(round(time.time() * 1000))
        order_dict = {
            "pair": clean_pair,
            "side": side.lower(),
            "order_type": order_type,
            "total_quantity": quantity,
            "leverage": leverage,
            "margin_currency_short_name": "INR"
        }
        if order_type == "limit_order" and price:
            order_dict["price"] = price

        body = {
            "timestamp": timestamp,
            "order": order_dict
        }

        json_body = json.dumps(body, separators=(",", ":"))
        headers = self._get_headers(json_body)

        try:
            response = requests.post(url, data=json_body, headers=headers, timeout=10)
            return response.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def cancel_futures_order(self, order_id: str) -> Dict[str, Any]:
        """Cancel a live futures order by ID."""
        if not self.api_key or not self.api_secret:
            return {"status": "success", "simulated": True}
        url = f"{self.API_URL}/exchange/v1/derivatives/futures/orders/cancel"
        timestamp = int(round(time.time() * 1000))
        body = {"timestamp": timestamp, "id": order_id}
        json_body = json.dumps(body, separators=(",", ":"))
        headers = self._get_headers(json_body)
        try:
            response = requests.post(url, data=json_body, headers=headers, timeout=10)
            return response.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def place_order(self, side: str, symbol: str, quantity: float, price_per_unit: float) -> Dict[str, Any]:
        """
        Place buy or sell order.
        If config.DRY_RUN is True, returns simulated filled order.
        """
        if config.DRY_RUN:
            return {
                "status": "success",
                "simulated": True,
                "side": side,
                "symbol": symbol,
                "quantity": quantity,
                "price": price_per_unit,
                "total_inr": quantity * price_per_unit,
                "timestamp": time.time(),
            }

        # Real order execution via CoinDCX API
        if not self.api_key or not self.api_secret:
            raise ValueError("API Key and Secret required for live trading!")

        url = f"{self.API_URL}/exchange/v1/orders/create"
        timestamp = int(round(time.time() * 1000))
        body = {
            "side": side.lower(),               # 'buy' or 'sell'
            "order_type": "market_order",       # instant market fill
            "market": symbol,
            "total_quantity": quantity,
            "timestamp": timestamp
        }
        json_body = json.dumps(body, separators=(",", ":"))
        headers = self._get_headers(json_body)

        try:
            response = requests.post(url, data=json_body, headers=headers, timeout=10)
            return response.json()
        except Exception as e:
            return {"status": "error", "message": str(e)}
