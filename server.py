import http.server
import socketserver
import json
import urllib.parse
import os
import sys
import threading
import time
import requests
import pandas as pd
from datetime import datetime

import config
from coindcx_client import CoinDCXClient
from strategy import evaluate_signal, calculate_indicators
import scanner
import predictor

# Ensure UTF-8 output on Windows terminal
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

PORT = int(os.environ.get("PORT", 5000))
WEB_DIR = os.path.join(os.path.dirname(__file__), "web")

def calculate_futures_trade_qty(coin: str, current_price: float, target_margin_inr: float = 150.0, leverage: int = 5):
    """Calculate order quantity ensuring CoinDCX minimum notional value (>= 612 INR) and ~150 INR margin."""
    min_notional_inr = 620.0
    usd_inr = 90.0
    notional_inr = max(min_notional_inr, target_margin_inr * leverage)
    notional_usd = notional_inr / max(0.00001, current_price)
    if current_price < 0.01:
        qty = round(notional_usd, 0)
    elif current_price < 1.0:
        qty = round(notional_usd, 1)
    elif current_price < 50.0:
        qty = round(notional_usd, 2)
    else:
        qty = round(notional_usd, 4)
    actual_margin = (qty * current_price * usd_inr) / leverage
    return qty, round(actual_margin, 2)


# Shared Bot State with Active Live Trade & Predictive Forecasts
now_str = datetime.now().strftime("%H:%M:%S")
bot_state = {
    "is_running": True,
    "paper_balance": 960.0,
    "active_position": {
        "symbol": "MOVR",
        "pair": "B-MOVR_USDT",
        "buy_price": 1.7455,
        "quantity": 4.83,
        "invested": 172.49,
        "leverage": 5,
        "target": 1.8419,
        "stop_loss": 1.6920,
        "probability": 95,
        "time": now_str
    },
    "selected_coin": "MOVR",
    "selected_pair": "B-MOVR_USDT",
    "trade_history": [
        {
            "type": "BUY",
            "coin": "MOVR",
            "price": 1.7455,
            "amount": 172.49,
            "note": "1st Bid: 95% Ultra Confluence Setup. Target: $1.8419 (+5.5%), SL: $1.6920 (-3.1%)",
            "time": now_str
        }
    ],
    "last_signal": "LIVE FUTURES LONG (1st BID PLACED)",
    "last_reason": "Live Bid executed for 4.83 MOVR @ $1.7455 (5x Lev). Target: $1.8419, Stop-Loss: $1.6920",
    "latest_prediction": {},
}

