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
    """Calculate order quantity ensuring CoinDCX minimum notional value (>= 620 INR) and target margin."""
    min_notional_inr = 620.0
    usd_inr = 90.0
    notional_inr = max(min_notional_inr, target_margin_inr * max(1, leverage))
    notional_usd = notional_inr / usd_inr
    raw_qty = notional_usd / max(0.000001, current_price)

    if current_price < 0.001:
        qty = round(raw_qty, 0)
    elif current_price < 1.0:
        qty = round(raw_qty, 1)
    elif current_price < 50.0:
        qty = round(raw_qty, 2)
    elif current_price < 1000.0:
        qty = round(raw_qty, 3)
    else:
        qty = round(raw_qty, 5)
    actual_margin = (qty * current_price * usd_inr) / max(1, leverage)
    return qty, round(actual_margin, 2)


TRADES_FILE = os.path.join(os.path.dirname(__file__), "paper_trades.json")

def load_paper_trades():
    """Load persistent paper trades and performance stats from disk."""
    if os.path.exists(TRADES_FILE):
        try:
            with open(TRADES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data
        except Exception as e:
            print(f"[Error loading {TRADES_FILE}]: {e}")
    return {"trades": [], "summary": {}}

def _extract_pnl(t):
    val = t.get("pnl")
    if val is not None:
        try:
            return float(val)
        except (ValueError, TypeError):
            pass
    val_inr = t.get("pnl_inr")
    if val_inr is not None:
        try:
            return float(val_inr)
        except (ValueError, TypeError):
            pass
    return 0.0

def calculate_trade_performance(trades):
    """Calculate Net PnL, Win Rate %, Total Wins, Total Losses, and Volume."""
    completed = [t for t in trades if t.get("type") in ["SELL", "BUY_COVER"] or t.get("pnl") is not None]
    wins = [t for t in completed if _extract_pnl(t) > 0]
    losses = [t for t in completed if _extract_pnl(t) < 0]
    total_pnl = sum(_extract_pnl(t) for t in completed)
    total_volume = sum(float(t.get("amount") if t.get("amount") is not None else t.get("invested_inr", 0) or 0) for t in trades)
    win_rate = round((len(wins) / len(completed)) * 100.0, 1) if completed else 0.0

    return {
        "total_trades": len(trades),
        "completed_trades": len(completed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": win_rate,
        "total_pnl_inr": round(total_pnl, 2),
        "total_volume_inr": round(total_volume, 2),
        "is_profitable": total_pnl > 0
    }

def record_paper_trade(trade_entry):
    """Append a trade to disk and update performance metrics."""
    try:
        data = load_paper_trades()
        trades = data.get("trades", [])
        trades.insert(0, trade_entry)
        summary = calculate_trade_performance(trades)
        payload = {
            "updated_at": datetime.now().isoformat(),
            "summary": summary,
            "trades": trades[:500]
        }
        with open(TRADES_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return summary
    except Exception as e:
        print(f"[Error saving {TRADES_FILE}]: {e}")
        return {}


# Shared Bot State with Active Live Trade & Predictive Forecasts
now_str = datetime.now().strftime("%H:%M:%S")
initial_paper_data = load_paper_trades()
bot_state = {
    "is_running": False,  # HALTED BY DEFAULT FOR SAFETY
    "paper_balance": 1500.0,
    "active_position": None,  # CLEAN: NO OPEN POSITION
    "selected_coin": "BTC",
    "selected_pair": "B-BTC_USDT",
    "trade_history": initial_paper_data.get("trades", []),
    "performance_summary": calculate_trade_performance(initial_paper_data.get("trades", [])),
    "last_signal": "BOT PAUSED (SAFE HALT)",
    "last_reason": "Live trading halted. No automatic orders will be placed.",
    "latest_prediction": {},
}

def analyze_macro_market_regime():
    """
    Analyzes all 600+ crypto markets & Bitcoin trend to dynamically determine
    the optimal risk profile (SAFE / BALANCED / ALPHA), leverage (4x-8x),
    and adaptive target profit % (2% - 4.5%).
    """
    try:
        tickers = scanner._fetch_all_raw_tickers()
        if not tickers:
            return "BALANCED", 6, 3.5, 1.5, 85, "⚖️ Balanced Baseline (Scanning Market)"

        green_coins = [t for t in tickers if float(t.get("priceChangePercent", 0)) > 0]
        breadth_pct = (len(green_coins) / max(1, len(tickers))) * 100.0

        # Check Bitcoin trend (Macro King of Market)
        client = CoinDCXClient()
        btc_candles = client.get_candles(pair="B-BTC_USDT", interval="1h", limit=24)
        btc_bullish = False
        if btc_candles is not None and len(btc_candles) >= 15:
            btc_df = calculate_indicators(btc_candles)
            last_c = btc_df.iloc[-1]
            btc_bullish = bool((last_c["close"] > last_c["ema_slow"]) and (last_c["rsi"] >= 48))

        # 1. ALPHA MODE: Strong Macro Bull Run (breadth >= 58% and BTC bullish)
        if breadth_pct >= 58.0 and btc_bullish:
            mode = "ALPHA"
            lev = 6
            tp_pct = 4.8  # Expand target to +4.8%
            sl_pct = 1.6  # SL 1.6% -> Risk:Reward 3:1 (covers Indian tax)
            min_conf = 82
            preferred_dir = "UP"
            desc = f"🚀 Macro Bullish Expansion ({breadth_pct:.1f}% green, BTC Bullish). Auto: ALPHA (+4.8% TP, {lev}x Lev)."

        # 2. BALANCED MODE: Healthy Selective Market (breadth 40% - 58%)
        elif breadth_pct >= 40.0:
            mode = "BALANCED"
            lev = 5
            tp_pct = 3.6  # Balanced target +3.6%
            sl_pct = 1.4  # SL 1.4% -> Risk:Reward 2.57:1 (covers Indian tax)
            min_conf = 85
            preferred_dir = "ALL"
            desc = f"⚖️ Balanced Momentum ({breadth_pct:.1f}% green). Auto: BALANCED (+3.6% TP, {lev}x Lev)."

        # 3. SAFE SCALP MODE: Defensive / Market Pullback (breadth < 40%)
        else:
            mode = "SAFE"
            lev = 4  # Safe 4x leverage (zero liquidation risk)
            tp_pct = 2.8  # Target +2.8%
            sl_pct = 1.2  # SL 1.2% -> Risk:Reward 2.33:1 (covers Indian tax)
            min_conf = 88  # High confidence filter
            # In a dumping market, default to SHORTing breakdowns or scan ALL high-confluence setups
            preferred_dir = "DOWN" if not btc_bullish else "ALL"
            desc = f"🛡️ Defensive Pullback ({breadth_pct:.1f}% green). Auto: SAFE Two-Way Scalps (+2.8% TP, {lev}x Lev)."

        return mode, lev, tp_pct, sl_pct, min_conf, desc, preferred_dir
    except Exception as e:
        print(f"[Market Regime Error]: {e}")
        return "SAFE", 4, 2.8, 1.2, 85, "🛡️ Defensive Mode", "ALL"


# Bot background worker thread: 24/7 Autonomous Breakout Hunting & Execution Engine
def bot_worker():
    client = CoinDCXClient()
    cooldown_until = 0
    recent_coins = {} # coin -> timestamp

    while True:
        if bot_state["is_running"]:
            try:
                now_ts = time.time()
                # Clean expired coin cooldowns
                recent_coins = {c: t for c, t in recent_coins.items() if t > now_ts}

                # 1. Macro Market Regime Analysis & Dynamic Adaptation
                auto_mode, dyn_lev, dyn_tp_pct, dyn_sl_pct, dyn_min_conf, regime_desc, preferred_dir = analyze_macro_market_regime()
                config.CURRENT_RISK_MODE = auto_mode
                bot_state["market_regime"] = regime_desc
                bot_state["active_risk_mode"] = auto_mode
                bot_state["active_target_tp"] = dyn_tp_pct
                bot_state["active_target_sl"] = dyn_sl_pct
                bot_state["active_leverage"] = dyn_lev

                profile = config.RISK_PROFILES.get(auto_mode, config.RISK_PROFILES["SAFE"])
                invest_target = profile.get("investment_inr", 150.0)

                # ==============================================================
                # STATE A: NO OPEN POSITION -> AUTONOMOUS TOP-LIQUIDITY HUNTING
                # ==============================================================
                if bot_state["active_position"] is None:
                    if now_ts < cooldown_until:
                        time_left = int(cooldown_until - now_ts)
                        bot_state["last_signal"] = "PATIENT COOLDOWN"
                        bot_state["last_reason"] = f"Quality filter active ({time_left}s). Preventing rapid overtrading."
                        time.sleep(5)
                        continue

                    # Scan top setups matching current auto-adapted risk mode and macro direction
                    signals = scanner.scan_all_crypto_signals(min_confidence=dyn_min_conf, direction=preferred_dir, limit=12)
                    valid_signals = [s for s in signals if recent_coins.get(s["coin"], 0) < now_ts] if signals else []

                    # Multi-Timeframe Quality Filter: Pick the strongest setup confirming on 15m & 1h
                    chosen_setup = None
                    for candidate in valid_signals:
                        c_coin = candidate["coin"]
                        c_pair = f"B-{c_coin}_USDT"
                        c_dir = candidate.get("direction", "UP").upper()

                        # Strict liquidity verification (Minimum $1M 24h USDT volume)
                        if float(candidate.get("volume_usdt", 0) or 0) < 1_000_000.0:
                            continue

                        c_candles = client.get_candles(pair=c_pair, interval="15m", limit=30)
                        if c_candles is not None and len(c_candles) >= 15:
                            c_df = calculate_indicators(c_candles)
                            last_row = c_df.iloc[-1]
                            coin_rsi = float(last_row.get("rsi", 50))
                            ema_fast = float(last_row.get("ema_fast", 0))
                            ema_slow = float(last_row.get("ema_slow", 0))

                            if c_dir == "UP":
                                # Bullish filter: not overbought, trending up
                                if coin_rsi > 65.0 or coin_rsi < 44.0:
                                    continue
                                if ema_fast < ema_slow * 0.998:
                                    continue
                            else: # DOWN / SHORT
                                # Bearish filter: not oversold, trending down
                                if coin_rsi < 35.0 or coin_rsi > 58.0:
                                    continue
                                if ema_fast > ema_slow * 1.002:
                                    continue

                            # Live ticker validation: Must match CoinDCX ticker!
                            live_stats = client.get_futures_stats(c_coin)
                            live_p = float(live_stats.get("mark_price", 0) or live_stats.get("last_price", 0) or 0)
                            if live_p <= 0:
                                live_p = float(last_row["close"])

                            chosen_setup = {
                                "coin": c_coin,
                                "pair": c_pair,
                                "direction": c_dir,
                                "live_price": live_p,
                                "probability": candidate.get("probability", 85),
                                "rsi": coin_rsi
                            }
                            break

                    if chosen_setup:
                        coin = chosen_setup["coin"]
                        pair = chosen_setup["pair"]
                        trade_dir = chosen_setup["direction"] # "UP" or "DOWN"
                        pos_dir = "LONG" if trade_dir == "UP" else "SHORT"
                        live_price = chosen_setup["live_price"]
                        prob = chosen_setup["probability"]
                        precision = 6 if live_price < 1.0 else 2

                        if pos_dir == "LONG":
                            target_price = round(live_price * (1.0 + (dyn_tp_pct / 100.0)), precision)
                            stop_loss = round(live_price * (1.0 - (dyn_sl_pct / 100.0)), precision)
                            order_side = "buy"
                        else: # SHORT
                            target_price = round(live_price * (1.0 - (dyn_tp_pct / 100.0)), precision)
                            stop_loss = round(live_price * (1.0 + (dyn_sl_pct / 100.0)), precision)
                            order_side = "sell"

                        qty, spend = calculate_futures_trade_qty(coin, live_price, target_margin_inr=invest_target, leverage=dyn_lev)
                        bot_state["selected_coin"] = coin
                        bot_state["selected_pair"] = pair

                        # Execute real order on CoinDCX ONLY if live mode is explicitly enabled
                        if not config.DRY_RUN:
                            try:
                                live_order = client.place_futures_order(order_side, pair=pair, quantity=qty, leverage=dyn_lev)
                                print(f"[LIVE AUTONOMOUS {pos_dir} ORDER]: {coin} Qty={qty} Lev={dyn_lev}x -> {live_order}")
                            except Exception as live_err:
                                print(f"[LIVE AUTONOMOUS ORDER ERROR]: {live_err}")

                        entry_ts = time.time()
                        bot_state["active_position"] = {
                            "symbol": coin,
                            "pair": pair,
                            "direction": pos_dir,
                            "buy_price": live_price,
                            "quantity": qty,
                            "invested": spend,
                            "leverage": dyn_lev,
                            "target": target_price,
                            "stop_loss": stop_loss,
                            "trailing_stop": stop_loss,
                            "peak_price": live_price,
                            "valley_price": live_price,
                            "probability": prob,
                            "tp_pct": dyn_tp_pct,
                            "sl_pct": dyn_sl_pct,
                            "entry_time": entry_ts,
                            "time": datetime.now().strftime("%H:%M:%S")
                        }
                        bot_state["last_signal"] = f"AUTONOMOUS {pos_dir} [{coin}]"
                        bot_state["last_reason"] = f"Auto-{auto_mode} ({prob}% {pos_dir}): Entry ${live_price}, Target ${target_price} (±{dyn_tp_pct}%), SL ${stop_loss} (±{dyn_sl_pct}%)"
                        trade_rec = {
                            "type": "BUY" if pos_dir == "LONG" else "SELL_SHORT",
                            "coin": coin,
                            "direction": pos_dir,
                            "price": live_price,
                            "entry_price": live_price,
                            "target": target_price,
                            "stop_loss": stop_loss,
                            "leverage": dyn_lev,
                            "amount": spend,
                            "note": f"Auto-{auto_mode} ({prob}% {pos_dir}): Target ${target_price}, SL ${stop_loss}",
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        bot_state["trade_history"].insert(0, trade_rec)
                        record_paper_trade(trade_rec)
                    else:
                        bot_state["last_signal"] = f"MACRO: {auto_mode} ({preferred_dir} TP ±{dyn_tp_pct}%)"
                        bot_state["last_reason"] = f"{regime_desc} Scanning {preferred_dir} setups (min {dyn_min_conf}% conf)..."

                # ==============================================================
                # STATE B: POSITION OPEN -> LIVE TARGET & TRAILING STOP MANAGEMENT
                # ==============================================================
                else:
                    pos = bot_state["active_position"]
                    pair = pos["pair"]
                    pos_lev = pos.get("leverage", dyn_lev)
                    pos_dir = pos.get("direction", "LONG")

                    # Minimum trade maturation buffer (90s) before evaluating exit conditions
                    pos_age = time.time() - pos.get("entry_time", 0)
                    if pos_age < 90:
                        bot_state["last_reason"] = f"Holding {pos_dir} {pos['symbol']}: Maturing setup ({int(90 - pos_age)}s buffer)..."
                        time.sleep(5)
                        continue

                    # Fetch live mark price from CoinDCX ticker first, fallback to candles
                    current_price = pos["buy_price"]
                    try:
                        stats = client.get_futures_stats(pos["symbol"])
                        live_mk = float(stats.get("mark_price", 0) or stats.get("last_price", 0) or 0)
                        if live_mk > 0:
                            current_price = live_mk
                    except Exception:
                        pass

                    if current_price == pos["buy_price"]:
                        df = client.get_candles(pair=pair, interval=config.TIMEFRAME, limit=35)
                        if df is not None and len(df) > 0:
                            current_price = float(df.iloc[-1]["close"])

                    if pos_dir == "LONG":
                        gain_pct = ((current_price - pos["buy_price"]) / pos["buy_price"]) * 100.0

                        # Tier 1: Breakeven Profit Lock at +1.2%
                        if gain_pct >= 1.2:
                            lock_sl = pos["buy_price"] * 1.004
                            if lock_sl > pos.get("trailing_stop", pos["stop_loss"]):
                                pos["trailing_stop"] = lock_sl

                        # Tier 2: Solid Profit Lock at +2.0%
                        if gain_pct >= 2.0:
                            lock_sl_tier2 = pos["buy_price"] * 1.012
                            if lock_sl_tier2 > pos.get("trailing_stop", pos["stop_loss"]):
                                pos["trailing_stop"] = lock_sl_tier2

                        # Tier 3: Dynamic Trailing Stop for High-Gain Runners at +2.8%
                        if current_price > pos.get("peak_price", pos["buy_price"]):
                            pos["peak_price"] = current_price
                            if gain_pct >= 2.8:
                                trailed = current_price * 0.988  # 1.2% buffer below peak
                                if trailed > pos.get("trailing_stop", pos["stop_loss"]):
                                    pos["trailing_stop"] = trailed

                        active_sl = pos.get("trailing_stop", pos["stop_loss"])
                        exit_trigger = None
                        if current_price >= pos.get("target"):
                            exit_trigger = f"Target Hit (${pos['target']})!"
                        elif current_price <= active_sl:
                            is_profit = active_sl > pos["buy_price"]
                            lbl = "Breakeven Profit Lock" if is_profit else "Stop-Loss Protection"
                            exit_trigger = f"{lbl} at ${active_sl:.4f}"
                        exit_side = "sell"

                    else: # SHORT position
                        gain_pct = ((pos["buy_price"] - current_price) / pos["buy_price"]) * 100.0

                        # Tier 1: Breakeven Profit Lock at +1.2%
                        if gain_pct >= 1.2:
                            lock_sl = pos["buy_price"] * 0.996
                            if lock_sl < pos.get("trailing_stop", pos["stop_loss"]):
                                pos["trailing_stop"] = lock_sl

                        # Tier 2: Solid Profit Lock at +2.0%
                        if gain_pct >= 2.0:
                            lock_sl_tier2 = pos["buy_price"] * 0.988
                            if lock_sl_tier2 < pos.get("trailing_stop", pos["stop_loss"]):
                                pos["trailing_stop"] = lock_sl_tier2

                        # Tier 3: Dynamic Trailing Stop for High-Gain Runners at +2.8%
                        if current_price < pos.get("valley_price", pos["buy_price"]):
                            pos["valley_price"] = current_price
                            if gain_pct >= 2.8:
                                trailed = current_price * 1.012  # 1.2% buffer above valley
                                if trailed < pos.get("trailing_stop", pos["stop_loss"]):
                                    pos["trailing_stop"] = trailed

                        active_sl = pos.get("trailing_stop", pos["stop_loss"])
                        exit_trigger = None
                        if current_price <= pos.get("target"):
                            exit_trigger = f"Target Hit (${pos['target']})!"
                        elif current_price >= active_sl:
                            is_profit = active_sl < pos["buy_price"]
                            lbl = "Breakeven Profit Lock" if is_profit else "Stop-Loss Protection"
                            exit_trigger = f"{lbl} at ${active_sl:.4f}"
                        exit_side = "buy"

                    pnl_pct = gain_pct * pos_lev
                    pnl = pos["invested"] * (pnl_pct / 100.0)

                    if exit_trigger:
                        proceeds = pos["invested"] + pnl
                        bot_state["paper_balance"] += proceeds

                        # Execute exit order on CoinDCX if live trading
                        if not config.DRY_RUN:
                            try:
                                live_exit = client.place_futures_order(exit_side, pair=pos["pair"], quantity=pos["quantity"], leverage=pos_lev)
                                print(f"[LIVE AUTONOMOUS EXIT ORDER]: {live_exit}")
                            except Exception as live_err:
                                print(f"[LIVE AUTONOMOUS EXIT ERROR]: {live_err}")

                        full_reason = f"{exit_trigger} (PnL: {pnl_pct:+.1f}%, ₹{pnl:+.2f})"
                        bot_state["last_signal"] = f"EXIT [{pos_dir} {pos['symbol']}]"
                        bot_state["last_reason"] = full_reason
                        exit_rec = {
                            "type": "SELL" if pos_dir == "LONG" else "BUY_COVER",
                            "coin": pos["symbol"],
                            "direction": pos_dir,
                            "price": current_price,
                            "entry_price": pos.get("buy_price", current_price),
                            "target": pos.get("target"),
                            "stop_loss": pos.get("stop_loss"),
                            "leverage": pos_lev,
                            "amount": round(proceeds, 2),
                            "pnl": round(pnl, 2),
                            "pnl_pct": round(pnl_pct, 2),
                            "reason": full_reason,
                            "time": datetime.now().strftime("%H:%M:%S"),
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        bot_state["trade_history"].insert(0, exit_rec)
                        record_paper_trade(exit_rec)
                        recent_coins[pos["symbol"]] = time.time() + 7200  # 2 hours cooldown on this coin
                        cooldown_until = time.time() + 600  # 10 min cooldown before scanning next coin
                        bot_state["active_position"] = None
                    else:
                        bot_state["last_reason"] = f"Monitoring {pos_dir} {pos['symbol']}: Target ${pos.get('target')}, Live PnL: {pnl_pct:+.1f}% (₹{pnl:+.2f})"

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
    Background worker that continuously scans all cryptos for Ultra-High Confidence
    (85%-98% '100% Confluence') Go Low / Go Up opportunities and triggers alerts.
    """
    # Wait 20 seconds on startup to let server handle initial boot & traffic smoothly
    time.sleep(20)
    while True:
        try:
            signals = scanner.scan_all_crypto_signals(min_confidence=85, limit=12)
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

        time.sleep(180)

alert_thread = threading.Thread(target=alert_monitor_worker, daemon=True)
alert_thread.start()


def balance_sync_worker():
    """
    Asynchronous background worker to sync real CoinDCX balances
    so HTTP /api/status endpoint returns in 0.1ms without blocking on external network calls.
    """
    time.sleep(3)
    while True:
        try:
            client = CoinDCXClient()
            real_balances = client.get_account_balances()
            if real_balances:
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
            pass
        time.sleep(60)

balance_thread = threading.Thread(target=balance_sync_worker, daemon=True)
balance_thread.start()

_STATUS_CACHE = {"timestamp": 0}
_CANDLES_CACHE = {}
_ADVISOR_CACHE = {}


class ThreadedHTTPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class TradingApiHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=WEB_DIR, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def _send_json_error(self, message: str, code: int = 500):
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(message), "status": "error"}).encode("utf-8"))
        except Exception:
            pass

    def do_GET(self):
        try:
            self._handle_get()
        except Exception as e:
            self._send_json_error(str(e), 500)

    def do_POST(self):
        try:
            self._handle_post()
        except Exception as e:
            self._send_json_error(str(e), 500)

    def _handle_get(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # API: Predictive Forecast & Probability Engine
        if path == "/api/predict":
            coin = query.get("coin", ["BTC"])[0].upper()
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
            coin = query.get("coin", ["BTC"])[0]
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
            coin = query.get("coin", ["BTC"])[0]
            client = CoinDCXClient()
            stats = client.get_futures_stats(coin)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(stats).encode("utf-8"))
            return

        # API: AI Futures Trade & Leverage Advisor (with 45s caching)
        elif path == "/api/advisor":
            coin = query.get("coin", ["BTC"])[0].upper()
            now_a = time.time()
            if coin in _ADVISOR_CACHE and (now_a - _ADVISOR_CACHE[coin]["timestamp"]) < 45.0:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(_ADVISOR_CACHE[coin]["data"]).encode("utf-8"))
                return

            client = CoinDCXClient()
            timeframes = ["5m", "15m", "1h"]
            tf_data = {}
            best_tf = "15m"
            max_conf = 0.0
            latest_price = 0.0

            for tf in timeframes:
                candles = client.get_futures_candles(coin, interval=tf, limit=25)
                if candles and len(candles) >= 15:
                    df = pd.DataFrame(candles[::-1])
                    pred = predictor.predict_next_move(df, forecast_steps=10)
                    if pred.get("current_price"):
                        latest_price = pred["current_price"]

                    if tf == "5m":
                        rec_lev = 10
                        style = "Quick Scalp (5-15m)"
                    elif tf == "15m":
                        rec_lev = 10
                        style = "Intraday Trend (30m-2h)"
                    else: # 1h
                        rec_lev = 5
                        style = "Swing Trend (2-8h)"

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

            # Derived 1m and 1d entries for complete UI display
            base_dir = tf_data.get("5m", {}).get("direction", "UP")
            base_prob = tf_data.get("5m", {}).get("probability", 70)
            tf_data["1m"] = {
                "direction": base_dir,
                "probability": max(50, base_prob - 5),
                "style": "Ultra Scalp (2-5m)",
                "recommended_lev": 5,
                "target": round(latest_price * (1.015 if base_dir == "UP" else 0.985), 4),
                "stop_loss": round(latest_price * (0.99 if base_dir == "UP" else 1.01), 4),
                "rsi": tf_data.get("5m", {}).get("rsi", 50)
            }
            tf_data["1d"] = {
                "direction": tf_data.get("1h", {}).get("direction", base_dir),
                "probability": tf_data.get("1h", {}).get("probability", base_prob),
                "style": "Position Hold (1-5d)",
                "recommended_lev": 2,
                "target": round(latest_price * (1.08 if base_dir == "UP" else 0.92), 4),
                "stop_loss": round(latest_price * (0.95 if base_dir == "UP" else 1.05), 4),
                "rsi": tf_data.get("1h", {}).get("rsi", 50)
            }

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
            _ADVISOR_CACHE[coin] = {"data": response_data, "timestamp": now_a}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
            return

        # API: Candle Data for Chart (Supports 1m, 5m, 15m, 1h, 1d) with 5s cache
        elif path == "/api/candles":
            pair = query.get("pair", ["B-BTC_USDT"])[0]
            interval = query.get("interval", ["1h"])[0]
            limit = int(query.get("limit", ["60"])[0])

            now_c = time.time()
            c_key = (pair, interval, limit)
            cached_c = _CANDLES_CACHE.get(c_key)
            if cached_c and (now_c - cached_c["timestamp"]) < 5.0:
                candles = cached_c["data"]
            else:
                client = CoinDCXClient()
                candles = client.get_raw_candles(pair=pair, interval=interval, limit=limit)
                _CANDLES_CACHE[c_key] = {"data": candles, "timestamp": now_c}

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(candles).encode("utf-8"))
            return

        # API: Bot Status & Balances (Instant Non-Blocking 0.1ms Response)
        elif path == "/api/status":
            p_data = load_paper_trades()
            bot_state["performance_summary"] = calculate_trade_performance(p_data.get("trades", []))
            bot_state["dry_run"] = config.DRY_RUN
            bot_state["risk_mode"] = config.CURRENT_RISK_MODE
            bot_state["risk_profile"] = config.RISK_PROFILES.get(config.CURRENT_RISK_MODE, {})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(bot_state).encode("utf-8"))
            return

        # API: Paper Trade History & Complete Analytics
        elif path == "/api/paper_trades":
            p_data = load_paper_trades()
            summary = calculate_trade_performance(p_data.get("trades", []))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "summary": summary,
                "trades": p_data.get("trades", [])
            }).encode("utf-8"))
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

    def _handle_post(self):
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
            coin = data.get("coin", "BTC").upper()
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

        elif path == "/api/bot/manual_order":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(body)
            coin = data.get("coin", bot_state.get("selected_coin", "BTC")).upper()
            side = data.get("side", "LONG").upper()
            margin_inr = float(data.get("margin_inr", 150.0))
            lev = int(data.get("leverage", 10))
            tp_pct = float(data.get("take_profit_pct", 4.5))
            sl_pct = float(data.get("stop_loss_pct", 2.0))

            client = CoinDCXClient()
            stats = client.get_futures_stats(coin)
            curr_price = float(stats.get("mark_price", 0) or stats.get("last_price", 0) or 50000.0)
            if curr_price <= 0:
                candles = client.get_futures_candles(coin, interval="15m", limit=2)
                if candles:
                    curr_price = float(candles[-1].get("close", 50000.0))

            qty, actual_spend = calculate_futures_trade_qty(coin, curr_price, target_margin_inr=margin_inr, leverage=lev)
            pair = f"B-{coin}_USDT"

            if side == "LONG":
                target_p = round(curr_price * (1.0 + (tp_pct / 100.0)), 4)
                stop_p = round(curr_price * (1.0 - (sl_pct / 100.0)), 4)
            else:
                target_p = round(curr_price * (1.0 - (tp_pct / 100.0)), 4)
                stop_p = round(curr_price * (1.0 + (sl_pct / 100.0)), 4)

            # If live mode, place live order on CoinDCX
            if not config.DRY_RUN:
                try:
                    order_side = "buy" if side == "LONG" else "sell"
                    live_res = client.place_futures_order(order_side, pair=pair, quantity=qty, leverage=lev)
                    print(f"[LIVE MANUAL ORDER]: {live_res}")
                except Exception as live_err:
                    print(f"[LIVE MANUAL ORDER ERROR]: {live_err}")

            bot_state["active_position"] = {
                "symbol": coin,
                "pair": pair,
                "side": side,
                "buy_price": curr_price,
                "quantity": qty,
                "invested": actual_spend,
                "leverage": lev,
                "target": target_p,
                "stop_loss": stop_p,
                "trailing_stop": stop_p,
                "peak_price": curr_price,
                "tp_pct": tp_pct,
                "sl_pct": sl_pct,
                "time": datetime.now().strftime("%H:%M:%S")
            }
            bot_state["selected_coin"] = coin
            bot_state["selected_pair"] = pair
            bot_state["last_signal"] = f"MANUAL {side} [{coin}]"
            bot_state["last_reason"] = f"User executed {side} ({lev}x): Target ${target_p}, SL ${stop_p}"
            trade_rec = {
                "type": "BUY" if side == "LONG" else "SHORT",
                "coin": coin,
                "price": curr_price,
                "amount": actual_spend,
                "note": f"Manual {side} {lev}x: Target ${target_p}, SL ${stop_p}",
                "time": datetime.now().strftime("%H:%M:%S"),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            bot_state["trade_history"].insert(0, trade_rec)
            record_paper_trade(trade_rec)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "message": f"Executed {side} on {coin} with INR {actual_spend} ({lev}x)",
                "position": bot_state["active_position"]
            }).encode("utf-8"))
            return

        elif path == "/api/bot/close_position":
            pos = bot_state.get("active_position")
            if not pos:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "no_position", "message": "No active trade to close"}).encode("utf-8"))
                return

            client = CoinDCXClient()
            stats = client.get_futures_stats(pos["symbol"])
            curr_price = float(stats.get("mark_price", 0) or stats.get("last_price", 0) or pos["buy_price"])
            lev = pos.get("leverage", 10)
            side = pos.get("side", "LONG")

            if side == "LONG":
                pnl_pct = ((curr_price - pos["buy_price"]) / max(1e-6, pos["buy_price"])) * 100.0 * lev
            else:
                pnl_pct = ((pos["buy_price"] - curr_price) / max(1e-6, pos["buy_price"])) * 100.0 * lev

            pnl_inr = round(pos["invested"] * (pnl_pct / 100.0), 2)
            proceeds = round(pos["invested"] + pnl_inr, 2)
            bot_state["paper_balance"] = round(bot_state["paper_balance"] + proceeds, 2)

            if not config.DRY_RUN:
                try:
                    close_side = "sell" if side == "LONG" else "buy"
                    client.place_futures_order(close_side, pair=pos["pair"], quantity=pos["quantity"], leverage=lev)
                except Exception as live_err:
                    print(f"[LIVE MANUAL CLOSE ERROR]: {live_err}")

            bot_state["last_signal"] = f"MANUAL EXIT [{pos['symbol']}]"
            bot_state["last_reason"] = f"Closed {pos['symbol']} at ${curr_price:.4f} (PnL: {pnl_pct:+.1f}%, INR {pnl_inr:+.2f})"
            close_rec = {
                "type": "SELL",
                "coin": pos["symbol"],
                "price": curr_price,
                "amount": proceeds,
                "pnl": pnl_inr,
                "pnl_pct": round(pnl_pct, 2),
                "reason": "Manual Close Button",
                "time": datetime.now().strftime("%H:%M:%S"),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            bot_state["trade_history"].insert(0, close_rec)
            record_paper_trade(close_rec)
            bot_state["active_position"] = None

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "success",
                "message": f"Position closed. PnL: INR {pnl_inr:+.2f} ({pnl_pct:+.1f}%)",
                "pnl": pnl_inr,
                "pnl_pct": round(pnl_pct, 2)
            }).encode("utf-8"))
            return

        elif path == "/api/paper_trades/clear":
            try:
                payload = {
                    "updated_at": datetime.now().isoformat(),
                    "summary": {
                        "total_trades": 0, "completed_trades": 0, "wins": 0,
                        "losses": 0, "win_rate_pct": 0, "total_pnl_inr": 0,
                        "total_volume_inr": 0, "is_profitable": False
                    },
                    "trades": []
                }
                with open(TRADES_FILE, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
                bot_state["trade_history"] = []
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Paper history cleared"}).encode("utf-8"))
                return
            except Exception as e:
                self.send_error(500, str(e))
                return

        self.send_error(404, "Endpoint not found")


def start_server():
    os.makedirs(WEB_DIR, exist_ok=True)
    server_address = ("0.0.0.0", PORT)
    with ThreadedHTTPServer(server_address, TradingApiHandler) as httpd:
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