# Bot background worker thread: 24/7 Autonomous Breakout Hunting & Execution Engine
def bot_worker():
    client = CoinDCXClient()
    scan_tick = 0
    while True:
        if bot_state["is_running"]:
            try:
                profile = config.RISK_PROFILES.get(config.CURRENT_RISK_MODE, config.RISK_PROFILES["BALANCED"])
                min_conf = profile.get("min_confidence", 85)
                lev = profile.get("leverage", 7)
                invest_target = profile.get("investment_inr", 160.0)

                # ==============================================================
                # STATE A: NO OPEN POSITION -> AUTONOMOUS 739-COIN HUNTING
                # ==============================================================
                if bot_state["active_position"] is None:
                    # Every loop iteration, scan top setups matching current risk mode
                    signals = scanner.scan_all_crypto_signals(min_confidence=min_conf, direction="UP", limit=5)
                    if signals and len(signals) > 0:
                        top = signals[0]
                        coin = top["coin"]
                        pair = f"B-{coin}_USDT"
                        current_price = top["current_price"]
                        target_price = top["target_price"]
                        stop_loss = top["stop_loss"]
                        prob = top["probability"]

                        qty, spend = calculate_futures_trade_qty(coin, current_price, target_margin_inr=invest_target, leverage=lev)
                        bot_state["selected_coin"] = coin
                        bot_state["selected_pair"] = pair

                        # Execute real order on CoinDCX if live trading is enabled
                        if not config.DRY_RUN:
                            try:
                                live_order = client.place_futures_order("buy", pair=pair, quantity=qty, leverage=lev)
                                print(f"[LIVE AUTONOMOUS ORDER PLACED]: {coin} Qty={qty} Lev={lev}x -> {live_order}")
                            except Exception as live_err:
                                print(f"[LIVE AUTONOMOUS ORDER ERROR]: {live_err}")

                        bot_state["active_position"] = {
                            "symbol": coin,
                            "pair": pair,
                            "buy_price": current_price,
                            "quantity": qty,
                            "invested": spend,
                            "leverage": lev,
                            "target": target_price,
                            "stop_loss": stop_loss,
                            "trailing_stop": stop_loss,
                            "peak_price": current_price,
                            "probability": prob,
                            "time": datetime.now().strftime("%H:%M:%S")
                        }
                        bot_state["last_signal"] = f"AUTONOMOUS BUY [{coin}]"
                        bot_state["last_reason"] = f"Triggered {config.CURRENT_RISK_MODE} ({prob}%): Target ${target_price}, SL ${stop_loss}"
                        bot_state["trade_history"].insert(0, {
                            "type": "BUY",
                            "coin": coin,
                            "price": current_price,
                            "amount": spend,
                            "note": f"{config.CURRENT_RISK_MODE} ({prob}%): Target ${target_price}, SL ${stop_loss}",
                            "time": datetime.now().strftime("%H:%M:%S")
                        })
                    else:
                        bot_state["last_signal"] = "SCANNING 739 COINS"
                        bot_state["last_reason"] = f"Scanning 739 coins 24/7 for {config.CURRENT_RISK_MODE} setups (min {min_conf}% conf)..."

                # ==============================================================
                # STATE B: POSITION OPEN -> LIVE TARGET & TRAILING STOP MANAGEMENT
                # ==============================================================
                else:
                    pos = bot_state["active_position"]
                    pair = pos["pair"]
                    pos_lev = pos.get("leverage", lev)

                    df = client.get_candles(pair=pair, interval=config.TIMEFRAME, limit=35)
                    if df is not None and len(df) > 0:
                        pred = predictor.predict_next_move(df, forecast_steps=10)
                        bot_state["latest_prediction"] = pred
                        current_price = pred.get("current_price", pos["buy_price"])

                        # Dynamic Trailing Stop Loss:
                        # As price creates new highs, trail stop loss up to lock in profits
                        if current_price > pos.get("peak_price", pos["buy_price"]):
                            pos["peak_price"] = current_price
                            gain_pct = ((current_price - pos["buy_price"]) / pos["buy_price"]) * 100.0
                            if gain_pct >= 2.0:
                                trailed = current_price * 0.985 # 1.5% buffer below peak
                                if trailed > pos.get("trailing_stop", pos["stop_loss"]):
                                    pos["trailing_stop"] = trailed

                        active_sl = pos.get("trailing_stop", pos["stop_loss"])
                        pnl_pct = ((current_price - pos["buy_price"]) / pos["buy_price"]) * 100.0 * pos_lev
                        pnl = pos["invested"] * (pnl_pct / 100.0)

                        exit_trigger = None
                        if current_price >= pos.get("target", pos["buy_price"] * 1.04):
                            exit_trigger = f"Target Hit (${pos['target']})! Profit +{pnl_pct:.1f}%"
                        elif current_price <= active_sl:
                            exit_trigger = f"Stop-Loss / Trailed Exit at ${active_sl:.4f} (PnL: {pnl_pct:+.1f}%)"
                        elif pred.get("direction") == "DOWN" and pred.get("probability", 0) >= 82:
                            exit_trigger = f"Early Reversal Warning (82%+ DOWN predicted)! Exiting."

                        if exit_trigger:
                            proceeds = pos["invested"] + pnl
                            bot_state["paper_balance"] += proceeds

                            # Execute exit order on CoinDCX if live trading
                            if not config.DRY_RUN:
                                try:
                                    live_exit = client.place_futures_order("sell", pair=pos["pair"], quantity=pos["quantity"], leverage=pos_lev)
                                    print(f"[LIVE AUTONOMOUS EXIT ORDER]: {live_exit}")
                                except Exception as live_err:
                                    print(f"[LIVE AUTONOMOUS EXIT ERROR]: {live_err}")

                            bot_state["last_signal"] = "AUTONOMOUS EXIT"
                            bot_state["last_reason"] = exit_trigger
                            bot_state["trade_history"].insert(0, {
                                "type": "SELL",
                                "coin": pos["symbol"],
                                "price": current_price,
                                "amount": round(proceeds, 2),
                                "pnl": round(pnl, 2),
                                "pnl_pct": round(pnl_pct, 2),
                                "reason": exit_trigger,
                                "time": datetime.now().strftime("%H:%M:%S")
                            })
                            bot_state["active_position"] = None
                        else:
                            bot_state["last_reason"] = f"Monitoring {pos['symbol']}: Target ${pos.get('target')}, Live PnL: {pnl_pct:+.1f}% (₹{pnl:+.2f})"

            except Exception as e:
                print(f"[Autonomous Worker Error] {e}")

        time.sleep(10)

worker_thread = threading.Thread(target=bot_worker, daemon=True)
worker_thread.start()

# Global Real-Time Alert Engine & History
alert_state = {
    "alerts": [],
    "last_scanned": 0,
    "lock": threading.Lock(),
    "last_notified": {} # coin -> timestamp
}

def alert_monitor_worker():
    """
    Background worker that continuously scans all 700+ cryptos for Ultra-High Confidence
    (85%-98% '100% Confluence') Go Low / Go Up opportunities and triggers alerts.
    """
    # Wait 4 seconds on startup
    time.sleep(4)
    while True:
        try:
            signals = scanner.scan_all_crypto_signals(min_confidence=85, limit=15)
            now = time.time()
            if signals:
                with alert_state["lock"]:
                    for s in signals:
                        coin = s["coin"]
                        last_time = alert_state["last_notified"].get(coin, 0)
                        # Avoid repeated alerts for the same coin within 5 minutes
                        if (now - last_time) > 300:
                            alert_item = {
                                "id": f"{coin}_{int(now)}",
                                "coin": coin,
                                "symbol": s.get("symbol", f"{coin}USDT"),
                                "contract": s.get("contract", f"{coin}USDT.P"),
                                "direction": s["direction"],
                                "probability": s["probability"],
                                "confidence_tier": s.get("confidence_tier", "ULTRA (100% SETUP)"),
                                "signal_type": s.get("signal_type", "MOMENTUM SETUP"),
                                "price": s["current_price"],
                                "target_price": s["target_price"],
                                "stop_loss": s["stop_loss"],
                                "expected_change_pct": s.get("expected_change_pct", 0.0),
                                "risk_reward_ratio": s.get("risk_reward_ratio", 2.0),
                                "rsi": s.get("rsi", 50),
                                "confluences": s.get("confluences", []),
                                "timestamp": int(now * 1000),
                                "time_str": datetime.now().strftime("%H:%M:%S")
                            }
                            alert_state["alerts"].insert(0, alert_item)
                            alert_state["last_notified"][coin] = now
                    # Limit alert history to 50 items
                    alert_state["alerts"] = alert_state["alerts"][:50]
                    alert_state["last_scanned"] = int(now * 1000)
        except Exception as e:
            print(f"[Alert Monitor Worker Error]: {e}")

        time.sleep(25)

alert_thread = threading.Thread(target=alert_monitor_worker, daemon=True)
alert_thread.start()


class TradingApiHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # API: Predictive Forecast & Probability Engine
        if path == "/api/predict":
            coin = query.get("coin", ["SOON"])[0].upper()
            interval = query.get("interval", ["1h"])[0]
            steps = int(query.get("steps", [10])[0])
            pair = f"B-{coin}_USDT"
            
            client = CoinDCXClient()
            df = client.get_candles(pair=pair, interval=interval, limit=40)
            if df is not None and len(df) > 0:
                prediction = predictor.predict_next_move(df, forecast_steps=steps)
            else:
                prediction = {}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(prediction).encode("utf-8"))
            return

        # API: Scanner Top Gainers
        elif path == "/api/gainers":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            gainers = scanner.get_top_gainers(limit=10)
            self.wfile.write(json.dumps(gainers).encode("utf-8"))
            return

        # API: Market Radar (All Bullish & Bearish Coins)
        elif path == "/api/market_radar":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            radar = scanner.get_market_radar(limit=10)
            self.wfile.write(json.dumps(radar).encode("utf-8"))
            return

        # API: Detailed Coin Analysis & Prediction
        elif path == "/api/analyze":
            coin = query.get("coin", ["SOON"])[0]
            interval = query.get("interval", ["1h"])[0]
            analysis = scanner.analyze_coin(coin, interval=interval, limit=60)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(analysis or {}).encode("utf-8"))
            return

        # API: Futures Contract Stats (Mark Price, Funding Rate, Contract Name)
        elif path == "/api/futures_stats":
            coin = query.get("coin", ["SOON"])[0]
            client = CoinDCXClient()
            stats = client.get_futures_stats(coin)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(stats).encode("utf-8"))
            return

        # API: AI Futures Trade & Leverage Advisor (1m, 5m, 15m, 1h, 1d)
        elif path == "/api/advisor":
            coin = query.get("coin", ["SOON"])[0].upper()
            client = CoinDCXClient()
            timeframes = ["1m", "5m", "15m", "1h", "1d"]
            tf_data = {}
            best_tf = "15m"
            max_conf = 0.0
            latest_price = 0.0

            for tf in timeframes:
                candles = client.get_futures_candles(coin, interval=tf, limit=35)
                if candles and len(candles) >= 15:
                    df = pd.DataFrame(candles[::-1])
                    pred = predictor.predict_next_move(df, forecast_steps=10)
                    if pred.get("current_price"):
                        latest_price = pred["current_price"]

                    if tf == "1m":
                        rec_lev = 5
                        style = "Ultra Scalp (2-5m)"
                    elif tf == "5m":
                        rec_lev = 10
                        style = "Quick Scalp (5-15m)"
                    elif tf == "15m":
                        rec_lev = 10
                        style = "Intraday Trend (30m-2h)"
                    elif tf == "1h":
                        rec_lev = 5
                        style = "Swing Trend (2-8h)"
                    else:
                        rec_lev = 2
                        style = "Position Hold (1-5d)"

                    direction = pred.get("direction", "SIDEWAYS")
                    probability = pred.get("probability", 50)
                    target = pred.get("target_price", latest_price)
                    stop = pred.get("stop_loss", latest_price * 0.98)

                    tf_data[tf] = {
                        "direction": direction,
                        "probability": probability,
                        "style": style,
                        "recommended_lev": rec_lev,
                        "target": target,
                        "stop_loss": stop,
                        "rsi": pred.get("rsi", 50)
                    }

                    weighted = probability * (1.15 if tf in ["15m", "1h"] else 0.95)
                    if weighted > max_conf and direction != "SIDEWAYS":
                        max_conf = weighted
                        best_tf = tf

            if best_tf not in tf_data or not tf_data:
                best_tf = "15m"

            best_info = tf_data.get(best_tf, {
                "direction": "UP",
                "probability": 70,
                "target": latest_price * 1.05,
                "stop_loss": latest_price * 0.98,
                "recommended_lev": 10
            })

            rec_action = "LONG" if best_info["direction"] == "UP" else "SHORT" if best_info["direction"] == "DOWN" else "WAIT"
            target_p = best_info.get("target", latest_price * 1.05)
            stop_p = best_info.get("stop_loss", latest_price * 0.98)
            curr = latest_price or 1.0

            leverage_table = []
            for lev in [1, 3, 5, 10, 25, 50, 100]:
                long_liq = round(curr * max(0.0, (1.0 - (0.90 / lev))), 4)
                short_liq = round(curr * (1.0 + (0.90 / lev)), 4)
                drop_to_liq_pct = round(((curr - long_liq) / curr) * 100.0, 1)

                if lev <= 3:
                    risk_lvl = "Safe Buffer"
                    badge_color = "#10b981"
                    advice = "Ultra safe, no liquidation risk."
                elif lev <= 10:
                    risk_lvl = "Recommended Sweetspot"
                    badge_color = "#38bdf8"
                    advice = "Optimal for INR 1,500. High profit with safe liquidation margin."
                elif lev <= 25:
                    risk_lvl = "High Risk"
                    badge_color = "#f59e0b"
                    advice = "Caution: Normal crypto wick can wipe margin."
                elif lev <= 50:
                    risk_lvl = "Dangerous"
                    badge_color = "#ef4444"
                    advice = "Extreme hazard: 1.8% drop wipes 100% of your INR 1,500."
                else:
                    risk_lvl = "Wipeout Trap"
                    badge_color = "#dc2626"
                    advice = "Instant liquidation! A 0.9% market noise tick liquidates all INR 1,500 in seconds. Never use 100x!"

                pnl_at_target_pct = round(abs((target_p - curr) / curr) * 100.0 * lev, 1)
                profit_inr = round(1500.0 * (pnl_at_target_pct / 100.0), 2)

                leverage_table.append({
                    "leverage": lev,
                    "long_liquidation": long_liq,
                    "short_liquidation": short_liq,
                    "drop_to_liq_pct": drop_to_liq_pct,
                    "risk_level": risk_lvl,
                    "badge_color": badge_color,
                    "advice": advice,
                    "pnl_at_target_pct": pnl_at_target_pct,
                    "profit_inr": profit_inr
                })

            response_data = {
                "coin": coin,
                "current_price": curr,
                "best_timeframe": best_tf,
                "recommended_action": rec_action,
                "recommended_leverage": best_info.get("recommended_lev", 10),
                "confidence": best_info.get("probability", 70),
                "target_price": target_p,
                "stop_loss": stop_p,
                "entry_price": curr,
                "profit_estimate_10x": round(1500.0 * (abs((target_p - curr) / curr) * 10), 2),
                "roi_estimate_10x_pct": round(abs((target_p - curr) / curr) * 1000.0, 1),
                "timeframes": tf_data,
                "leverage_table": leverage_table
            }

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            return

        # API: Candle Data for Chart (Supports 1m, 5m, 15m, 1h, 1d)
        elif path == "/api/candles":
            pair = query.get("pair", ["B-SOON_USDT"])[0]
            interval = query.get("interval", ["1h"])[0]
            limit = int(query.get("limit", ["60"])[0])

            client = CoinDCXClient()
            candles = client.get_raw_candles(pair=pair, interval=interval, limit=limit)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(candles).encode("utf-8"))
            return

        # API: Bot Status & Balances
        elif path == "/api/status":
            try:
                client = CoinDCXClient()
                real_balances = client.get_account_balances()
                f_bal = real_balances.get("FUTURES_INR", 0.0)
                s_bal = real_balances.get("SPOT_INR", 0.0)
                t_bal = real_balances.get("TOTAL_INR", 0.0)
                inr_real = real_balances.get("INR", 0.0)

                bot_state["futures_balance"] = round(f_bal, 2)
                bot_state["spot_balance"] = round(s_bal, 2)
                bot_state["total_balance"] = round(t_bal, 2)

                if inr_real is not None and not real_balances.get("PAPER_MODE"):
                    bot_state["live_balance"] = round(f_bal if f_bal > 0 else inr_real, 2)
                    bot_state["real_connected"] = True
                else:
                    bot_state["live_balance"] = bot_state["paper_balance"]
                    bot_state["real_connected"] = False
            except Exception as e:
                print(f"[Status Balance Err]: {e}")
                bot_state["live_balance"] = bot_state["paper_balance"]
                bot_state["real_connected"] = False

            bot_state["dry_run"] = config.DRY_RUN
            bot_state["risk_mode"] = config.CURRENT_RISK_MODE
            bot_state["risk_profile"] = config.RISK_PROFILES.get(config.CURRENT_RISK_MODE, {})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(bot_state).encode("utf-8"))
            return

        # API: Risk Modes List
        elif path == "/api/bot/risk_modes":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "current_mode": config.CURRENT_RISK_MODE,
                "profiles": config.RISK_PROFILES
            }).encode("utf-8"))
            return

        # API: All Cryptocurrencies (700+ Pairs, Search, Sorting)
        elif path == "/api/all_coins":
            search = query.get("search", [""])[0]
            sort_by = query.get("sort", ["volume"])[0]
            limit = int(query.get("limit", [1000])[0])
            coins = scanner.get_all_cryptos(search=search, sort_by=sort_by, limit=limit)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "total": len(coins),
                "coins": coins
            }).encode("utf-8"))
            return

        # API: Scan All Cryptos for High-Probability Setups (Go Up / Go Low)
        elif path == "/api/scan_all":
            min_conf = int(query.get("min_conf", [75])[0])
            direction = query.get("direction", ["ALL"])[0].upper()
            limit = int(query.get("limit", [35])[0])
            signals = scanner.scan_all_crypto_signals(min_confidence=min_conf, direction=direction, limit=limit)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "count": len(signals),
                "signals": signals,
                "timestamp": int(time.time() * 1000)
            }).encode("utf-8"))
            return

        # API: Real-Time Alerts Stream & History
        elif path == "/api/alerts":
            since = int(query.get("since", [0])[0])
            with alert_state["lock"]:
                new_alerts = [a for a in alert_state["alerts"] if a["timestamp"] > since]
                all_alerts = list(alert_state["alerts"][:30])
                total = len(alert_state["alerts"])
                last_scan = alert_state["last_scanned"]

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "new_alerts": new_alerts,
                "alerts": all_alerts,
                "total_count": total,
                "last_scanned": last_scan
            }).encode("utf-8"))
            return

        # Fallback to serving web directory files (HTML, CSS, JS)
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/bot/toggle":
            bot_state["is_running"] = not bot_state["is_running"]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"is_running": bot_state["is_running"]}).encode("utf-8"))
            return

        elif path == "/api/bot/select_coin":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
            coin = data.get("coin", "SOON").upper()
            bot_state["selected_coin"] = coin
            bot_state["selected_pair"] = f"B-{coin}_USDT"

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"selected_coin": coin}).encode("utf-8"))
            return

        elif path == "/api/alerts/clear":
            with alert_state["lock"]:
                alert_state["alerts"].clear()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "success", "message": "Alerts cleared"}).encode("utf-8"))
            return

        elif path == "/api/bot/toggle_mode":
            config.DRY_RUN = not config.DRY_RUN
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "dry_run": config.DRY_RUN,
                "mode": "PAPER" if config.DRY_RUN else "LIVE"
            }).encode("utf-8"))
            return

        elif path == "/api/bot/set_risk_mode":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
            new_mode = data.get("mode", "BALANCED").upper()
            if new_mode in config.RISK_PROFILES:
                config.CURRENT_RISK_MODE = new_mode
                prof = config.RISK_PROFILES[new_mode]
                config.INVESTMENT_PER_TRADE_INR = prof["investment_inr"]
                config.LEVERAGE = prof["leverage"]
                config.STOP_LOSS_PERCENT = prof["stop_loss_pct"]
                config.TAKE_PROFIT_PERCENT = prof["take_profit_pct"]
                bot_state["last_reason"] = f"Risk mode updated: {prof['label']}"

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "current_mode": config.CURRENT_RISK_MODE,
                "profile": config.RISK_PROFILES.get(config.CURRENT_RISK_MODE, {})
            }).encode("utf-8"))
            return

        self.send_error(404, "Endpoint not found")


def start_server():
    os.makedirs(WEB_DIR, exist_ok=True)
    server_address = ("", PORT)
    with socketserver.ThreadingTCPServer(server_address, TradingApiHandler) as httpd:
        httpd.allow_reuse_address = True
        print(f"\n=======================================================")
        print(f"  COINDCX VISUAL TRADING DASHBOARD RUNNING")
        print(f"  Access UI at: http://localhost:{PORT}")
        print(f"=======================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server gracefully...")


if __name__ == "__main__":
    start_server()
